"""Kiểm thử riêng cho search, scorer, luật chọn và các đầu ra Phase 5."""

import copy
import itertools
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LinearRegression
from threadpoolctl import threadpool_limits

from scripts.prepare_training_features import FEATURES, HISTORY_FEATURES, HistoryMedianImputer, ROOT, load_dataset
from scripts.training.train_models import MODEL_NAMES, evaluate_predictions, model_templates
from scripts.training.tune_models import (
    AuditedClippedScorer, BUDGETS, SEARCH_SEED, assert_same_evaluation, build_comparison,
    build_pipeline, candidate_configurations, canonical_params, export_outputs,
    make_search, prepare_development, search_result_rows, select_best_candidate, validate_outputs,
)


def synthetic_outputs():
    """Số liệu nhân tạo chỉ dùng trong thư mục tạm; không phải kết quả thí nghiệm."""
    rows, diagnostics, metadata = [], [], {}
    for model in BUDGETS:
        for number, params in enumerate(candidate_configurations(model), 1):
            for fold in (1, 2, 3):
                train_mae = 0.2 + number * 0.001
                validation_mae = 0.5 + number * 0.001 + fold * 0.01
                rows.append(dict(model=model, candidate_id=number, fold=fold,
                    train_seasons=';'.join(map(str, range(2019, 2020 + fold))), validation_season=2020 + fold,
                    train_samples=(fold + 1) * 760, validation_samples=760, hyperparameters=canonical_params(params),
                    train_mae=train_mae, train_rmse=train_mae + 0.1,
                    validation_mae=validation_mae, validation_rmse=validation_mae + 0.1,
                    mae_gap=validation_mae - train_mae, rmse_gap=validation_mae - train_mae,
                    train_negative_predictions=0, validation_negative_predictions=0,
                    train_prediction_sha256=f'train_{model}_{number}_{fold}',
                    validation_prediction_sha256=f'validation_{model}_{number}_{fold}', execution_status='success'))
    trials = pd.DataFrame(rows)
    for model in BUDGETS:
        selected = select_best_candidate(trials.loc[trials.model.eq(model)])
        metadata[model] = dict(candidate_id=int(selected['candidate_id']),
            best_params=__import__('json').loads(selected['hyperparameters']),
            mean_validation_mae=selected['mean_validation_mae'], mean_validation_rmse=selected['mean_validation_rmse'])
        selected_rows = trials.loc[trials.model.eq(model) & trials.candidate_id.eq(selected['candidate_id'])]
        for record in selected_rows.to_dict('records'):
            record.pop('candidate_id')
            diagnostics.extend([dict(record, configuration_stage='before'), dict(record, configuration_stage='after')])
    for fold in (1, 2, 3):
        base = dict(diagnostics[fold - 1], model='Historical Baseline', fold=fold, hyperparameters='null')
        diagnostics.extend([dict(base, configuration_stage='before'), dict(base, configuration_stage='after')])
    diagnostics = pd.DataFrame(diagnostics)
    return trials, build_comparison(diagnostics), {'models': metadata}, diagnostics


class TuningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.development = prepare_development(load_dataset())
        cls.imputer_fits, cls.model_fits = [], []
        original_imputer_fit = HistoryMedianImputer.fit
        original_model_fit = LinearRegression.fit

        def audited_imputer(instance, X, y=None):
            cls.imputer_fits.append((instance, X.index.copy(), tuple(X.columns)))
            return original_imputer_fit(instance, X, y)

        def audited_model(instance, X, y, **kwargs):
            cls.model_fits.append((X.index.copy(), y.index.copy()))
            return original_model_fit(instance, X, y, **kwargs)

        cls.scorer = AuditedClippedScorer(cls.development, 'Linear Regression')
        cls.search = make_search('Linear Regression', model_templates()['Linear Regression'], cls.development, cls.scorer)
        with patch.object(HistoryMedianImputer, 'fit', audited_imputer), patch.object(LinearRegression, 'fit', audited_model):
            with threadpool_limits(limits=1):
                cls.search.fit(cls.development.X, cls.development.y)
        cls.linear_trials = search_result_rows('Linear Regression', cls.search, cls.scorer)

    def test_budget_unique_and_reproducible_candidates(self):
        self.assertEqual(sum(BUDGETS.values()), 79)
        for model, budget in BUDGETS.items():
            first = candidate_configurations(model)
            self.assertEqual(len(first), budget)
            self.assertEqual(len({canonical_params(p) for p in first}), budget)
            self.assertEqual(first, candidate_configurations(model, SEARCH_SEED))
            if model != 'Linear Regression':
                self.assertNotEqual(first, candidate_configurations(model, SEARCH_SEED + 1))

    def test_linear_search_exhausts_exact_four_combinations(self):
        combinations = {(p['fit_intercept'], p['positive']) for p in candidate_configurations('Linear Regression')}
        self.assertEqual(combinations, set(itertools.product([True, False], repeat=2)))
        self.assertEqual(len(self.linear_trials), 12)
        self.assertEqual(len(self.search.cv_results_['params']), 4)

    def test_development_positions_align_with_search_inputs(self):
        data = self.development
        self.assertEqual(set(data.frame.season), {2019, 2020, 2021, 2022, 2023})
        self.assertTrue(data.X.index.equals(data.frame.index))
        self.assertTrue(data.y.index.equals(data.frame.index))
        for train, val in self.search.cv:
            self.assertEqual(set(data.frame.iloc[train].season), set(range(2019, int(data.frame.iloc[val].season.iloc[0]))))

    def test_pipeline_clones_without_fitted_state(self):
        pipeline = build_pipeline(model_templates()['Linear Regression'])
        copied = clone(pipeline)
        self.assertFalse(hasattr(copied.named_steps['preprocessing'].named_steps['median'], 'imputer_'))
        self.assertIsNot(pipeline.named_steps['preprocessing'], copied.named_steps['preprocessing'])

    def test_search_does_not_refit_full_development(self):
        self.assertFalse(self.search.refit)
        self.assertFalse(hasattr(self.search, 'best_estimator_'))
        self.assertEqual(len(self.imputer_fits), 12)
        self.assertEqual(len(self.model_fits), 12)
        self.assertEqual(len({id(entry[0]) for entry in self.imputer_fits}), 12)

    def test_every_candidate_fits_only_its_training_partition(self):
        expected = {tuple(self.development.X.iloc[f.train_indices].index): f for f in self.development.folds}
        for _, indices, names in self.imputer_fits:
            self.assertIn(tuple(indices), expected)
            self.assertEqual(names, tuple(FEATURES))
            self.assertNotIn('xg', names)
        for indices, targets in self.model_fits:
            self.assertIn(tuple(indices), expected)
            self.assertTrue(indices.equals(targets))
            self.assertFalse(set(self.development.frame.loc[indices, 'season']) & {2024, 2025})

    def test_search_scores_have_correct_sign_and_clip(self):
        self.assertTrue(self.linear_trials.validation_mae.ge(0).all())
        self.assertTrue(self.linear_trials.validation_rmse.ge(0).all())
        self.assertEqual(len(self.scorer.ledger), 24)
        # Dùng prediction âm nhân tạo qua chính scorer mới, giữ Pipeline đã fit thật.
        fold = self.development.folds[0]
        pipeline = build_pipeline(model_templates()['Linear Regression'])
        pipeline.fit(self.development.X.iloc[fold.train_indices], self.development.y.iloc[fold.train_indices])
        X, y = self.development.X.iloc[fold.validation_indices], self.development.y.iloc[fold.validation_indices]
        scorer = AuditedClippedScorer(self.development, 'Linear Regression')
        with patch.object(pipeline, 'predict', return_value=np.full(len(X), -2.0)):
            scores = scorer(pipeline, X, y)
        expected, _ = evaluate_predictions(y, np.full(len(X), -2.0))
        self.assertEqual(scores['mae'], -expected['mae'])
        self.assertEqual(scores['rmse'], -expected['rmse'])
        self.assertEqual(scores['negative_predictions'], -len(X))

    def test_selection_uses_mae_then_rmse_tolerance_and_stable_params(self):
        rows = []
        for number, params, mae, rmse in [(1, {'x': 2}, 0.5, 0.8), (2, {'x': 1}, 0.5 + 5e-13, 0.7),
                                          (3, {'x': 0}, 0.6, 0.6)]:
            for fold in (1, 2, 3):
                rows.append(dict(model='test', candidate_id=number, hyperparameters=canonical_params(params),
                                 fold=fold, validation_mae=mae, validation_rmse=rmse))
        trials = pd.DataFrame(rows)
        self.assertEqual(select_best_candidate(trials)['candidate_id'], 2)
        self.assertEqual(select_best_candidate(trials, tolerance=0)['candidate_id'], 1)
        trials.loc[trials.candidate_id.eq(1), 'validation_rmse'] = 0.7
        self.assertEqual(select_best_candidate(trials)['candidate_id'], 2)

    def test_selected_evaluation_comparison_detects_prediction_change(self):
        first = self.linear_trials.loc[self.linear_trials.candidate_id.eq(1)].copy()
        changed = first.copy()
        changed.loc[changed.index[0], 'validation_prediction_sha256'] = 'changed'
        with self.assertRaises(AssertionError):
            assert_same_evaluation(first, changed)

    def test_output_validation_rejects_missing_trial_or_artificial_baseline_params(self):
        trials, summary, best, diagnostics = synthetic_outputs()
        validate_outputs(trials, summary, best, diagnostics)
        with self.assertRaises(ValueError):
            validate_outputs(trials.iloc[:-1], summary, best, diagnostics)
        best['models']['Historical Baseline'] = {}
        with self.assertRaises(ValueError):
            validate_outputs(trials, summary, best, diagnostics)

    def test_exported_csv_json_roundtrip_and_failed_validation_preserves_outputs(self):
        trials, summary, best, diagnostics = synthetic_outputs()
        with tempfile.TemporaryDirectory(prefix='tuning-export-check-') as folder:
            directory = Path(folder)
            export_outputs(trials, summary, best, diagnostics, directory)
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            self.assertEqual(set(before), {'tuning_trials.csv', 'tuning_summary.csv', 'best_params.json', 'overfitting_diagnostics.csv'})
            self.assertEqual(len(pd.read_csv(directory / 'tuning_trials.csv')), 237)
            self.assertEqual(len(pd.read_csv(directory / 'overfitting_diagnostics.csv')), 30)
            with self.assertRaises(ValueError):
                export_outputs(trials.iloc[:-1], summary, best, diagnostics, directory)
            self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})

    @unittest.skipUnless(os.name == 'nt', 'Kiểm chứng ACL chỉ áp dụng trên Windows.')
    def test_tuning_json_and_csv_inherit_directory_permissions(self):
        directory = ROOT / 'outputs' / f'.tuning-acl-check-{uuid.uuid4().hex}'
        directory.mkdir()
        try:
            export_outputs(*synthetic_outputs(), output_dir=directory)
            for path in directory.iterdir():
                escaped = str(path).replace("'", "''")
                result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                    f"(Get-Acl -LiteralPath '{escaped}').AreAccessRulesProtected"], check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout.strip(), 'False')
        finally:
            for path in directory.iterdir():
                path.unlink()
            directory.rmdir()


if __name__ == '__main__':
    unittest.main()
