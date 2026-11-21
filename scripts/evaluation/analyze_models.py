"""Điều phối Phase 6, kiểm chứng và xuất kết quả; không chạy tuning hoặc Final Test."""

from __future__ import annotations

import ast
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

import matplotlib
import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.base import clone
from threadpoolctl import threadpool_limits
import threadpoolctl
import xgboost

from scripts.prepare_training_features import (
    FEATURES, HISTORY_FEATURES, INPUT_PATH, PASSTHROUGH_FEATURES, PREPROCESS_PATH,
    ROOT, audit_history_counts, load_dataset, read_history_config,
)
from scripts.training.cross_validation import DEFAULT_FOLDS, RESERVED_SEASONS
from scripts.training.train_models import MODEL_NAMES, STD_DDOF, csv_bytes, evaluate_predictions, model_templates
from scripts.training.tune_models import _prediction_hash, build_pipeline, canonical_params, json_safe, prepare_development
from .error_analysis import (
    DISAGREEMENT_THRESHOLD, LARGE_ERROR_THRESHOLD, NOTABLE_CASES, SMALL_SAMPLE_THRESHOLD,
    cross_model_errors, match_error_analysis, notable_errors, prediction_table, summarize_errors,
)
from .feature_analysis import (
    FEATURE_GROUPS, GROUP_NAMES, PERMUTATION_REPEATS, RANDOM_SEED, FittedReference,
    require, retained_features, run_ablation, run_permutation, summarize_ablation, summarize_permutation, validate_groups,
)


OUTPUT_DIR = ROOT / "outputs/evaluation"
FIGURE_DIR = ROOT / "outputs/figures/phase6"
REPORT_PATH = ROOT / "Phases/Analyze Feature Contributions and Prediction Errors for La Liga xG Models.md"
BEST_PATH = ROOT / "outputs/tuning/best_params.json"
CONSISTENCY_TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_files() -> tuple[Path, ...]:
    allowed = ROOT / "scripts/evaluation"
    paths = [p for folder in ("data", "scripts", "tests", "Phases", "outputs/training", "outputs/tuning")
             for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and not p.name.startswith("~$") and not p.is_relative_to(allowed)
             and p not in (ROOT / "tests/test_evaluation.py", REPORT_PATH)]
    return tuple(sorted([*paths, ROOT / ".gitignore"]))


def record(state: dict, name: str, condition: bool, evidence: str) -> None:
    state["checks"].append((name, bool(condition), evidence))
    require(bool(condition), f"{name}: {evidence}")


def load_selected_models(path: Path = BEST_PATH) -> tuple[dict, dict]:
    """Đọc selected params; xác minh fixed parameters thay vì hard-code cấu hình chọn."""
    metadata = json.loads(path.read_text(encoding="utf-8"))
    templates = model_templates()
    require(set(metadata["models"]) == set(templates), "JSON phải có đúng bốn regression algorithms.")
    require(metadata["features"] == list(FEATURES) and metadata["target"] == "xg", "Schema Phase 5 không khớp features/target.")
    require(metadata["excluded_seasons"] == sorted(RESERVED_SEASONS)
            and metadata["scoring"]["minimum_prediction"] == 0
            and metadata["scoring"]["std_ddof"] == STD_DDOF, "Quy tắc Phase 5 khác phạm vi Phase 6.")
    require(metadata["dataset_sha256"] == sha256(INPUT_PATH), "Dataset hiện tại khác SHA-256 dùng trong Phase 5.")
    models = {}
    for name, template in templates.items():
        config = metadata["models"][name]
        observed = template.get_params(deep=False)
        fixed = {key: json_safe(observed[key]) for key in config["fixed_parameters"]}
        require(fixed == config["fixed_parameters"], f"{name}: fixed parameters đã khác Phase 5.")
        models[name] = clone(template).set_params(**config["best_params"])
        require(all(json_safe(models[name].get_params()[key]) == value for key, value in config["best_params"].items()),
                f"{name}: selected params chưa được áp dụng đúng.")
    return metadata, models


