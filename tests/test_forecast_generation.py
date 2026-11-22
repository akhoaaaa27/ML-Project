"""Frozen LR, exact ordered input, and strict-before forecast tests."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.inference.common import sha256
from scripts.multisource.composite_inference import CompositePredictor
from scripts.multisource.forecast_eligibility import ForecastEligibility
from scripts.multisource.forecast_examples import FIRST, TARGET, synthetic_snapshot
from scripts.multisource.forecast_generation import generate_forecast
from scripts.prepare_training_features import FEATURES


class ForecastGenerationTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "history"
        self.engine = ForecastEligibility(synthetic_root=self.root, simulated_clock=lambda:FIRST)

    def test_predictions_match_existing_frozen_pipeline_and_bind_snapshot(self):
        store = synthetic_snapshot(self.root,"v1",completed=range(7))
        before = sha256(store.path)
        result = generate_forecast(TARGET,"v1",eligibility=self.engine)
        self.assertEqual(result["status"],"GENERATED")
        forecast = result["forecast"]
        self.assertEqual(forecast["features"]["order"],list(FEATURES))
        direct = CompositePredictor(store).predict("Valencia","Real Madrid","2026-11-23",2026,prediction_cutoff="2026-11-19")
        self.assertEqual(forecast["raw_predictions"],direct["raw_predictions"])
        self.assertEqual(forecast["home_xg"],direct["home_xg"])
        self.assertEqual(forecast["away_xg"],direct["away_xg"])
        self.assertEqual(forecast["history_database_sha256"],before)
        self.assertEqual(sha256(store.path),before)
        self.assertEqual(forecast["model_artifact_sha256"],"0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69")
        self.assertFalse(forecast["production_approved"])
        self.assertEqual(forecast["demo_label"],"SYNTHETIC_DEMO")

    def test_same_day_and_later_completed_records_do_not_enter_features(self):
        a = synthetic_snapshot(self.root,"only_past")
        b = synthetic_snapshot(self.root,"with_extra",completed=range(10))
        baseline = generate_forecast(TARGET,a.manifest["version_id"],eligibility=self.engine)["forecast"]
        extra = generate_forecast(TARGET,b.manifest["version_id"],eligibility=self.engine)["forecast"]
        self.assertEqual(extra["features"],baseline["features"])
        self.assertEqual(extra["raw_predictions"],baseline["raw_predictions"])

    def test_missing_data_creates_no_forecast_candidate(self):
        synthetic_snapshot(self.root,"pending",pending={(2026,5)})
        result = generate_forecast(TARGET,"pending",eligibility=self.engine)
        self.assertEqual(result["status"],"WAITING_DATA")
        self.assertNotIn("forecast",result)
