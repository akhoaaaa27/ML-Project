"""Fixtures nhân tạo chỉ kiểm tra cơ chế Phase 6; không xuất vào kết quả thật."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin

from scripts.prepare_training_features import FEATURES, ROOT
from scripts.training.cross_validation import FoldSpec, SeasonFold
from scripts.training.train_models import MODEL_NAMES, evaluate_predictions
from scripts.evaluation.analyze_models import BEST_PATH, export_tables, load_selected_models
from scripts.evaluation.error_analysis import (
    actual_xg_groups, cross_model_errors, history_groups, match_error_analysis,
    notable_errors, parse_matchweeks, prediction_table, summarize_errors,
)
from scripts.evaluation.feature_analysis import (
    FEATURE_GROUPS, FittedReference, retained_features, run_ablation, run_permutation,
    summarize_ablation, summarize_permutation, validate_groups,
)
from scripts.evaluation.visualizations import generate_figures


class SpyRegressor(RegressorMixin, BaseEstimator):
    calls = []

    def __init__(self, slope=0.7):
        self.slope = slope

    def fit(self, X, y):
        type(self).calls.append((self, X.index.copy(), tuple(X.columns)))
        self.n_features_in_ = X.shape[1]
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.offset_ = float((y - self.slope * X.iloc[:, 0]).mean())
        return self

    def predict(self, X):
        if list(X.columns) != list(self.feature_names_in_):
            raise ValueError('Sai thứ tự features của fixture.')
        return self.offset_ + self.slope * X.iloc[:, 0].to_numpy()


def reference_fixture():
    rng = np.random.default_rng(19)
    train = pd.DataFrame(rng.uniform(size=(20, 13)), columns=list(FEATURES), index=range(20))
    validation = pd.DataFrame(rng.uniform(size=(12, 13)), columns=list(FEATURES), index=range(20, 32))
    y_train = (0.5 + 0.7 * train.iloc[:, 0]).rename('xg')
    y_val = (0.5 + 0.7 * validation.iloc[:, 0]).rename('xg')
    model = SpyRegressor().fit(train, y_train)
    metrics, _ = evaluate_predictions(y_val, model.predict(validation))
    fold = SeasonFold(1, FoldSpec((2019, 2020), 2021), np.arange(20), np.arange(20, 32),
                      '2019-08-01', '2021-05-01', '2021-08-01', '2022-05-01')
    return FittedReference('Linear Regression', fold, model, train, validation, y_train, y_val, metrics)


def predictions_fixture(all_folds=False):
    frames = []
    for fold in ((1, 2, 3) if all_folds else (1,)):
        season = 2020 + fold
        metadata = pd.DataFrame(dict(season=[season] * 4,
            date=[f'{season}-08-13'] * 2 + [f'{season}-08-14'] * 2,
            round=['Matchweek 2'] * 2 + ['Matchweek 12'] * 2,
            match_id=[100 * fold + 1] * 2 + [100 * fold + 2] * 2,
            team=['A', 'B', 'C', 'D'], opponent=['B', 'A', 'D', 'C'], is_home=[1, 0, 1, 0],
            matches_seen=[0, 1, 4, 5], opponent_matches_seen=[1, 0, 5, 4],
            short_history=[1, 1, 1, 0], opponent_short_history=[1, 1, 0, 1], xg=[0.9, 1.0, 1.999, 2.0]),
            index=np.arange((fold - 1) * 4, fold * 4))
        for position, name in enumerate(MODEL_NAMES):
            frames.append(prediction_table(metadata, name, fold, metadata.xg,
                                          np.array([2., 3., -1., 1.]) + position * 0.2))
    return pd.concat(frames, ignore_index=True)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        SpyRegressor.calls = []

    def test_six_groups_partition_exact_thirteen_features(self):
        validate_groups()
        broken = copy.deepcopy(FEATURE_GROUPS)
        broken['G1'] = ('is_home', 'xg_avg5')
        with self.assertRaises(ValueError):
            validate_groups(broken)
        for group in FEATURE_GROUPS:
            self.assertEqual(retained_features(group), [c for c in FEATURES if c not in FEATURE_GROUPS[group]])

    def test_ablation_fresh_estimators_train_only_exact_columns(self):
        reference = reference_fixture()
        before = len(SpyRegressor.calls)
        result = run_ablation(reference)
        calls = SpyRegressor.calls[before:]
        self.assertEqual(len(result), 6)
        self.assertEqual(len(calls), 6)
        self.assertEqual(len({id(c[0]) for c in calls}), 6)
        for (model, indices, columns), group in zip(calls, FEATURE_GROUPS):
            self.assertIsNot(model, reference.estimator)
            self.assertEqual(model.slope, reference.estimator.slope)
            self.assertTrue(indices.equals(reference.y_train.index))
            self.assertEqual(list(columns), retained_features(group))
            self.assertNotIn('xg', columns)
        np.testing.assert_allclose(result.delta_mae, result.ablated_mae - result.full_mae, rtol=0, atol=0)
        np.testing.assert_allclose(result.delta_rmse, result.ablated_rmse - result.full_rmse, rtol=0, atol=0)

    def test_permutation_never_refits_or_changes_target_and_repeats_exactly(self):
        reference = reference_fixture()
        X, y = reference.X_validation.copy(deep=True), reference.y_validation.copy(deep=True)
        with patch.object(reference.estimator, 'fit', side_effect=AssertionError('Không được refit.')):
            first = run_permutation(reference, n_repeats=3, seed=42)
            second = run_permutation(reference, n_repeats=3, seed=42)
        self.assertEqual(len(first), 13 * 3)
        self.assertEqual(set(first.repetition), {1, 2, 3})
        pd.testing.assert_frame_equal(first, second, check_exact=True)
        pd.testing.assert_frame_equal(X, reference.X_validation, check_exact=True)
        pd.testing.assert_series_equal(y, reference.y_validation, check_exact=True)
        np.testing.assert_allclose(first.importance_mae, first.permuted_mae - first.original_mae, atol=0, rtol=0)

    def test_permutation_sign_and_two_levels_of_dispersion(self):
        result = run_permutation(reference_fixture(), n_repeats=3)
        self.assertGreater(result.loc[result.feature.eq('is_home'), 'importance_mae'].mean(), 0)
        expanded = pd.concat([result.assign(fold=fold, validation_season=2020 + fold) for fold in (1, 2, 3)], ignore_index=True)
        folds, summary = summarize_permutation(expanded)
        self.assertEqual(len(folds), 39)
        self.assertEqual(len(summary), 13)
        np.testing.assert_allclose(summary.std_between_folds, 0, atol=1e-16)
        self.assertTrue(summary.mean_std_within_fold.ge(0).all())

    def test_load_selected_params_and_reject_fixed_parameter_drift(self):
        metadata, models = load_selected_models()
        for name, model in models.items():
            for key, value in metadata['models'][name]['best_params'].items():
                self.assertEqual(model.get_params()[key], value)
        metadata['models']['Decision Tree']['fixed_parameters']['random_state'] = 41
        with tempfile.TemporaryDirectory(prefix='phase6-config-check-') as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps(metadata), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'fixed parameters'):
                load_selected_models(path)

    def test_prediction_clipping_residuals_and_traceability(self):
        predictions = predictions_fixture()
        self.assertTrue(predictions.predicted_xg.ge(0).all())
        np.testing.assert_allclose(predictions.residual, predictions.predicted_xg - predictions.actual_xg, rtol=0, atol=0)
        np.testing.assert_allclose(predictions.absolute_error, abs(predictions.residual), rtol=0, atol=0)
        np.testing.assert_allclose(predictions.squared_error, predictions.residual ** 2, rtol=0, atol=0)
        self.assertEqual(predictions.groupby('model').source_row.nunique().tolist(), [4] * 5)

    def test_actual_xg_and_history_group_boundaries(self):
        self.assertEqual(actual_xg_groups(pd.Series([0.99, 1., 1.999, 2.])).tolist(), ['xg_lt_1', 'xg_1_to_2', 'xg_1_to_2', 'xg_ge_2'])
        self.assertEqual(history_groups(pd.Series([0, 1, 4, 5])).tolist(), ['zero', 'one_to_four', 'one_to_four', 'five_or_more'])

    def test_error_subgroup_counts_and_matchweek_numeric_order(self):
        predictions = predictions_fixture()
        summary, messages = summarize_errors(predictions)
        self.assertFalse(messages)
        self.assertTrue(summary.groupby(['model', 'dimension']).n_observations.sum().eq(4).all())
        venue = summary.loc[summary.dimension.eq('venue')]
        self.assertTrue(venue.n_observations.eq(2).all())
        week = summary.loc[summary.dimension.eq('matchweek') & summary.model.eq('Linear Regression')]
        self.assertEqual(week.group.tolist(), ['2', '12'])
        self.assertTrue(summary.small_sample.all())
        for model in MODEL_NAMES:
            rows = predictions.loc[predictions.model.eq(model)]
            overall = summary.loc[summary.model.eq(model) & summary.dimension.eq('overall')].iloc[0]
            self.assertAlmostEqual(overall.mae, rows.absolute_error.mean())
            self.assertAlmostEqual(overall.rmse, np.sqrt(rows.squared_error.mean()))
            self.assertEqual(overall.n_matches, 2)

    def test_invalid_matchweek_omits_only_that_analysis(self):
        predictions = predictions_fixture()
        predictions.loc[0, 'round'] = 'Unknown'
        summary, messages = summarize_errors(predictions)
        self.assertEqual(len(messages), 1)
        self.assertNotIn('matchweek', set(summary.dimension))
        self.assertIn('season', set(summary.dimension))
        with self.assertRaises(ValueError):
            parse_matchweeks(pd.Series(['Matchweek 0']))

    def test_match_and_cross_model_units_are_not_double_counted(self):
        predictions = predictions_fixture()
        matches = match_error_analysis(predictions)
        self.assertEqual(len(matches), 2 * len(MODEL_NAMES))
        self.assertFalse(matches.duplicated(['model', 'fold', 'match_id']).any())
        np.testing.assert_allclose(matches.sum_absolute_error, matches.home_absolute_error + matches.away_absolute_error)
        cross = cross_model_errors(predictions)
        self.assertEqual(len(cross), 4)
        np.testing.assert_allclose(cross.lr_xgb_prediction_difference,
                                  abs(cross.linear_regression_predicted_xg - cross.xgboost_predicted_xg))
        self.assertTrue(cross.regression_models_large.between(0, 4).all())

    def test_notable_cases_are_unique_and_include_over_and_under_extremes(self):
        predictions = predictions_fixture()
        cases = notable_errors(predictions, top_n=2)
        self.assertFalse(cases.duplicated(['model', 'fold', 'match_id', 'team']).any())
        for model, group in cases.groupby('model'):
            source = predictions.loc[predictions.model.eq(model)]
            self.assertEqual(group.residual.max(), source.residual.max())
            self.assertEqual(group.residual.min(), source.residual.min())
            self.assertTrue(group.largest_overprediction.any())
            self.assertTrue(group.largest_underprediction.any())

    def test_export_csv_roundtrip_preserves_original_inputs(self):
        predictions = predictions_fixture()
        snapshot = predictions.copy(deep=True)
        summary, _ = summarize_errors(predictions)
        with tempfile.TemporaryDirectory(prefix='phase6-export-check-') as folder:
            hashes = export_tables({'predictions.csv': predictions, 'summary.csv': summary}, Path(folder))
            self.assertEqual(set(hashes), {'predictions.csv', 'summary.csv'})
            pd.testing.assert_frame_equal(predictions, pd.read_csv(Path(folder) / 'predictions.csv'), check_dtype=False, rtol=1e-14, atol=1e-14)
        pd.testing.assert_frame_equal(predictions, snapshot, check_exact=True)

    def test_visualizations_match_supplied_tables(self):
        predictions = predictions_fixture(all_folds=True)
        errors, _ = summarize_errors(predictions)
        ablation = pd.DataFrame([dict(model=model, removed_group=group, mean_delta_mae=0.01 * position)
            for model in MODEL_NAMES[1:] for position, group in enumerate(FEATURE_GROUPS)])
        importance = pd.DataFrame([dict(model=model, feature=feature, mean_importance_mae=0.001 * position, std_between_folds=0.0001)
            for model in MODEL_NAMES[1:] for position, feature in enumerate(FEATURES)])
        with tempfile.TemporaryDirectory(prefix='phase6-figures-check-') as folder:
            audits = generate_figures({'validation_predictions.csv': predictions, 'error_analysis.csv': errors,
                'ablation_summary.csv': ablation, 'permutation_summary.csv': importance}, Path(folder))
            self.assertEqual(len(audits), 7)
            self.assertEqual(len(list(Path(folder).glob('*.png'))), 7)
            self.assertTrue(all(item['dpi'] == 220 and len(item['source_sha256']) == 64 for item in audits))


if __name__ == '__main__':
    unittest.main()