def verify_feature_definitions(full: pd.DataFrame, development, state: dict) -> None:
    config = read_history_config()
    tree = ast.parse(PREPROCESS_PATH.read_text(encoding="utf-8-sig"))
    mappings = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "ROLLING_MAP" for t in n.targets)]
    require(len(mappings) == 1, "Không xác minh được ROLLING_MAP.")
    mapping = mappings[0]
    record(state, "sh và sot là hai biến riêng", mapping["sh"] == "shot_avg5" and mapping["sot"] == "sot_avg5"
           and development.frame.sh.ge(development.frame.sot).all(),
           f"Theo schema dự án, sh là tổng cú sút, sot là sút trúng đích; {int(development.frame.sh.ne(development.frame.sot).sum())} dòng development có hai giá trị khác nhau.")
    state["history_config"] = dict(priors=config.priors, window=config.window, short_history_min=config.short_history_min)
    state["history_stints"] = audit_history_counts(development.frame)
    record(state, "Lịch sử và công thức", config.window == 5 and config.short_history_min == 5,
           "Đã đọc shift(1), rolling tối đa 5, min_periods=1; đối chiếu counters theo team/stint, reset khi gap mùa > 1, không có ngưỡng 300 ngày.")
    record(state, "Dataset và Development", full.shape[1] == 26 and full.match_id.nunique() * 2 == len(full)
           and set(development.frame.season) == {2019, 2020, 2021, 2022, 2023}
           and not set(development.frame.season) & RESERVED_SEASONS,
           f"Nguồn {len(full)} dòng/{full.match_id.nunique()} trận; development {len(development.frame)} dòng, Final Test chỉ đọc kiểm tra toàn vẹn.")
    validate_groups()
    record(state, "Sáu nhóm feature", True, "G1–G6 phân hoạch chính xác 13 features, không thiếu hoặc lặp.")


def fit_full_references(development, models: dict, selected: dict, state: dict
                        ) -> tuple[list[FittedReference], pd.DataFrame, pd.DataFrame]:
    phase5 = pd.read_csv(ROOT / "outputs/tuning/overfitting_diagnostics.csv", keep_default_na=False)
    phase5 = phase5.loc[phase5.configuration_stage.eq("after")].set_index(["model", "fold"])
    require(len(phase5) == 15 and phase5.index.is_unique, "Tham chiếu Phase 5 không đủ 15 model-fold duy nhất.")
    references, predictions, results = [], [], []
    for fold in development.folds:
        declared = selected["folds"][fold.fold - 1]
        record(state, f"Fold {fold.fold}: ranh giới", declared["train_seasons"] == list(fold.spec.train_seasons)
               and declared["validation_season"] == fold.spec.validation_season
               and declared["train_samples"] == len(fold.train_indices)
               and declared["validation_samples"] == len(fold.validation_indices)
               and declared["train_end"] == fold.train_end and declared["validation_start"] == fold.validation_start,
               "Indices tạo từ development bằng splitter hiện có; cặp trận không tách, Train trước Validation và không có Final Test.")
        X_train, X_val = development.X.iloc[fold.train_indices], development.X.iloc[fold.validation_indices]
        y_train, y_val = development.y.iloc[fold.train_indices], development.y.iloc[fold.validation_indices]
        metadata = development.frame.iloc[fold.validation_indices]
        baseline_processed = None
        for name, model in models.items():
            pipeline = build_pipeline(model)
            with threadpool_limits(limits=1):
                pipeline.fit(X_train, y_train)
                preprocessor = pipeline.named_steps["preprocessing"]
                processed_train, processed_val = preprocessor.transform(X_train), preprocessor.transform(X_val)
                fitted_model = pipeline.named_steps["model"]
                raw = fitted_model.predict(processed_val)
            median = preprocessor.named_steps["median"]
            record(state, f"{name}/fold {fold.fold}: median Train-only", median.n_samples_fit_ == len(X_train)
                   and np.array_equal(median.imputer_.statistics_, X_train.loc[:, list(HISTORY_FEATURES)].median().to_numpy()),
                   "Preprocessing fit mới trên Train; tám median đối chiếu độc lập, không dùng Validation.")
            for label, before, after in (("Train", X_train, processed_train), ("Validation", X_val, processed_val)):
                record(state, f"{name}/fold {fold.fold}: {label} 13 features", list(after.columns) == list(FEATURES)
                       and before.index.equals(after.index) and np.isfinite(after.to_numpy(dtype=float)).all()
                       and after.where(before.notna()).equals(before.where(before.notna()))
                       and before.loc[:, list(PASSTHROUGH_FEATURES)].equals(after.loc[:, list(PASSTHROUGH_FEATURES)]),
                       "Giữ nguyên index, thứ tự 13 cột và mọi ô hợp lệ; không có target/metadata hoặc NaN/vô hạn.")
            require(list(fitted_model.feature_names_in_) == list(FEATURES), "Full estimator nhận sai feature order.")
            metrics, clipped = evaluate_predictions(y_val, raw)
            reference = phase5.loc[(name, fold.fold)]
            verify_reference(name, fold, metrics, clipped, reference, state)
            references.append(FittedReference(name, fold, fitted_model, processed_train, processed_val, y_train, y_val, metrics))
            predictions.append(prediction_table(metadata, name, fold.fold, y_val, raw))
            results.append(dict(model=name, fold=fold.fold, train_seasons=";".join(map(str, fold.spec.train_seasons)),
                validation_season=fold.spec.validation_season, train_samples=len(X_train), validation_samples=len(X_val),
                estimator_parameters=canonical_params(fitted_model.get_params(deep=False)),
                mae=metrics["mae"], rmse=metrics["rmse"], negative_predictions=metrics["negative_predictions"],
                prediction_sha256=_prediction_hash(clipped), phase5_hash_matches=True))
            if baseline_processed is None:
                baseline_processed = processed_val
        raw = baseline_processed.xg_avg5.to_numpy()
        metrics, clipped = evaluate_predictions(y_val, raw)
        verify_reference("Historical Baseline", fold, metrics, clipped, phase5.loc[("Historical Baseline", fold.fold)], state)
        predictions.append(prediction_table(metadata, "Historical Baseline", fold.fold, y_val, raw))
        results.append(dict(model="Historical Baseline", fold=fold.fold, train_seasons=";".join(map(str, fold.spec.train_seasons)),
            validation_season=fold.spec.validation_season, train_samples=len(X_train), validation_samples=len(X_val),
            estimator_parameters="null", mae=metrics["mae"], rmse=metrics["rmse"],
            negative_predictions=metrics["negative_predictions"], prediction_sha256=_prediction_hash(clipped), phase5_hash_matches=True))
        print(f"Đã tái tạo và đối chiếu đủ năm phương pháp ở fold {fold.fold}.", flush=True)
    return references, pd.DataFrame(results), pd.concat(predictions, ignore_index=True)


