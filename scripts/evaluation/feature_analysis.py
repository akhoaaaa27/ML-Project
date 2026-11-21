"""Ablation và Permutation Importance trên các reference đã fit bằng Train."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from threadpoolctl import threadpool_limits

from scripts.prepare_training_features import FEATURES
from scripts.training.train_models import STD_DDOF, evaluate_predictions
from scripts.training.tune_models import canonical_params


FEATURE_GROUPS = {
    "G1": ("is_home",),
    "G2": ("xg_avg5", "xga_avg5"),
    "G3": ("gf_avg5", "ga_avg5"),
    "G4": ("shot_avg5", "sot_avg5"),
    "G5": ("opponent_xg_avg5", "opponent_xga_avg5"),
    "G6": ("matches_seen", "short_history", "opponent_matches_seen", "opponent_short_history"),
}
GROUP_NAMES = {"G1": "Venue", "G2": "Historical xG", "G3": "Historical Goals",
               "G4": "Shooting Performance", "G5": "Opponent Strength", "G6": "History Availability"}
PERMUTATION_REPEATS = 10
RANDOM_SEED = 42


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_groups(groups: dict = FEATURE_GROUPS) -> None:
    flattened = [c for group in groups.values() for c in group]
    require(len(groups) == 6 and len(flattened) == 13 and len(set(flattened)) == 13
            and set(flattened) == set(FEATURES), "Sáu nhóm phải phân hoạch đúng 13 features, không trùng hoặc thiếu.")


def retained_features(group: str) -> list[str]:
    validate_groups()
    require(group in FEATURE_GROUPS, f"Nhóm Ablation không hợp lệ: {group}.")
    return [c for c in FEATURES if c not in FEATURE_GROUPS[group]]


@dataclass
class FittedReference:
    model: str
    fold: Any
    estimator: Any
    X_train: pd.DataFrame
    X_validation: pd.DataFrame
    y_train: pd.Series
    y_validation: pd.Series
    metrics: dict


def run_ablation(reference: FittedReference) -> pd.DataFrame:
    """Giữ preprocessing 13 cột đã fit Train; clone estimator mới cho mỗi nhóm."""
    validate_groups()
    train_snapshot = reference.X_train.copy(deep=True)
    validation_snapshot = reference.X_validation.copy(deep=True)
    parameters = canonical_params(reference.estimator.get_params(deep=False))
    rows = []
    for group in FEATURE_GROUPS:
        columns = retained_features(group)
        train = reference.X_train.loc[:, columns].copy()
        validation = reference.X_validation.loc[:, columns].copy()
        require(train.index.equals(reference.y_train.index) and validation.index.equals(reference.y_validation.index),
                "Ablation không khớp index X/y.")
        model = clone(reference.estimator)
        require(canonical_params(model.get_params(deep=False)) == parameters, "Ablation đã thay hyperparameters.")
        with threadpool_limits(limits=1):
            model.fit(train, reference.y_train)
            metrics, _ = evaluate_predictions(reference.y_validation, model.predict(validation))
        require(model.n_features_in_ == len(columns) and list(model.feature_names_in_) == columns,
                "Estimator Ablation nhận sai số lượng hoặc thứ tự cột.")
        rows.append(dict(model=reference.model, fold=reference.fold.fold,
            train_seasons=";".join(map(str, reference.fold.spec.train_seasons)),
            validation_season=reference.fold.spec.validation_season,
            train_samples=len(train), validation_samples=len(validation), removed_group=group,
            group_name=GROUP_NAMES[group], removed_features=canonical_params({"columns": list(FEATURE_GROUPS[group])}),
            retained_features=canonical_params({"columns": columns}), n_features=len(columns),
            estimator_parameters=parameters, full_mae=reference.metrics["mae"], full_rmse=reference.metrics["rmse"],
            ablated_mae=metrics["mae"], ablated_rmse=metrics["rmse"],
            delta_mae=metrics["mae"] - reference.metrics["mae"],
            delta_rmse=metrics["rmse"] - reference.metrics["rmse"],
            negative_predictions=metrics["negative_predictions"]))
    require(reference.X_train.equals(train_snapshot) and reference.X_validation.equals(validation_snapshot),
            "Ablation đã sửa ma trận full-feature.")
    return pd.DataFrame(rows)


class PermutationScorer:
    """Scorer có ledger để kiểm tra từng perturbation và không đụng target."""

    def __init__(self, reference: FittedReference):
        self.reference = reference
        self.target = reference.y_validation.copy(deep=True)
        self.original = reference.X_validation.copy(deep=True)
        self.metrics = []

    def __call__(self, estimator, X: pd.DataFrame, y: pd.Series) -> float:
        require(estimator is self.reference.estimator, "Permutation dùng estimator khác reference đã fit.")
        require(list(X.columns) == list(FEATURES) and X.index.equals(self.original.index),
                "Permutation sai feature names hoặc index.")
        require(y.equals(self.target), "Permutation đã thay đổi target.")
        changed = [c for c in FEATURES if not X[c].equals(self.original[c])]
        require(len(changed) <= 1, "Permutation đã thay nhiều hơn một cột.")
        if not self.metrics:
            require(not changed, "Lượt score đầu phải là Validation nguyên bản.")
        metrics, _ = evaluate_predictions(y, estimator.predict(X))
        self.metrics.append(metrics)
        return -metrics["mae"]


def run_permutation(reference: FittedReference, n_repeats: int = PERMUTATION_REPEATS,
                    seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Không fit: permute sau preprocessing, lưu mỗi feature/fold/repetition."""
    require(n_repeats > 0, "n_repeats phải dương.")
    before = reference.X_validation.copy(deep=True)
    target = reference.y_validation.copy(deep=True)
    scorer = PermutationScorer(reference)
    with threadpool_limits(limits=1):
        result = permutation_importance(reference.estimator, reference.X_validation,
            reference.y_validation, scoring=scorer, n_repeats=n_repeats,
            random_state=seed, n_jobs=1)
    require(len(scorer.metrics) == 1 + len(FEATURES) * n_repeats, "Sai số prediction evaluations của permutation.")
    original_mae = scorer.metrics[0]["mae"]
    require(np.isclose(original_mae, reference.metrics["mae"], rtol=0, atol=1e-12),
            "MAE gốc của Permutation khác full-feature reference.")
    rows = []
    for position, feature in enumerate(FEATURES):
        for repetition in range(n_repeats):
            metrics = scorer.metrics[1 + position * n_repeats + repetition]
            importance = metrics["mae"] - original_mae
            require(np.isclose(importance, result.importances[position, repetition], rtol=0, atol=1e-15),
                    "Dấu importance không khớp scorer âm.")
            rows.append(dict(model=reference.model, fold=reference.fold.fold,
                validation_season=reference.fold.spec.validation_season, validation_samples=len(target),
                feature=feature, repetition=repetition + 1, random_seed=seed,
                original_mae=original_mae, permuted_mae=metrics["mae"], importance_mae=importance,
                negative_predictions=metrics["negative_predictions"]))
    require(reference.X_validation.equals(before) and reference.y_validation.equals(target),
            "Permutation đã sửa dữ liệu hoặc target nguồn.")
    return pd.DataFrame(rows)


