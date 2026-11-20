"""Thí nghiệm CV ba fold và năm phương pháp; không chọn hoặc lưu Final Model.

Chạy từ workspace: python -m scripts.training.train_models
Mỗi lần gọi thực thi hai lượt độc lập để kiểm tra khả năng tái lập.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import warnings

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.base import clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.tree import DecisionTreeRegressor
import threadpoolctl
from threadpoolctl import threadpool_limits

from scripts.prepare_training_features import (
    FEATURES, HISTORY_FEATURES, INPUT_PATH, PASSTHROUGH_FEATURES, REQUIRED_COLUMNS,
    ROOT, load_dataset, make_preprocessor, prepare_features, read_history_config,
)
from .cross_validation import DEFAULT_FOLDS, RESERVED_SEASONS, make_season_folds


OUTPUT_DIR = ROOT / "outputs/training"
REPORT_PATH = ROOT / "Phases/Implement Expanding Window Cross-Validation and Initial Model Training.md"
MODEL_NAMES = ("Historical Baseline", "Linear Regression", "Decision Tree", "Random Forest", "XGBoost")
STD_DDOF = 0


@dataclass
class ExperimentResult:
    fold_results: pd.DataFrame
    summary: pd.DataFrame
    predictions: dict[tuple[int, str], np.ndarray]
    checks: list[tuple[str, bool, str]]
    fold_audits: list[dict]
    parameters: dict[str, dict]
    warnings: list[str]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def model_templates() -> dict:
    try:
        from xgboost import XGBRegressor
    except (ImportError, OSError) as exc:
        raise RuntimeError("Không dùng được XGBoost. Cài dependency bằng python -m pip install -r "
                           "scripts/training/requirements.txt trong môi trường đang chạy; không thay bằng thuật toán khác.") from exc
    # Cấu hình cơ bản cố định trước khi quan sát metrics; không tuning.
    return {
        "Linear Regression": LinearRegression(n_jobs=1),
        "Decision Tree": DecisionTreeRegressor(random_state=42),
        "Random Forest": RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1),
        "XGBoost": XGBRegressor(objective="reg:squarederror", random_state=42,
                                n_estimators=100, max_depth=6, learning_rate=0.3,
                                tree_method="hist", device="cpu", n_jobs=1),
    }


def evaluate_predictions(y: pd.Series, raw_predictions: np.ndarray) -> tuple[dict, np.ndarray]:
    raw = np.asarray(raw_predictions, dtype=float)
    target = np.asarray(y, dtype=float)
    _require(raw.ndim == 1 and raw.shape == target.shape and len(raw) > 0, "Dự báo không khớp target.")
    _require(np.isfinite(raw).all() and np.isfinite(target).all(), "Target hoặc dự báo có NaN/vô hạn.")
    prediction = np.maximum(0.0, raw)
    metrics = dict(mae=float(mean_absolute_error(target, prediction)),
                   rmse=float(root_mean_squared_error(target, prediction)),
                   negative_predictions=int((raw < 0).sum()),
                   min_prediction_before_clip=float(raw.min()),
                   min_prediction_after_clip=float(prediction.min()))
    _require(np.isfinite(list(metrics.values())).all() and prediction.min() >= 0, "Metric hoặc dự báo sau clipping không hợp lệ.")
    return metrics, prediction


def summarize_results(results: pd.DataFrame) -> pd.DataFrame:
    _require(len(results) == len(MODEL_NAMES) * len(DEFAULT_FOLDS), "Cần đúng 15 kết quả model-fold.")
    _require(not results.duplicated(["fold", "model"]).any(), "Trùng kết quả model-fold.")
    _require(set(results.model) == set(MODEL_NAMES) and set(results.fold) == {1, 2, 3}, "Sai tập model hoặc fold.")
    _require(results.groupby("model").size().eq(3).all(), "Mỗi model cần đủ ba fold.")
    _require(np.isfinite(results[["mae", "rmse"]].to_numpy()).all(), "Kết quả có metric không hữu hạn.")
    rows = []
    for name in MODEL_NAMES:
        group = results.loc[results.model.eq(name)]
        rows.append(dict(model=name, mean_mae=float(group.mae.mean()),
                         std_mae=float(group.mae.std(ddof=STD_DDOF)),
                         mean_rmse=float(group.rmse.mean()),
                         std_rmse=float(group.rmse.std(ddof=STD_DDOF))))
    summary = pd.DataFrame(rows).sort_values(["mean_mae", "mean_rmse", "model"], kind="stable").reset_index(drop=True)
    summary["rank"] = summary.mean_mae.rank(method="min", ascending=True).astype(int)
    return summary


def run_experiment(data: pd.DataFrame, templates: dict | None = None) -> ExperimentResult:
    """Chạy một lượt; templates tùy chọn phục vụ kiểm thử, CLI luôn dùng bốn model thật."""
    templates = model_templates() if templates is None else templates
    _require(set(templates) == set(MODEL_NAMES[1:]), "Cần đủ bốn estimator đúng tên, không thay XGBoost âm thầm.")
    checks, rows, fold_audits, predictions, emitted_warnings = [], [], [], {}, []
    parameters = {name: model.get_params(deep=False) for name, model in templates.items()}
    preprocessors = []  # Giữ instance để xác nhận không dùng lại giữa các fold.

    def record(name: str, condition: bool, detail: str):
        checks.append((name, bool(condition), detail))
        _require(bool(condition), f"{name}: {detail}")

    record("Schema và dữ liệu nguồn", list(data.columns) == list(REQUIRED_COLUMNS)
           and not data.duplicated().any(), f"{len(data)} dòng, {len(data.columns)} cột, {data.match_id.nunique()} trận; schema đúng, không dòng trùng.")
    read_history_config()  # Kiểm tra shift(1)/rolling/prior từ code, không chạy Feature Engineering.
    record("Công thức lịch sử", True, "Đã kiểm tra code shift(1), rolling và prior qua API hiện có; không tính lại rolling averages.")
    folds = make_season_folds(data)
    for fold in folds:
        train = data.iloc[fold.train_indices].copy()
        validation = data.iloc[fold.validation_indices].copy()
        prefix = f"Fold {fold.fold}"
        record(f"{prefix}: mùa, ngày và cặp trận", not (set(train.season) | set(validation.season)) & RESERVED_SEASONS
               and set(train.match_id).isdisjoint(validation.match_id),
               f"Train {fold.spec.train_seasons}, {fold.train_start} → {fold.train_end}; Validation {fold.spec.validation_season}, {fold.validation_start} → {fold.validation_end}; splitter đã kiểm tra đầy đủ cặp trận.")
        X_train, y_train, train_audit = prepare_features(train)
        X_val, y_val, val_audit = prepare_features(validation)
        record(f"{prefix}: 13 features và target", list(X_train.columns) == list(FEATURES)
               and list(X_val.columns) == list(FEATURES) and len(FEATURES) == 13
               and "xg" not in X_train and y_train.equals(train.xg) and y_val.equals(validation.xg),
               "X chỉ có 13 features theo thứ tự; y=xg giữ nguyên, không chứa metadata hoặc thống kê hiện trận.")
        preprocessor = make_preprocessor()
        record(f"{prefix}: imputer mới", all(preprocessor is not p for p in preprocessors), "Tạo instance mới cho fold; không dùng chung trạng thái đã fit.")
        preprocessors.append(preprocessor)
        preprocessor.fit(X_train)
        median_estimator = preprocessor.named_steps["median"]
        medians = median_estimator.imputer_.statistics_.copy()
        record(f"{prefix}: fit median Train-only", np.array_equal(medians, X_train.loc[:, list(HISTORY_FEATURES)].median().to_numpy())
               and median_estimator.n_samples_fit_ == len(train)
               and list(median_estimator.imputer_.feature_names_in_) == list(HISTORY_FEATURES),
               f"Fit đúng {len(train)} dòng Train; tám median khớp phép tính độc lập trên Train.")
        processed_train = preprocessor.transform(X_train)
        processed_val = preprocessor.transform(X_val)
        for label, before, after in (("Train", X_train, processed_train), ("Validation", X_val, processed_val)):
            record(f"{prefix}: toàn vẹn {label}", before.shape == after.shape and before.index.equals(after.index)
                   and list(after.columns) == list(FEATURES) and np.isfinite(after.to_numpy(dtype=float)).all()
                   and after.where(before.notna()).equals(before.where(before.notna()))
                   and before.loc[:, list(PASSTHROUGH_FEATURES)].equals(after.loc[:, list(PASSTHROUGH_FEATURES)]),
                   f"{len(after)} dòng × 13 features hữu hạn; index, ô hợp lệ và năm features còn lại giữ nguyên.")
        shifted_validation = X_val.copy(deep=True)
        shifted_validation.loc[:, list(HISTORY_FEATURES)] += 1_000_000
        shifted_result = preprocessor.transform(shifted_validation)
        record(f"{prefix}: Validation không cập nhật median", np.array_equal(medians, median_estimator.imputer_.statistics_)
               and all(shifted_result.loc[X_val[c].isna(), c].eq(m).all() for c, m in zip(HISTORY_FEATURES, medians)),
               "Sau transform và dịch phân phối Validation thêm 1.000.000, statistics_ và giá trị điền vẫn dùng median Train.")
        fold_audits.append(dict(fold=fold.fold, train_samples=len(train), validation_samples=len(validation),
            train_seasons=list(fold.spec.train_seasons), validation_season=fold.spec.validation_season,
            train_start=fold.train_start, train_end=fold.train_end,
            validation_start=fold.validation_start, validation_end=fold.validation_end,
            train_restored_cells=train_audit.restored_cells, validation_restored_cells=val_audit.restored_cells,
            medians=dict(zip(HISTORY_FEATURES, medians.tolist()))))
        for name in MODEL_NAMES:
            if name == "Historical Baseline":
                raw_prediction = processed_val.xg_avg5.to_numpy()
            else:
                model = clone(templates[name])
                record(f"{prefix}: tham số {name}", _canonical(model.get_params(deep=False)) == _canonical(parameters[name]),
                       "Clone giữ nguyên cấu hình cố định qua các fold.")
                record(f"{prefix}: fit {name} chỉ nhận Train", processed_train.index.equals(train.index)
                       and y_train.index.equals(train.index) and processed_train.index.intersection(validation.index).empty,
                       f"fit(X_train_processed, y_train), {len(processed_train)} dòng × 13 features; không eval_set hoặc y_validation.")
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    with threadpool_limits(limits=1):
                        model.fit(processed_train, y_train)
                        raw_prediction = model.predict(processed_val)
                emitted_warnings.extend(f"{prefix}/{name}: {w.message}" for w in caught)
                record(f"{prefix}: đầu vào estimator {name}", model.n_features_in_ == 13,
                       "Estimator đã fit nhận đúng 13 features.")
            metrics, prediction = evaluate_predictions(y_val, raw_prediction)
            record(f"{prefix}: dự báo và metric {name}", np.isfinite(prediction).all() and (prediction >= 0).all(),
                   f"MAE/RMSE hữu hạn; {metrics['negative_predictions']} dự báo âm trước clipping, không còn âm sau clipping.")
            predictions[(fold.fold, name)] = prediction.copy()
            rows.append(dict(fold=fold.fold, train_seasons=";".join(map(str, fold.spec.train_seasons)),
                validation_season=fold.spec.validation_season, model=name,
                train_samples=len(train), validation_samples=len(validation), **metrics))
    fold_results = pd.DataFrame(rows)
    summary = summarize_results(fold_results)
    record("Đủ kết quả và bảo vệ Final Test", len(fold_results) == 15 and len(summary) == 5
           and set(fold_results.validation_season).isdisjoint(RESERVED_SEASONS),
           "15 tổ hợp, 5 model; chỉ dùng Train 2019–2022 và Validation 2021–2023.")
    return ExperimentResult(fold_results, summary, predictions, checks, fold_audits, parameters, emitted_warnings)


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, float_format="%.17g", lineterminator="\n").encode("utf-8")


def verify_reproducibility(first: ExperimentResult, second: ExperimentResult) -> None:
    pd.testing.assert_frame_equal(first.fold_results, second.fold_results, check_exact=True)
    pd.testing.assert_frame_equal(first.summary, second.summary, check_exact=True)
    _require(_canonical(first.parameters) == _canonical(second.parameters), "Tham số thay đổi giữa hai lượt.")
    _require(_canonical(first.fold_audits) == _canonical(second.fold_audits), "Audit hoặc median khác giữa hai lượt.")
    _require(first.predictions.keys() == second.predictions.keys() and all(
        np.array_equal(values, second.predictions[key]) for key, values in first.predictions.items()),
        "Dự báo khác giữa hai lượt thí nghiệm.")
    _require(csv_bytes(first.fold_results) == csv_bytes(second.fold_results)
             and csv_bytes(first.summary) == csv_bytes(second.summary), "CSV không tái lập từng byte.")


def export_results(result: ExperimentResult, output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    """Kiểm tra file tạm cạnh đầu ra để giữ quyền kế thừa của thư mục trên Windows."""
    pd.testing.assert_frame_equal(summarize_results(result.fold_results), result.summary, check_exact=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    digests = {}
    staged = []
    try:
        for name, frame in (("cv_fold_results.csv", result.fold_results), ("cv_summary.csv", result.summary)):
            # TemporaryDirectory có ACL riêng trên Windows; rename file ra ngoài
            # sẽ mang theo ACL đó. Tạo trực tiếp cạnh đầu ra để kế thừa quyền đúng.
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".cv-", suffix=".tmp", delete=False) as handle:
                path = Path(handle.name)
            staged.append((path, output_dir / name))
            payload = csv_bytes(frame)
            path.write_bytes(payload)
            loaded = pd.read_csv(path)
            pd.testing.assert_frame_equal(frame, loaded, check_dtype=False, check_exact=False, rtol=1e-14, atol=1e-14)
            digests[name] = hashlib.sha256(payload).hexdigest()
        for source, target in staged:
            os.replace(source, target)
    finally:
        for source, _ in staged:
            source.unlink(missing_ok=True)
    return digests


def _table(frame: pd.DataFrame, decimals: int = 6) -> list[str]:
    lines = ["| " + " | ".join(map(str, frame.columns)) + " |", "|" + "---|" * len(frame.columns)]
    for row in frame.itertuples(index=False, name=None):
        values = [f"{v:.{decimals}f}" if isinstance(v, (float, np.floating)) else str(v) for v in row]
        lines.append("| " + " | ".join(v.replace("|", "/") for v in values) + " |")
    return lines


def build_report(state: dict, error: str | None = None) -> str:
    result = state.get("result")
    lines = ["# Expanding Window Cross-Validation và huấn luyện mô hình ban đầu", "",
        "## 1. Mục tiêu và phạm vi", "",
        "Triển khai ba fold theo mùa, tái sử dụng Median Imputation hiện có và so sánh Historical Baseline với bốn thuật toán Regression. Chỉ huấn luyện ban đầu: không Hyperparameter Tuning, Feature Selection, Ablation Study, Final Test, chọn Final Model hoặc lưu model.", "",
        "## 2. Cấu trúc thư mục và kiểm tra mã nguồn", "",
        "Trước tác vụ: `data/` chứa bốn dataset và preprocess_laliga.py; `scripts/` chứa hai script chuẩn hóa/chuẩn bị features; `Phases/` chứa hai báo cáo cũ. Không có module training tương đương. Giữ nguyên vị trí và nội dung các file này.", "",
        "Bổ sung:", "", "```text", "scripts/training/", "  __init__.py", "  cross_validation.py",
        "  train_models.py", "  requirements.txt", "tests/", "  test_training.py", "outputs/training/",
        "  cv_fold_results.csv", "  cv_summary.csv", "Phases/",
        f"  {REPORT_PATH.name}", "```", "",
        "Đã đọc preprocessing, chuẩn hóa, module chuẩn bị features và báo cáo trong Phases/. Các API load_dataset(), prepare_features(), make_preprocessor() hoạt động đúng chữ ký đã mô tả. Điểm khác tài liệu hiện tại: REPORT_PATH của script chuẩn bị features cũ vẫn trỏ vào data/ mặc dù báo cáo đã được chuyển sang Phases/. Tác vụ chỉ import API, không gọi CLI của script cũ và không sửa preprocessing; báo cáo mới luôn ở Phases/.", "",
        "## 3. Dataset, features và target", ""]
    if "dataset" in state:
        info = state["dataset"]
        lines += [f"Nguồn `data/laliga_processed_normalized.csv`: **{info['rows']} dòng, {info['columns']} cột, {info['matches']} trận**, mỗi trận hai dòng. Không có missing ban đầu; load_dataset đã kiểm tra kiểu số, tính hữu hạn và sự nhất quán hai phía.", "",
                  "| Thứ tự | Feature |", "|---|---|"]
        lines += [f"| {i} | `{c}` |" for i, c in enumerate(FEATURES, 1)]
        lines += ["", "Target riêng: y=xg. Không có season, date, match_id, team, opponent, gf, ga, sh, sot, xga hoặc xg trong X.", "",
                  "### Mã mùa và số dòng quan sát", ""]
        lines += _table(pd.DataFrame(info["seasons"]))
    lines += ["", "## 4. Expanding Window và Median Imputation", "",
        "cross_validation.py chọn bằng season, không dùng thứ tự CSV để chia. Indices iloc được sắp theo date, match_id và is_home trong bộ nhớ. Kiểm tra mùa tăng, ngày cuối Train < ngày đầu Validation, không chung dòng hoặc match_id, đủ hai bản ghi cùng trận trong một tập. SeasonExpandingWindowCV tương thích giao diện splitter của scikit-learn; để tái sử dụng với X không có metadata, tạo list(cv.split(metadata)) trong cùng thứ tự dòng.", "",
        "Mỗi fold gọi prepare_features() riêng cho Train và Validation, chỉ khôi phục các prior đã xác minh. Tạo make_preprocessor() mới; fit(X_train), transform hai tập rồi dùng 13 features đã xử lý cho tất cả phương pháp. Tám median được đối chiếu phép tính độc lập từ Train; năm features còn lại và các giá trị hợp lệ được giữ nguyên.", "",
        "### Ranh giới thực tế", ""]
    if result is not None:
        columns = ["fold", "train_seasons", "validation_season", "train_samples", "validation_samples",
                   "train_start", "train_end", "validation_start", "validation_end",
                   "train_restored_cells", "validation_restored_cells"]
        frame = pd.DataFrame(result.fold_audits)
        lines += _table(frame.loc[:, columns])
        lines += ["", "### Tám median học riêng từ Train", ""]
        lines += _table(pd.DataFrame([dict(feature=c, **{f"fold_{a['fold']}": a['medians'][c]
                     for a in result.fold_audits}) for c in HISTORY_FEATURES]))
    lines += ["", "## 5. Kiểm soát Data Leakage và giả định dự báo", "",
        "Dự báo trước từng trận theo trình tự thời gian: các trận đã kết thúc trước trận cần dự báo có thể cung cấp lịch sử, kể cả trận trước đó trong cùng mùa Validation. Không giả định dự báo đồng thời cả mùa ngay từ đầu mùa. Module hiện có kiểm tra code shift(1) trước rolling; tác vụ không tính lại rolling hoặc kiểm toán lại toàn bộ Feature Engineering. Dataset và mã nguồn lịch sử được bảo toàn bằng SHA-256.", "",
        "Season 2024 (Final Test) và 2025 (Supplemental Test) chỉ được đọc trong kiểm tra schema/toàn vẹn nguồn; không nằm trong bất kỳ tập fit, prediction, metric hoặc so sánh thí nghiệm nào. Không early stopping, eval_set, fit Validation hoặc điều chỉnh tham số theo kết quả Validation. Trong code, estimator.fit chỉ nhận processed_train và y_train; kiểm chứng độc lập ghi nhận indices thực tế của các lệnh fit.", "",
        "## 6. Thuật toán, tham số và quy tắc dự báo", "",
        "Cấu hình đã cố định trước khi quan sát metrics; giữ nguyên qua ba fold:", "",
        "- Historical Baseline: lấy xg_avg5 sau imputation theo fold, không fit estimator hoặc học y_validation.",
        "- LinearRegression(n_jobs=1); các tham số khác mặc định.",
        "- DecisionTreeRegressor(random_state=42); các tham số khác mặc định.",
        "- RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1); các tham số khác mặc định.",
        "- XGBRegressor(objective=\"reg:squarederror\", random_state=42, n_estimators=100, max_depth=6, learning_rate=0.3, tree_method=\"hist\", device=\"cpu\", n_jobs=1); các tham số khác mặc định. Không early stopping.",
        "- threadpool_limits(limits=1) khi fit/predict estimator để hạn chế biến động do song song BLAS/OpenMP.", "",
        "Mọi phương pháp đều dùng prediction=max(0,prediction) trước MAE và RMSE. Số dự báo âm được đếm trước clipping; không áp trần trên. Với target xG không âm, clipping loại các giá trị dự báo không hợp lệ và không làm tăng sai số tuyệt đối hoặc bình phương tại các điểm bị cắt. So sánh trong báo cáo và CSV đều là kết quả sau clipping.", ""]
    if result is not None:
        lines += ["### Tham số thực tế đầy đủ từ get_params()", "", "```json",
                  json.dumps(result.parameters, indent=2, ensure_ascii=False, sort_keys=True, default=str), "```", ""]
    lines += ["## 7. Môi trường và lệnh thực thi", "",
        f"Python {platform.python_version()}; NumPy {np.__version__}; Pandas {pd.__version__}; SciPy {scipy.__version__}; scikit-learn {sklearn.__version__}; threadpoolctl {threadpoolctl.__version__}.",
        f"XGBoost: {state.get('xgboost_version', 'chưa nạp thành công')}. Môi trường .venv nằm trong workspace, kế thừa các package sẵn có bằng --system-site-packages. Dependency đã dùng được ghim tại scripts/training/requirements.txt.", "",
        "Các lệnh thiết lập và thực thi:", "", "```powershell", "python -m venv --system-site-packages .venv",
        ".\\.venv\\Scripts\\python.exe -m pip install --disable-pip-version-check --no-cache-dir xgboost",
        ".\\.venv\\Scripts\\python.exe -m scripts.training.train_models", "```", "",
        "Tái tạo môi trường trên máy khác: tạo venv và dùng python -m pip install -r scripts/training/requirements.txt, sau đó python -m scripts.training.train_models bằng interpreter đã có dependency. Không cần kích hoạt môi trường nếu gọi trực tiếp interpreter trong .venv.", "",
        "## 8. Kết quả từng fold", ""]
    if result is not None:
        lines += _table(result.fold_results)
        lines += ["", "## 9. Tổng hợp và so sánh ban đầu", "",
                  "Trung bình ba fold có trọng số bằng nhau. Standard deviation dùng quy ước tổng thể ddof=0 cho cả MAE và RMSE; RMSE là căn MSE. Rank dựa Mean MAE tăng dần; Mean MAE bằng nhau được cùng rank, Mean RMSE chỉ hỗ trợ sắp thứ tự.", ""]
        lines += _table(result.summary)
        best = result.summary.iloc[0]
        baseline = result.summary.loc[result.summary.model.eq("Historical Baseline")].iloc[0]
        runner_up = result.summary.iloc[1]
        improvement = float(baseline.mean_mae - best.mean_mae)
        lines += ["", f"**{best.model}** có Mean MAE thấp nhất trong cấu hình ban đầu: **{best.mean_mae:.6f}**; Mean RMSE **{best.mean_rmse:.6f}**. So với Historical Baseline (Mean MAE {baseline.mean_mae:.6f}), chênh lệch giảm MAE là {improvement:.6f} ({100 * improvement / baseline.mean_mae:.2f}%).",
                  f"Chênh lệch Mean MAE với phương pháp đứng kế tiếp ({runner_up.model}) là {runner_up.mean_mae - best.mean_mae:.6f}. Ba fold chưa đủ để suy ra khác biệt có ý nghĩa thống kê; các mùa cũng có phân phối và độ khó khác nhau. Cần xét cả kết quả từng fold, RMSE và độ biến động thay vì chỉ rank.",
                  "Đây chỉ là phương pháp có kết quả ban đầu tốt nhất trong thí nghiệm đã chạy, chưa phải Final Model. Không chỉnh tham số sau khi quan sát bảng kết quả.", ""]
    lines += ["## 10. Kiểm chứng thực thi và khả năng tái lập", ""]
    if result is not None:
        lines += [f"Lượt thí nghiệm thứ nhất ghi nhận {len(result.checks)} kiểm chứng đạt; lượt thứ hai lặp lại toàn bộ fit/predict với dữ liệu đọc lại từ nguồn.", ""]
        lines += _table(pd.DataFrame(result.checks, columns=["Kiểm chứng", "Đạt", "Bằng chứng"]))
    lines += ["", f"Tái lập hai lượt: **{state.get('reproducibility', 'chưa xác nhận')}**. Kiểm tra chính xác DataFrame metrics, summary, tham số, audit, medians, mọi mảng dự báo và byte CSV; không dùng tolerance cho so sánh giữa hai lượt.", ""]
    if "output_hashes" in state:
        lines += _table(pd.DataFrame([dict(file=k, sha256=v) for k, v in state["output_hashes"].items()]))
        lines += ["", "Hai CSV đã được ghi bằng code và đọc lại kiểm tra schema, số dòng và giá trị. Dùng 17 chữ số có nghĩa khi ghi; đối chiếu lần đọc mặc định cho phép sai số phân tích số thực 1e-14. Không chỉnh tay kết quả."]
    lines += ["", "## 11. Bảo toàn file và tóm tắt thay đổi", "",
        "Tạo hai module training, package marker, requirements và một file kiểm thử độc lập. Tạo/cập nhật hai CSV trong outputs/training/ và chính báo cáo này trong Phases/. Không di chuyển file cũ, không tạo outputs/models/, outputs/figures/, app/ hoặc thư mục rỗng.", "",
        "| File có sẵn | SHA-256 trước thực thi | Sau thực thi |", "|---|---|---|"]
    for path, digest in state["protected"].items():
        matches = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        lines.append(f"| `{path.relative_to(ROOT).as_posix()}` | `{digest}` | {'Giữ nguyên' if matches else 'Không khớp'} |")
    lines += ["", "## 12. Cảnh báo và vấn đề", "",
        "Đã sửa lỗi quyền file trên Windows ở hàm export_results: file xuất từ TemporaryDirectory trước đây có thể mang ACL riêng của tài khoản tạo thư mục, khiến VS Code hoặc Git của tài khoản người dùng bị Permission denied. File tạm hiện được tạo trực tiếp cạnh đầu ra để kế thừa ACL của outputs/training/; vẫn kiểm tra trước khi os.replace. Hai CSV đã có được bật lại quyền kế thừa; nội dung kết quả không đổi.", "",
        "XGBoost ban đầu chưa có trong interpreter hệ thống. Lần tải trong sandbox bị chặn kết nối; đã cài thành công XGBoost 3.4.1 vào .venv sau khi được cấp quyền tải. Kiểm tra tương thích fit/predict trên dữ liệu nhân tạo đã chạy trước thí nghiệm chính; không thay thế thuật toán. Thí nghiệm chính dùng đúng cấu hình cố định nêu trên.", ""]
    if result is not None:
        lines += result.warnings if result.warnings else ["Không có cảnh báo từ các lệnh fit/predict estimator trong thí nghiệm."]
    if error:
        lines += ["", "**Chưa hoàn tất:**", "", "```text", error, "```",
                  "Chỉ các kết quả và kiểm chứng đã ghi mới được xác nhận; không coi lỗi hoặc kết quả thiếu là thành công. Các CSV cũ không bị thay thế khi thí nghiệm hoặc đối chiếu tái lập thất bại."]
    else:
        lines += ["", "Không có vấn đề chặn hoàn thành trong phạm vi thí nghiệm. Hạn chế: chỉ ba mùa Validation, hai dòng cùng trận có tương quan, không báo khoảng tin cậy hoặc kiểm định thống kê. Chưa có kết quả Final Test. Kiểm tra rolling giới hạn ở logic code và bảo toàn nguồn, không tái tính toàn bộ features."]
    lines += ["", "## 13. Tài liệu kỹ thuật đối chiếu", "",
        "API và cấu hình XGBRegressor: [tài liệu XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html#xgboost.XGBRegressor).",
        "RMSE dùng API căn sai số bình phương: [tài liệu scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.root_mean_squared_error.html).", "",
        "## 14. Kết luận và hướng tiếp theo", "",
        ("Chưa thể xác nhận hoàn thành; xem nguyên nhân và kết quả còn thiếu ở trên." if error else
         "Đã hoàn tất framework Expanding Window, so sánh đủ năm phương pháp trên ba fold, xuất 15 kết quả và bảng tổng hợp, đồng thời xác minh tái lập. Các dataset, preprocessing và báo cáo cũ được giữ nguyên. Không lưu estimator đã fit hoặc chọn Final Model."), "",
        "Giai đoạn sau có thể xây dựng kế hoạch Hyperparameter Tuning trên chính các fold Train/Validation này và giữ Final Test tách biệt; chưa thực hiện tuning hoặc bước tiếp theo khi chưa có yêu cầu rõ ràng của người dùng."]
    return "\n".join(lines) + "\n"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    old_paths = [ROOT / p for p in ("data/matches_laliga.csv", "data/laliga_processed.csv",
        "data/laliga_processed.xlsx", "data/laliga_processed_normalized.csv", "data/preprocess_laliga.py",
        "scripts/normalize_laliga_numeric.py", "scripts/prepare_training_features.py",
        "Phases/Normalize Numeric Formats in the La Liga Dataset.md",
        "Phases/Prepare Leakage-Safe Median Imputation for La Liga.md")]
    state = {"protected": {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in old_paths}}
    try:
        import xgboost
        state["xgboost_version"] = xgboost.__version__
        data = load_dataset()
        state["dataset"] = dict(rows=len(data), columns=len(data.columns), matches=data.match_id.nunique(),
            seasons=data.groupby("season", as_index=False).agg(rows=("season", "size"), start=("date", "min"), end=("date", "max")).to_dict("records"))
        print("Lượt 1/2: huấn luyện và kiểm chứng ba fold...", flush=True)
        first = run_experiment(data)
        state["result"] = first
        print("Lượt 2/2: đọc lại dữ liệu và chạy lại cấu hình giống hệt...", flush=True)
        second = run_experiment(load_dataset())
        verify_reproducibility(first, second)
        state["reproducibility"] = "Đạt, giống chính xác từng dự báo, metric và byte CSV"
        _require(all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in state["protected"].items()),
                 "File có sẵn đã thay đổi trong lúc thực thi.")
        state["output_hashes"] = export_results(first)
    except Exception as exc:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(build_report(state, f"{type(exc).__name__}: {exc}"), encoding="utf-8")
        print(f"Chưa hoàn tất: {exc}", file=sys.stderr)
        return 1
    REPORT_PATH.write_text(build_report(state), encoding="utf-8")
    print(first.summary.to_string(index=False))
    print(f"Đã xuất 15 kết quả model-fold; {len(first.checks)} kiểm chứng mỗi lượt; tái lập đạt.")
    print(f"Báo cáo: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
