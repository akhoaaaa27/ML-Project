"""Kiểm chứng ranh giới thời gian, luồng fit, metric và xuất kết quả an toàn."""

import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin

from scripts.prepare_training_features import FEATURES, HistoryMedianImputer, load_dataset
from scripts.training.cross_validation import (
    DEFAULT_FOLDS, FoldSpec, RESERVED_SEASONS, SeasonExpandingWindowCV, make_season_folds,
)
from scripts.training.train_models import (
    MODEL_NAMES, OUTPUT_DIR, _canonical, evaluate_predictions, export_results,
    model_templates, run_experiment, summarize_results, verify_reproducibility,
)


class AuditedRegressor(RegressorMixin, BaseEstimator):
    """Estimator nhân tạo chỉ dùng ghi nhận đối số fit trong kiểm thử, không xuất kết quả."""

    calls = []

    def fit(self, X, y):
        type(self).calls.append((X.index.copy(), y.index.copy(), tuple(X.columns)))
        self.n_features_in_ = X.shape[1]
        self.mean_ = float(y.mean())
        return self

    def predict(self, X):
        return np.full(len(X), self.mean_)


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_dataset()
        cls.original = cls.data.copy(deep=True)
        cls.imputer_calls = []
        original_fit = HistoryMedianImputer.fit

        def audited_fit(instance, X, y=None):
            cls.imputer_calls.append(X.index.copy())
            return original_fit(instance, X, y)

        AuditedRegressor.calls = []
        with patch.object(HistoryMedianImputer, "fit", audited_fit):
            cls.result = run_experiment(cls.data, {name: AuditedRegressor() for name in MODEL_NAMES[1:]})

    def test_actual_fold_counts_and_reserved_seasons(self):
        folds = make_season_folds(self.data)
        self.assertEqual([(len(f.train_indices), len(f.validation_indices)) for f in folds],
                         [(1520, 760), (2280, 760), (3040, 760)])
        for fold in folds:
            train, validation = self.data.iloc[fold.train_indices], self.data.iloc[fold.validation_indices]
            self.assertEqual(set(train.season), set(fold.spec.train_seasons))
            self.assertEqual(set(validation.season), {fold.spec.validation_season})
            self.assertTrue(set(train.match_id).isdisjoint(validation.match_id))
            self.assertFalse((set(train.season) | set(validation.season)) & RESERVED_SEASONS)
            self.assertTrue(train.groupby('match_id').size().eq(2).all())
            self.assertTrue(validation.groupby('match_id').size().eq(2).all())
            self.assertLess(train.date.max(), validation.date.min())

    def test_split_is_independent_of_csv_order(self):
        shuffled = self.data.sample(frac=1, random_state=19)
        for a, b in zip(make_season_folds(self.data), make_season_folds(shuffled)):
            for left, right in ((a.train_indices, b.train_indices), (a.validation_indices, b.validation_indices)):
                self.assertEqual(self.data.iloc[left].index.tolist(), shuffled.iloc[right].index.tolist())

    def test_sklearn_splitter_interface(self):
        splitter = SeasonExpandingWindowCV()
        self.assertEqual(splitter.get_n_splits(), 3)
        for (train, validation), fold in zip(splitter.split(self.data, groups=self.data.match_id), make_season_folds(self.data)):
            np.testing.assert_array_equal(train, fold.train_indices)
            np.testing.assert_array_equal(validation, fold.validation_indices)

    def test_reject_incomplete_match(self):
        with self.assertRaisesRegex(ValueError, 'hai bản ghi'):
            make_season_folds(self.data.iloc[1:])

    def test_reject_match_crossing_seasons(self):
        broken = self.data.copy(deep=True)
        broken.loc[broken.index[0], 'season'] = 2024
        with self.assertRaisesRegex(ValueError, 'mùa khác nhau'):
            make_season_folds(broken)

    def test_reject_future_dates_in_training_season(self):
        broken = self.data.copy(deep=True)
        broken.loc[broken.season.eq(2019), 'date'] = '2040-01-01'
        with self.assertRaisesRegex(ValueError, 'ngày Train'):
            make_season_folds(broken)

    def test_reject_reserved_season_configuration(self):
        with self.assertRaisesRegex(ValueError, 'Final Test'):
            make_season_folds(self.data, (FoldSpec((2019, 2020, 2021, 2022, 2023), 2024),))

    def test_reject_non_expanding_configuration(self):
        with self.assertRaisesRegex(ValueError, 'mở rộng'):
            make_season_folds(self.data, (DEFAULT_FOLDS[0], FoldSpec((2020, 2021), 2022)))

    def test_imputer_fit_receives_only_training_indices(self):
        self.assertEqual(len(self.imputer_calls), 3)
        for indices, fold in zip(self.imputer_calls, make_season_folds(self.data)):
            self.assertEqual(indices.tolist(), self.data.iloc[fold.train_indices].index.tolist())
            self.assertTrue(indices.intersection(self.data.iloc[fold.validation_indices].index).empty)

    def test_every_estimator_fit_receives_only_training_indices(self):
        self.assertEqual(len(AuditedRegressor.calls), 12)
        for number, fold in enumerate(make_season_folds(self.data)):
            expected = self.data.iloc[fold.train_indices].index
            for indices, targets, names in AuditedRegressor.calls[number * 4:(number + 1) * 4]:
                self.assertEqual(indices.tolist(), expected.tolist())
                self.assertEqual(targets.tolist(), expected.tolist())
                self.assertEqual(names, tuple(FEATURES))
                self.assertNotIn('xg', names)
                self.assertFalse(set(self.data.loc[indices, 'season']) & RESERVED_SEASONS)

    def test_metrics_use_clipped_predictions_and_rmse(self):
        metrics, prediction = evaluate_predictions(pd.Series([0., 1., 2.]), np.array([-2., 2., 4.]))
        np.testing.assert_array_equal(prediction, [0., 2., 4.])
        self.assertEqual(metrics['negative_predictions'], 1)
        self.assertAlmostEqual(metrics['mae'], 1.)
        self.assertAlmostEqual(metrics['rmse'], np.sqrt(5 / 3))

    def test_reject_non_finite_predictions(self):
        for value in (np.inf, np.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate_predictions(pd.Series([1.]), np.array([value]))

    def test_summary_population_std_and_equal_fold_weights(self):
        rows = [dict(fold=fold, model=name, mae=float(fold), rmse=float(fold + 1))
                for name in MODEL_NAMES for fold in (1, 2, 3)]
        summary = summarize_results(pd.DataFrame(rows))
        np.testing.assert_allclose(summary.mean_mae, 2.)
        np.testing.assert_allclose(summary.mean_rmse, 3.)
        np.testing.assert_allclose(summary.std_mae, np.sqrt(2 / 3))
        np.testing.assert_allclose(summary.std_rmse, np.sqrt(2 / 3))

    def test_reject_missing_model_fold(self):
        with self.assertRaisesRegex(ValueError, '15'):
            summarize_results(self.result.fold_results.iloc[:-1])

    def test_fixed_model_configuration_and_seeds(self):
        first, second = model_templates(), model_templates()
        self.assertEqual(_canonical({k: v.get_params() for k, v in first.items()}),
                         _canonical({k: v.get_params() for k, v in second.items()}))
        for name in ('Decision Tree', 'Random Forest', 'XGBoost'):
            self.assertEqual(first[name].random_state, 42)
        self.assertEqual(first['XGBoost'].objective, 'reg:squarederror')

    def test_reproducibility_detects_changed_prediction(self):
        changed = copy.deepcopy(self.result)
        changed.predictions[(1, MODEL_NAMES[0])][0] += 0.1
        with self.assertRaisesRegex(ValueError, 'Dự báo khác'):
            verify_reproducibility(self.result, changed)

    def test_csv_roundtrip_and_protection_on_failed_validation(self):
        with tempfile.TemporaryDirectory(prefix='laliga-output-check-') as folder:
            directory = Path(folder)
            export_results(self.result, directory)
            hashes_before = {p.name: p.read_bytes() for p in directory.iterdir()}
            self.assertEqual(pd.read_csv(directory / 'cv_fold_results.csv').shape[0], 15)
            self.assertEqual(pd.read_csv(directory / 'cv_summary.csv').shape[0], 5)
            invalid = copy.deepcopy(self.result)
            invalid.fold_results = invalid.fold_results.iloc[:-1]
            with self.assertRaises(ValueError):
                export_results(invalid, directory)
            self.assertEqual(hashes_before, {p.name: p.read_bytes() for p in directory.iterdir()})

    def test_source_dataframe_preserved(self):
        pd.testing.assert_frame_equal(self.data, self.original, check_exact=True)

    @unittest.skipUnless(os.name == 'nt', 'Kiểm chứng ACL chỉ áp dụng trên Windows.')
    def test_windows_exports_inherit_directory_permissions(self):
        # mkdir mặc định kế thừa ACL; không dùng TemporaryDirectory có ACL riêng.
        directory = OUTPUT_DIR / f'.acl-check-{uuid.uuid4().hex}'
        directory.mkdir(parents=True)
        try:
            export_results(self.result, directory)
            for path in directory.iterdir():
                escaped = str(path).replace("'", "''")
                result = subprocess.run(
                    ['powershell', '-NoProfile', '-NonInteractive', '-Command',
                     f"(Get-Acl -LiteralPath '{escaped}').AreAccessRulesProtected"],
                    check=True, capture_output=True, text=True,
                )
                self.assertEqual(result.stdout.strip(), 'False', f'{path.name}: quyền kế thừa bị tắt')
        finally:
            for path in directory.iterdir():
                path.unlink()
            directory.rmdir()


if __name__ == '__main__':
    unittest.main()
