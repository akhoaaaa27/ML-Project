"""Tuning theo ba fold đã cố định; không fit Final Model hoặc dùng Final Test.

Chạy: python -m scripts.training.tune_models
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import unittest
import warnings

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.base import clone
from sklearn.model_selection import GridSearchCV, ParameterGrid, ParameterSampler, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits
import threadpoolctl

from scripts.prepare_training_features import (
    FEATURES, HISTORY_FEATURES, PASSTHROUGH_FEATURES, ROOT,
    load_dataset, make_preprocessor, prepare_features,
)
from .cross_validation import DEFAULT_FOLDS, RESERVED_SEASONS, make_season_folds
from .train_models import MODEL_NAMES, STD_DDOF, _table, csv_bytes, evaluate_predictions, model_templates, summarize_results


OUTPUT_DIR = ROOT / "outputs/tuning"
REPORT_PATH = ROOT / "Phases/Optimize Regression Models with Time-Aware Hyperparameter Tuning.md"
SEARCH_SEED = 42
TIE_TOLERANCE = 1e-12
REFERENCE_TOLERANCE = 1e-12
BUDGETS = {"Linear Regression": 4, "Decision Tree": 25, "Random Forest": 25, "XGBoost": 25}
SEARCH_SPACES = {
    "Linear Regression": {"fit_intercept": [True, False], "positive": [True, False]},
    "Decision Tree": {"max_depth": [3, 5, 8, 12, None], "min_samples_split": [2, 5, 10, 20],
                      "min_samples_leaf": [1, 2, 5, 10, 20]},
    "Random Forest": {"n_estimators": [100, 200, 300], "max_depth": [4, 8, 12, None],
                      "min_samples_leaf": [1, 2, 5, 10], "max_features": [0.6, 0.8, 1.0]},
    "XGBoost": {"n_estimators": [100, 200, 350], "learning_rate": [0.02, 0.05, 0.1, 0.2],
                "max_depth": [2, 3, 4, 6], "min_child_weight": [1, 3, 5, 10],
                "subsample": [0.7, 0.85, 1.0], "colsample_bytree": [0.7, 0.85, 1.0],
                "reg_lambda": [1, 5, 10]},
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)  # Chỉ dùng mô tả marker missing=nan của estimator, không phải metric.
    return value


def canonical_params(params: dict) -> str:
    return json.dumps(json_safe(params), ensure_ascii=False, sort_keys=True, allow_nan=False)


def candidate_configurations(model: str, seed: int = SEARCH_SEED) -> list[dict]:
    space = SEARCH_SPACES[model]
    configs = (list(ParameterGrid(space)) if model == "Linear Regression" else
               list(ParameterSampler(space, n_iter=BUDGETS[model], random_state=seed)))
    configs = [json_safe(p) for p in configs]
    _require(len(configs) == BUDGETS[model] and len({canonical_params(p) for p in configs}) == len(configs),
             f"{model}: sai số lượng hoặc trùng candidate.")
    return configs


def build_pipeline(estimator) -> Pipeline:
    return Pipeline([("preprocessing", make_preprocessor()), ("model", clone(estimator))])


@dataclass
class DevelopmentData:
    frame: pd.DataFrame
    X: pd.DataFrame
    y: pd.Series
    folds: tuple


def prepare_development(full: pd.DataFrame) -> DevelopmentData:
    seasons = {s for spec in DEFAULT_FOLDS for s in (*spec.train_seasons, spec.validation_season)}
    _require(not seasons & RESERVED_SEASONS, "Cấu hình development chứa Final Test.")
    frame = full.loc[full.season.isin(seasons)].copy()
    X, y, _ = prepare_features(frame)  # Chỉ khôi phục prior xác định; chưa fit median.
    _require(list(X.columns) == list(FEATURES) and len(X.columns) == 13 and "xg" not in X,
             "X không đúng 13 features hoặc chứa target.")
    _require(X.index.equals(frame.index) and y.index.equals(frame.index), "X/y/metadata không khớp thứ tự dòng.")
    folds = make_season_folds(frame)
    return DevelopmentData(frame, X, y, folds)


def load_phase4_reference() -> tuple[pd.DataFrame, pd.DataFrame]:
    folds = pd.read_csv(ROOT / "outputs/training/cv_fold_results.csv")
    summary = pd.read_csv(ROOT / "outputs/training/cv_summary.csv")
    expected = summarize_results(folds)
    pd.testing.assert_frame_equal(expected, summary, check_dtype=False, check_exact=False,
                                  rtol=0, atol=REFERENCE_TOLERANCE)
    for fold, spec in zip(sorted(folds.fold.unique()), DEFAULT_FOLDS):
        group = folds.loc[folds.fold.eq(fold)]
        _require(group.train_seasons.eq(";".join(map(str, spec.train_seasons))).all()
                 and group.validation_season.eq(spec.validation_season).all(), "Phase 4 có cấu hình fold khác yêu cầu.")
    return folds, summary


def _prediction_hash(prediction: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(prediction, dtype="<f8").tobytes()).hexdigest()


class AuditedClippedScorer:
    """Callable multi-metric cho sklearn; kiểm tra cả median và indices ở từng lần score."""

    def __init__(self, development: DevelopmentData, model: str):
        self.development = development
        self.model = model
        self.ledger = {}
        self.progress = False
        self.partitions = {}
        self.expected_medians = {}
        for fold in development.folds:
            for stage, indices in (("train", fold.train_indices), ("validation", fold.validation_indices)):
                self.partitions[tuple(development.X.iloc[indices].index)] = (fold.fold, stage)
            self.expected_medians[fold.fold] = development.X.iloc[fold.train_indices].loc[:, list(HISTORY_FEATURES)].median().to_numpy()

    def __call__(self, estimator: Pipeline, X: pd.DataFrame, y: pd.Series) -> dict:
        key = tuple(X.index)
        _require(key in self.partitions and X.index.equals(y.index), "Search scorer nhận sai tập/index hoặc dữ liệu ngoài fold.")
        fold_number, stage = self.partitions[key]
        fold = self.development.folds[fold_number - 1]
        preprocessor = estimator.named_steps["preprocessing"]
        median = preprocessor.named_steps["median"]
        _require(median.n_samples_fit_ == len(fold.train_indices)
                 and np.array_equal(median.imputer_.statistics_, self.expected_medians[fold_number]),
                 f"{self.model}/fold {fold_number}: median không khớp Train.")
        processed = preprocessor.transform(X)
        _require(list(processed.columns) == list(FEATURES) and processed.index.equals(X.index)
                 and np.isfinite(processed.to_numpy(dtype=float)).all()
                 and processed.where(X.notna()).equals(X.where(X.notna()))
                 and processed.loc[:, list(PASSTHROUGH_FEATURES)].equals(X.loc[:, list(PASSTHROUGH_FEATURES)]),
                 "Preprocessing làm thay đổi ô hợp lệ, features hoặc thứ tự dòng.")
        _require(estimator.named_steps["model"].n_features_in_ == 13, "Estimator không nhận đúng 13 features.")
        metrics, prediction = evaluate_predictions(y, estimator.predict(X))
        _require(np.array_equal(median.imputer_.statistics_, self.expected_medians[fold_number]), "Median đổi sau khi score.")
        model_params = estimator.named_steps["model"].get_params(deep=False)
        params = {name: json_safe(model_params[name]) for name in SEARCH_SPACES[self.model]}
        ledger_key = (canonical_params(params), fold_number, stage)
        _require(ledger_key not in self.ledger, "Một candidate/fold/tập đã bị score lặp ngoài dự kiến.")
        self.ledger[ledger_key] = dict(**metrics, prediction_sha256=_prediction_hash(prediction))
        if self.progress and stage == "train" and fold_number == len(self.development.folds):
            completed = len(self.ledger) // (2 * len(self.development.folds))
            if completed % 5 == 0 or completed == BUDGETS[self.model]:
                print(f"  {self.model}: đã xong {completed}/{BUDGETS[self.model]} cấu hình", flush=True)
        return {"mae": -metrics["mae"], "rmse": -metrics["rmse"],
                "negative_predictions": -float(metrics["negative_predictions"])}


def make_search(model: str, estimator, development: DevelopmentData, scorer: AuditedClippedScorer):
    kwargs = dict(estimator=build_pipeline(estimator), scoring=scorer,
                  cv=[(f.train_indices.copy(), f.validation_indices.copy()) for f in development.folds],
                  refit=False, return_train_score=True, n_jobs=1, pre_dispatch=1, error_score="raise")
    space = {f"model__{key}": values for key, values in SEARCH_SPACES[model].items()}
    if model == "Linear Regression":
        return GridSearchCV(param_grid=space, **kwargs)
    return RandomizedSearchCV(param_distributions=space, n_iter=BUDGETS[model], random_state=SEARCH_SEED, **kwargs)


def _trial_row(model: str, candidate_id: int, params: dict, fold, scorer: AuditedClippedScorer) -> dict:
    param_text = canonical_params(params)
    train = scorer.ledger[(param_text, fold.fold, "train")]
    validation = scorer.ledger[(param_text, fold.fold, "validation")]
    return dict(model=model, candidate_id=candidate_id, fold=fold.fold,
        train_seasons=";".join(map(str, fold.spec.train_seasons)), validation_season=fold.spec.validation_season,
        train_samples=len(fold.train_indices), validation_samples=len(fold.validation_indices),
        hyperparameters=param_text, train_mae=train["mae"], train_rmse=train["rmse"],
        validation_mae=validation["mae"], validation_rmse=validation["rmse"],
        mae_gap=validation["mae"] - train["mae"], rmse_gap=validation["rmse"] - train["rmse"],
        train_negative_predictions=train["negative_predictions"], validation_negative_predictions=validation["negative_predictions"],
        train_prediction_sha256=train["prediction_sha256"], validation_prediction_sha256=validation["prediction_sha256"],
        execution_status="success")


def search_result_rows(model: str, search, scorer: AuditedClippedScorer) -> pd.DataFrame:
    actual = [{key.removeprefix("model__"): json_safe(value) for key, value in p.items()}
              for p in search.cv_results_["params"]]
    expected = candidate_configurations(model)
    _require(actual == expected, f"{model}: candidate thực tế khác mẫu tái tạo với seed cố định.")
    _require(len(scorer.ledger) == len(actual) * len(scorer.development.folds) * 2, "Thiếu audit của candidate/fold/tập.")
    rows = []
    for number, params in enumerate(actual, 1):
        for fold in scorer.development.folds:
            row = _trial_row(model, number, params, fold, scorer)
            for subset, prefix in (("train", "train"), ("test", "validation")):
                for metric in ("mae", "rmse"):
                    reported = -search.cv_results_[f"split{fold.fold - 1}_{subset}_{metric}"][number - 1]
                    _require(reported == row[f"{prefix}_{metric}"], "Dấu score hoặc metric trong cv_results_ không khớp audit.")
            rows.append(row)
        group = rows[-len(scorer.development.folds):]
        _require(np.isclose(np.mean([r["validation_mae"] for r in group]),
                            -search.cv_results_["mean_test_mae"][number - 1], rtol=0, atol=1e-15),
                 "Mean score không khớp trung bình trọng số bằng nhau.")
    return pd.DataFrame(rows)


def candidate_summary(trials: pd.DataFrame) -> pd.DataFrame:
    return trials.groupby(["model", "candidate_id", "hyperparameters"], as_index=False, sort=False).agg(
        mean_validation_mae=("validation_mae", "mean"), mean_validation_rmse=("validation_rmse", "mean"),
        std_validation_mae=("validation_mae", lambda x: x.std(ddof=STD_DDOF)),
        std_validation_rmse=("validation_rmse", lambda x: x.std(ddof=STD_DDOF)))


def select_best_candidate(trials: pd.DataFrame, tolerance: float = TIE_TOLERANCE) -> dict:
    _require(trials.model.nunique() == 1 and tolerance >= 0, "Chọn cấu hình cần đúng một model và tolerance không âm.")
    summary = candidate_summary(trials)
    _require(np.isfinite(summary.select_dtypes(include="number").to_numpy()).all(), "Candidate có score không hữu hạn.")
    eligible = summary.loc[summary.mean_validation_mae.le(summary.mean_validation_mae.min() + tolerance)]
    eligible = eligible.loc[eligible.mean_validation_rmse.le(eligible.mean_validation_rmse.min() + tolerance)]
    return eligible.sort_values(["hyperparameters", "candidate_id"], kind="stable").iloc[0].to_dict()


def diagnose_configuration(model: str, template, params: dict, development: DevelopmentData,
                           stage: str) -> pd.DataFrame:
    """Fit mới từng fold; scorer và cách tính metric dùng chung với search."""
    scorer = AuditedClippedScorer(development, model)
    actual = clone(template).set_params(**params)
    selected = {key: json_safe(actual.get_params(deep=False)[key]) for key in SEARCH_SPACES[model]}
    rows = []
    for fold in development.folds:
        pipeline = build_pipeline(actual)
        with threadpool_limits(limits=1):
            pipeline.fit(development.X.iloc[fold.train_indices], development.y.iloc[fold.train_indices])
            scorer(pipeline, development.X.iloc[fold.train_indices], development.y.iloc[fold.train_indices])
            scorer(pipeline, development.X.iloc[fold.validation_indices], development.y.iloc[fold.validation_indices])
        row = _trial_row(model, 0, selected, fold, scorer)
        row.pop("candidate_id")
        row["configuration_stage"] = stage
        rows.append(row)
    return pd.DataFrame(rows)


def baseline_diagnostics(development: DevelopmentData) -> pd.DataFrame:
    rows = []
    for fold in development.folds:
        train = development.X.iloc[fold.train_indices]
        validation = development.X.iloc[fold.validation_indices]
        preprocessor = make_preprocessor().fit(train)
        metrics, predictions = {}, {}
        for label, X, indices in (("train", train, fold.train_indices), ("validation", validation, fold.validation_indices)):
            metrics[label], predictions[label] = evaluate_predictions(development.y.iloc[indices], preprocessor.transform(X).xg_avg5.to_numpy())
        row = dict(model="Historical Baseline", fold=fold.fold, train_seasons=";".join(map(str, fold.spec.train_seasons)),
            validation_season=fold.spec.validation_season, train_samples=len(train), validation_samples=len(validation),
            hyperparameters="null", train_mae=metrics["train"]["mae"], train_rmse=metrics["train"]["rmse"],
            validation_mae=metrics["validation"]["mae"], validation_rmse=metrics["validation"]["rmse"],
            mae_gap=metrics["validation"]["mae"] - metrics["train"]["mae"],
            rmse_gap=metrics["validation"]["rmse"] - metrics["train"]["rmse"],
            train_negative_predictions=metrics["train"]["negative_predictions"],
            validation_negative_predictions=metrics["validation"]["negative_predictions"],
            train_prediction_sha256=_prediction_hash(predictions["train"]), validation_prediction_sha256=_prediction_hash(predictions["validation"]),
            execution_status="success")
        rows.extend([dict(row, configuration_stage="before"), dict(row, configuration_stage="after")])
    return pd.DataFrame(rows)


def assert_same_evaluation(first: pd.DataFrame, second: pd.DataFrame) -> None:
    columns = ["model", "fold", "train_mae", "train_rmse", "validation_mae", "validation_rmse",
               "train_prediction_sha256", "validation_prediction_sha256"]
    left = first.loc[:, columns].sort_values(["model", "fold"]).reset_index(drop=True)
    right = second.loc[:, columns].sort_values(["model", "fold"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right, check_exact=True)


def build_comparison(diagnostics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model in MODEL_NAMES:
        row = dict(model=model, tuned=model != "Historical Baseline")
        for stage in ("before", "after"):
            group = diagnostics.loc[diagnostics.model.eq(model) & diagnostics.configuration_stage.eq(stage)]
            _require(len(group) == 3 and group.fold.nunique() == 3, f"{model}/{stage}: thiếu diagnostics ba fold.")
            for subset in ("train", "validation"):
                for metric in ("mae", "rmse"):
                    row[f"mean_{subset}_{metric}_{stage}"] = float(group[f"{subset}_{metric}"].mean())
                    row[f"std_{subset}_{metric}_{stage}"] = float(group[f"{subset}_{metric}"].std(ddof=STD_DDOF))
            for metric in ("mae", "rmse"):
                row[f"mean_{metric}_gap_{stage}"] = float(group[f"{metric}_gap"].mean())
        row["mae_improvement"] = row["mean_validation_mae_before"] - row["mean_validation_mae_after"]
        row["mae_improvement_percent"] = 100 * row["mae_improvement"] / row["mean_validation_mae_before"]
        rows.append(row)
    result = pd.DataFrame(rows)
    for stage in ("before", "after"):
        result[f"rank_{stage}"] = result[f"mean_validation_mae_{stage}"].rank(method="min").astype(int)
    return result.sort_values(["mean_validation_mae_after", "mean_validation_rmse_after", "model"], kind="stable").reset_index(drop=True)


def protected_files() -> tuple[Path, ...]:
    paths = [p for folder in ("data", "scripts", "tests", "Phases", "outputs/training")
             for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and not p.name.startswith("~$") and p not in (Path(__file__).resolve(), ROOT / "tests/test_tuning.py", REPORT_PATH)]
    return tuple(sorted(paths))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_outputs(trials: pd.DataFrame, summary: pd.DataFrame, best: dict, diagnostics: pd.DataFrame) -> None:
    _require(len(trials) == sum(BUDGETS.values()) * len(DEFAULT_FOLDS), "Cần đúng 237 dòng tuning_trials.")
    _require(set(trials.model) == set(BUDGETS) and not trials.duplicated(["model", "candidate_id", "fold"]).any(), "Sai hoặc trùng candidate-fold.")
    _require(trials.execution_status.eq("success").all(), "Có trial không thành công.")
    _require(not set(trials.validation_season) & RESERVED_SEASONS, "Trials chứa Final Test.")
    _require(set(best["models"]) == set(BUDGETS), "best_params chỉ được chứa bốn regression algorithms.")
    for model, budget in BUDGETS.items():
        group = trials.loc[trials.model.eq(model)]
        _require(group.candidate_id.nunique() == budget and group.hyperparameters.nunique() == budget
                 and group.groupby("candidate_id").size().eq(3).all(), f"{model}: thiếu hoặc trùng cấu hình.")
        for number, params in enumerate(candidate_configurations(model), 1):
            candidate = group.loc[group.candidate_id.eq(number)]
            _require(candidate.hyperparameters.eq(canonical_params(params)).all(), "Cấu hình/id khác mẫu candidate đã cố định.")
            for fold_number, spec in enumerate(DEFAULT_FOLDS, 1):
                row = candidate.loc[candidate.fold.eq(fold_number)]
                _require(len(row) == 1 and row.train_seasons.eq(";".join(map(str, spec.train_seasons))).all()
                         and row.validation_season.eq(spec.validation_season).all(), "Trials có ranh giới mùa khác cấu hình cố định.")
        selected = select_best_candidate(group)
        metadata = best["models"][model]
        _require(int(selected["candidate_id"]) == metadata["candidate_id"]
                 and json.loads(selected["hyperparameters"]) == metadata["best_params"], "best_params không khớp luật chọn.")
        for metric in ("mae", "rmse"):
            _require(metadata[f"mean_validation_{metric}"] == selected[f"mean_validation_{metric}"], "Score chọn không khớp metadata.")
        chosen = group.loc[group.candidate_id.eq(selected["candidate_id"])]
        after = diagnostics.loc[diagnostics.model.eq(model) & diagnostics.configuration_stage.eq("after")]
        assert_same_evaluation(chosen, after)
    _require(len(diagnostics) == 30 and not diagnostics.duplicated(["model", "configuration_stage", "fold"]).any(), "Cần 30 dòng diagnostics gồm benchmark cố định.")
    for table in (trials, summary, diagnostics):
        _require(np.isfinite(table.select_dtypes(include="number").to_numpy()).all(), "Đầu ra có số không hữu hạn.")
    pd.testing.assert_frame_equal(build_comparison(diagnostics), summary, check_exact=True)
    baseline = summary.loc[summary.model.eq("Historical Baseline")].iloc[0]
    _require(baseline.mae_improvement == 0 and baseline.mae_improvement_percent == 0, "Baseline đã thay đổi.")


def export_outputs(trials: pd.DataFrame, summary: pd.DataFrame, best: dict, diagnostics: pd.DataFrame,
                   output_dir: Path = OUTPUT_DIR) -> dict:
    validate_outputs(trials, summary, best, diagnostics)
    output_dir.mkdir(parents=True, exist_ok=True)
    staged, digests = [], {}
    try:
        for name, frame in (("tuning_trials.csv", trials), ("tuning_summary.csv", summary),
                            ("overfitting_diagnostics.csv", diagnostics)):
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".tuning-", suffix=".tmp", delete=False) as handle:
                path = Path(handle.name)
            staged.append((path, output_dir / name))
            path.write_bytes(csv_bytes(frame))
            loaded = pd.read_csv(path, keep_default_na=False)
            pd.testing.assert_frame_equal(frame, loaded, check_dtype=False, check_exact=False, rtol=1e-14, atol=1e-14)
            digests[name] = sha256(path)
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".tuning-", suffix=".tmp", delete=False) as handle:
            path = Path(handle.name)
        staged.append((path, output_dir / "best_params.json"))
        path.write_text(json.dumps(json_safe(best), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        _require(json.loads(path.read_text(encoding="utf-8")) == json_safe(best), "JSON đọc lại không khớp.")
        digests["best_params.json"] = sha256(path)
        for source, target in staged:
            os.replace(source, target)
    finally:
        for source, _ in staged:
            source.unlink(missing_ok=True)
    return digests


def _record(state: dict, name: str, condition: bool, evidence: str) -> None:
    state["checks"].append((name, bool(condition), evidence))
    _require(bool(condition), f"{name}: {evidence}")


def run_tuning(state: dict) -> None:
    phase4_folds, phase4_summary = load_phase4_reference()
    state["phase4_summary"] = phase4_summary
    _record(state, "Kiểm chứng tham chiếu Phase 4", True, "Đọc 15 kết quả thật và tính lại summary; khớp CSV Phase 4 với atol=1e-12, rtol=0.")
    full = load_dataset()
    development = prepare_development(full)
    state.update(dataset_shape=full.shape, source_matches=int(full.match_id.nunique()),
                 development_rows=len(development.X), folds=development.folds)
    _record(state, "Development và Final Test", not set(development.frame.season) & RESERVED_SEASONS,
            f"{len(development.frame)} dòng mùa 2019–2023; chỉ ba fold cũ, mùa 2024/2025 không tham gia fit/score.")
    _record(state, "Thứ tự và schema", development.X.index.equals(development.y.index)
            and development.X.index.equals(development.frame.index)
            and list(development.X.columns) == list(FEATURES) and "xg" not in development.X,
            "X/y/metadata giữ cùng thứ tự; đúng 13 features và target tách riêng.")
    templates = model_templates()
    state["initial_parameters"] = {name: json_safe(model.get_params(deep=False)) for name, model in templates.items()}
    state["initial_diagnostics"] = []
    print("Chẩn đoán trước tuning: bốn cấu hình Phase 4 trên ba fold...", flush=True)
    baseline = baseline_diagnostics(development)
    for model, template in templates.items():
        before = diagnose_configuration(model, template, {}, development, "before")
        state["initial_diagnostics"].append(before)
    before_all = pd.concat([baseline.loc[baseline.configuration_stage.eq("before")], *state["initial_diagnostics"]], ignore_index=True)
    reference = phase4_folds.set_index(["model", "fold"])
    for row in before_all.itertuples(index=False):
        actual = reference.loc[(row.model, row.fold)]
        _record(state, f"Tham chiếu {row.model}/fold {row.fold}",
                np.isclose(row.validation_mae, actual.mae, rtol=0, atol=REFERENCE_TOLERANCE)
                and np.isclose(row.validation_rmse, actual.rmse, rtol=0, atol=REFERENCE_TOLERANCE),
                "Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping.")
    state["search_trials"] = []
    state["best_models"] = {}
    state["selected_diagnostics"] = []
    for model, template in templates.items():
        configurations = candidate_configurations(model)
        _record(state, f"{model}: mẫu candidate tái lập", configurations == candidate_configurations(model)
                and len({canonical_params(p) for p in configurations}) == BUDGETS[model],
                f"{BUDGETS[model]} cấu hình duy nhất, seed={SEARCH_SEED}; không đổi ngân sách.")
        scorer = AuditedClippedScorer(development, model)
        scorer.progress = True
        search = make_search(model, template, development, scorer)
        state["current_search"] = dict(model=model, scorer=scorer)
        _record(state, f"{model}: search theo thời gian", search.refit is False and len(search.cv) == 3
                and all(np.array_equal(train, fold.train_indices) and np.array_equal(val, fold.validation_indices)
                        for (train, val), fold in zip(search.cv, development.folds)),
                "Truyền rõ indices iloc khớp X/y; Pipeline chứa preprocessing, refit=False, error_score=raise, n_jobs=1.")
        print(f"Tìm kiếm {model}: {BUDGETS[model]} cấu hình × 3 fold...", flush=True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with threadpool_limits(limits=1):
                search.fit(development.X, development.y)
        state["warnings"].extend(f"{model}: {w.message}" for w in caught)
        trials = search_result_rows(model, search, scorer)
        state["search_trials"].append(trials)
        _record(state, f"{model}: search và audit hoàn tất", len(trials) == BUDGETS[model] * 3,
                f"{len(trials)} candidate-fold; median Train-only, 13 features, ô hợp lệ giữ nguyên, metric hữu hạn; ledger kiểm tra cả Train và Validation.")
        selected = select_best_candidate(trials)
        params = json.loads(selected["hyperparameters"])
        state["best_models"][model] = dict(candidate_id=int(selected["candidate_id"]), best_params=params,
            mean_validation_mae=float(selected["mean_validation_mae"]), mean_validation_rmse=float(selected["mean_validation_rmse"]),
            std_validation_mae=float(selected["std_validation_mae"]), std_validation_rmse=float(selected["std_validation_rmse"]),
            search_seed=SEARCH_SEED, candidate_count=BUDGETS[model],
            fixed_parameters={k: json_safe(v) for k, v in template.get_params(deep=False).items() if k not in SEARCH_SPACES[model]})
        after = diagnose_configuration(model, template, params, development, "after")
        selected_trials = trials.loc[trials.candidate_id.eq(selected["candidate_id"])]
        assert_same_evaluation(selected_trials, after)
        _record(state, f"{model}: fit mới sau chọn", True, "Train/Validation metrics và hash mọi dự báo khớp candidate được chọn trong search.")
        repeated = diagnose_configuration(model, template, params, development, "reproducibility")
        assert_same_evaluation(after, repeated)
        _record(state, f"{model}: tái lập cấu hình chọn", True, "Fit lại bằng các Pipeline mới; metric và hash dự báo Train/Validation giống chính xác ở cả ba fold.")
        state["selected_diagnostics"].append(after)
        print(f"Hoàn tất {model}: candidate {selected['candidate_id']}, Mean Validation MAE={selected['mean_validation_mae']:.6f}", flush=True)
    trials = pd.concat(state["search_trials"], ignore_index=True)
    diagnostics = pd.concat([baseline, *state["initial_diagnostics"], *state["selected_diagnostics"]], ignore_index=True)
    diagnostics["_model_order"] = diagnostics.model.map({name: i for i, name in enumerate(MODEL_NAMES)})
    diagnostics["_stage_order"] = diagnostics.configuration_stage.map({"before": 0, "after": 1})
    diagnostics = diagnostics.sort_values(["_model_order", "_stage_order", "fold"], kind="stable").drop(columns=["_model_order", "_stage_order"]).reset_index(drop=True)
    summary = build_comparison(diagnostics)
    import xgboost
    best = dict(schema_version=1, search_seed=SEARCH_SEED,
        dataset_sha256=sha256(ROOT / "data/laliga_processed_normalized.csv"),
        development_seasons=sorted(development.frame.season.unique().tolist()), excluded_seasons=sorted(RESERVED_SEASONS),
        features=list(FEATURES), target="xg", pipeline=["preprocessing", "model"],
        scoring=dict(primary="clipped_mae", secondary="clipped_rmse", minimum_prediction=0,
                     fold_weighting="equal", std_ddof=STD_DDOF, refit=False,
                     mae_tie_atol=TIE_TOLERANCE, rmse_tie_atol=TIE_TOLERANCE, tie_rtol=0,
                     final_tie_break="canonical_hyperparameters_then_candidate_id"),
        folds=[dict(fold=f.fold, train_seasons=list(f.spec.train_seasons), validation_season=f.spec.validation_season,
                    train_samples=len(f.train_indices), validation_samples=len(f.validation_indices),
                    train_start=f.train_start, train_end=f.train_end, validation_start=f.validation_start, validation_end=f.validation_end)
               for f in development.folds],
        search_spaces=SEARCH_SPACES, candidate_budgets=BUDGETS,
        versions=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__,
                      scipy=scipy.__version__, sklearn=sklearn.__version__, xgboost=xgboost.__version__, threadpoolctl=threadpoolctl.__version__),
        models=state["best_models"])
    state.update(trials=trials, diagnostics=diagnostics, summary=summary, best=best)
    validate_outputs(trials, summary, best, diagnostics)
    _record(state, "237 trial và bốn thuật toán", len(trials) == 237, "79 cấu hình × 3 fold; đủ 4 Linear Regression và 25 cấu hình cho mỗi thuật toán còn lại.")
    baseline_pair = diagnostics.loc[diagnostics.model.eq("Historical Baseline")]
    assert_same_evaluation(baseline_pair.loc[baseline_pair.configuration_stage.eq("before")],
                           baseline_pair.loc[baseline_pair.configuration_stage.eq("after")])
    _record(state, "Benchmark cố định", True, "Baseline không tuning, không có best_params; mọi dự báo trước/sau giống nhau và khớp Phase 4.")
    _record(state, "Không thay file Phase 4", all(sha256(path) == digest for path, digest in state["protected"].items()),
            f"SHA-256 của {len(state['protected'])} file hiện có không đổi.")
    state["output_hashes"] = export_outputs(trials, summary, best, diagnostics)
    _record(state, "Đọc lại đầu ra", True, "Ba CSV và một JSON đã đọc lại, kiểm tra schema và giá trị trước khi thay thế file đích; file tạm kế thừa quyền thư mục đích.")


def execute_tests(state: dict) -> None:
    buffer = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
    state["tests"] = dict(run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                          skipped=len(result.skipped), log=buffer.getvalue())
    _record(state, "Kiểm thử Phase 4 và Phase 5", result.wasSuccessful(),
            f"Đã chạy {result.testsRun} tests; failures={len(result.failures)}, errors={len(result.errors)}, skipped={len(result.skipped)}.")


def build_report(state: dict, error: str | None = None) -> str:
    lines = ["# Tối ưu Regression bằng Hyperparameter Tuning theo thời gian", "",
        "## 1. Mục tiêu và phạm vi Phase 5", "",
        "Phân tích Training Error/Validation Error trước và sau tuning của Linear Regression, Decision Tree, Random Forest và XGBoost; giữ Historical Baseline cố định. Không thêm features, không dùng Final Test, không huấn luyện trên toàn bộ development để tạo Final Model và không lưu model.", "",
        "## 2. Khảo sát repository và kết quả Phase 4", "",
        "Đã đọc CSV chuẩn hóa, module chuẩn bị features, cross_validation.py, train_models.py, requirements.txt, hai CSV kết quả Phase 4, tests/test_training.py và báo cáo Phase 4. Không thay đổi các API hoặc file cũ. Các version đang cài khớp requirements của Phase 4.", ""]
    if "phase4_summary" in state:
        lines += _table(state["phase4_summary"])
        lines += ["", f"Bảng trên được đọc từ outputs/training/cv_summary.csv và đối chiếu tính lại từ từng fold. Validation metrics của cấu hình trước tuning cũng được fit/predict lại và đối chiếu từng model/fold với atol={REFERENCE_TOLERANCE}, rtol=0; ngưỡng này chỉ bao phủ sai số số thực/parsing CSV, không che thay đổi thực nghiệm."]
    lines += ["", "## 3. Tổ chức file", "", "```text", "scripts/training/tune_models.py", "tests/test_tuning.py",
        "outputs/tuning/tuning_trials.csv", "outputs/tuning/tuning_summary.csv", "outputs/tuning/best_params.json",
        "outputs/tuning/overfitting_diagnostics.csv", f"Phases/{REPORT_PATH.name}", "```", "",
        "Chỉ bổ sung module tuning, tests và đầu ra Phase 5. Tái sử dụng model_templates(), evaluate_predictions(), csv_bytes() và định dạng bảng từ train_models.py; dùng make_season_folds(), load_dataset(), prepare_features(), make_preprocessor() hiện có. Không di chuyển hoặc refactor code Phase 4; không ghi đè hai CSV hoặc báo cáo Phase 4.", "",
        "## 4. Dataset, features và target", ""]
    if "dataset_shape" in state:
        lines += [f"Nguồn có {state['dataset_shape'][0]} dòng × {state['dataset_shape'][1]} cột, {state['source_matches']} trận. Development chỉ có **{state['development_rows']} dòng**, season 2019–2023. Các mùa 2024 và 2025 chỉ được đọc khi kiểm tra schema/toàn vẹn CSV nguồn, sau đó bị loại trước prepare_features và search.", ""]
    lines += ["| Thứ tự | Feature |", "|---|---|"]
    lines += [f"| {i} | `{c}` |" for i, c in enumerate(FEATURES, 1)]
    lines += ["", "Target y=xg được giữ riêng. Không đưa metadata hoặc gf, ga, sh, sot, xga, xg hiện trận vào X. Không thay đổi dataset hoặc công thức rolling.", "",
        "## 5. Fold và Median Imputation", "",
        "Giữ ba fold Phase 4, chọn bằng season thay vì thứ tự CSV. Splitter kiểm tra ngày Train trước Validation, không chung match_id hoặc bản ghi, hai phía trận ở cùng tập. Indices iloc được tạo trên chính DataFrame development giữ cùng thứ tự X/y; tuyệt đối không tái dùng indices của CSV đầy đủ cho một X đã lọc.", ""]
    if "folds" in state:
        lines += _table(pd.DataFrame([dict(fold=f.fold, train_seasons=";".join(map(str, f.spec.train_seasons)),
            validation_season=f.spec.validation_season, train_samples=len(f.train_indices), validation_samples=len(f.validation_indices),
            train_start=f.train_start, train_end=f.train_end, validation_start=f.validation_start, validation_end=f.validation_end)
            for f in state["folds"]]))
    lines += ["", "prepare_features() chỉ khôi phục prior đã xác minh về NaN trong development, không học thống kê. Mỗi candidate/fold clone Pipeline([('preprocessing', make_preprocessor()), ('model', estimator)]). SimpleImputer vẫn được fit mới trên Train bên trong Pipeline. Scorer kiểm tra n_samples_fit_, tám median từ Train, đúng 13 tên cột, index, số hữu hạn và mọi ô hợp lệ sau transform.", "",
        "Các median tính riêng bằng Pandas trên từng X_train chỉ dùng làm giá trị đối chiếu audit; không được đưa vào imputer hoặc dùng thay bước fit. Validation, season 2024/2025 và target không tham gia học median. Không xuất dataset impute toàn cục.", "",
        "Dự báo tuần tự trước từng trận: có thể dùng kết quả những trận đã kết thúc trước đó trong cùng mùa Validation. Không dùng kết quả hiện trận/future; không giả định dự báo đồng thời cả mùa từ ngày đầu mùa. Giữ nguyên Feature Engineering đã kiểm chứng, không tính lại rolling.", "",
        "## 6. Phương pháp search và ngân sách", "",
        "Linear Regression dùng GridSearchCV với đúng bốn tổ hợp fit_intercept/positive. Các thuật toán còn lại dùng RandomizedSearchCV với seed 42, 25 cấu hình duy nhất lấy không hoàn lại từ không gian danh sách hữu hạn. Tạo lại ParameterGrid/ParameterSampler và đối chiếu từng cấu hình cùng id với cv_results_.", "",
        "Tất cả search đều truyền rõ ba fold thời gian, return_train_score=True, refit=False, error_score='raise', n_jobs=1, pre_dispatch=1. Không dùng CV mặc định, early stopping, eval_set hoặc tuning thích nghi theo kết quả. RF/XGBoost và BLAS/OpenMP giới hạn một luồng như Phase 4.", "",
        "### Không gian tham số cố định trước khi chạy", "", "```json",
        json.dumps(SEARCH_SPACES, ensure_ascii=False, indent=2, sort_keys=True), "```", "",
        "| Thuật toán | Kích thước không gian | Cấu hình được đánh giá | Lượt fit search |", "|---|---:|---:|---:|"]
    for model, budget in BUDGETS.items():
        done = next((len(t) // 3 for t in state.get("search_trials", []) if t.model.iloc[0] == model), 0)
        lines.append(f"| {model} | {len(ParameterGrid(SEARCH_SPACES[model]))} | {done}/{budget} | {done * 3} |")
    if "trials" in state:
        lines += ["", "Đã hoàn tất **79 cấu hình × 3 fold = 237 lượt fit search**. Ngoài search: 12 lượt cấu hình ban đầu, 12 lượt chẩn đoán cấu hình chọn và 12 lượt kiểm chứng lại cấu hình chọn; tổng cộng **273 lượt fit Regression trong thí nghiệm**, chưa kể các fits của unit tests. Baseline không fit Regression, chỉ có ba lần fit preprocessing theo fold. Không refit model trên toàn development."]
    lines += ["", "positive=True trong LinearRegression ràng buộc các hệ số không âm; có thể không phù hợp khi một số features có quan hệ âm với target. Đây không phải bước clipping dự báo, và không có Ridge/Lasso trong search. Tham khảo [LinearRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LinearRegression.html).", "",
        "### Scoring và luật chọn", "",
        f"AuditedClippedScorer gọi evaluate_predictions() Phase 4, tức clipping max(0,prediction) trước MAE và RMSE. Search nhận score âm để tối đa hóa; khi xuất chuyển dấu về lỗi dương. Chọn Mean Validation MAE thấp nhất; các candidate cách minimum không quá {TIE_TOLERANCE} (rtol=0) được xét hòa MAE, sau đó dùng RMSE với cùng tolerance. Nếu vẫn hòa, chọn chuỗi JSON tham số theo thứ tự từ điển rồi candidate_id tăng dần. refit=False nên tự chọn từ cv_results_, không phụ thuộc best_params_. Trung bình các fold có trọng số bằng nhau; standard deviation dùng ddof={STD_DDOF}.", "",
        "## 7. Chẩn đoán trước và sau tuning", ""]
    if "diagnostics" in state:
        columns = ["model", "configuration_stage", "fold", "train_mae", "validation_mae", "mae_gap", "train_rmse", "validation_rmse", "rmse_gap"]
        lines += _table(state["diagnostics"].loc[:, columns])
        lines += ["", "30 dòng gồm 24 chẩn đoán Regression và 6 dòng benchmark trước/sau giống nhau. Mỗi bộ cấu hình trước/sau được fit bằng estimator và preprocessing mới theo từng fold; không lấy lại estimator đã fit trong search."]
    elif state.get("initial_diagnostics"):
        lines += _table(pd.concat(state["initial_diagnostics"], ignore_index=True).loc[:, ["model", "fold", "train_mae", "validation_mae", "train_rmse", "validation_rmse"]])
    lines += ["", "## 8. Cấu hình tốt nhất trong không gian đã xét", ""]
    if state.get("best_models"):
        lines += _table(pd.DataFrame([dict(model=name, candidate_id=meta["candidate_id"],
            best_params=canonical_params(meta["best_params"]), mean_validation_mae=meta["mean_validation_mae"],
            mean_validation_rmse=meta["mean_validation_rmse"]) for name, meta in state["best_models"].items()]))
        lines += ["", "Không có best_params cho Historical Baseline. JSON lưu thêm seed, không gian, budget, folds, phiên bản, source SHA-256, feature order, quy tắc scoring/chọn và các tham số giữ cố định. Marker missing=nan của XGBoost được mô tả bằng chuỗi 'nan' trong metadata để JSON hợp lệ; không có metric NaN."]
    lines += ["", "## 9. So sánh trước/sau và độ ổn định", ""]
    if "summary" in state:
        summary = state["summary"]
        for metric in ("mae", "rmse"):
            lines += [f"### Validation {metric.upper()}", ""]
            columns = ["model", f"mean_validation_{metric}_before", f"std_validation_{metric}_before",
                       f"mean_validation_{metric}_after", f"std_validation_{metric}_after"]
            if metric == "mae":
                columns += ["mae_improvement", "mae_improvement_percent", "rank_before", "rank_after"]
            lines += _table(summary.loc[:, columns]) + [""]
        lines += ["### Overfitting, Underfitting và khác biệt mùa", ""]
        for model in BUDGETS:
            row = summary.loc[summary.model.eq(model)].iloc[0]
            data = state["diagnostics"].loc[state["diagnostics"].model.eq(model)]
            initial = data.loc[data.configuration_stage.eq("before")]
            after = data.loc[data.configuration_stage.eq("after")]
            lines += [f"**{model}:** Mean Train MAE {row.mean_train_mae_before:.6f} → {row.mean_train_mae_after:.6f}; Mean Validation MAE {row.mean_validation_mae_before:.6f} → {row.mean_validation_mae_after:.6f}. Mean MAE gap (Validation−Train) {row.mean_mae_gap_before:.6f} → {row.mean_mae_gap_after:.6f}; RMSE gap {row.mean_rmse_gap_before:.6f} → {row.mean_rmse_gap_after:.6f}. Validation MAE sau tuning trải từ {after.validation_mae.min():.6f} đến {after.validation_mae.max():.6f}, std={row.std_validation_mae_after:.6f}. Cải thiện MAE trung bình {row.mae_improvement:.6f} ({row.mae_improvement_percent:.2f}%)."]
            if (initial.mae_gap > 0).all() and row.mean_train_mae_before < row.mean_validation_mae_before * 0.5:
                lines += ["Training Error thấp hơn rõ rệt trong cả ba fold và Validation Error cao hơn, gợi ý cấu hình ban đầu có xu hướng quá khớp. Đây là dấu hiệu từ nhiều fold, không phải kết luận chỉ từ một metric."]
            if row.mean_validation_mae_after < row.mean_validation_mae_before and row.mean_mae_gap_after < row.mean_mae_gap_before:
                lines += ["Validation MAE và gap cùng giảm sau tuning, phù hợp với việc giảm mức quá khớp ở cấu hình được chọn; chưa chứng minh nguyên nhân duy nhất của thay đổi."]
            elif abs(row.mae_improvement) <= TIE_TOLERANCE:
                lines += ["Không có cải thiện MAE đáng kể trong không gian đã xét; không coi tuning là bắt buộc phải tốt hơn cấu hình ban đầu."]
            elif row.mae_improvement < 0:
                lines += ["Cấu hình được chọn có MAE kém hơn cấu hình ban đầu; báo cáo giữ nguyên kết quả, không mở rộng không gian search sau khi xem score."]
            lines += [""]
        lines += ["Training metrics là in-sample diagnostics, không phải ước lượng tổng quát hóa độc lập. Train và Validation cùng cao có thể liên quan giới hạn biểu diễn, nhiễu xG hoặc khác biệt phân phối mùa; chưa đủ để kết luận underfitting. Gap nhỏ hoặc âm ở một mùa không chứng minh hết overfitting. So sánh RMSE, độ lệch chuẩn và từng mùa cùng MAE; không thêm kiểm định thống kê hoặc khoảng tin cậy từ ba fold.", ""]
    lines += ["## 10. Toàn bộ candidate thực tế", "",
        "tuning_trials.csv lưu từng candidate/fold, cấu hình JSON, mùa, số dòng, Train/Validation MAE/RMSE, gaps, số dự báo âm, hash dự báo và trạng thái. Không lưu mảng dự báo hoặc model. Bảng dưới tóm tắt tất cả cấu hình đã hoàn tất; bản chi tiết từng fold nằm trong CSV.", ""]
    if state.get("search_trials"):
        all_trials = pd.concat(state["search_trials"], ignore_index=True)
        lines += _table(candidate_summary(all_trials))
    lines += ["", "## 11. Model-selection bias và giới hạn phương pháp", "",
        "Ba fold này đồng thời dùng chọn hyperparameters và mô tả cấu hình được chọn, nên score tốt nhất có thể lạc quan do quá trình lựa chọn. Đây là kết quả development, không phải ước lượng hiệu năng độc lập sau chọn hoặc bằng chứng chắc chắn cho dữ liệu tương lai. Fit lại để kiểm chứng tái lập vẫn dùng chính folds cũ và không tạo một phép đánh giá độc lập. Final Test 2024/2025 được giữ nguyên cho giai đoạn sau. Không thực hiện Nested Cross-Validation trong tác vụ này. Xem [giải thích selection bias của scikit-learn](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html).", "",
        "Ngân sách 25 cấu hình ngẫu nhiên mỗi thuật toán cây không bảo đảm tối ưu toàn bộ không gian. Không thay fold, budget, features hoặc thêm model sau khi xem kết quả. Hai bản ghi cùng trận có tương quan; không báo độ tin cậy thống kê quá mức.", "",
        "## 12. Kiểm chứng đã thực thi và tái lập", ""]
    lines += _table(pd.DataFrame([(name, "Đạt" if passed else "Không đạt", detail) for name, passed, detail in state["checks"]],
                                columns=["Kiểm chứng", "Kết quả", "Bằng chứng"]))
    if "tests" in state:
        tests = state["tests"]
        lines += ["", f"Unit tests thực tế: {tests['run']} đã chạy; failures={tests['failures']}, errors={tests['errors']}, skipped={tests['skipped']}.", "",
                  "```text", tests["log"].strip(), "```", "",
                  "Tests mới kiểm chứng budget/mẫu seed, đúng bốn cấu hình Linear Regression, alignment của development, clone Pipeline, fit mới đúng Train trong search, refit=False, score âm/clipping, luật hòa, dấu vết dự báo, schema/JSON và bảo toàn quyền ACL khi xuất. Số liệu nhân tạo trong tests chỉ phục vụ fixtures, không được dùng làm kết quả Phase 5."]
    lines += ["", "Phạm vi tái lập: tạo lại đủ mẫu 79 candidate và so khớp với search; với từng cấu hình chọn, fit mới ba fold để kiểm tra khớp search, sau đó chạy lại thêm ba fold để đối chiếu metric và hash mọi dự báo Train/Validation chính xác. Không chạy lại toàn bộ search lần hai và không tuyên bố đã xác minh từng candidate qua hai lần full search.", ""]
    if "output_hashes" in state:
        lines += _table(pd.DataFrame([dict(file=name, sha256=value) for name, value in state["output_hashes"].items()]))
        lines += ["", "Các file CSV được ghi 17 chữ số có nghĩa và đọc lại với atol/rtol=1e-14 để bao phủ sai số parser; JSON được đối chiếu đầy đủ. Trước khi ghi, kiểm tra lựa chọn best từ trials, summary từ diagnostics, đủ 237 dòng/79 cấu hình/30 diagnostics/5 dòng summary và không có duplicate ngoài ba folds chủ đích."]
    lines += ["", "## 13. Môi trường và cách chạy", "",
        f"Python {platform.python_version()}, NumPy {np.__version__}, Pandas {pd.__version__}, SciPy {scipy.__version__}, scikit-learn {sklearn.__version__}, threadpoolctl {threadpoolctl.__version__}. XGBoost dùng version cài sẵn trong .venv: {state.get('xgboost_version', 'chưa xác nhận')}. Không thêm dependency; tái sử dụng scripts/training/requirements.txt.", "",
        "Lệnh đã thực thi:", "", "```powershell", ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p test_tuning.py -v",
        ".\\.venv\\Scripts\\python.exe -m scripts.training.tune_models", "```", "",
        "Lệnh tuning tự chạy lại cả tests Phase 4/5 trước search, sau đó thực hiện full budget và cập nhật đúng bốn output cùng báo cáo này. Có thể chạy python -m scripts.training.tune_models nếu interpreter hiện hành đã có đủ dependency. Không cần quyền Administrator; file tạm nằm trực tiếp cạnh output để kế thừa ACL.", ""]
    if "elapsed_seconds" in state:
        lines += [f"Thời gian thực thi của lệnh tuning này (gồm tests và diagnostics): {state['elapsed_seconds']:.2f} giây.", ""]
    lines += ["## 14. Bảo toàn file, thay đổi và vấn đề", "",
        "Tạo scripts/training/tune_models.py, tests/test_tuning.py, bốn file outputs/tuning/ và duy nhất báo cáo Phase 5 này. Không thay preprocessing, training Phase 4, requirements, tests Phase 4, dataset hoặc báo cáo cũ. Không commit/push, không lưu model, không tạo bản sao phiên bản hoặc thư mục không cần thiết.", "",
        "| File có sẵn | SHA-256 trước thực thi | Sau thực thi |", "|---|---|---|"]
    for path, digest in state["protected"].items():
        unchanged = path.exists() and sha256(path) == digest
        lines.append(f"| `{path.relative_to(ROOT).as_posix()}` | `{digest}` | {'Giữ nguyên' if unchanged else 'Không khớp'} |")
    lines += [""]
    if state["warnings"]:
        lines += ["Cảnh báo thực tế trong search:", ""] + [f"- {message}" for message in state["warnings"]]
    else:
        lines += ["Không ghi nhận cảnh báo từ các lệnh search đã hoàn tất."]
    if error:
        lines += ["", "**Tác vụ chưa hoàn tất.**", "", "```text", error, "```", "",
                  "Chỉ những kiểm chứng và candidate ghi ở trên đã được xác nhận. Không giảm ngân sách, thay thuật toán hoặc sửa dữ liệu để bỏ qua lỗi. File đầu ra cũ không bị thay bởi kết quả chưa vượt qua validation."]
        if "current_search" in state:
            current = state["current_search"]
            lines += [f"Search đang xử lý khi có lỗi: {current['model']}; đã ghi nhận {len(current['scorer'].ledger)} lần score của các candidate/fold/tập trong bộ nhớ."]
    else:
        lines += ["Không có lỗi hoặc vấn đề chưa giải quyết chặn hoàn thành Phase 5 trong phạm vi đã nêu."]
    lines += ["", "## 15. Tài liệu API", "",
        "Search lấy mẫu từ danh sách hữu hạn và hỗ trợ multi-metric: [RandomizedSearchCV](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.RandomizedSearchCV.html). Scorer callable trả dictionary metrics theo [hướng dẫn scikit-learn](https://scikit-learn.org/stable/modules/model_evaluation.html#using-multiple-metric-evaluation).", "",
        "## 16. Kết luận và đề xuất Phase 6", ""]
    if error:
        lines += ["Chưa thể xác nhận hoàn thành; xem lỗi và phần thí nghiệm còn thiếu ở trên."]
    else:
        best_row = state["summary"].iloc[0]
        lines += [f"Đã hoàn tất đúng ngân sách search, chẩn đoán trước/sau, kiểm chứng và bốn file kết quả. {best_row.model} có Mean Validation MAE sau tuning thấp nhất trong so sánh development ({best_row.mean_validation_mae_after:.6f}); đây chưa phải Final Model hoặc hiệu năng Final Test.", "",
                  "Phase 6 có thể lập kế hoạch kiểm tra độ bền của cấu hình và đánh giá độc lập theo phạm vi được phê duyệt; chưa thực hiện Ablation Study, Feature Importance, Final Test, serialization hoặc triển khai. Dừng sau Phase 5 và chờ yêu cầu tiếp theo."]
    return "\n".join(lines) + "\n"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    state = dict(protected={path: sha256(path) for path in protected_files()}, checks=[], warnings=[])
    started = time.perf_counter()
    try:
        import xgboost
        state["xgboost_version"] = xgboost.__version__
        print("Kiểm thử hồi quy Phase 4 và kiểm thử tuning...", flush=True)
        execute_tests(state)
        run_tuning(state)
    except Exception as exc:
        state["elapsed_seconds"] = time.perf_counter() - started
        REPORT_PATH.write_text(build_report(state, f"{type(exc).__name__}: {exc}"), encoding="utf-8")
        print(f"Chưa hoàn tất: {exc}", file=sys.stderr)
        return 1
    state["elapsed_seconds"] = time.perf_counter() - started
    REPORT_PATH.write_text(build_report(state), encoding="utf-8")
    print(state["summary"].loc[:, ["model", "mean_validation_mae_before", "mean_validation_mae_after", "mae_improvement_percent", "rank_after"]].to_string(index=False))
    print(f"Hoàn tất: 237 dòng search, {state['tests']['run']} tests đạt, {len(state['checks'])} kiểm chứng workflow.")
    print(f"Báo cáo: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
