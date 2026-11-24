from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from scripts.inference.common import MODEL_DIR, sha256
from scripts.multisource.composite_history import CompositeHistory
from scripts.multisource.composite_inference import CompositePredictor
from scripts.multisource.forecast_examples import TARGET
from scripts.xpecta_api.app import create_app
from scripts.xpecta_api.demo import initialize_demo
from scripts.xpecta_api.settings import MODEL_SHA256, Mode, Settings


BASE = "/api/v1/"


class WebsiteRefinementTests(unittest.TestCase):
    def test_real_simulation_uses_verified_history_with_venue_and_leaves_ledger_unchanged(self):
        with TestClient(create_app(Settings()), base_url="http://localhost") as client:
            service = client.app.state.service
            before = client.get(BASE + "forecasts").json()["total"]
            with patch.object(CompositeHistory, "fixture", side_effect=AssertionError("Fixture lookup in simulation")):
                for home, away in (("Malaga", "Barcelona"), ("Barcelona", "Malaga")):
                    response = client.post(BASE + "simulations", json={"home": home, "away": away})
                    self.assertEqual(response.status_code, 200, response.json())
                    result = response.json()
                    cutoff, season = result["history_cutoff"], result["season"]
                    direct = CompositePredictor(service.store).predict(home, away, cutoff, season, hypothetical=True)
                    self.assertEqual((result["home_team"], result["away_team"]), (home, away))
                    self.assertEqual([result["home_xg"], result["away_xg"]], [direct["home_xg"], direct["away_xg"]])
                    self.assertEqual(direct["features"][0]["is_home"], 1)
                    self.assertEqual(direct["features"][1]["is_home"], 0)
                    self.assertTrue(all(row["last_date"] < cutoff for row in direct["history_summary"].values()))
                    self.assertLessEqual(cutoff, datetime.fromisoformat(result["generated_at_utc"]).date().isoformat())
                    self.assertNotIn("canonical_fixture_key", result)
                    self.assertNotIn("forecast_revision", result)
                    self.assertEqual(result["model_artifact_sha256"], MODEL_SHA256)
                    self.assertFalse(result["production_approved"])
            self.assertEqual(client.get(BASE + "forecasts").json()["total"], before)
            self.assertEqual(sha256(MODEL_DIR / "laliga_lr_pipeline.joblib"), MODEL_SHA256)

    def test_simulations_succeed_independently_of_official_preview_and_validate_inputs(self):
        with TemporaryDirectory() as folder, patch("scripts.xpecta_api.settings.PRIVATE", Path(folder)):
            initialize_demo(Path(folder) / "demos" / "ui-refinement")
            for profile in ("updated", "incomplete"):
                with TestClient(create_app(Settings(Mode.SYNTHETIC_DEMO, profile, "ui-refinement")),
                                base_url="http://localhost") as client:
                    same = client.post(BASE + "simulations", json={"home": "Valencia", "away": "Valencia"})
                    self.assertEqual(same.json()["error"]["message"], "Select two different teams to simulate.")
                    self.assertEqual(same.status_code, 422)
                    unknown = client.post(BASE + "simulations", json={"home": "Valencia", "away": "Unknown"})
                    self.assertEqual(unknown.status_code, 404)
                    invalid = client.post(BASE + "simulations", json={"home": "Valencia", "away": "Real Madrid", "kickoff": "2026-01-01"})
                    self.assertEqual(invalid.status_code, 422)
                    simulation = client.post(BASE + "simulations", json={"home": "Valencia", "away": "Real Madrid"})
                    if profile == "incomplete":
                        self.assertEqual(simulation.status_code, 422, simulation.json())
                        self.assertEqual(simulation.json()["error"]["code"], "SIMULATION_INSUFFICIENT_DATA")
                    else:
                        self.assertEqual(simulation.status_code, 200, simulation.json())
                        self.assertEqual(simulation.json()["dataset_kind"], "synthetic")
                        preview = client.post(BASE + "forecasts/preview", json={"fixture_key": TARGET})
                        self.assertEqual(preview.json()["status"], "EARLY_READY")
                        # The reversed pairing has already been played in this fixture catalogue.
                        reversed_pair = client.post(BASE + "simulations", json={"home": "Real Madrid", "away": "Valencia"})
                        self.assertEqual(reversed_pair.status_code, 200, reversed_pair.json())
                    self.assertEqual(client.get(BASE + "forecasts").json()["total"], 0)

    def test_phase7_science_contract(self):
        with TestClient(create_app(Settings()), base_url="http://localhost") as client:
            response = client.get(BASE + "model/summary")
            self.assertEqual(response.status_code, 200)
            data = response.json()
        main, points = data["main_test"], data["main_observations"]
        self.assertEqual(main["label"], "main_final_test")
        self.assertEqual(main["observations"], len(points))
        self.assertEqual(len(points), 760)
        self.assertAlmostEqual(main["mae"], 0.5665239063025542)
        self.assertAlmostEqual(main["rmse"], 0.7496762531826113)
        self.assertAlmostEqual(main["baseline_mae"], 0.6367697368421052)
        self.assertEqual({row["label"] for row in data["phase7"]}, {"main_final_test", "supplemental_test"})
        self.assertEqual({row["source"] for row in data["retrospective"]}, {"Understat", "Sportmonks"})
        self.assertEqual(len(data["features"]), 13)
