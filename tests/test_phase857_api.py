"""Local HTTP contracts over the real frozen model and isolated synthetic snapshots."""

from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from scripts.inference.common import InferenceError, sha256
from scripts.multisource.forecast_eligibility import utc
from scripts.multisource.forecast_examples import FIRST, TARGET, synthetic_snapshot
from scripts.multisource.forecast_generation import generate_forecast
from scripts.multisource.forecast_ledger import ForecastLedger
from scripts.multisource.match_registry import canonical_key
from scripts.multisource.refresh_demo import CLUBS
from scripts.xpecta_api.app import create_app
from scripts.xpecta_api.demo import initialize_demo
from scripts.xpecta_api.schemas import Fixture, ForecastRequest
from scripts.xpecta_api.settings import MODEL_SHA256, Mode, REAL_VERSION, Settings
from scripts.xpecta_api.prepare_frontend import build

BASE = "/api/v1"
OPERATOR = "deterministic-synthetic-operator-for-tests"
AUTH = {"Authorization": f"Bearer {OPERATOR}"}
OBSERVED_STATUSES = ("scheduled", "completed", "live", "postponed", "cancelled", "unverified")


def create_live_demo(root):
    index = next(i for i, teams in enumerate(permutations(CLUBS, 2)) if canonical_key(2026, *teams) == TARGET)
    return synthetic_snapshot(root / "history", "initial", status_changes={index: "live"})


class Phase857SchemaTests(unittest.TestCase):
    def test_fixture_supports_all_registry_observed_statuses(self):
        fixture = dict(canonical_fixture_key=TARGET, season=2026, home_team="Valencia", away_team="Real Madrid",
                       match_date="2026-11-23", kickoff_utc="2026-11-23T19:30:00Z", match_status="UNVERIFIED",
                       statistics_status="UNVERIFIED", snapshot_version="initial", verified_at=FIRST)
        for status in OBSERVED_STATUSES:
            with self.subTest(status=status):
                validated = Fixture.model_validate(dict(fixture, observed_status=status))
                self.assertEqual(validated.observed_status, status)
        with self.assertRaises(ValidationError):
            Fixture.model_validate(dict(fixture, observed_status="finished"))

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
            {"render_hostname": "https://test.onrender.com"},
            {"render_hostname": "*.onrender.com"},
            {"render_hostname": "test.onrender.com", "operator_token": OPERATOR},
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