def verify_reference(name, fold, metrics, prediction, phase5_row, state):
    record(state, f"{name}/fold {fold.fold}: tái tạo Phase 5",
           phase5_row.train_samples == len(fold.train_indices) and phase5_row.validation_samples == len(fold.validation_indices)
           and phase5_row.validation_season == fold.spec.validation_season
           and np.isclose(metrics["mae"], phase5_row.validation_mae, rtol=0, atol=CONSISTENCY_TOLERANCE)
           and np.isclose(metrics["rmse"], phase5_row.validation_rmse, rtol=0, atol=CONSISTENCY_TOLERANCE)
           and _prediction_hash(prediction) == phase5_row.validation_prediction_sha256,
           "MAE/RMSE khớp atol=1e-12, rtol=0; SHA-256 float64 little-endian của dự báo sau clipping khớp chính xác.")


def validate_tables(tables: dict, development) -> None:
    full = tables["full_feature_results.csv"]
    ablation, permutation = tables["ablation_results.csv"], tables["permutation_importance.csv"]
    predictions, errors = tables["validation_predictions.csv"], tables["error_analysis.csv"]
    observations = sum(len(f.validation_indices) for f in development.folds)
    require(len(full) == len(MODEL_NAMES) * 3 and not full.duplicated(["model", "fold"]).any(), "Thiếu full-feature results.")
    expected_ablation = {(model, fold.fold, group) for model in MODEL_NAMES[1:] for fold in development.folds for group in FEATURE_GROUPS}
    require(len(ablation) == 72 and set(zip(ablation.model, ablation.fold, ablation.removed_group)) == expected_ablation,
            "Ablation phải có đúng 72 model-fold-group.")
    reference = full.set_index(["model", "fold"])
    for row in ablation.itertuples(index=False):
        require(json.loads(row.retained_features)["columns"] == retained_features(row.removed_group)
                and json.loads(row.removed_features)["columns"] == list(FEATURE_GROUPS[row.removed_group])
                and row.n_features == len(retained_features(row.removed_group)), "Ablation bỏ sai nhóm hoặc sai thứ tự features.")
        original = reference.loc[(row.model, row.fold)]
        require(row.estimator_parameters == original.estimator_parameters, "Ablation đã thay hyperparameters.")
        np.testing.assert_allclose([row.full_mae, row.full_rmse, row.delta_mae, row.delta_rmse],
            [original.mae, original.rmse, row.ablated_mae - original.mae, row.ablated_rmse - original.rmse], rtol=0, atol=1e-14)
    require(len(permutation) == 4 * 3 * 13 * PERMUTATION_REPEATS and not permutation.duplicated(["model", "fold", "feature", "repetition"]).any(),
            "Permutation thiếu hoặc trùng model-fold-feature-repetition.")
    require(set(permutation.feature) == set(FEATURES) and permutation.random_seed.eq(RANDOM_SEED).all()
            and permutation.groupby(["model", "fold", "feature"]).repetition.apply(lambda x: set(x) == set(range(1, PERMUTATION_REPEATS + 1))).all(),
            "Sai feature, seed hoặc số lần permutation.")
    np.testing.assert_allclose(permutation.importance_mae, permutation.permuted_mae - permutation.original_mae, rtol=0, atol=1e-14)
    pd.testing.assert_frame_equal(summarize_ablation(ablation), tables["ablation_summary.csv"], check_exact=True)
    per_fold, per_summary = summarize_permutation(permutation)
    pd.testing.assert_frame_equal(per_fold, tables["permutation_fold_summary.csv"], check_exact=True)
    pd.testing.assert_frame_equal(per_summary, tables["permutation_summary.csv"], check_exact=True)
    require(len(predictions) == observations * len(MODEL_NAMES)
            and predictions.groupby("model").size().eq(observations).all()
            and set(predictions.model) == set(MODEL_NAMES)
            and not predictions.duplicated(["fold", "model", "match_id", "team"]).any(), "Sai số lượng hoặc khóa dự báo Validation.")
    require(set(predictions.season) == {spec.validation_season for spec in DEFAULT_FOLDS}
            and predictions.groupby(["model", "fold", "match_id"]).size().eq(2).all()
            and predictions.predicted_xg.ge(0).all(), "Dự báo ngoài Validation, thiếu cặp trận hoặc có giá trị âm.")
    source = development.frame.loc[predictions.source_row]
    for c in ("season", "date", "round", "match_id", "team", "opponent", "is_home", "matches_seen", "opponent_matches_seen", "short_history", "opponent_short_history"):
        require(np.array_equal(predictions[c].to_numpy(), source[c].to_numpy()), f"Metadata {c} sai so với nguồn.")
    require(np.array_equal(predictions.actual_xg.to_numpy(), source.xg.to_numpy()), "Target trong dự báo khác nguồn.")
    np.testing.assert_allclose(predictions.residual, predictions.predicted_xg - predictions.actual_xg, rtol=0, atol=1e-14)
    np.testing.assert_allclose(predictions.absolute_error, predictions.residual.abs(), rtol=0, atol=1e-14)
    np.testing.assert_allclose(predictions.squared_error, predictions.residual ** 2, rtol=0, atol=1e-14)
    require(errors.groupby(["model", "dimension"]).n_observations.sum().eq(observations).all(), "Subgroup counts không phân hoạch đủ bản ghi cho mỗi dimension/model.")
    for row in tables["notable_errors.csv"].groupby("model").size():
        require(NOTABLE_CASES <= row <= NOTABLE_CASES + 2, "Sai ngân sách notable cases theo model.")
    require(len(tables["match_error_analysis.csv"]) == observations // 2 * len(MODEL_NAMES)
            and not tables["match_error_analysis.csv"].duplicated(["model", "fold", "match_id"]).any(), "Trận bị đếm trùng ở match-level.")
    require(len(tables["cross_model_errors.csv"]) == observations
            and not tables["cross_model_errors.csv"].duplicated(["fold", "match_id", "team"]).any(), "Sai đơn vị đội–trận khi đối chiếu model.")
    for name, table in tables.items():
        require(not table.isna().any().any() and np.isfinite(table.select_dtypes(include="number").to_numpy()).all(),
                f"{name} có missing hoặc số không hữu hạn.")


