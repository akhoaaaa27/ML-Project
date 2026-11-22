"""Manual refreshed successor, ledger history and read-only handoff."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.inference.common import InferenceError, sha256
from scripts.multisource.forecast_demo import refreshed_example
from scripts.multisource.forecast_examples import FIRST, TARGET, UPDATE, synthetic_snapshot
from scripts.multisource.forecast_service import ForecastService


class ForecastIntegrationTests(unittest.TestCase):
    def test_freshly_verified_result_creates_revision_and_metadata_only_snapshot_does_not(self):
        with TemporaryDirectory() as name:
            base = Path(name)
            root = base/"history"
            time = [FIRST]
            service = ForecastService(synthetic_history=root,synthetic_ledger_base=base/"ledger",
                                     simulated_clock=lambda:time[0])
            parent = synthetic_snapshot(root,"initial")
            original_hash = sha256(parent.path)
            first = service.generate_forecast(TARGET,"initial")
            first_hash = first["forecast"]["record_sha256"]
            self.assertEqual(first["forecast"]["forecast_stage"],"INITIAL")
            self.assertEqual(first["forecast"]["eligibility_status"],"EARLY_READY")
            self.assertEqual(refreshed_example(base,parent)["PUBLISH_STATUS"],"PUBLISHED")
            time[0] = UPDATE
            second = service.generate_forecast(TARGET,"updated")
            self.assertEqual(second["forecast"]["forecast_stage"],"UPDATED")
            self.assertEqual(second["forecast"]["eligibility_status"],"EARLY_READY")
            self.assertEqual(second["forecast"]["previous_forecast_id"],first["forecast_id"])
            comparison = service.compare_forecasts(TARGET,first["forecast_id"],second["forecast_id"])
            self.assertTrue(comparison["changed_features"])
            self.assertNotEqual(comparison["history_window_changes"]["before"],comparison["history_window_changes"]["after"])
            self.assertEqual(service.get_forecast(first["forecast_id"])["record_sha256"],first_hash)
            update = service.eligibility.open("updated")
            self.assertEqual(second["forecast"]["history_database_sha256"],sha256(update.path))
            synthetic_snapshot(root,"same",completed=[*range(6),7],now=UPDATE,parent=update)
            unchanged = service.generate_forecast(TARGET,"same")
            self.assertEqual(unchanged["status"],"NO_CHANGE")
            self.assertEqual(unchanged["forecast_id"],second["forecast_id"])
            self.assertEqual(unchanged["evaluated_snapshot_version"],"same")
            self.assertEqual(len(service.list_fixture_forecasts(TARGET)),2)
            self.assertEqual(sha256(parent.path),original_hash)
            self.assertFalse(service.get_forecast_data_status("updated")["production_approved"])
            synthetic_snapshot(root,"unrelated",completed=[*range(6),7],now=UPDATE)
            with self.assertRaises(InferenceError) as caught:
                service.generate_forecast(TARGET,"unrelated")
            self.assertEqual(caught.exception.code,"STALE_FORECAST_SNAPSHOT")
