"""Dự báo Validation có truy vết và thống kê sai số sau dự báo."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.training.cross_validation import DEFAULT_FOLDS
from scripts.training.train_models import MODEL_NAMES, STD_DDOF, evaluate_predictions
from .feature_analysis import require


LARGE_ERROR_THRESHOLD = 1.0
DISAGREEMENT_THRESHOLD = 0.5
SMALL_SAMPLE_THRESHOLD = 30
NOTABLE_CASES = 15
MODEL_SLUGS = {"Historical Baseline": "baseline", "Linear Regression": "linear_regression",
               "Decision Tree": "decision_tree", "Random Forest": "random_forest", "XGBoost": "xgboost"}


def build_prediction_records(metadata: pd.DataFrame, model: str,
                             y: pd.Series, raw_prediction: np.ndarray) -> pd.DataFrame:
    """Tạo records sau dự báo; wrapper của mỗi thí nghiệm phải kiểm tra partition."""
    require(model in MODEL_NAMES, "Sai model của dự báo.")
    require(metadata.index.equals(y.index) and y.equals(metadata.xg), "Metadata/target không khớp từng bản ghi.")
    require(metadata.groupby("match_id").size().eq(2).all(), "Dự báo thiếu một phía của trận.")
    _, prediction = evaluate_predictions(y, raw_prediction)
    columns = ["season", "date", "round", "match_id", "team", "opponent", "is_home",
               "matches_seen", "opponent_matches_seen", "short_history", "opponent_short_history"]
    result = metadata.loc[:, columns].copy()
    result.insert(0, "source_row", metadata.index.to_numpy())
    result["model"] = model
    result["actual_xg"] = y.to_numpy()
    result["predicted_xg"] = prediction
    result["residual"] = prediction - y.to_numpy()
    result["absolute_error"] = np.abs(result.residual)
    result["squared_error"] = result.residual ** 2
    return result.reset_index(drop=True)


def prediction_table(metadata: pd.DataFrame, model: str, fold: int,
                     y: pd.Series, raw_prediction: np.ndarray) -> pd.DataFrame:
    require(model in MODEL_NAMES and fold in range(1, len(DEFAULT_FOLDS) + 1), "Sai model hoặc fold của dự báo.")
    require(metadata.season.eq(DEFAULT_FOLDS[fold - 1].validation_season).all(), "Dự báo chứa bản ghi ngoài Validation.")
    result = build_prediction_records(metadata, model, y, raw_prediction)
    result.insert(0, "fold", fold)
    return result


def parse_matchweeks(rounds: pd.Series) -> pd.Series:
    parsed = rounds.astype(str).str.extract(r"^Matchweek ([1-9][0-9]*)$", expand=False)
    require(parsed.notna().all(), "Không chuyển đổi được toàn bộ round thành matchweek số; bỏ riêng phân tích matchweek.")
    result = parsed.astype(int)
    require(result.between(1, 38).all(), "Matchweek ngoài khoảng La Liga 1–38; không tự sửa.")
    return result


def history_groups(counts: pd.Series) -> pd.Series:
    require(counts.ge(0).all() and counts.mod(1).eq(0).all(), "Số trận lịch sử không hợp lệ.")
    return pd.Series(np.select([counts.eq(0), counts.lt(5)], ["zero", "one_to_four"],
                               default="five_or_more"), index=counts.index)


def actual_xg_groups(values: pd.Series) -> pd.Series:
    return pd.Series(np.select([values.lt(1), values.lt(2)], ["xg_lt_1", "xg_1_to_2"],
                               default="xg_ge_2"), index=values.index)


def summarize_errors(predictions: pd.DataFrame, *, partition_column: str = "fold",
                     scope: str = "pooled_development_validation") -> tuple[pd.DataFrame, list[str]]:
    """Mỗi dòng là một subgroup trong Validation gộp; không trộn với mean-CV RMSE."""
    working = predictions.copy(deep=True)
    dimensions = {
        "overall": pd.Series("all", index=working.index),
        "season": working.season,
        "venue": working.is_home.map({1: "Home", 0: "Away"}),
        "actual_xg": actual_xg_groups(working.actual_xg),
        "team_history": history_groups(working.matches_seen),
        "opponent_history": history_groups(working.opponent_matches_seen),
    }
    messages = []
    try:
        dimensions["matchweek"] = parse_matchweeks(working["round"])
    except ValueError as exc:
        messages.append(str(exc))
    rows = []
    for dimension, labels in dimensions.items():
        for model in MODEL_NAMES:
            subset = working.loc[working.model.eq(model)]
            require(not subset.empty, f"Thiếu dự báo của {model}.")
            for label, group in subset.groupby(labels.loc[subset.index], sort=True):
                metrics, _ = evaluate_predictions(group.actual_xg, group.predicted_xg.to_numpy())
                rows.append(dict(model=model, dimension=dimension, group=str(label),
                    scope=scope, **{"folds" if partition_column == "fold" else "test_splits":
                        ";".join(map(str, sorted(group[partition_column].unique())))},
                    seasons=";".join(map(str, sorted(group.season.unique()))),
                    n_observations=len(group), n_matches=group.match_id.nunique(),
                    mae=metrics["mae"], rmse=metrics["rmse"], mean_residual=float(group.residual.mean()),
                    median_absolute_error=float(group.absolute_error.median()),
                    residual_std=float(group.residual.std(ddof=STD_DDOF)),
                    absolute_error_std=float(group.absolute_error.std(ddof=STD_DDOF)),
                    p90_absolute_error=float(group.absolute_error.quantile(0.9)),
                    max_absolute_error=float(group.absolute_error.max()),
                    mean_actual_xg=float(group.actual_xg.mean()), mean_predicted_xg=float(group.predicted_xg.mean()),
                    small_sample=len(group) < SMALL_SAMPLE_THRESHOLD))
    return pd.DataFrame(rows), messages


def notable_errors(predictions: pd.DataFrame, top_n: int = NOTABLE_CASES) -> pd.DataFrame:
    """Top 15 tuyệt đối cùng cực trị over/under, gộp thành các bản ghi duy nhất."""
    rows = []
    for model in MODEL_NAMES:
        group = predictions.loc[predictions.model.eq(model)].sort_values(
            ["absolute_error", "date", "match_id", "is_home"], ascending=[False, True, True, True], kind="stable").copy()
        group["absolute_error_rank_all"] = np.arange(1, len(group) + 1)
        selected = set(group.head(top_n).index)
        over = group.residual.idxmax() if group.residual.gt(0).any() else None
        under = group.residual.idxmin() if group.residual.lt(0).any() else None
        selected.update(index for index in (over, under) if index is not None)
        result = group.loc[group.index.isin(selected)].copy()
        result["top_absolute_error"] = result.absolute_error_rank_all.le(top_n)
        result["largest_overprediction"] = result.index == over
        result["largest_underprediction"] = result.index == under
        result["direction"] = np.select([result.residual.gt(0), result.residual.lt(0)],
                                        ["overprediction", "underprediction"], default="exact")
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


def match_error_analysis(predictions: pd.DataFrame, *, partition_column: str = "fold") -> pd.DataFrame:
    keys = ["model", partition_column, "match_id"]
    require(predictions.groupby(keys).size().eq(2).all(), "Match-level cần đúng hai phía cho mỗi model/trận.")
    common = ["season", "date", "round"]
    fields = ["team", "actual_xg", "predicted_xg", "residual", "absolute_error"]
    home = predictions.loc[predictions.is_home.eq(1), keys + common + fields].copy()
    away = predictions.loc[predictions.is_home.eq(0), keys + fields].copy()
    require(len(home) == len(away) and not home.duplicated(keys).any() and not away.duplicated(keys).any(),
            "Cặp trận không có đúng một Home/Away.")
    home = home.rename(columns={c: f"home_{c}" for c in fields})
    away = away.rename(columns={c: f"away_{c}" for c in fields})
    result = home.merge(away, on=keys, how="inner", validate="one_to_one")
    result["sum_absolute_error"] = result.home_absolute_error + result.away_absolute_error
    result["mean_absolute_error"] = result.sum_absolute_error / 2
    result["min_team_absolute_error"] = result[["home_absolute_error", "away_absolute_error"]].min(axis=1)
    result["both_large_errors"] = result.min_team_absolute_error.ge(LARGE_ERROR_THRESHOLD)
    return result.sort_values(["model", partition_column, "match_id"], kind="stable").reset_index(drop=True)


def cross_model_errors(predictions: pd.DataFrame, *, partition_column: str = "fold") -> pd.DataFrame:
    keys = [partition_column, "season", "date", "round", "match_id", "team", "opponent", "is_home", "actual_xg"]
    require(not predictions.duplicated(keys + ["model"]).any(), "Trùng khóa dự báo khi đối chiếu model.")
    wide = predictions.set_index(keys + ["model"])[["predicted_xg", "absolute_error"]].unstack("model")
    require(not wide.isna().any().any(), "Không đủ năm model trên cùng bản ghi.")
    wide.columns = [f"{MODEL_SLUGS[model]}_{measure}" for measure, model in wide.columns]
    result = wide.reset_index()
    errors = [f"{MODEL_SLUGS[model]}_absolute_error" for model in MODEL_NAMES if model != "Historical Baseline"]
    result["regression_models_large"] = result[errors].ge(LARGE_ERROR_THRESHOLD).sum(axis=1)
    result["multiple_regressors_large"] = result.regression_models_large.ge(2)
    result["all_regressors_large"] = result.regression_models_large.eq(4)
    result["mean_regressor_absolute_error"] = result[errors].mean(axis=1)
    result["signed_lr_minus_xgb"] = result.linear_regression_predicted_xg - result.xgboost_predicted_xg
    result["lr_xgb_prediction_difference"] = result.signed_lr_minus_xgb.abs()
    result["large_disagreement"] = result.lr_xgb_prediction_difference.ge(DISAGREEMENT_THRESHOLD)
    return result.sort_values([partition_column, "match_id", "is_home"], kind="stable").reset_index(drop=True)