def export_tables(tables: dict[str, pd.DataFrame], output_dir: Path = OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    staged, digests = [], {}
    try:
        for name, table in tables.items():
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".evaluation-", suffix=".tmp", delete=False) as handle:
                path = Path(handle.name)
            staged.append((path, output_dir / name))
            path.write_bytes(csv_bytes(table))
            string_columns = {column: str for column in table if pd.api.types.is_string_dtype(table[column])}
            loaded = pd.read_csv(path, keep_default_na=False, dtype=string_columns)
            pd.testing.assert_frame_equal(table, loaded, check_dtype=False, check_exact=False, rtol=1e-14, atol=1e-14)
            digests[name] = sha256(path)
        for source, target in staged:
            os.replace(source, target)
    finally:
        for source, _ in staged:
            source.unlink(missing_ok=True)
    return digests


def execute_tests(state: dict) -> None:
    buffer = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
    state["tests"] = dict(run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                          skipped=len(result.skipped), log=buffer.getvalue())
    record(state, "Tests Phase 4/5/6", result.wasSuccessful(),
           f"{result.testsRun} tests; failures={len(result.failures)}, errors={len(result.errors)}, skipped={len(result.skipped)}. Fixtures không phải kết quả thực nghiệm.")


def run_analysis(state: dict) -> None:
    selected, models = load_selected_models()
    full = load_dataset()
    development = prepare_development(full)
    state.update(selected=selected, development=development, dataset_shape=full.shape, source_matches=int(full.match_id.nunique()))
    verify_feature_definitions(full, development, state)
    references, full_results, predictions = fit_full_references(development, models, selected, state)
    # Hoàn tất và đối chiếu toàn bộ reference trước mọi Ablation/Permutation.
    record(state, "Full-feature reference trước phân tích", len(references) == 12 and len(full_results) == 15,
           "12 Regression fits và baseline tái sử dụng preprocessing; toàn bộ 15 dòng khớp Phase 5 trước khi perturbation.")
    ablations, permutations = [], []
    for reference in references:
        print(f"Phân tích {reference.model}, fold {reference.fold.fold}: 6 Ablation và 130 permutation...", flush=True)
        ablations.append(run_ablation(reference))
        permutations.append(run_permutation(reference))
    ablation = pd.concat(ablations, ignore_index=True)
    permutation = pd.concat(permutations, ignore_index=True)
    repeat = run_permutation(references[0])
    expected = permutation.loc[permutation.model.eq(references[0].model) & permutation.fold.eq(references[0].fold.fold)].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected, repeat, check_exact=True)
    record(state, "Tái lập permutation", True,
           "Chạy lại 130 perturbation của reference đầu tiên với seed 42; từng repetition/metric giống chính xác. Không refit.")
    per_fold, per_summary = summarize_permutation(permutation)
    errors, messages = summarize_errors(predictions)
    state["warnings"].extend(messages)
    tables = {"full_feature_results.csv": full_results, "ablation_results.csv": ablation,
        "ablation_summary.csv": summarize_ablation(ablation), "permutation_importance.csv": permutation,
        "permutation_fold_summary.csv": per_fold, "permutation_summary.csv": per_summary,
        "validation_predictions.csv": predictions, "error_analysis.csv": errors,
        "notable_errors.csv": notable_errors(predictions), "match_error_analysis.csv": match_error_analysis(predictions),
        "cross_model_errors.csv": cross_model_errors(predictions)}
    validate_tables(tables, development)
    state["tables"] = tables
    record(state, "Ablation và permutation đầy đủ", len(ablation) == 72 and len(permutation) == 1560,
           "72 fresh estimators giữ tham số; 1.560 primary perturbation, n_repeats=10/seed=42, không đổi target hoặc ma trận nguồn.")
    record(state, "Dự báo và Error Analysis", True,
           f"{len(predictions)} dự báo Validation có truy vết; residual/absolute/squared đúng, subgroup counts và cặp Home/Away được kiểm chứng.")
    record(state, "Bảo toàn file cũ", all(sha256(path) == value for path, value in state["protected"].items()),
           f"SHA-256 của {len(state['protected'])} dataset, source, tests, báo cáo và kết quả cũ giữ nguyên.")
    state["output_hashes"] = export_tables(tables)
    record(state, "CSV đọc lại", True, f"Đã đọc lại {len(tables)} bảng CSV, đối chiếu schema và giá trị; file tạm kế thừa ACL thư mục đích.")
    from .visualizations import generate_figures
    state["figures"] = generate_figures(tables, FIGURE_DIR)
    record(state, "Biểu đồ khớp dữ liệu", len(state["figures"]) == 7,
           "Đã đối chiếu heatmap, chiều cao/độ rộng cột, scatter coordinates và histogram bins với bảng nguồn; xuất 7 PNG 220 dpi.")
    manifest = dict(schema_version=1, development_seasons=[2019, 2020, 2021, 2022, 2023], excluded_seasons=sorted(RESERVED_SEASONS),
        features=list(FEATURES), feature_groups={key: list(values) for key, values in FEATURE_GROUPS.items()},
        selected_hyperparameters={name: data["best_params"] for name, data in selected["models"].items()},
        source_sha256=sha256(INPUT_PATH), best_params_sha256=sha256(BEST_PATH), folds=selected["folds"],
        permutation=dict(n_repeats=PERMUTATION_REPEATS, random_state=RANDOM_SEED,
                         stage="after_training_fitted_preprocessing", primary_evaluations=1560,
                         primary_baseline_scores=12, reproducibility_evaluations=130, reproducibility_baseline_scores=1),
        fits=dict(full_feature_regression=12, ablated_regression=72, permutation=0, total_regression=84),
        error_analysis=dict(large_absolute_error=LARGE_ERROR_THRESHOLD, large_lr_xgb_difference=DISAGREEMENT_THRESHOLD,
                            small_sample_n_lt=SMALL_SAMPLE_THRESHOLD, top_absolute_cases_per_model=NOTABLE_CASES),
        metrics=dict(clipping_minimum=0, residual="predicted_xg - actual_xg", std_ddof=STD_DDOF,
                     cv_aggregation="equal_fold_means", error_group_aggregation="pooled_team_match_observations"),
        versions=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                      sklearn=sklearn.__version__, xgboost=xgboost.__version__, matplotlib=matplotlib.__version__, threadpoolctl=threadpoolctl.__version__),
        table_schemas={name: table.dtypes.astype(str).to_dict() for name, table in tables.items()},
        csv_hashes=state["output_hashes"], figures=state["figures"])
    path = OUTPUT_DIR / "analysis_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    require(json.loads(path.read_text(encoding="utf-8")) == manifest, "Manifest đọc lại không khớp.")
    state["manifest"] = manifest
    record(state, "Manifest và bảo toàn cuối", all(sha256(path) == digest for path, digest in state["protected"].items()),
           "Manifest JSON đọc lại khớp; không có model serialization, tuning mới, thay file cũ hoặc đánh giá Final Test.")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    state = dict(protected={path: sha256(path) for path in protected_files()}, checks=[], warnings=[])
    started = time.perf_counter()
    from .reporting import build_report
    try:
        print("Kiểm thử hồi quy và kiểm thử Phase 6...", flush=True)
        execute_tests(state)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_analysis(state)
        state["warnings"].extend(str(message.message) for message in caught)
    except Exception as exc:
        state["elapsed_seconds"] = time.perf_counter() - started
        REPORT_PATH.write_text(build_report(state, f"{type(exc).__name__}: {exc}"), encoding="utf-8")
        print(f"Chưa hoàn tất: {exc}", file=sys.stderr)
        return 1
    state["elapsed_seconds"] = time.perf_counter() - started
    REPORT_PATH.write_text(build_report(state), encoding="utf-8")
    print(f"Hoàn tất: 72 Ablation, 1.560 primary permutation, {len(state['tables']['validation_predictions.csv'])} dự báo Validation.")
    print(f"Tests: {state['tests']['run']} đạt; {len(state['checks'])} kiểm chứng workflow.")
    print(f"Báo cáo: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