def summarize_ablation(results: pd.DataFrame) -> pd.DataFrame:
    return results.groupby(["model", "removed_group", "group_name"], as_index=False, sort=False).agg(
        folds=("fold", "nunique"), mean_full_mae=("full_mae", "mean"), mean_ablated_mae=("ablated_mae", "mean"),
        mean_full_rmse=("full_rmse", "mean"), mean_ablated_rmse=("ablated_rmse", "mean"),
        mean_delta_mae=("delta_mae", "mean"), std_delta_mae=("delta_mae", lambda x: x.std(ddof=STD_DDOF)),
        mean_delta_rmse=("delta_rmse", "mean"), std_delta_rmse=("delta_rmse", lambda x: x.std(ddof=STD_DDOF)),
        positive_delta_folds=("delta_mae", lambda x: int(x.gt(0).sum())))


def summarize_permutation(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    by_fold = results.groupby(["model", "fold", "validation_season", "feature"], as_index=False, sort=False).agg(
        repetitions=("repetition", "size"), original_mae=("original_mae", "first"),
        mean_importance_mae=("importance_mae", "mean"),
        std_repetitions=("importance_mae", lambda x: x.std(ddof=STD_DDOF)))
    summary = by_fold.groupby(["model", "feature"], as_index=False, sort=False).agg(
        folds=("fold", "nunique"), mean_importance_mae=("mean_importance_mae", "mean"),
        std_between_folds=("mean_importance_mae", lambda x: x.std(ddof=STD_DDOF)),
        mean_std_within_fold=("std_repetitions", "mean"),
        positive_importance_folds=("mean_importance_mae", lambda x: int(x.gt(0).sum())))
    return by_fold, summary
