"""Phase 7: đóng băng protocol, fit Development một lần, đánh giá hai holdout."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import platform
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.prepare_training_features import (
    FEATURES, HISTORY_FEATURES, PASSTHROUGH_FEATURES, INPUT_PATH, PREPROCESS_PATH,
    ROOT, audit_history_counts, load_dataset, prepare_features, read_history_config,
)
from scripts.training.train_models import MODEL_NAMES, evaluate_predictions
from scripts.training.tune_models import build_pipeline, json_safe, _prediction_hash
from .analyze_models import BEST_PATH, export_tables, load_selected_models, sha256
from .bootstrap_analysis import paired_bootstrap
from .error_analysis import (
    build_prediction_records, cross_model_errors, match_error_analysis, notable_errors,
    summarize_errors, LARGE_ERROR_THRESHOLD, DISAGREEMENT_THRESHOLD,
    SMALL_SAMPLE_THRESHOLD, NOTABLE_CASES,
)
from .feature_analysis import require

OUTPUT_DIR = ROOT / "outputs/final_test"
PROTOCOL_PATH = OUTPUT_DIR / "evaluation_protocol.json"
REPORT_PATH = ROOT / "Phases/Evaluate La Liga xG Models on Independent Temporal Holdouts.md"
SPLITS = {"development": (2019, 2020, 2021, 2022, 2023),
          "main_final_test": (2024,), "supplemental_test": (2025,)}
PRIMARY = "Linear Regression"
CHALLENGER = "XGBoost"
BASELINE = "Historical Baseline"
COMPARISONS = [dict(comparison_id=key, model_a=a, model_b=b) for key, a, b in (
    ("lr_minus_baseline", PRIMARY, BASELINE), ("lr_minus_xgb", PRIMARY, CHALLENGER),
    ("rf_minus_baseline", "Random Forest", BASELINE),
    ("dt_minus_baseline", "Decision Tree", BASELINE), ("xgb_minus_baseline", CHALLENGER, BASELINE))]


def partition_data(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    require(frame.index.is_unique, "Source row không duy nhất.")
    require(set(frame.season) == set(sum(SPLITS.values(), ())), "Dataset chứa thiếu/thừa mùa.")
    parts = {key: frame.loc[frame.season.isin(seasons)].sort_values(
        ["date", "match_id", "is_home"], kind="stable").copy() for key, seasons in SPLITS.items()}
    seen_rows, seen_matches = set(), set()
    last_end = None
    for key, part in parts.items():
        require(not part.empty, f"Partition rỗng: {key}.")
        require(not seen_rows.intersection(part.index) and not seen_matches.intersection(part.match_id), "Overlap partitions.")
        pairs = part.groupby("match_id")
        require(pairs.size().eq(2).all() and pairs.is_home.nunique().eq(2).all()
                and part.is_home.isin([0, 1]).all() and pairs.season.nunique().eq(1).all()
                and pairs.date.nunique().eq(1).all(), "Không đủ đúng cặp Home/Away cùng ngày, mùa.")
        require(last_end is None or last_end < part.date.min(), "Sai thứ tự thời gian giữa partitions.")
        last_end = part.date.max()
        seen_rows.update(part.index)
        seen_matches.update(part.match_id)
    require(len(seen_rows) == len(frame), "Bỏ sót source rows.")
    return parts


def temporal_audit(frame: pd.DataFrame) -> dict:
    """Đối chiếu chỉ đọc với công thức hiện có; không ghi/tạo rolling features."""
    config = read_history_config()
    stints = audit_history_counts(frame)
    ambiguity = frame.groupby(["team", "date"]).match_id.nunique().gt(1)
    require(not ambiguity.any(), "Không xác định thứ tự cùng đội/cùng ngày: dừng đánh giá.")
    tree = ast.parse(PREPROCESS_PATH.read_text(encoding="utf-8-sig"))
    mapping = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "ROLLING_MAP" for t in n.targets))
    checks, max_difference = 0, 0.0
    for _, team in frame.groupby("team", sort=True):
        history, previous_season = [], None
        for row in team.sort_values("date", kind="stable").itertuples():
            if previous_season is not None and row.season - previous_season > 1:
                history = []
            require(all(past.date < row.date for past in history), "Lịch sử không thực sự trước ngày dự báo.")
            for source, feature in mapping.items():
                expected = float(np.mean([getattr(past, source) for past in history])) if history else config.priors[feature]
                difference = abs(getattr(row, feature) - expected)
                max_difference = max(max_difference, difference)
                # CSV nguồn: 5/3 -> 1,666666667; 46/3 -> 15,33333333.
                # Phase 2 chỉ đổi dấu thập phân. Dung sai 0,5*10^-8 + float.
                require(difference <= 5.1e-9, f"Rolling sai tại source_row={row.Index}, {feature}: dừng, không tự sửa.")
                checks += 1
            history = (history + [row])[-config.window:]
            previous_season = row.season
    return dict(rolling_values_checked=checks, max_absolute_difference=max_difference,
                stint_count=stints, same_team_same_date_ambiguous=0, resolution="date_only",
                kickoff_timestamp_confirmed=False, current_and_future_rows_excluded=True,
                operation="read_only_comparison_with_existing_shift1_rolling5_formula",
                absolute_tolerance=5.1e-9, tolerance_basis="source_csv_eight_decimal_rounding_for_two_digit_values_plus_float_error")


def partition_manifest(parts: dict) -> dict:
    return {key: dict(seasons=list(SPLITS[key]), n_observations=len(part), n_matches=int(part.match_id.nunique()),
                     start=str(part.date.min()), end=str(part.date.max())) for key, part in parts.items()}


def build_protocol() -> dict:
    full = load_dataset()
    parts = partition_data(full)
    require(full.shape == (4700, 26) and full.match_id.nunique() == 2350, "Dataset khác kích thước đã xác minh.")
    require([len(p) for p in parts.values()] == [3800, 760, 140], "Sai số dòng Dev/Main/Supplemental.")
    selected, models = load_selected_models()
    cv = pd.read_csv(ROOT / "outputs/tuning/tuning_summary.csv").set_index("model")
    require(set(cv.index) == set(MODEL_NAMES) and cv.index.is_unique, "Sai tham chiếu CV.")
    require(abs(cv.loc[PRIMARY, "mean_validation_mae_after"] - 0.5588376439) < 1e-10
            and abs(cv.loc[CHALLENGER, "mean_validation_mae_after"] - 0.5623028410) < 1e-10, "Reference Phase 5 không khớp.")
    sources = ["data/preprocess_laliga.py", "scripts/prepare_training_features.py", "scripts/training/cross_validation.py",
               "scripts/training/train_models.py", "scripts/training/tune_models.py", "scripts/evaluation/error_analysis.py",
               "scripts/evaluation/final_test.py", "scripts/evaluation/bootstrap_analysis.py"]
    return dict(version=1, phase=7, purpose="pre_evaluation_frozen_protocol", dataset=dict(path=str(INPUT_PATH.relative_to(ROOT)),
        sha256=sha256(INPUT_PATH), shape=list(full.shape)), partitions=partition_manifest(parts),
        features=list(FEATURES), target="xg", methods=list(MODEL_NAMES), primary_candidate=PRIMARY,
        main_challenger=CHALLENGER, benchmark=BASELINE, best_params_sha256=sha256(BEST_PATH),
        selected_models=selected["models"], effective_estimator_parameters={n: json_safe(m.get_params(deep=False)) for n, m in models.items()},
        baseline=dict(feature="xg_avg5", preprocessing="reuse_development_fitted_primary_preprocessor", tuning=False),
        imputation=dict(strategy="median", fit_scope="development_only", restored_to_nan="verified_zero_history_fixed_priors_only",
                        imputed_columns=list(HISTORY_FEATURES), passthrough_columns=list(PASSTHROUGH_FEATURES),
                        priors=read_history_config().priors, fit_count_per_regressor=1),
        training=dict(strategy="fit_once_evaluate_twice", estimator_fits_per_regressor=1, no_test_fit=True, serialization=False),
        scoring=dict(primary="mae", secondary="rmse", clipping="maximum(0,raw_prediction)", residual="predicted_minus_actual",
                     std_ddof=0, cv_aggregation="arithmetic_mean_of_three_validation_fold_metrics_not_pooled_rmse",
                     baseline_improvement="baseline_mae_minus_model_mae; percent=100*improvement/baseline_mae"),
        development_cv={n: dict(mae=float(cv.loc[n, "mean_validation_mae_after"]), rmse=float(cv.loc[n, "mean_validation_rmse_after"])) for n in MODEL_NAMES},
        error_analysis=dict(dimensions=["overall", "season", "venue", "actual_xg", "team_history", "opponent_history", "matchweek"],
            actual_xg_groups=["<1", "1<=x<2", ">=2"], history_groups=["zero", "one_to_four", "five_or_more"],
            matchweek="numeric_1_to_38", large_error_threshold=LARGE_ERROR_THRESHOLD,
            disagreement_threshold=DISAGREEMENT_THRESHOLD, small_sample_threshold=SMALL_SAMPLE_THRESHOLD, notable_top_n=NOTABLE_CASES),
        bootstrap=dict(sampling_unit="match_id", paired_home_away=True, replacement=True, preserve_multiplicity=True,
            same_draws_all_comparisons_within_split=True, separate_splits=True, n_bootstrap=2000, random_seed=42,
            delta="mae_A_minus_mae_B", negative_means="A_has_lower_MAE", interval="percentile", quantiles=[0.025, 0.975],
            quantile_method="linear", comparisons=COMPARISONS, multiplicity_correction="none; intervals_are_marginal"),
        temporal_audit=temporal_audit(full), decision_source_sha256={p: sha256(ROOT / p) for p in sources},
        reference_sha256={p: sha256(ROOT / p) for p in ["outputs/tuning/tuning_summary.csv", "outputs/evaluation/analysis_manifest.json"]})


def prepare_protocol(path: Path = PROTOCOL_PATH) -> dict:
    expected = build_protocol()  # Chỉ schema/toàn vẹn và quyết định Development, không score Test.
    if path.exists():
        require(json.loads(path.read_text(encoding="utf-8")) == expected, "Protocol có sẵn khác cấu hình/nguồn; không ghi đè.")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(expected, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    return expected


def verify_protocol(path: Path = PROTOCOL_PATH) -> tuple[dict, str]:
    require(path.is_file(), "Chưa có protocol. Chạy lệnh prepare trước evaluate.")
    digest = sha256(path)
    observed = json.loads(path.read_text(encoding="utf-8"))
    require(observed == build_protocol(), "Protocol/source/config đã thay đổi; dừng, không ghi đè.")
    require(sha256(path) == digest, "Protocol thay đổi trong khi xác minh.")
    return observed, digest


def fit_development(part: pd.DataFrame, models: dict) -> tuple[dict, dict]:
    require(set(part.season) == set(SPLITS["development"]), "Phải fit đủ Development và cấm fit mùa Test.")
    require(set(models) == set(MODEL_NAMES) - {BASELINE}, "Phải có đúng bốn regressors.")
    X, y, restoration = prepare_features(part)
    require(X.index.equals(y.index) and X.index.equals(part.index), "Sai alignment Dev.")
    fitted, audits = {}, {}
    for name, template in models.items():
        pipeline = build_pipeline(template)
        with threadpool_limits(limits=1):
            pipeline.fit(X, y)  # Duy nhất một fit/estimator và một fit/imputer, trên full Development.
        pre = pipeline.named_steps["preprocessing"]
        median = pre.named_steps["median"]
        expected = X.loc[:, list(HISTORY_FEATURES)].median().to_numpy()
        require(median.n_samples_fit_ == len(X) and np.array_equal(expected, median.imputer_.statistics_), "Median không phải Dev-only.")
        transformed = pre.transform(X)
        validate_transform(X, transformed)
        require(list(pipeline.named_steps["model"].feature_names_in_) == list(FEATURES), "Estimator sai feature order.")
        fitted[name] = pipeline
        audits[name] = dict(estimator_fit_calls=1, imputer_fit_calls=1, fit_partition="development",
            n_fit_records=len(X), medians=dict(zip(HISTORY_FEATURES, expected.tolist())), restored_cells=restoration.restored_cells,
            effective_parameters=json_safe(pipeline.named_steps["model"].get_params(deep=False)))
    return fitted, audits


def validate_transform(before: pd.DataFrame, after: pd.DataFrame) -> None:
    require(list(after.columns) == list(FEATURES) and before.index.equals(after.index)
            and np.isfinite(after.to_numpy(dtype=float)).all(), "Sai schema/alignment/finite sau transform.")
    require(before.where(before.notna()).equals(after.where(before.notna()))
            and before.loc[:, list(PASSTHROUGH_FEATURES)].equals(after.loc[:, list(PASSTHROUGH_FEATURES)]), "Transform sửa ô hợp lệ.")


def infer_split(part: pd.DataFrame, split: str, fitted: dict) -> tuple[pd.DataFrame, list]:
    require(split in ("main_final_test", "supplemental_test") and set(part.season) == set(SPLITS[split]), "Sai Test partition.")
    X, y, _ = prepare_features(part)
    require(X.index.equals(y.index) and X.index.equals(part.index), "Sai Test X/y/metadata.")
    predictions, diagnostics = [], []
    baseline = None
    for name, pipeline in fitted.items():
        pre = pipeline.named_steps["preprocessing"]
        imputer = pre.named_steps["median"]
        snapshot = imputer.imputer_.statistics_.copy()
        transformed = pre.transform(X)
        validate_transform(X, transformed)
        with threadpool_limits(limits=1):
            raw = pipeline.named_steps["model"].predict(transformed)
        require(np.array_equal(snapshot, imputer.imputer_.statistics_), "Test thay median.")
        if name == PRIMARY:
            baseline = transformed.xg_avg5.to_numpy(copy=True)
        predictions.append(test_prediction_table(part, split, name, y, raw))
        diagnostics.append(diagnostic_row(predictions[-1], raw))
    require(baseline is not None, "Thiếu preprocessor của Primary để tạo Baseline.")
    predictions.append(test_prediction_table(part, split, BASELINE, y, baseline))
    diagnostics.append(diagnostic_row(predictions[-1], baseline))
    result = pd.concat(predictions, ignore_index=True)
    validate_predictions(result, {split: part})
    return result, diagnostics


def test_prediction_table(metadata, split, model, y, raw):
    require(split in ("main_final_test", "supplemental_test") and set(metadata.season) == set(SPLITS[split]), "Sai season cho Test records.")
    result = build_prediction_records(metadata, model, y, raw)
    result.insert(0, "test_split", split)
    result["raw_prediction"] = np.asarray(raw, dtype=float)
    return result


def diagnostic_row(records, raw):
    return dict(test_split=records.test_split.iloc[0], model=records.model.iloc[0],
        n_observations=len(records), n_matches=int(records.match_id.nunique()), mean_residual=float(records.residual.mean()),
        median_absolute_error=float(records.absolute_error.median()), residual_std=float(records.residual.std(ddof=0)),
        negative_raw_predictions=int((np.asarray(raw) < 0).sum()), prediction_sha256=_prediction_hash(records.predicted_xg.to_numpy()))


def validate_predictions(predictions: pd.DataFrame, parts: dict) -> None:
    require(not predictions.isna().any().any() and not predictions.duplicated(["test_split", "model", "source_row"]).any(), "Missing/duplicate predictions.")
    require(set(predictions.test_split) == set(parts), "Thiếu/thừa split trong dự báo.")
    for split, part in parts.items():
        subset = predictions.loc[predictions.test_split.eq(split)]
        require(set(subset.model) == set(MODEL_NAMES) and len(subset) == len(part) * 5, "Thiếu model/records.")
        for _, records in subset.groupby("model"):
            require(set(records.source_row) == set(part.index), "Sai source-row coverage.")
            source = part.loc[records.source_row]
            for column in ["season", "date", "round", "match_id", "team", "opponent", "is_home",
                           "matches_seen", "opponent_matches_seen", "short_history", "opponent_short_history"]:
                require(np.array_equal(records[column].to_numpy(), source[column].to_numpy()), f"Metadata sai: {column}.")
            require(np.array_equal(records.actual_xg.to_numpy(), source.xg.to_numpy()), "Actual không khớp nguồn.")
            require(records.groupby("match_id").size().eq(2).all() and records.groupby("match_id").is_home.nunique().eq(2).all(), "Thiếu cặp dự báo.")
    require(np.isfinite(predictions.select_dtypes(include="number").to_numpy()).all(), "Dự báo không hữu hạn.")
    require(np.array_equal(predictions.predicted_xg, np.maximum(0, predictions.raw_prediction)), "Sai clipping.")
    residual = predictions.predicted_xg.to_numpy() - predictions.actual_xg.to_numpy()
    require(np.array_equal(residual, predictions.residual) and np.array_equal(abs(residual), predictions.absolute_error)
            and np.array_equal(residual ** 2, predictions.squared_error), "Sai residual/error.")


def score_predictions(predictions, protocol):
    rows = []
    for split, subset in predictions.groupby("test_split", sort=False):
        baseline_mae = subset.loc[subset.model.eq(BASELINE), "absolute_error"].mean()
        for name in MODEL_NAMES:
            group = subset.loc[subset.model.eq(name)]
            mae, rmse = float(group.absolute_error.mean()), float(np.sqrt(group.squared_error.mean()))
            cv = protocol["development_cv"][name]
            rows.append(dict(test_split=split, model=name, designation="primary_candidate" if name == PRIMARY else
                "main_challenger" if name == CHALLENGER else "benchmark" if name == BASELINE else "comparison_regressor",
                n_observations=len(group), n_matches=int(group.match_id.nunique()), mae=mae, rmse=rmse,
                development_cv_mean_fold_mae=cv["mae"], development_cv_mean_fold_rmse=cv["rmse"],
                mae_minus_development_cv=mae-cv["mae"], rmse_minus_development_cv=rmse-cv["rmse"],
                baseline_mae_improvement=float(baseline_mae-mae), baseline_mae_improvement_percent=float(100*(baseline_mae-mae)/baseline_mae)))
    result = pd.DataFrame(rows)
    result["observed_mae_rank"] = result.groupby("test_split").mae.rank(method="min").astype(int)
    return result


def protected_snapshot() -> dict:
    paths = [p for folder in ("data", "scripts", "tests", "Phases", "outputs") for p in (ROOT/folder).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("~$")
             and not p.is_relative_to(OUTPUT_DIR) and not p.is_relative_to(ROOT/"outputs/figures/phase7")
             and p != REPORT_PATH]
    return {str(p.relative_to(ROOT)): sha256(p) for p in paths}


def run_tests() -> dict:
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.discover(str(ROOT/"tests"), pattern="test_*.py"))
    log = dict(run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped), log=stream.getvalue())
    require(result.wasSuccessful(), "Tests thất bại:\n" + log["log"])
    return log


def independent_readback(tables: dict, parts: dict, protocol: dict) -> dict:
    """Đọc CSV chuẩn, parse float Python để kiểm tra round-trip 17 chữ số."""
    loaded = {}
    for name, expected in tables.items():
        with (OUTPUT_DIR/name).open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            require(reader.fieldnames == list(expected.columns), f"Sai schema readback: {name}.")
            rows = list(reader)
        require(len(rows) == len(expected), f"Sai row count readback: {name}.")
        columns = {}
        for column in expected:
            if pd.api.types.is_bool_dtype(expected[column]):
                columns[column] = [r[column] == "True" for r in rows]
            elif pd.api.types.is_integer_dtype(expected[column]):
                columns[column] = [int(r[column]) for r in rows]
            elif pd.api.types.is_numeric_dtype(expected[column]):
                columns[column] = [float(r[column]) for r in rows]
            else:
                columns[column] = [r[column] for r in rows]
        table = pd.DataFrame(columns)
        pd.testing.assert_frame_equal(expected.reset_index(drop=True), table, check_dtype=False, check_exact=True)
        loaded[name] = table
    predictions = loaded["final_test_predictions.csv"]
    validate_predictions(predictions, parts)
    pd.testing.assert_frame_equal(score_predictions(predictions, protocol), loaded["final_test_metrics.csv"], check_dtype=False, check_exact=True)
    for (split, model), group in predictions.groupby(["test_split", "model"]):
        raw = group.raw_prediction.to_numpy()
        residual = np.maximum(0, raw) - group.actual_xg.to_numpy()
        metric = loaded["final_test_metrics.csv"].loc[lambda f: f.test_split.eq(split)&f.model.eq(model)].iloc[0]
        diag = loaded["final_test_diagnostics.csv"].loc[lambda f: f.test_split.eq(split)&f.model.eq(model)].iloc[0]
        require(metric.mae == float(np.mean(np.abs(residual))) and metric.rmse == float(np.sqrt(np.mean(residual**2))), "Readback MAE/RMSE không khớp tính trực tiếp.")
        require(diag.mean_residual == float(np.mean(residual)) and diag.median_absolute_error == float(np.median(abs(residual)))
                and diag.residual_std == float(np.std(residual, ddof=0)) and diag.negative_raw_predictions == int((raw<0).sum()), "Readback diagnostics sai.")
    for split, group in predictions.groupby("test_split", sort=False):
        summary, reps, _ = paired_bootstrap(group, split, protocol["bootstrap"]["comparisons"],
            protocol["bootstrap"]["n_bootstrap"], protocol["bootstrap"]["random_seed"])
        for name, expected in (("bootstrap_results.csv", summary), ("bootstrap_replicates.csv", reps)):
            pd.testing.assert_frame_equal(expected.reset_index(drop=True), loaded[name].loc[loaded[name].test_split.eq(split)].reset_index(drop=True),
                                          check_dtype=False, check_exact=True)
    return dict(csv_files=len(loaded), exact_float_round_trip=True, source_row_alignment=True,
                independent_score_recomputed=True, bootstrap_replayed=True)


def evaluate(path: Path = PROTOCOL_PATH) -> dict:
    protocol, digest = verify_protocol(path)  # Bắt buộc trước fit/predict/score Test.
    require(not (OUTPUT_DIR/"final_test_manifest.json").exists(),
            "Đã có lần đánh giá hoàn tất; không tự retrain/ghi đè. Dùng outputs/manifest để kiểm toán.")
    before = protected_snapshot()
    tests = run_tests()
    full = load_dataset()
    all_parts = partition_data(full)
    parts = {k: v for k, v in all_parts.items() if k != "development"}
    _, models = load_selected_models()
    print("Protocol hợp lệ; fit bốn model một lần trên 3.800 dòng Development...", flush=True)
    fitted, training_audit = fit_development(all_parts["development"], models)
    require(all(training_audit[n]["effective_parameters"] == protocol["effective_estimator_parameters"][n] for n in fitted), "Parameters không khớp protocol.")
    ids = {name: (id(pipeline), id(pipeline.named_steps["model"]), id(pipeline.named_steps["preprocessing"])) for name, pipeline in fitted.items()}
    predictions, diagnostics = [], []
    for split, part in parts.items():
        print(f"Đánh giá {split}: {len(part)} dòng, không fit lại...", flush=True)
        pred, diag = infer_split(part, split, fitted)
        predictions.append(pred)
        diagnostics.extend(diag)
    predictions = pd.concat(predictions, ignore_index=True)
    validate_predictions(predictions, parts)
    # Tái lập inference trên chính bốn fitted objects, không tạo fit thứ hai.
    for split, part in parts.items():
        repeat, _ = infer_split(part, split, fitted)
        pd.testing.assert_frame_equal(repeat, predictions.loc[predictions.test_split.eq(split)].reset_index(drop=True), check_exact=True)
    require(ids == {name: (id(p), id(p.named_steps["model"]), id(p.named_steps["preprocessing"])) for name, p in fitted.items()}, "Đã thay fitted object.")
    tables = {"final_test_metrics.csv": score_predictions(predictions, protocol), "final_test_predictions.csv": predictions,
              "final_test_diagnostics.csv": pd.DataFrame(diagnostics)}
    summaries, replicates, boot_audit, errors, notable, matches, cross, messages = [], [], [], [], [], [], [], []
    for split, part in parts.items():
        pred = predictions.loc[predictions.test_split.eq(split)].reset_index(drop=True)
        summary, reps, audit = paired_bootstrap(pred, split, protocol["bootstrap"]["comparisons"],
            protocol["bootstrap"]["n_bootstrap"], protocol["bootstrap"]["random_seed"])
        summaries.append(summary); replicates.append(reps); boot_audit.append(audit)
        error, warnings = summarize_errors(pred, partition_column="test_split", scope=split)
        error.insert(0, "test_split", split)
        errors.append(error); messages.extend(warnings)
        notable.append(notable_errors(pred))
        matches.append(match_error_analysis(pred, partition_column="test_split"))
        cross.append(cross_model_errors(pred, partition_column="test_split"))
    tables.update({name: pd.concat(frames, ignore_index=True) for name, frames in (
        ("bootstrap_results.csv", summaries), ("bootstrap_replicates.csv", replicates),
        ("final_test_error_analysis.csv", errors), ("final_test_notable_errors.csv", notable),
        ("final_test_match_errors.csv", matches), ("final_test_cross_model_errors.csv", cross))})
    for name, table in tables.items():
        require(not table.isna().any().any() and np.isfinite(table.select_dtypes(include="number").to_numpy()).all(), f"Missing/inf trong {name}.")
    output_hashes = export_tables(tables, OUTPUT_DIR)
    readback = independent_readback(tables, parts, protocol)
    from .final_test_visualizations import generate_figures
    figures = generate_figures(tables)
    import importlib.metadata
    manifest = dict(phase=7, evaluation_protocol_sha256=digest, dataset_sha256=sha256(INPUT_PATH),
        best_params_sha256=sha256(BEST_PATH), features=list(FEATURES), partitions=partition_manifest(all_parts),
        temporal_audit=protocol["temporal_audit"], training=training_audit, same_fitted_objects_both_tests=True,
        repeat_inference_exact=True, test_fit_calls=0, serialization=False,
        bootstrap=boot_audit, readback=readback, csv_sha256=output_hashes, figures=figures,
        tests=tests, environment=dict(python=platform.python_version(), packages={n: importlib.metadata.version(n) for n in
            ("numpy", "pandas", "scipy", "scikit-learn", "xgboost", "matplotlib", "threadpoolctl")}),
        warnings=messages, protected_file_sha256=before,
        source_sha256={str(p.relative_to(ROOT)): sha256(p) for p in (ROOT/"scripts/evaluation").glob("*.py")})
    require(before == protected_snapshot(), "Một file được bảo vệ đã thay đổi.")
    require(sha256(path) == digest and json.loads(path.read_text(encoding="utf-8")) == protocol, "Protocol bị thay đổi.")
    manifest["protocol_unchanged"] = True
    manifest["protected_files_unchanged"] = True
    from .final_test_reporting import write_report
    write_report(tables, protocol, manifest, REPORT_PATH)
    manifest["report_sha256"] = sha256(REPORT_PATH)
    (OUTPUT_DIR/"final_test_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    require(json.loads((OUTPUT_DIR/"final_test_manifest.json").read_text(encoding="utf-8")) == manifest, "Manifest readback sai.")
    print(tables["final_test_metrics.csv"][["test_split", "model", "mae", "rmse"]].to_string(index=False), flush=True)
    return manifest


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "evaluate"])
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare_protocol()
        print(f"Đã đóng băng/xác minh protocol; chưa tính Test metrics. SHA-256: {sha256(PROTOCOL_PATH)}")
    else:
        evaluate()


if __name__ == "__main__":
    main()
