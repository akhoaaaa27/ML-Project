"""Generated forecast records exercise concurrency and persistence invariants."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch

from scripts.inference.common import InferenceError, sha256
from scripts.multisource.forecast_eligibility import ForecastEligibility
from scripts.multisource.forecast_examples import FIRST, TARGET, synthetic_snapshot
from scripts.multisource.forecast_generation import generate_forecast
from scripts.multisource.forecast_ledger import FORECAST_ROOT, ForecastLedger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        history = base/"history"
        self.store = synthetic_snapshot(history,"v1")
        engine = ForecastEligibility(synthetic_root=history,simulated_clock=lambda:FIRST)
        self.candidate = generate_forecast(TARGET,"v1",eligibility=engine)["forecast"]
        self.ledger = ForecastLedger(synthetic_base=base/"ledger")

    def test_duplicate_with_same_inputs_returns_existing_id(self):
        first = self.ledger.append(self.candidate,expected_previous_id=None)
        duplicate = self.ledger.append(self.candidate,expected_previous_id=first["forecast_id"])
        self.assertEqual(duplicate["status"],"NO_CHANGE")
        self.assertEqual(duplicate["forecast_id"],first["forecast_id"])
        self.assertEqual(len(list(self.ledger.directory.glob("*.json"))),1)

    def test_stale_expected_revision_fails(self):
        self.ledger.append(self.candidate,expected_previous_id=None)
        with self.assertRaisesRegex(InferenceError,"Latest forecast changed"):
            self.ledger.append(self.candidate,expected_previous_id=None)

    def test_concurrent_writer_rejected_without_removing_lock(self):
        acquired, release = Event(), Event()

        def hold():
            with self.ledger._writer():
                acquired.set()
                release.wait(5)

        writer = Thread(target=hold)
        writer.start()
        try:
            self.assertTrue(acquired.wait(5))
            with self.assertRaises(InferenceError) as caught:
                self.ledger.append(self.candidate,expected_previous_id=None)
            self.assertEqual(caught.exception.code,"LEDGER_BUSY")
            self.assertTrue((self.ledger.root/".writer.lock").exists())
        finally:
            release.set()
            writer.join(5)
        self.assertEqual(self.ledger.append(self.candidate,expected_previous_id=None)["status"],"PUBLISHED")

    def test_failed_atomic_publication_cleans_only_its_temporary_file(self):
        before = sha256(self.store.path)
        old = self.ledger.append(self.candidate,expected_previous_id=None)["forecast"]
        old_path = self.ledger.directory/(old["forecast_id"]+".json")
        old_hash = sha256(old_path)
        revised = dict(self.candidate,target_kickoff_utc="2026-11-23T20:30:00Z")
        with patch("scripts.multisource.forecast_ledger.os.link",side_effect=OSError("injected publish failure")):
            with self.assertRaises(OSError):
                self.ledger.append(revised,expected_previous_id=old["forecast_id"])
        self.assertEqual(sha256(old_path),old_hash)
        self.assertEqual(sha256(self.store.path),before)
        self.assertEqual(list(self.ledger.directory.iterdir()),[old_path])
        self.assertFalse((self.ledger.root/".writer.lock").exists())

    def test_tampered_record_fails_read(self):
        record = self.ledger.append(self.candidate,expected_previous_id=None)["forecast"]
        path = self.ledger.directory/(record["forecast_id"]+".json")
        path.write_text(path.read_text(encoding="utf-8").replace('"INITIAL"','"UPDATED"'),encoding="utf-8")
        with self.assertRaises(InferenceError) as caught:
            self.ledger.get_forecast(record["forecast_id"])
        self.assertEqual(caught.exception.code,"LEDGER_CORRUPT")

    def test_older_generated_timestamp_is_rejected(self):
        result = self.ledger.append(self.candidate,expected_previous_id=None)
        earlier = dict(self.candidate,generated_at_utc="2026-11-19T08:00:00Z")
        with self.assertRaises(InferenceError) as caught:
            self.ledger.append(earlier,expected_previous_id=result["forecast_id"])
        self.assertEqual(caught.exception.code,"STALE_FORECAST_WRITE")

    def test_equal_features_with_different_prediction_is_rejected(self):
        result = self.ledger.append(self.candidate,expected_previous_id=None)
        inconsistent = deepcopy(self.candidate)
        inconsistent["raw_predictions"][0] += 1
        inconsistent["home_xg"] = max(0,inconsistent["raw_predictions"][0])
        with self.assertRaises(InferenceError) as caught:
            self.ledger.append(inconsistent,expected_previous_id=result["forecast_id"])
        self.assertEqual(caught.exception.code,"FORECAST_PARITY_FAILED")

    def test_rescheduled_target_creates_revision_and_schedule_notice(self):
        first = self.ledger.append(self.candidate,expected_previous_id=None)
        changed = dict(self.candidate,target_kickoff_utc="2026-11-23T20:30:00Z")
        second = self.ledger.append(changed,expected_previous_id=first["forecast_id"])
        result = self.ledger.compare_forecasts(TARGET,first["forecast_id"],second["forecast_id"])
        self.assertEqual(result["schedule_notice"],"SCHEDULE_REVISED")
        self.assertEqual(result["changed_features"],[])
        self.assertEqual(result["home_xg_delta"],0)
        third = self.ledger.append(self.candidate,expected_previous_id=second["forecast_id"])
        self.assertEqual(third["forecast"]["forecast_revision"],3)

    def test_synthetic_candidate_and_root_cannot_enter_real_namespace(self):
        with self.assertRaises(InferenceError):
            ForecastLedger().append(self.candidate,expected_previous_id=None)
        with self.assertRaises(InferenceError):
            ForecastLedger(synthetic_base=FORECAST_ROOT/"real")
