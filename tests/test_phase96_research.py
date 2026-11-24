"""Offline freshness and trusted server binding checks."""

from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.inference.common import InferenceError, sha256
from scripts.multisource.forecast_eligibility import FIXTURE_MAX_AGE, utc, utc_text
from scripts.multisource.forecast_service import ForecastService
from scripts.multisource.refresh_validation import CURRENT
from scripts.multisource.revision_review import POLICY_VERSION
from scripts.xpecta_api.research_binding import verify_real_snapshot
from scripts.xpecta_api.research_preflight import source_readiness
from scripts.xpecta_api.schedule_status import schedule_status
from scripts.xpecta_api.settings import Mode, REAL_VERSION, Settings
from scripts.xpecta_api import share_snapshot


class ResearchReadinessTests(unittest.TestCase):
    def test_shared_selection_default_and_explicit_override(self):
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "shared_snapshot.json"
            with (patch("scripts.xpecta_api.settings.SHARED_SNAPSHOT", config),
                  patch.dict(os.environ, {}, clear=True)):
                self.assertEqual(Settings.from_env().snapshot_version, REAL_VERSION)
                config.write_text(json.dumps(dict(snapshot_version="reviewed-v4", snapshot_sha256="a" * 64,
                                                  snapshot_manifest_sha256="b" * 64)), encoding="utf-8")
                self.assertEqual(Settings.from_env().snapshot_version, "reviewed-v4")
                self.assertEqual(Settings.from_env().snapshot_manifest_sha256, "b" * 64)
                with patch.dict(os.environ, {"XPECTA_SNAPSHOT": REAL_VERSION}):
                    self.assertEqual(Settings.from_env().snapshot_version, REAL_VERSION)
                with patch.dict(os.environ, {"XPECTA_MODE": Mode.SYNTHETIC_DEMO.value}):
                    self.assertEqual(Settings.from_env().snapshot_version, "updated")
                config.write_text('{"snapshot_version": "reviewed-v4"}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid shared snapshot configuration"):
                    Settings.from_env()

    def test_share_stages_exact_snapshot_bytes_and_leaves_other_files_ignored(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            research_root = repo / "data/history/research"
            config = research_root.parent / "shared_snapshot.json"
            attributes = (share_snapshot.ROOT / ".gitattributes").read_bytes()

            def make_snapshot(version, parent):
                directory = research_root / version
                directory.mkdir(parents=True)
                database = directory / "laliga_composite.sqlite3"
                database.write_bytes(b"\x00sqlite\n")
                (directory / "manifest.json").write_bytes(b"{}\r\n")
                (directory / "private.txt").write_text("private", encoding="utf-8")
                return SimpleNamespace(path=database, manifest=dict(version_id=version, parent_version=parent))

            baseline = make_snapshot(REAL_VERSION, None)
            child = make_snapshot("reviewed-v4", REAL_VERSION)
            (repo / ".gitattributes").write_bytes(attributes)
            (research_root.parent / ".gitignore").write_text("/research/*\n", encoding="utf-8")
            engine = SimpleNamespace(root=research_root, open={REAL_VERSION: baseline, "reviewed-v4": child}.get)
            with (patch.object(share_snapshot, "ROOT", repo),
                  patch.object(share_snapshot, "SHARED_SNAPSHOT", config),
                  patch.object(share_snapshot, "ForecastEligibility", return_value=engine),
                  patch.object(share_snapshot, "verify_real_snapshot") as verify):
                share_snapshot.git("init", "--quiet")
                share_snapshot.git("config", "core.autocrlf", "true")
                with self.assertRaisesRegex(InferenceError, "Share parent"):
                    share_snapshot.stage_release("reviewed-v4")
                self.assertFalse(config.exists())
                parent_paths = [file.relative_to(repo).as_posix() for file in share_snapshot.snapshot_files(baseline)]
                share_snapshot.git("add", "--force", "--", *parent_paths)
                index_lock = repo / ".git/index.lock"
                index_lock.touch()
                try:
                    with self.assertRaises(subprocess.CalledProcessError):
                        share_snapshot.stage_release("reviewed-v4")
                    self.assertFalse(config.exists())
                finally:
                    index_lock.unlink()
                selection = share_snapshot.stage_release("reviewed-v4")
                verify.assert_called_with(engine, child, Settings(**selection))
                paths = [file.relative_to(repo).as_posix() for file in share_snapshot.snapshot_files(child)]
                self.assertCountEqual(share_snapshot.git("ls-files").splitlines(),
                                      [*parent_paths, *paths, config.relative_to(repo).as_posix()])
                for path in paths:
                    self.assertEqual(share_snapshot.git("rev-parse", f":{path}"),
                                     share_snapshot.git("hash-object", "--no-filters", path))
                self.assertEqual(json.loads(config.read_text(encoding="utf-8")), selection)

    def test_schedule_distinguishes_expiry_and_missing_evidence(self):
        acquired = utc("2026-11-21T20:20:23Z")
        engine = SimpleNamespace(_schedule_evidence=lambda store, fixture, catalogue: acquired)
        store = SimpleNamespace(query=lambda sql: [dict(season=2026, payload='{"season":2026}')])
        complete = dict(season=2026, kickoff_utc="2026-11-23T20:25:00Z")
        rows = [complete, dict(complete, kickoff_utc=None)]
        deadline = acquired + FIXTURE_MAX_AGE
        verified = schedule_status(engine, store, rows, deadline)
        self.assertEqual(verified["recent_review_upcoming_fixtures"], 1)
        self.assertEqual(verified["missing_review_upcoming_fixtures"], 1)
        self.assertEqual(verified["schedule_evidence"][0]["expires_at_utc"], utc_text(deadline))
        stale = schedule_status(engine, store, rows, deadline + timedelta(microseconds=1))
        self.assertEqual(stale["recent_review_upcoming_fixtures"], 0)
        self.assertEqual(stale["expired_review_upcoming_fixtures"], 1)

    def test_new_download_time_with_same_bytes_does_not_prepare(self):
        now = utc("2026-11-23T06:00:00Z")
        evidence = [dict(acquired_at_utc="2026-11-21T20:20:23Z")]
        header = dict(input_hashes={"raw/" + CURRENT: "old-sha"})
        entry = dict(retrieved_at="2026-11-23T05:00:00Z", sha256="old-sha", url="public-source")
        with patch("scripts.xpecta_api.research_preflight.manifest", return_value=({CURRENT: entry}, {})):
            self.assertEqual(source_readiness(Path("unused"), header, evidence, now)["status"], "SAME_SOURCE_BYTES")
            entry["sha256"] = "new-sha"
            self.assertEqual(source_readiness(Path("unused"), header, evidence, now)["status"], "NEWER_BYTES_REVIEW_REQUIRED")
            entry["retrieved_at"] = "2026-11-21T20:20:23Z"
            self.assertEqual(source_readiness(Path("unused"), header, evidence, now)["status"], "SOURCE_ACQUISITION_NOT_CURRENT")

    def test_successor_requires_explicit_pins_and_rejects_other_namespaces(self):
        both = dict(snapshot_sha256="a" * 64, snapshot_manifest_sha256="b" * 64)
        self.assertEqual(Settings(snapshot_version="reviewed-v4", **both).snapshot_version, "reviewed-v4")
        for options in (dict(snapshot_version="reviewed-v4"), dict(snapshot_version="../reviewed", **both),
                        dict(mode=Mode.SYNTHETIC_DEMO, snapshot_version="initial", **both)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                Settings(**options)

    def test_successor_binding_checks_receipts_parent_digest_and_both_pins(self):
        with TemporaryDirectory() as tmp:
            def snapshot(name, parent=None):
                path = Path(tmp) / name / "laliga_composite.sqlite3"
                path.parent.mkdir()
                path.write_text(name, encoding="utf-8")
                path.with_name("manifest.json").write_text(name + "-manifest", encoding="utf-8")
                return SimpleNamespace(path=path, manifest=dict(version_id=name, parent_version=parent))

            v3 = snapshot(REAL_VERSION)
            successor = snapshot("reviewed-v4", REAL_VERSION)
            successor.manifest.update(
                research_validation_status="validated_registry_rolling_features_and_frozen_inference_parity",
                inference_validation=dict(production_approved=False, targets=1, success=1, expected_blocked=0,
                                          max_raw_parity_delta=0, max_clipped_parity_delta=0))
            change = dict(change_id="schedule", decision="MANUAL_REVIEW")
            receipt = dict(change, review_decision="APPROVE", candidate_content_sha256="bound",
                           candidate_version="reviewed-v4", parent_version=REAL_VERSION, review_reason="Verified",
                           evidence_reference="record")
            refresh = dict(dataset_kind="real", policy_version=POLICY_VERSION, parent_sha256=sha256(v3.path),
                           candidate_content_sha256="bound", changes=[change], reviews={"schedule": receipt})
            engine = SimpleNamespace(open={REAL_VERSION: v3}.get)
            pins = dict(snapshot_sha256=sha256(successor.path),
                        snapshot_manifest_sha256=sha256(successor.path.with_name("manifest.json")))
            settings = Settings(snapshot_version="reviewed-v4", **pins)
            with (patch("scripts.xpecta_api.research_binding.refresh_metadata", return_value=refresh),
                  patch("scripts.xpecta_api.research_binding.REAL_SHA256", sha256(v3.path)),
                  patch("scripts.xpecta_api.research_binding.REAL_MANIFEST_SHA256", sha256(v3.path.with_name("manifest.json")))):
                self.assertEqual(verify_real_snapshot(engine, successor, settings), tuple(pins.values()))
                wrong = Settings(snapshot_version="reviewed-v4", **dict(pins, snapshot_manifest_sha256="0" * 64))
                with self.assertRaisesRegex(InferenceError, "server pins"):
                    verify_real_snapshot(engine, successor, wrong)
                receipt["review_decision"] = "REJECT"
                with self.assertRaisesRegex(InferenceError, "review receipts"):
                    verify_real_snapshot(engine, successor, settings)
                receipt["review_decision"] = "APPROVE"
                refresh["parent_sha256"] = "0" * 64
                with self.assertRaisesRegex(InferenceError, "parent hash"):
                    verify_real_snapshot(engine, successor, settings)

    def test_real_changed_inputs_require_a_successor_before_append(self):
        service = object.__new__(ForecastService)
        service.eligibility = SimpleNamespace(dataset_kind="real")
        service.ledger = Mock()
        service._check_successor = Mock()
        earlier = dict(forecast_id="earlier", history_snapshot_version=REAL_VERSION, canonical_fixture_key="fixture",
                       target_match_date="2026-11-23", target_kickoff_utc="2026-11-23T20:00:00Z",
                       target_semantics={}, model_artifact_sha256="frozen", features=[1, 2])
        service.ledger.list_fixture_forecasts.return_value = [earlier]
        candidate = dict(earlier, features=[1, 3])
        with patch("scripts.multisource.forecast_service.generate_forecast",
                   return_value=dict(status="GENERATED", forecast=candidate)):
            with self.assertRaisesRegex(InferenceError, "verified successor"):
                service.generate_forecast("fixture", REAL_VERSION)
        service.ledger.append.assert_not_called()
