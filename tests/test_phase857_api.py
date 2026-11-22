"""Local HTTP contracts over the real frozen model and isolated synthetic snapshots."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from scripts.inference.common import InferenceError, sha256
from scripts.multisource.forecast_examples import TARGET
from scripts.multisource.forecast_generation import generate_forecast
from scripts.multisource.forecast_ledger import ForecastLedger
from scripts.xpecta_api.app import create_app
from scripts.xpecta_api.demo import initialize_demo
from scripts.xpecta_api.schemas import ForecastRequest
from scripts.xpecta_api.settings import MODEL_SHA256, Mode, REAL_VERSION, Settings
from scripts.xpecta_api.prepare_frontend import build

BASE = "/api/v1"
OPERATOR = "deterministic-synthetic-operator-for-tests"
AUTH = {"Authorization": f"Bearer {OPERATOR}"}


class Phase857SchemaTests(unittest.TestCase):
    def test_rejects_unknown_fields_types_and_paths(self):
        for invalid in (
            {"fixture_key": "/tmp/other.sqlite3"},
            {"fixture_key": 42},
            {"fixture_key": TARGET, "snapshot_version": "updated"},
            {"fixture_key": TARGET, "mode": "REAL_RESEARCH"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                ForecastRequest.model_validate(invalid)
        self.assertEqual(ForecastRequest(fixture_key=TARGET).fixture_key, TARGET)

    def test_mode_snapshot_allowlist_and_write_policy(self):
        for args in (
            {"mode": Mode.REAL_RESEARCH, "snapshot_version": "updated"},
            {"mode": Mode.SYNTHETIC_DEMO, "snapshot_version": REAL_VERSION},
            {"mode": Mode.SYNTHETIC_DEMO, "snapshot_version": "../real"},
            {"mode": Mode.HISTORICAL_REFERENCE, "operator_token": OPERATOR},
            {"origins": ("*",)},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Settings(**args)

    def test_frontend_refuses_unknown_input_bytes(self):
        with TemporaryDirectory() as work:
            path = Path(work) / "reference.html"
            path.write_text("<script>unexpected()</script>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                build(path, Path(work) / "output")
            self.assertFalse((Path(work) / "output").exists())


class Phase857HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = TemporaryDirectory(prefix="phase857-api-")
        cls.addClassCleanup(temporary.cleanup)
        cls.private = Path(temporary.name).resolve()
        settings_path = patch("scripts.xpecta_api.settings.PRIVATE", cls.private)
        settings_path.start()
        cls.addClassCleanup(settings_path.stop)
        cls.demo = cls.private / "demos" / "test-run"
        initialize_demo(cls.demo)

    def client(self, profile="initial", *, token="", origins=()):
        return TestClient(create_app(Settings(Mode.SYNTHETIC_DEMO, profile, "test-run", token, origins)),
                          base_url="http://localhost", raise_server_exceptions=False)

    def isolated_ledger(self, label):
        # Each mutating test owns a separate ledger while sharing read-only synthetic snapshots.
        ledger = ForecastLedger(synthetic_base=self.private / label)
        mocker = patch("scripts.multisource.forecast_service.ForecastLedger", return_value=ledger)
        mocker.start()
        self.addCleanup(mocker.stop)
        return ledger

    def test_routes_and_local_readiness(self):
        with self.client() as client:
            self.assertEqual(client.get(BASE + "/health/live").json()["status"], "ALIVE")
            ready = client.get(BASE + "/health/ready")
            self.assertEqual(ready.status_code, 200)
            self.assertEqual(ready.json()["model_version"], "1.0.0")
            self.assertFalse(ready.json()["production_approved"])
            data = client.get(BASE + "/bootstrap").json()
            self.assertEqual(data["snapshot_version"], "initial")
            self.assertEqual(data["label"], "SYNTHETIC DEMO")
            protected = client.get("/data/history/laliga_history.sqlite3")
            self.assertEqual(protected.status_code, 404)
            self.assertEqual(client.get("/assets/reference.html").status_code, 404)
            self.assertIn("default-src 'none'", ready.headers["content-security-policy"])
            self.assertEqual(len(client.get("/openapi.json").json()["paths"]), 15)

    def test_team_fixture_identity_pagination_and_query_limits(self):
        with self.client() as client:
            first = client.get(BASE + "/teams?season=2026&limit=2").json()
            second = client.get(BASE + "/teams?season=2026&limit=2&offset=2").json()
            self.assertEqual(first["total"], second["total"])
            self.assertEqual(second["offset"], 2)
            self.assertTrue({team["id"] for team in first["items"]}.isdisjoint(team["id"] for team in second["items"]))
            exact = client.get(BASE + "/fixtures", params={
                "season": 2026, "home": "Valencia", "away": "Real Madrid", "upcoming": "true"
            }).json()
            self.assertEqual(exact["total"], 1)
            self.assertEqual(exact["items"][0]["canonical_fixture_key"], TARGET)
            self.assertNotIn("fixture_id", exact["items"][0])
            for query in ("limit=101", "offset=-1", "season=word", "mode=SYNTHETIC_DEMO", "unexpected=1"):
                response = client.get(BASE + "/fixtures?" + query)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_preview_parity_and_no_ledger_mutation(self):
        with self.client() as client:
            service = client.app.state.service
            original = generate_forecast(TARGET, "initial", eligibility=service.forecast.eligibility)["forecast"]
            snapshot_before = sha256(service.store.path)
            response = client.post(BASE + "/forecasts/preview", json={"fixture_key": TARGET})
            result = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(result["status"], "EARLY_READY")
            for field in ("home_xg", "away_xg", "history_cutoff", "history_database_sha256", "model_artifact_sha256"):
                self.assertEqual(result["preview"][field], original[field])
            self.assertEqual(result["preview"]["model_artifact_sha256"], MODEL_SHA256)
            self.assertTrue({"features", "raw_predictions", "history_provenance"}.isdisjoint(result["preview"]))
            self.assertFalse(service.forecast.ledger.directory.exists())
            self.assertEqual(sha256(service.store.path), snapshot_before)

    def test_a_b_c_d_e_http_and_immutable_revision_chain(self):
        ledger = self.isolated_ledger("abcdef")
        body = {"fixture_key": TARGET}
        with self.client("initial", token=OPERATOR) as client:
            result = client.post(BASE + "/forecasts/publish", headers=AUTH, json=body)
            self.assertEqual(result.status_code, 200)
            a = result.json()
            self.assertEqual((a["status"], a["forecast"]["forecast_stage"]), ("PUBLISHED", "INITIAL"))
            key = "research:laliga:2026:Valencia:Eibar"
            unavailable = client.post(BASE + "/forecasts/preview", json={"fixture_key": key}).json()
            self.assertEqual(unavailable["status"], "UNAVAILABLE")
            self.assertIsNone(unavailable["preview"])
        first_file = ledger.directory / (a["forecast"]["forecast_id"] + ".json")
        before = first_file.read_bytes()
        with self.client("updated", token=OPERATOR) as client:
            b = client.post(BASE + "/forecasts/publish", headers=AUTH, json=body).json()
            self.assertEqual((b["status"], b["forecast"]["forecast_stage"]), ("PUBLISHED", "UPDATED"))
            self.assertEqual(b["forecast"]["previous_forecast_id"], a["forecast"]["forecast_id"])
            history = client.get(BASE + "/forecasts", params=body).json()
            self.assertEqual([row["forecast_revision"] for row in history["items"]], [2, 1])
            v1, v2 = [r["forecast"]["forecast_id"] for r in (a, b)]
            detail = client.get(BASE + "/forecasts/" + v2).json()
            self.assertEqual(detail["forecast_id"], v2)
            params = dict(body, v1=v1, v2=v2)
            comparison = client.get(BASE + "/forecasts/compare", params=params).json()
            self.assertEqual(comparison["v1"]["forecast_id"], v1)
            self.assertEqual(comparison["v2"]["forecast_id"], v2)
            self.assertTrue(comparison["changed_features"])
            invalid = client.get(BASE + "/forecasts/compare", params=dict(params, v1=v2, v2=v1))
            self.assertEqual(invalid.status_code, 422)
        with self.client("same-features", token=OPERATOR) as client:
            c = client.post(BASE + "/forecasts/publish", headers=AUTH, json=body).json()
            self.assertEqual(c["status"], "NO_CHANGE")
            self.assertEqual(c["forecast"]["forecast_id"], v2)
            self.assertEqual(c["evaluated_snapshot_version"], "same-features")
        with self.client("incomplete", token=OPERATOR) as client:
            d = client.post(BASE + "/forecasts/publish", headers=AUTH, json=body).json()
            self.assertEqual(d["status"], "WAITING_DATA")
            self.assertEqual(d["eligibility"]["reason"], "MISSING_ROLLING_STATISTICS")
            self.assertIsNone(d["forecast"])
        self.assertEqual(before, first_file.read_bytes())
        self.assertEqual(len(list(ledger.directory.glob("*.json"))), 2)

    def test_stale_schedule_keeps_null_predictions(self):
        with self.client() as client:
            engine = client.app.state.service.forecast.eligibility
            with patch.object(engine, "_clock", return_value="2026-11-22T10:00:00Z"):
                result = client.get(BASE + "/eligibility", params={"fixture_key": TARGET}).json()
                preview = client.post(BASE + "/forecasts/preview", json={"fixture_key": TARGET}).json()
                freshness = client.get(BASE + "/data-status").json()
            self.assertEqual(result["reason"], "FIXTURE_FRESHNESS_UNVERIFIED")
            self.assertEqual(preview["status"], "WAITING_DATA")
            self.assertIsNone(preview["preview"])
            self.assertEqual(freshness["schedule_freshness"], "UNVERIFIED")

    def test_history_distinguishes_incomplete_insufficient_and_zero(self):
        with self.client("incomplete") as client:
            result = client.get(BASE + "/historical/team-stats", params={"team": "Real Madrid", "season": 2026}).json()
            self.assertEqual(result["status"], "INCOMPLETE_STATISTICS")
            self.assertGreater(result["overall"]["missing_xg_fixtures"], 0)
            self.assertTrue(any(row["xg"] is None for row in result["trend"]))
            analysis = client.get(BASE + "/historical/match-analysis", params={
                "home": "Real Madrid", "away": "Valencia", "season": 2025, "window": "10"
            }).json()
            self.assertEqual(analysis["window"], 10)
            self.assertEqual(analysis["home"]["status"], "INSUFFICIENT_HISTORY")
            self.assertLess(len(analysis["home"]["trend"]), 10)
            service = client.app.state.service
            with patch.object(service, "_history_cutoff", return_value="2025-01-01"):
                zero = client.get(BASE + "/historical/team-stats", params={"team": "Valencia", "season": 2025}).json()
            self.assertEqual(zero["status"], "ZERO_HISTORY")
            self.assertEqual(zero["overall"]["verified_fixtures"], 0)
            self.assertIsNone(zero["overall"]["mean_xg"])

    def test_historical_reference_and_real_namespace_isolation(self):
        with self.client() as synthetic:
            digest = synthetic.app.state.service.digest
            self.assertEqual(synthetic.get(BASE + "/forecasts").json()["total"], 0)
        with patch("scripts.xpecta_api.services.REAL_SHA256", "forbidden-test-digest"):
            # A changed binding is rejected before access. This test does not need a real private snapshot.
            with TestClient(create_app(Settings(Mode.HISTORICAL_REFERENCE)), base_url="http://localhost",
                            raise_server_exceptions=False) as real:
                self.assertEqual(real.get(BASE + "/health/ready").status_code, 503)
                self.assertEqual(real.get(BASE + "/bootstrap").json()["error"]["code"], "SERVICE_NOT_READY")
        with self.client() as client:
            self.assertEqual(client.app.state.service.digest, digest)

    def test_model_summary_and_read_only_sqlite(self):
        with self.client() as client:
            model = client.get(BASE + "/model/summary").json()
            self.assertEqual(model["model"], "Linear Regression")
            self.assertEqual(len(model["features"]), 13)
            self.assertEqual(model["features"][11], "opponent_matches_seen")
            self.assertEqual({r["source"] for r in model["phase7"]}, {"FBref"})
            self.assertEqual({r["source"] for r in model["retrospective"]}, {"Understat", "Sportmonks"})
            store = client.app.state.service.store
            with self.assertRaisesRegex(sqlite3.DatabaseError, "not authorized"):
                store.query("DELETE FROM registry")

    def test_write_authorization_and_origin_restrictions(self):
        body = {"fixture_key": TARGET}
        with self.client() as client:
            self.assertEqual(client.post(BASE + "/forecasts/publish", json=body).status_code, 403)
        with self.client(token=OPERATOR, origins=("http://127.0.0.1:8080",)) as client:
            denied = client.post(BASE + "/forecasts/publish", json=body)
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(denied.headers["www-authenticate"], "Bearer")
            denied = client.post(BASE + "/forecasts/publish", json=body, headers=AUTH | {"Origin": "https://unknown.example"})
            self.assertEqual(denied.json()["error"]["code"], "CROSS_ORIGIN_WRITE")
            denied = client.post(BASE + "/forecasts/publish", json=body, headers=AUTH | {"Sec-Fetch-Site": "cross-site"})
            self.assertEqual(denied.status_code, 403)
            allowed = client.options(BASE + "/forecasts/publish", headers={
                "Origin": "http://127.0.0.1:8080", "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, content-type",
            })
            self.assertEqual(allowed.headers["access-control-allow-origin"], "http://127.0.0.1:8080")
            self.assertNotIn("access-control-allow-credentials", allowed.headers)
            self.assertFalse(client.app.state.service.forecast.ledger.directory.exists())

    def test_http_error_mapping_and_request_size(self):
        with self.client() as client:
            response = client.get(BASE + "/bootstrap", headers={"Host": "unknown.example"})
            self.assertEqual(response.json()["error"]["code"], "INVALID_HOST")
            bad_json = client.post(BASE + "/forecasts/preview", content=b"{", headers={"Content-Type": "application/json"})
            self.assertEqual(bad_json.status_code, 422)
            large = client.post(BASE + "/forecasts/preview", headers={"Content-Type": "application/json"},
                                content=iter([b" " * 1500, b" " * 1500]))
            self.assertEqual(large.status_code, 413)
            text = client.post(BASE + "/forecasts/preview", data={"fixture_key": TARGET})
            self.assertEqual(text.status_code, 415)
            response = client.get(BASE + "/forecasts/" + "a" * 32)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["error"]["code"], "FORECAST_NOT_FOUND")

    def test_corrupt_trusted_artifact_blocks_readiness_without_leaking_path(self):
        with patch("scripts.xpecta_api.services.load_trusted_pipeline",
                   side_effect=InferenceError("ARTIFACT_CORRUPT", "private path")):
            with self.client() as client:
                ready = client.get(BASE + "/health/ready")
                self.assertEqual(ready.status_code, 503)
                self.assertEqual(ready.json()["reason"], "TRUSTED_INPUT_UNAVAILABLE")
                self.assertNotIn("private path", ready.text)

    def test_filesystem_failure_returns_safe_error_and_releases_lock(self):
        ledger = self.isolated_ledger("filesystem")
        with self.client(token=OPERATOR) as client:
            with patch.object(ledger, "_publish_record", side_effect=PermissionError("private filesystem path")):
                result = client.post(BASE + "/forecasts/publish", headers=AUTH, json={"fixture_key": TARGET})
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json()["error"]["code"], "STORAGE_UNAVAILABLE")
            self.assertNotIn("private filesystem path", result.text)
            self.assertFalse((ledger.root / ".writer.lock").exists())
            retry = client.post(BASE + "/forecasts/publish", headers=AUTH, json={"fixture_key": TARGET})
            self.assertEqual(retry.json()["status"], "PUBLISHED")

    def test_two_concurrent_http_writers_create_at_most_one_revision(self):
        ledger = self.isolated_ledger("concurrency")
        start = Barrier(2, timeout=10)
        with self.client(token=OPERATOR) as client, ThreadPoolExecutor(2) as executor:
            def publish():
                start.wait()
                return client.post(BASE + "/forecasts/publish", headers=AUTH, json={"fixture_key": TARGET})
            result = [future.result(timeout=20) for future in [executor.submit(publish) for _ in range(2)]]
        self.assertEqual(sum(row.json().get("status") == "PUBLISHED" for row in result), 1)
        for row in result:
            if row.status_code == 409:
                self.assertIn(row.json()["error"]["code"], {"LEDGER_BUSY", "STALE_FORECAST_WRITE"})
            else:
                self.assertIn(row.json()["status"], {"PUBLISHED", "NO_CHANGE"})
        self.assertEqual(len(list(ledger.directory.glob("*.json"))), 1)
