"""Offline semantics and frozen-artifact checks; no cache, network or credentials."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.data_provider.audit_fbref_penalties import audit_dataset
from scripts.data_provider.penalty_semantics import (
    CountContract, NonPenaltyCounts, SemanticAuditError, reconstruct_non_penalty_counts,
)
from scripts.inference.model_artifact import load_trusted_pipeline
from scripts.prepare_training_features import FEATURES, HISTORY_FEATURES


ROOT = Path(__file__).resolve().parents[1]
VERIFIED_SYNTHETIC_CONTRACT = CountContract(True, True, True, True, True)
EXPECTED_FEATURES = (
    "is_home", "matches_seen", "short_history", "xg_avg5", "xga_avg5", "gf_avg5",
    "ga_avg5", "shot_avg5", "sot_avg5", "opponent_xg_avg5", "opponent_xga_avg5",
    "opponent_matches_seen", "opponent_short_history",
)


class PenaltySemanticsTests(unittest.TestCase):
    def convert(self, **changes):
        inputs = dict(total_shots=10, total_sot=4, penalty_attempts=0,
                      penalty_shots_on_target=0, contract=VERIFIED_SYNTHETIC_CONTRACT)
        inputs.update(changes)
        # Unexpected HTTP traffic is an error even if a credential exists locally.
        with patch("socket.socket.connect", side_effect=AssertionError("Offline only")):
            return reconstruct_non_penalty_counts(**inputs)

    def test_no_penalties(self):
        self.assertEqual(self.convert(), NonPenaltyCounts(10, 4))

    def test_successful_penalty(self):
        self.assertEqual(self.convert(penalty_attempts=1, penalty_shots_on_target=1,
                                     penalty_goals=1), NonPenaltyCounts(9, 3))

    def test_saved_penalty_is_on_target_despite_zero_goals(self):
        self.assertEqual(self.convert(penalty_attempts=1, penalty_shots_on_target=1,
                                     penalty_goals=0), NonPenaltyCounts(9, 3))

    def test_missed_wide_or_woodwork_penalty_is_off_target(self):
        self.assertEqual(self.convert(penalty_attempts=1, penalty_shots_on_target=0,
                                     penalty_goals=0), NonPenaltyCounts(9, 4))

    def test_multiple_penalties_one_goal_one_save_one_wide(self):
        self.assertEqual(self.convert(penalty_attempts=3, penalty_shots_on_target=2,
                                     penalty_goals=1), NonPenaltyCounts(7, 2))

    def test_goals_and_attempts_do_not_identify_penalty_sot(self):
        saved = self.convert(penalty_attempts=1, penalty_goals=0, penalty_shots_on_target=1)
        wide = self.convert(penalty_attempts=1, penalty_goals=0, penalty_shots_on_target=0)
        self.assertNotEqual(saved.shots_on_target, wide.shots_on_target)
        with self.assertRaisesRegex(SemanticAuditError, "Missing metadata"):
            self.convert(penalty_attempts=1, penalty_goals=0, penalty_shots_on_target=None)

    def test_missing_metadata_even_for_apparently_zero_or_all_scored_penalties(self):
        for changes in [dict(penalty_attempts=None), dict(penalty_shots_on_target=None),
                        dict(penalty_attempts=1, penalty_goals=1, penalty_shots_on_target=None),
                        dict(total_shots=None), dict(total_sot=None)]:
            with self.subTest(changes=changes), self.assertRaisesRegex(SemanticAuditError, "Missing metadata"):
                self.convert(**changes)

    def test_negative_reconstructed_counts_rejected(self):
        for changes in [dict(penalty_attempts=11),
                        dict(penalty_attempts=5, penalty_shots_on_target=5)]:
            with self.subTest(changes=changes), self.assertRaisesRegex(SemanticAuditError, "Negative"):
                self.convert(**changes)

    def test_impossible_subset_counts_rejected(self):
        for changes in [dict(total_sot=11), dict(penalty_attempts=1, penalty_shots_on_target=2),
                        dict(penalty_attempts=1, penalty_shots_on_target=0, penalty_goals=1),
                        dict(penalty_attempts=9, penalty_shots_on_target=0)]:
            with self.subTest(changes=changes), self.assertRaises(SemanticAuditError):
                self.convert(**changes)

    def test_unknown_definitions_incomplete_coverage_or_mixed_scope_rejected(self):
        for field in CountContract.__dataclass_fields__:
            with self.subTest(field=field), self.assertRaisesRegex(SemanticAuditError, "Unverified"):
                self.convert(contract=replace(VERIFIED_SYNTHETIC_CONTRACT, **{field: False}))
        for contract in [None, CountContract(), replace(VERIFIED_SYNTHETIC_CONTRACT, same_scope_and_complete=1)]:
            with self.subTest(contract=contract), self.assertRaises(SemanticAuditError):
                self.convert(contract=contract)

    def test_invalid_count_types_are_not_rounded_or_imputed(self):
        for field in ["total_shots", "total_sot", "penalty_attempts", "penalty_shots_on_target", "penalty_goals"]:
            for value in [-1, 1.0, 0.5, True, "1", float("nan"), float("inf")]:
                with self.subTest(field=field, value=value), self.assertRaises(SemanticAuditError):
                    self.convert(**{field: value})

    def test_zero_non_penalty_counts_are_valid(self):
        self.assertEqual(self.convert(total_shots=1, total_sot=1, penalty_attempts=1,
                                     penalty_shots_on_target=1, penalty_goals=1), NonPenaltyCounts(0, 0))

    def test_original_frozen_files_match_pinned_manifest(self):
        manifest = ROOT / "outputs/provider_poc/reports/protected_files.json"
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(),
                         "c3747965e7f5e86418236adfc6f2c8d0044e532c3a2fafeb987d2d2dde309cc3")
        expected = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(len(expected), 107)
        for name in ["data/matches_laliga.csv", "data/preprocess_laliga.py",
                     "data/history/laliga_history.sqlite3", "models/laliga_lr_pipeline.joblib",
                     "models/model_metadata.json", "scripts/inference/build_fixture_features.py",
                     "scripts/prepare_training_features.py"]:
            self.assertIn(name, expected)
        for name, digest in expected.items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)

    def test_frozen_linear_regression_imputer_and_13_features(self):
        self.assertEqual(tuple(FEATURES), EXPECTED_FEATURES)
        with patch("socket.socket.connect", side_effect=AssertionError("Offline only")):
            pipeline, metadata = load_trusted_pipeline()
        self.assertEqual(metadata["model"], "Linear Regression")
        self.assertEqual(metadata["artifact_sha256"],
                         "0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69")
        fitted = pipeline.named_steps["preprocessing"].named_steps["median"]
        self.assertEqual(fitted.n_samples_fit_, 3800)
        np.testing.assert_array_equal(fitted.imputer_.statistics_,
                                     [metadata["imputation_statistics"][f] for f in HISTORY_FEATURES])

    def test_original_dataset_audit_is_read_only_and_reproduces_report(self):
        source = ROOT / "data/matches_laliga.csv"
        before = source.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("Offline only")):
            result = audit_dataset(source)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual((result["team_rows"], result["matches"]), (4700, 2350))
        self.assertEqual(result["exclusive_team_row_categories"],
                         dict(no_penalties=3978, all_scored=543, all_unconverted=150, mixed=29))
        totals = result["team_row_totals"]
        for key, expected in dict(attempts=794, penalty_goals=613, unconverted_attempts=181,
                                  successful_penalty=572, unconverted_penalty=179,
                                  zero_sh_with_penalty=1, zero_sot_with_penalty=36,
                                  zero_sot_with_penalty_goal=29).items():
            self.assertEqual(totals[key], expected, key)
        self.assertEqual(result["matches_by_season"]["2025"]["matches"], 70)
        self.assertEqual(result["match_totals"],
                         dict(matches=2350, no_penalties=1707, successful_penalty=518,
                              unconverted_penalty=173))
        self.assertTrue(result["paired_xg_xga_exact"])
        self.assertEqual(result["zero_xg_with_penalty"], 0)

    def test_dataset_auditor_rejects_missing_perspective_and_fractional_counts(self):
        rows = pd.DataFrame(dict(season=[2023, 2023], date=["2023-10-28"] * 2,
                                 team=["Barcelona", "Real Madrid"], opponent=["Real Madrid", "Barcelona"],
                                 venue=["Home", "Away"], sh=[10, 10], sot=[3, 3], pk=[0, 0],
                                 pkatt=[0, 0], xg=[1.2, 1.3], xga=[1.3, 1.2]))
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "synthetic.csv"
            rows.iloc[:1].to_csv(source, index=False)
            with self.assertRaisesRegex(ValueError, "perspectives"):
                audit_dataset(source)
            rows["pkatt"] = [0.5, 0]
            rows.to_csv(source, index=False)
            with self.assertRaisesRegex(ValueError, "Non-integer"):
                audit_dataset(source)


if __name__ == "__main__":
    unittest.main()
