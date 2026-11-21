"""Paired Bootstrap theo trận; giữ hai phía và cùng mẫu cho mọi so sánh."""

from __future__ import annotations

import hashlib
import numpy as np
import pandas as pd

from scripts.training.train_models import MODEL_NAMES
from .feature_analysis import require


def match_losses(predictions: pd.DataFrame) -> pd.DataFrame:
    require(not predictions.duplicated(["model", "match_id", "is_home"]).any(), "Bootstrap có dự báo trùng.")
    grouped = predictions.groupby(["match_id", "model"])
    require(grouped.size().eq(2).all() and grouped.is_home.nunique().eq(2).all(), "Bootstrap phải giữ đủ Home/Away của mỗi trận.")
    require(predictions.is_home.isin([0, 1]).all(), "Sai mã Home/Away.")
    losses = grouped.absolute_error.mean().unstack("model").loc[:, list(MODEL_NAMES)].sort_index()
    require(not losses.isna().any().any(), "Thiếu model trên cùng tập trận.")
    return losses


def paired_bootstrap(predictions: pd.DataFrame, split: str, comparisons: list,
                     n_bootstrap: int = 2000, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    require(predictions.test_split.eq(split).all(), "Không trộn hai Test split trong Bootstrap.")
    require(n_bootstrap > 0, "Số bootstrap phải dương.")
    losses = match_losses(predictions)
    require(len(losses) > 0, "Không có trận để bootstrap.")
    samples = np.random.default_rng(seed).integers(0, len(losses), size=(n_bootstrap, len(losses)))
    # Hai phía có cùng trọng số: trung bình match-mean bằng MAE trên 2*n records.
    draws = losses.to_numpy()[samples].mean(axis=1)
    positions = {model: i for i, model in enumerate(losses.columns)}
    observed = losses.mean(axis=0)
    rows, summary = [], []
    for comparison in comparisons:
        a, b = comparison["model_a"], comparison["model_b"]
        delta = draws[:, positions[a]] - draws[:, positions[b]]
        lower, upper = np.quantile(delta, [0.025, 0.975], method="linear")
        summary.append(dict(test_split=split, comparison_id=comparison["comparison_id"], model_a=a, model_b=b,
            observed_delta_mae=float(observed[a] - observed[b]), bootstrap_mean_delta=float(delta.mean()),
            ci_lower=float(lower), ci_upper=float(upper), interval_contains_zero=bool(lower <= 0 <= upper),
            n_matches=len(losses), n_bootstrap=n_bootstrap, random_seed=seed))
        rows.extend(dict(test_split=split, comparison_id=comparison["comparison_id"], model_a=a, model_b=b,
                         repetition=i + 1, delta_mae=float(value), random_seed=seed) for i, value in enumerate(delta))
    audit = dict(test_split=split, n_matches=len(losses), sample_shape=list(samples.shape),
                 sampling_unit="match_id", sorted_match_ids_sha256=hashlib.sha256(losses.index.to_numpy(dtype="<i8").tobytes()).hexdigest(),
                 sample_indices_sha256=hashlib.sha256(samples.astype("<i8").tobytes()).hexdigest())
    return pd.DataFrame(summary), pd.DataFrame(rows), audit
