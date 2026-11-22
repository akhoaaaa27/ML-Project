"""Offline eligibility and cutoff checks against isolated Composite History."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.inference.common import InferenceError
from scripts.multisource.forecast_eligibility import ForecastEligibility
from scripts.multisource.forecast_examples import FIRST, TARGET, synthetic_snapshot


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "history"
        self.time = FIRST
        self.engine = ForecastEligibility(synthetic_root=self.root, simulated_clock=lambda:self.time)

    def evaluate(self, *, key=TARGET, **kwargs):
        synthetic_snapshot(self.root,"sample",**kwargs)
        return self.engine.evaluate_forecast_eligibility(key,"sample")

    def test_multiple_intermediate_fixtures_are_early_ready(self):
        result = self.evaluate()
        self.assertEqual(result["eligibility_status"],"EARLY_READY")
        self.assertEqual(len(result["intermediate_fixtures"]),3)
        self.assertEqual(result["history_cutoff"],"2026-11-19")

    def test_one_intermediate(self):
        result = self.evaluate(key="research:laliga:2026:Sevilla:Real Madrid")
        self.assertEqual(result["eligibility_status"],"EARLY_READY")
        self.assertEqual(len(result["intermediate_fixtures"]),1)

    def test_same_day_before_kickoff_ready(self):
        self.assertEqual(self.evaluate(key="research:laliga:2026:Sevilla:Barcelona")["eligibility_status"],"READY")

    def test_same_day_unknown_kickoff_waits(self):
        result = self.evaluate(key="research:laliga:2026:Sevilla:Barcelona",kickoff_changes={6:None})
        self.assertEqual((result["eligibility_status"],result["reason"]),("WAITING_DATA","KICKOFF_UNVERIFIED"))

    def test_started_at_exact_kickoff(self):
        self.time = "2026-11-19T19:30:00Z"
        result = self.evaluate(key="research:laliga:2026:Sevilla:Barcelona")
        self.assertEqual(result["reason"],"TARGET_ALREADY_STARTED")

    def test_pending_inside_last_five_blocks(self):
        result = self.evaluate(pending={(2026,5)})
        self.assertEqual(result["reason"],"MISSING_ROLLING_STATISTICS")

    def test_pending_outside_window_is_eligible(self):
        result = self.evaluate(pending={(2025,0)})
        self.assertEqual(result["eligibility_status"],"EARLY_READY")

    def test_missing_completion_coverage_blocks(self):
        self.assertEqual(self.evaluate(completed=range(5))["reason"],"REGISTRY_COVERAGE_UNVERIFIED")

    def test_stale_fixture_evidence_blocks(self):
        self.time = "2026-11-22T09:00:00Z"
        self.assertEqual(self.evaluate()["reason"],"FIXTURE_FRESHNESS_UNVERIFIED")

    def test_real_clock_cannot_be_overridden(self):
        with self.assertRaises(InferenceError):
            ForecastEligibility(simulated_clock=lambda:FIRST)
        before = datetime.now(timezone.utc)
        self.assertGreaterEqual(ForecastEligibility().now(),before)

    def test_snapshot_paths_are_rejected(self):
        with self.assertRaises(InferenceError):
            self.engine.open("../sample")

    def test_cancelled_and_live_and_completed_targets_are_unavailable(self):
        for state in ("cancelled","live","completed"):
            with self.subTest(state=state):
                synthetic_snapshot(self.root,state,status_changes={10:state})
                result = self.engine.evaluate_forecast_eligibility(TARGET,state)
                self.assertEqual(result["eligibility_status"],"UNAVAILABLE")

    def test_unknown_fixture_is_unavailable(self):
        self.assertEqual(self.evaluate(key="missing")["eligibility_status"],"UNAVAILABLE")