class RenderHttpTests(unittest.TestCase):
    hostname = "xpecta-test.onrender.com"

    def test_render_hostname_serves_packaged_frontend_and_read_only_research(self):
        settings = Settings(render_hostname=self.hostname)
        with TestClient(create_app(settings), base_url=f"https://{self.hostname}") as client:
            ready = client.get(BASE + "/health/ready")
            self.assertEqual(ready.status_code, 200)
            self.assertTrue(ready.json()["frontend_available"])
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn('<script type="module" src="/assets/app.js"></script>', response.text)
            self.assertIn('<link rel="icon" type="image/png" sizes="64x64" href="/assets/favicon.png">', response.text)
            icon = client.get("/assets/favicon.png")
            self.assertEqual(icon.status_code, 200)
            self.assertEqual(icon.headers["content-type"], "image/png")
            self.assertEqual(icon.content[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(client.get("/assets/app.js").status_code, 200)
            self.assertEqual(client.get("/assets/reference.html").status_code, 404)
            denied = client.get(BASE + "/health/ready", headers={"Host": "other.onrender.com"})
            self.assertEqual(denied.json()["error"]["code"], "INVALID_HOST")
            denied = client.post(BASE + "/forecasts/publish", json={"fixture_key": TARGET})
            self.assertEqual(denied.json()["error"]["code"], "PUBLICATION_DISABLED")

    def test_render_readiness_requires_bundled_frontend(self):
        settings = Settings(render_hostname=self.hostname)
        with TemporaryDirectory() as tmp, patch("scripts.xpecta_api.app.FRONTEND", Path(tmp)):
            with TestClient(create_app(settings), base_url=f"https://{self.hostname}") as client:
                ready = client.get(BASE + "/health/ready")
                self.assertEqual(ready.status_code, 503)
                self.assertEqual(ready.json()["reason"], "FRONTEND_UNAVAILABLE")
                self.assertFalse(ready.json()["frontend_available"])


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

    def client(self, profile="initial", *, token="", origins=(), demo_name="test-run"):
        return TestClient(create_app(Settings(Mode.SYNTHETIC_DEMO, profile, demo_name, token, origins)),
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
            self.assertEqual(client.get("/assets/phase9.css").status_code, 200)
            favicon = client.get("/favicon.ico")
            self.assertEqual(favicon.status_code, 200)
            self.assertEqual(favicon.headers["content-type"], "image/png")
            self.assertIn("default-src 'none'", ready.headers["content-security-policy"])
            routes = client.get("/openapi.json").json()["paths"]
            self.assertEqual(len(routes), 17)
            self.assertIn("post", routes["/api/v1/simulations"])
            self.assertIn("get", routes["/api/v1/historical/season-leaderboard"])

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

    def test_live_fixture_serializes_with_identical_public_fields(self):
        with self.client() as client:
            params = dict(season=2026, home="Valencia", away="Real Madrid")
            original = client.get(BASE + "/fixtures", params=params).json()["items"][0]
            self.assertEqual(original["canonical_fixture_key"], TARGET)
            self.assertEqual(original["observed_status"], "scheduled")
            rows = client.app.state.service.fixtures
            with patch.dict(rows, {TARGET: dict(rows[TARGET], observed_status="live")}):
                response = client.get(BASE + "/fixtures")
            self.assertEqual(response.status_code, 200)
            match = next(row for row in response.json()["items"] if row["canonical_fixture_key"] == TARGET)
            self.assertEqual(match, dict(original, observed_status="live"))

    def test_live_filter_excludes_upcoming_and_is_documented_in_openapi(self):
        with self.client() as client:
            rows = client.app.state.service.fixtures
            with patch.dict(rows, {TARGET: dict(rows[TARGET], observed_status="live")}):
                result = client.get(BASE + "/fixtures?status=live")
                self.assertEqual(result.status_code, 200)
                self.assertEqual([(row["canonical_fixture_key"], row["observed_status"])
                                  for row in result.json()["items"]], [(TARGET, "live")])
                result = client.get(BASE + "/fixtures?status=live&upcoming=true")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["items"], [])
                result = client.get(BASE + "/fixtures?season=2026&upcoming=true")
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.json()["items"])
                self.assertNotIn(TARGET, {row["canonical_fixture_key"] for row in result.json()["items"]})
            schema = client.get("/openapi.json").json()
            fixtures = schema["paths"][BASE + "/fixtures"]["get"]
            status_filter = next(param for param in fixtures["parameters"] if param["name"] == "status")
            alternatives = status_filter["schema"]["anyOf"]
            self.assertEqual(set(next(item["enum"] for item in alternatives if "enum" in item)),
                             set(OBSERVED_STATUSES))
            self.assertEqual(set(schema["components"]["schemas"]["Fixture"]["properties"]["observed_status"]["enum"]),
                             set(OBSERVED_STATUSES))
            result = client.get(BASE + "/fixtures?status=finished")
            self.assertEqual((result.status_code, result.json()["error"]["code"]), (422, "INVALID_REQUEST"))

    def test_live_target_cannot_preview_or_publish_even_with_future_kickoff(self):
        store = create_live_demo(self.private / "demos" / "live-boundary")
        before = sha256(store.path)
        with self.client(token=OPERATOR, demo_name="live-boundary") as client:
            query = {"fixture_key": TARGET}
            eligibility = client.get(BASE + "/eligibility", params=query)
            self.assertEqual(eligibility.status_code, 200)
            expected = eligibility.json()
            self.assertEqual(expected["target"]["observed_status"], "live")
            self.assertEqual(expected["target"]["canonical_fixture_key"], TARGET)
            self.assertGreater(utc(expected["target"]["kickoff_utc"]), utc(expected["generated_at_utc"]))
            self.assertEqual((expected["eligibility_status"], expected["reason"]), ("UNAVAILABLE", "TARGET_NOT_UPCOMING"))
            for route, headers in (("preview", {}), ("publish", AUTH)):
                with self.subTest(route=route):
                    response = client.post(BASE + "/forecasts/" + route, headers=headers, json=query)
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(result["eligibility"], expected)
                    self.assertEqual(result["status"], "UNAVAILABLE")
                    self.assertIsNone(result["preview"])
                    self.assertIsNone(result["forecast"])
            self.assertEqual(client.get(BASE + "/forecasts", params=query).json()["total"], 0)
        self.assertEqual(sha256(store.path), before)

    def test_previous_observed_statuses_serialize_and_filter_over_http(self):
        with self.client() as client:
            rows = client.app.state.service.fixtures
            completed = next(row for row in rows.values()
                             if row["season"] == 2026 and row["observed_status"] == "completed")
            for status in ("scheduled", "completed", "postponed", "cancelled", "unverified"):
                with self.subTest(status=status):
                    expected = completed if status == "completed" else dict(rows[TARGET], observed_status=status)
                    key = expected["canonical_fixture_key"]
                    with patch.dict(rows, {key: expected}):
                        response = client.get(BASE + "/fixtures", params={"season": 2026, "status": status})
                    self.assertEqual(response.status_code, 200)
                    items = response.json()["items"]
                    self.assertEqual({row["observed_status"] for row in items}, {status})
                    actual = next(row for row in items if row["canonical_fixture_key"] == key)
                    for field in ("home_team", "away_team", "match_date", "match_status", "statistics_status"):
                        self.assertEqual(actual[field], expected[field], field)

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
            self.assertGreater(freshness["expired_review_upcoming_fixtures"], 0)
            self.assertTrue(any(row["status"] == "EXPIRED" for row in freshness["schedule_evidence"]))

    def test_publish_rejects_changed_preview_binding_before_write(self):
        ledger = self.isolated_ledger("preview-binding")
        with self.client(token=OPERATOR) as client:
            body = {"fixture_key": TARGET}
            preview = client.post(BASE + "/forecasts/preview", json=body).json()["preview"]
            keys = ("history_database_sha256", "features_sha256")
            binding = {key: preview[key] for key in keys}
            for key in keys:
                with self.subTest(key=key):
                    bad = dict(binding, **{key: "0" * 64})
                    result = client.post(BASE + "/forecasts/publish", headers=AUTH, json=dict(body, expected=bad))
                    self.assertEqual(result.status_code, 409)
                    self.assertEqual(result.json()["error"]["code"], "PREVIEW_BINDING_CHANGED")
                    self.assertFalse(ledger.root.exists())
            result = client.post(BASE + "/forecasts/publish", headers=AUTH, json=dict(body, expected=binding))
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["forecast"]["features_sha256"], preview["features_sha256"])

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

    def test_leaderboard_matches_individual_statistics_with_one_integrity_check(self):
        with self.client("incomplete") as client:
            service = client.app.state.service
            with patch.object(service, "_verify_bound_snapshot", wraps=service._verify_bound_snapshot) as verify:
                leaderboard = client.get(BASE + "/historical/season-leaderboard", params={"season": 2026})
                self.assertEqual(leaderboard.status_code, 200)
                verify.assert_called_once()
            payload = leaderboard.json()
            self.assertEqual(payload["snapshot_version"], "incomplete")
            teams = {row["id"] for row in service.teams.values() if 2026 in row["seasons"]}
            self.assertEqual({row["team"] for row in payload["items"]}, teams)
            for row in payload["items"]:
                stats = client.get(BASE + "/historical/team-stats", params={"team": row["team"], "season": 2026})
                self.assertEqual(row["overall"], stats.json()["overall"])

    def test_historical_reference_and_real_namespace_isolation(self):
        with self.client() as synthetic:
            digest = synthetic.app.state.service.digest
            self.assertEqual(synthetic.get(BASE + "/forecasts").json()["total"], 0)
        with patch("scripts.xpecta_api.research_binding.REAL_SHA256", "forbidden-test-digest"):
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
            self.assertEqual({r["period"] for r in model["phase7"]},
                             {"2024-08-15 to 2025-05-25", "2025-08-15 to 2025-09-30"})
            self.assertEqual({r["period"] for r in model["retrospective"]}, {"2025/26 after 2025-09-30", "2026/27"})
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
