"""Chỉ load artifact từ thư mục backend tin cậy, sau xác minh hash và môi trường."""

import io
import json
from pathlib import Path
import warnings

import joblib
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline

from scripts.prepare_training_features import FEATURES, HISTORY_FEATURES, HistoryMedianImputer
from .common import MODEL_DIR, InferenceError, check, versions


def load_trusted_pipeline(directory=MODEL_DIR, *, trusted_directory=MODEL_DIR):
    directory, trusted = Path(directory).resolve(), Path(trusted_directory).resolve()
    check(directory == trusted, "UNTRUSTED_ARTIFACT", "Không load artifact từ đường dẫn/upload không được backend tin cậy.")
    artifact, metadata_path = directory/"laliga_lr_pipeline.joblib", directory/"model_metadata.json"
    check(artifact.is_file() and metadata_path.is_file(), "ARTIFACT_MISSING", "Thiếu model artifact hoặc metadata. Chạy export tường minh.")
    check(artifact.resolve().parent == trusted and metadata_path.resolve().parent == trusted,
          "UNTRUSTED_ARTIFACT", "Không cho phép symlink thoát thư mục trusted.")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        data = artifact.read_bytes()
        import hashlib
        check(hashlib.sha256(data).hexdigest() == metadata["artifact_sha256"], "ARTIFACT_CORRUPT", "Checksum artifact không khớp metadata tin cậy.")
        check(metadata["schema_version"] == 1 and metadata["features"] == list(FEATURES)
              and metadata["model"] == "Linear Regression" and metadata["target"] == "xg"
              and metadata["clipping_policy"] == "maximum(0,raw_prediction)", "ARTIFACT_INCOMPATIBLE", "Metadata/schema không tương thích.")
        check(metadata["environment"] == versions(), "ENVIRONMENT_INCOMPATIBLE", "Python/dependencies khác môi trường export; tái tạo môi trường đã pin trước khi load.")
        # Bytes đã hash được load từ chính buffer, tránh đọc lại file sau kiểm tra.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pipeline = joblib.load(io.BytesIO(data))
        check(type(pipeline) is Pipeline and set(pipeline.named_steps) == {"preprocessing","model"}
              and type(pipeline.named_steps["model"]) is LinearRegression, "ARTIFACT_INCOMPATIBLE", "Sai kiểu pipeline/estimator.")
        estimator = pipeline.named_steps["model"]
        imputer = pipeline.named_steps["preprocessing"].named_steps["median"]
        check(type(imputer) is HistoryMedianImputer and imputer.n_samples_fit_ == 3800
              and list(estimator.feature_names_in_) == list(FEATURES)
              and estimator.get_params(deep=False) == metadata["effective_estimator_parameters"], "ARTIFACT_INCOMPATIBLE", "Sai trạng thái fitted/schema/params.")
        check(np.array_equal(estimator.coef_, metadata["coefficients"]) and estimator.intercept_ == metadata["intercept"]
              and np.array_equal(imputer.imputer_.statistics_, [metadata["imputation_statistics"][f] for f in HISTORY_FEATURES]),
              "ARTIFACT_CORRUPT", "Fitted parameters hoặc median không khớp metadata.")
        return pipeline, metadata
    except InferenceError:
        raise
    except Exception as exc:
        raise InferenceError("ARTIFACT_CORRUPT", "Không đọc được artifact/metadata hợp lệ.") from exc
