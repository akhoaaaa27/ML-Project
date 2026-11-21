"""Lệnh export LR tường minh; không chạy khi suy luận hoặc khởi động ứng dụng."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression
from threadpoolctl import threadpool_limits

from scripts.prepare_training_features import FEATURES, HISTORY_FEATURES, ROOT, INPUT_PATH, load_dataset, prepare_features
from .common import MODEL_DIR, MODEL_VERSION, check, sha256, utc_now, versions, write_json, cli_output

DEV_SEASONS = (2019, 2020, 2021, 2022, 2023)
REFERENCE_FILES = ("outputs/tuning/best_params.json", "outputs/final_test/evaluation_protocol.json",
                   "outputs/final_test/final_test_predictions.csv", "outputs/final_test/final_test_manifest.json")


def train_production_pipeline():
    # Chỉ export phụ thuộc research helper; runtime loading không import XGBoost/tuning.
    from scripts.training.tune_models import build_pipeline
    full = load_dataset()
    check(full.shape == (4700, 26), "TRAINING_DATA_MISMATCH", "Dataset khác snapshot đã đánh giá.")
    selected = json.loads((ROOT/REFERENCE_FILES[0]).read_text(encoding="utf-8"))
    protocol = json.loads((ROOT/REFERENCE_FILES[1]).read_text(encoding="utf-8"))
    check(sha256(INPUT_PATH) == selected["dataset_sha256"] == protocol["dataset"]["sha256"]
          and sha256(ROOT/REFERENCE_FILES[0]) == protocol["best_params_sha256"],
          "TRAINING_DATA_MISMATCH", "Dataset hoặc best parameters không khớp Phase 7.")
    check(selected["features"] == protocol["features"] == list(FEATURES) and selected["target"] == "xg",
          "FEATURE_SCHEMA_MISMATCH", "Schema khác nghiên cứu đóng băng.")
    config = selected["models"]["Linear Regression"]
    template = LinearRegression(**config["fixed_parameters"], **config["best_params"])
    check(template.get_params(deep=False) == protocol["effective_estimator_parameters"]["Linear Regression"],
          "PARAMETER_MISMATCH", "Effective LR parameters khác Phase 7.")
    dev = full.loc[full.season.isin(DEV_SEASONS)].sort_values(["date", "match_id", "is_home"], kind="stable")
    check(len(dev) == 3800 and set(dev.season) == set(DEV_SEASONS) and dev.match_id.nunique() == 1900,
          "TRAINING_DATA_MISMATCH", "Phải đúng 3.800 Development rows / 1.900 trận.")
    X, y, restoration = prepare_features(dev)
    pipeline = build_pipeline(template)
    with threadpool_limits(limits=1):
        pipeline.fit(X, y)  # Một production fit, chỉ Development.
    imputer = pipeline.named_steps["preprocessing"].named_steps["median"]
    check(imputer.n_samples_fit_ == 3800 and np.array_equal(imputer.imputer_.statistics_, X[list(HISTORY_FEATURES)].median().to_numpy()),
          "TRAINING_DATA_MISMATCH", "Median không phải Development-only.")
    estimator = pipeline.named_steps["model"]
    check(list(estimator.feature_names_in_) == list(FEATURES), "FEATURE_SCHEMA_MISMATCH", "Sai thứ tự X.")
    metadata = dict(schema_version=1, model="Linear Regression", model_version=MODEL_VERSION, target="xg",
        target_semantics="total_team_match_xg_not_shot_probability", features=list(FEATURES),
        training_seasons=list(DEV_SEASONS), training_observations=len(X), training_matches=1900,
        training_start=str(dev.date.min()), training_end=str(dev.date.max()), estimator_fit_calls=1, imputer_fit_calls=1,
        effective_estimator_parameters=estimator.get_params(deep=False),
        imputation_statistics=dict(zip(HISTORY_FEATURES, imputer.imputer_.statistics_.tolist())),
        restored_training_cells=restoration.restored_cells, coefficients=estimator.coef_.tolist(), intercept=float(estimator.intercept_),
        clipping_policy="maximum(0,raw_prediction)", dataset_sha256=sha256(INPUT_PATH),
        parameter_file_sha256=sha256(ROOT/REFERENCE_FILES[0]),
        research_references={name: sha256(ROOT/name) for name in REFERENCE_FILES}, environment=versions(),
        serialization=dict(format="joblib", compression=3, pickle_protocol=5, cross_environment_byte_identity_promised=False),
        custom_transformer="scripts.prepare_training_features.HistoryMedianImputer")
    return pipeline, metadata, X


def export_pipeline(directory=MODEL_DIR):
    directory = Path(directory)
    artifact, metadata_path = directory/"laliga_lr_pipeline.joblib", directory/"model_metadata.json"
    check(not artifact.exists() and not metadata_path.exists(), "ARTIFACT_EXISTS", "Artifact/metadata đã tồn tại; không ghi đè, không fit lại.")
    pipeline, metadata, X = train_production_pipeline()
    first = io.BytesIO()
    joblib.dump(pipeline, first, compress=3, protocol=5)
    second = io.BytesIO()
    joblib.dump(pipeline, second, compress=3, protocol=5)
    check(first.getvalue() == second.getvalue(), "SERIALIZATION_MISMATCH", "Hai lần serialize cùng fitted object không khớp trong môi trường này.")
    metadata["same_object_serialization_byte_identical"] = True
    directory.mkdir(parents=True, exist_ok=True)
    # x mode: không ghi đè. Nếu xuất dở, loader từ chối vì thiếu metadata; không tự retrain.
    with artifact.open("xb") as handle:
        handle.write(first.getvalue())
    metadata.update(artifact_filename=artifact.name, artifact_sha256=sha256(artifact), exported_at=utc_now())
    write_json(metadata_path, metadata, exclusive=True)
    from .model_artifact import load_trusted_pipeline
    loaded, _ = load_trusted_pipeline(directory, trusted_directory=directory)
    np.testing.assert_array_equal(pipeline.predict(X), loaded.predict(X))
    return dict(status="success", artifact=str(artifact), metadata=str(metadata_path),
                artifact_sha256=metadata["artifact_sha256"], training_observations=3800, model="Linear Regression")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=MODEL_DIR, help="Đích trusted do quản trị chọn, không lấy từ HTTP request.")
    args=parser.parse_args()
    return cli_output(lambda: export_pipeline(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
