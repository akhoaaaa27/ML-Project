# Expanding Window Cross-Validation và huấn luyện mô hình ban đầu

## 1. Mục tiêu và phạm vi

Triển khai ba fold theo mùa, tái sử dụng Median Imputation hiện có và so sánh Historical Baseline với bốn thuật toán Regression. Chỉ huấn luyện ban đầu: không Hyperparameter Tuning, Feature Selection, Ablation Study, Final Test, chọn Final Model hoặc lưu model.

## 2. Cấu trúc thư mục và kiểm tra mã nguồn

Trước tác vụ: `data/` chứa bốn dataset và preprocess_laliga.py; `scripts/` chứa hai script chuẩn hóa/chuẩn bị features; `Phases/` chứa hai báo cáo cũ. Không có module training tương đương. Giữ nguyên vị trí và nội dung các file này.

Bổ sung:

```text
scripts/training/
  __init__.py
  cross_validation.py
  train_models.py
  requirements.txt
tests/
  test_training.py
outputs/training/
  cv_fold_results.csv
  cv_summary.csv
Phases/
  Implement Expanding Window Cross-Validation and Initial Model Training.md
```

Đã đọc preprocessing, chuẩn hóa, module chuẩn bị features và báo cáo trong Phases/. Các API load_dataset(), prepare_features(), make_preprocessor() hoạt động đúng chữ ký đã mô tả. Điểm khác tài liệu hiện tại: REPORT_PATH của script chuẩn bị features cũ vẫn trỏ vào data/ mặc dù báo cáo đã được chuyển sang Phases/. Tác vụ chỉ import API, không gọi CLI của script cũ và không sửa preprocessing; báo cáo mới luôn ở Phases/.

## 3. Dataset, features và target

Nguồn `data/laliga_processed_normalized.csv`: **4700 dòng, 26 cột, 2350 trận**, mỗi trận hai dòng. Không có missing ban đầu; load_dataset đã kiểm tra kiểu số, tính hữu hạn và sự nhất quán hai phía.

| Thứ tự | Feature |
|---|---|
| 1 | `is_home` |
| 2 | `matches_seen` |
| 3 | `short_history` |
| 4 | `xg_avg5` |
| 5 | `xga_avg5` |
| 6 | `gf_avg5` |
| 7 | `ga_avg5` |
| 8 | `shot_avg5` |
| 9 | `sot_avg5` |
| 10 | `opponent_xg_avg5` |
| 11 | `opponent_xga_avg5` |
| 12 | `opponent_matches_seen` |
| 13 | `opponent_short_history` |

Target riêng: y=xg. Không có season, date, match_id, team, opponent, gf, ga, sh, sot, xga hoặc xg trong X.

### Mã mùa và số dòng quan sát

| season | rows | start | end |
|---|---|---|---|
| 2019 | 760 | 2019-08-16 | 2020-07-19 |
| 2020 | 760 | 2020-09-12 | 2021-05-23 |
| 2021 | 760 | 2021-08-13 | 2022-05-22 |
| 2022 | 760 | 2022-08-12 | 2023-06-04 |
| 2023 | 760 | 2023-08-11 | 2024-05-26 |
| 2024 | 760 | 2024-08-15 | 2025-05-25 |
| 2025 | 140 | 2025-08-15 | 2025-09-30 |

## 4. Expanding Window và Median Imputation

cross_validation.py chọn bằng season, không dùng thứ tự CSV để chia. Indices iloc được sắp theo date, match_id và is_home trong bộ nhớ. Kiểm tra mùa tăng, ngày cuối Train < ngày đầu Validation, không chung dòng hoặc match_id, đủ hai bản ghi cùng trận trong một tập. SeasonExpandingWindowCV tương thích giao diện splitter của scikit-learn; để tái sử dụng với X không có metadata, tạo list(cv.split(metadata)) trong cùng thứ tự dòng.

Mỗi fold gọi prepare_features() riêng cho Train và Validation, chỉ khôi phục các prior đã xác minh. Tạo make_preprocessor() mới; fit(X_train), transform hai tập rồi dùng 13 features đã xử lý cho tất cả phương pháp. Tám median được đối chiếu phép tính độc lập từ Train; năm features còn lại và các giá trị hợp lệ được giữ nguyên.

### Ranh giới thực tế

| fold | train_seasons | validation_season | train_samples | validation_samples | train_start | train_end | validation_start | validation_end | train_restored_cells | validation_restored_cells |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [2019, 2020] | 2021 | 1520 | 760 | 2019-08-16 | 2021-05-23 | 2021-08-13 | 2022-05-22 | 184 | 24 |
| 2 | [2019, 2020, 2021] | 2022 | 2280 | 760 | 2019-08-16 | 2022-05-22 | 2022-08-12 | 2023-06-04 | 208 | 24 |
| 3 | [2019, 2020, 2021, 2022] | 2023 | 3040 | 760 | 2019-08-16 | 2023-06-04 | 2023-08-11 | 2024-05-26 | 232 | 24 |

### Tám median học riêng từ Train

| feature | fold_1 | fold_2 | fold_3 |
|---|---|---|---|
| xg_avg5 | 1.180000 | 1.180000 | 1.180000 |
| xga_avg5 | 1.220000 | 1.200000 | 1.220000 |
| gf_avg5 | 1.200000 | 1.200000 | 1.200000 |
| ga_avg5 | 1.200000 | 1.200000 | 1.200000 |
| shot_avg5 | 10.600000 | 10.800000 | 11.000000 |
| sot_avg5 | 3.400000 | 3.400000 | 3.600000 |
| opponent_xg_avg5 | 1.180000 | 1.180000 | 1.180000 |
| opponent_xga_avg5 | 1.220000 | 1.200000 | 1.220000 |

## 5. Kiểm soát Data Leakage và giả định dự báo

Dự báo trước từng trận theo trình tự thời gian: các trận đã kết thúc trước trận cần dự báo có thể cung cấp lịch sử, kể cả trận trước đó trong cùng mùa Validation. Không giả định dự báo đồng thời cả mùa ngay từ đầu mùa. Module hiện có kiểm tra code shift(1) trước rolling; tác vụ không tính lại rolling hoặc kiểm toán lại toàn bộ Feature Engineering. Dataset và mã nguồn lịch sử được bảo toàn bằng SHA-256.

Season 2024 (Final Test) và 2025 (Supplemental Test) chỉ được đọc trong kiểm tra schema/toàn vẹn nguồn; không nằm trong bất kỳ tập fit, prediction, metric hoặc so sánh thí nghiệm nào. Không early stopping, eval_set, fit Validation hoặc điều chỉnh tham số theo kết quả Validation. Trong code, estimator.fit chỉ nhận processed_train và y_train; kiểm chứng độc lập ghi nhận indices thực tế của các lệnh fit.

## 6. Thuật toán, tham số và quy tắc dự báo

Cấu hình đã cố định trước khi quan sát metrics; giữ nguyên qua ba fold:

- Historical Baseline: lấy xg_avg5 sau imputation theo fold, không fit estimator hoặc học y_validation.
- LinearRegression(n_jobs=1); các tham số khác mặc định.
- DecisionTreeRegressor(random_state=42); các tham số khác mặc định.
- RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1); các tham số khác mặc định.
- XGBRegressor(objective="reg:squarederror", random_state=42, n_estimators=100, max_depth=6, learning_rate=0.3, tree_method="hist", device="cpu", n_jobs=1); các tham số khác mặc định. Không early stopping.
- threadpool_limits(limits=1) khi fit/predict estimator để hạn chế biến động do song song BLAS/OpenMP.

Mọi phương pháp đều dùng prediction=max(0,prediction) trước MAE và RMSE. Số dự báo âm được đếm trước clipping; không áp trần trên. Với target xG không âm, clipping loại các giá trị dự báo không hợp lệ và không làm tăng sai số tuyệt đối hoặc bình phương tại các điểm bị cắt. So sánh trong báo cáo và CSV đều là kết quả sau clipping.

### Tham số thực tế đầy đủ từ get_params()

```json
{
  "Decision Tree": {
    "ccp_alpha": 0.0,
    "criterion": "squared_error",
    "max_depth": null,
    "max_features": null,
    "max_leaf_nodes": null,
    "min_impurity_decrease": 0.0,
    "min_samples_leaf": 1,
    "min_samples_split": 2,
    "min_weight_fraction_leaf": 0.0,
    "monotonic_cst": null,
    "random_state": 42,
    "splitter": "best"
  },
  "Linear Regression": {
    "copy_X": true,
    "fit_intercept": true,
    "n_jobs": 1,
    "positive": false,
    "tol": 1e-06
  },
  "Random Forest": {
    "bootstrap": true,
    "ccp_alpha": 0.0,
    "criterion": "squared_error",
    "max_depth": null,
    "max_features": 1.0,
    "max_leaf_nodes": null,
    "max_samples": null,
    "min_impurity_decrease": 0.0,
    "min_samples_leaf": 1,
    "min_samples_split": 2,
    "min_weight_fraction_leaf": 0.0,
    "monotonic_cst": null,
    "n_estimators": 100,
    "n_jobs": 1,
    "oob_score": false,
    "random_state": 42,
    "verbose": 0,
    "warm_start": false
  },
  "XGBoost": {
    "base_score": null,
    "booster": null,
    "callbacks": null,
    "colsample_bylevel": null,
    "colsample_bynode": null,
    "colsample_bytree": null,
    "device": "cpu",
    "early_stopping_rounds": null,
    "enable_categorical": true,
    "eval_metric": null,
    "feature_types": null,
    "feature_weights": null,
    "gamma": null,
    "grow_policy": null,
    "importance_type": null,
    "interaction_constraints": null,
    "learning_rate": 0.3,
    "max_bin": null,
    "max_cat_threshold": null,
    "max_cat_to_onehot": null,
    "max_delta_step": null,
    "max_depth": 6,
    "max_leaves": null,
    "min_child_weight": null,
    "missing": NaN,
    "monotone_constraints": null,
    "multi_strategy": null,
    "n_estimators": 100,
    "n_jobs": 1,
    "num_parallel_tree": null,
    "objective": "reg:squarederror",
    "random_state": 42,
    "reg_alpha": null,
    "reg_lambda": null,
    "sampling_method": null,
    "scale_pos_weight": null,
    "subsample": null,
    "tree_method": "hist",
    "validate_parameters": null,
    "verbosity": null
  }
}
```

## 7. Môi trường và lệnh thực thi

Python 3.14.0; NumPy 2.5.4; Pandas 3.1.0; SciPy 1.18.1; scikit-learn 1.9.1; threadpoolctl 3.8.0.
XGBoost: 3.4.1. Môi trường .venv nằm trong workspace, kế thừa các package sẵn có bằng --system-site-packages. Dependency đã dùng được ghim tại scripts/training/requirements.txt.

Các lệnh thiết lập và thực thi:

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir xgboost
.\.venv\Scripts\python.exe -m scripts.training.train_models
```

Tái tạo môi trường trên máy khác: tạo venv và dùng python -m pip install -r scripts/training/requirements.txt, sau đó python -m scripts.training.train_models bằng interpreter đã có dependency. Không cần kích hoạt môi trường nếu gọi trực tiếp interpreter trong .venv.

## 8. Kết quả từng fold

| fold | train_seasons | validation_season | model | train_samples | validation_samples | mae | rmse | negative_predictions | min_prediction_before_clip | min_prediction_after_clip |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2019;2020 | 2021 | Historical Baseline | 1520 | 760 | 0.622037 | 0.807998 | 0 | 0.400000 | 0.400000 |
| 1 | 2019;2020 | 2021 | Linear Regression | 1520 | 760 | 0.575382 | 0.748049 | 0 | 0.028821 | 0.028821 |
| 1 | 2019;2020 | 2021 | Decision Tree | 1520 | 760 | 0.869868 | 1.126189 | 0 | 0.000000 | 0.000000 |
| 1 | 2019;2020 | 2021 | Random Forest | 1520 | 760 | 0.612738 | 0.775512 | 0 | 0.764000 | 0.764000 |
| 1 | 2019;2020 | 2021 | XGBoost | 1520 | 760 | 0.681006 | 0.875170 | 0 | 0.157049 | 0.157049 |
| 2 | 2019;2020;2021 | 2022 | Historical Baseline | 2280 | 760 | 0.614235 | 0.796441 | 0 | 0.100000 | 0.100000 |
| 2 | 2019;2020;2021 | 2022 | Linear Regression | 2280 | 760 | 0.530931 | 0.688029 | 0 | 0.437192 | 0.437192 |
| 2 | 2019;2020;2021 | 2022 | Decision Tree | 2280 | 760 | 0.863421 | 1.112323 | 0 | 0.100000 | 0.100000 |
| 2 | 2019;2020;2021 | 2022 | Random Forest | 2280 | 760 | 0.565754 | 0.713804 | 0 | 0.563000 | 0.563000 |
| 2 | 2019;2020;2021 | 2022 | XGBoost | 2280 | 760 | 0.620515 | 0.789142 | 0 | 0.179182 | 0.179182 |
| 3 | 2019;2020;2021;2022 | 2023 | Historical Baseline | 3040 | 760 | 0.612246 | 0.785152 | 0 | 0.300000 | 0.300000 |
| 3 | 2019;2020;2021;2022 | 2023 | Linear Regression | 3040 | 760 | 0.570200 | 0.736786 | 0 | 0.289616 | 0.289616 |
| 3 | 2019;2020;2021;2022 | 2023 | Decision Tree | 3040 | 760 | 0.828553 | 1.065592 | 0 | 0.000000 | 0.000000 |
| 3 | 2019;2020;2021;2022 | 2023 | Random Forest | 3040 | 760 | 0.598288 | 0.745267 | 0 | 0.672000 | 0.672000 |
| 3 | 2019;2020;2021;2022 | 2023 | XGBoost | 3040 | 760 | 0.639241 | 0.803427 | 0 | 0.219778 | 0.219778 |

## 9. Tổng hợp và so sánh ban đầu

Trung bình ba fold có trọng số bằng nhau. Standard deviation dùng quy ước tổng thể ddof=0 cho cả MAE và RMSE; RMSE là căn MSE. Rank dựa Mean MAE tăng dần; Mean MAE bằng nhau được cùng rank, Mean RMSE chỉ hỗ trợ sắp thứ tự.

| model | mean_mae | std_mae | mean_rmse | std_rmse | rank |
|---|---|---|---|---|---|
| Linear Regression | 0.558838 | 0.019846 | 0.724288 | 0.026048 | 1 |
| Random Forest | 0.592260 | 0.019649 | 0.744861 | 0.025194 | 2 |
| Historical Baseline | 0.616173 | 0.004226 | 0.796530 | 0.009327 | 3 |
| XGBoost | 0.646921 | 0.025285 | 0.822580 | 0.037641 | 4 |
| Decision Tree | 0.853947 | 0.018149 | 1.101368 | 0.025923 | 5 |

**Linear Regression** có Mean MAE thấp nhất trong cấu hình ban đầu: **0.558838**; Mean RMSE **0.724288**. So với Historical Baseline (Mean MAE 0.616173), chênh lệch giảm MAE là 0.057335 (9.31%).
Chênh lệch Mean MAE với phương pháp đứng kế tiếp (Random Forest) là 0.033422. Ba fold chưa đủ để suy ra khác biệt có ý nghĩa thống kê; các mùa cũng có phân phối và độ khó khác nhau. Cần xét cả kết quả từng fold, RMSE và độ biến động thay vì chỉ rank.
Đây chỉ là phương pháp có kết quả ban đầu tốt nhất trong thí nghiệm đã chạy, chưa phải Final Model. Không chỉnh tham số sau khi quan sát bảng kết quả.

### Đối chiếu với Historical Baseline

- Linear Regression: MAE trung bình thấp hơn baseline 0.057335, tương ứng 9.31%.
- Random Forest: MAE trung bình thấp hơn baseline 0.023913, tương ứng 3.88%.
- XGBoost: MAE trung bình cao hơn baseline 0.030748, tương ứng 4.99%.
- Decision Tree: MAE trung bình cao hơn baseline 0.237775, tương ứng 38.59%.

Trong ba fold, Linear Regression đều có MAE thấp nhất. Random Forest đều cải thiện MAE so với baseline. XGBoost và Decision Tree ở cấu hình ban đầu có MAE cao hơn baseline; kết quả này chưa xác định khả năng của các thuật toán sau tuning. Không suy ra overfitting chỉ từ các metric Validation hiện có.

Tổng số dự báo âm trước clipping trên 15 tổ hợp: **0**. Vì vậy, quy tắc clipping được áp dụng nhưng không thay đổi dự báo hoặc metrics của thí nghiệm thực tế này.

## 10. Kiểm chứng thực thi và khả năng tái lập

Lượt thí nghiệm thứ nhất ghi nhận 75 kiểm chứng đạt; lượt thứ hai lặp lại toàn bộ fit/predict với dữ liệu đọc lại từ nguồn.

| Kiểm chứng | Đạt | Bằng chứng |
|---|---|---|
| Schema và dữ liệu nguồn | True | 4700 dòng, 26 cột, 2350 trận; schema đúng, không dòng trùng. |
| Công thức lịch sử | True | Đã kiểm tra code shift(1), rolling và prior qua API hiện có; không tính lại rolling averages. |
| Fold 1: mùa, ngày và cặp trận | True | Train (2019, 2020), 2019-08-16 → 2021-05-23; Validation 2021, 2021-08-13 → 2022-05-22; splitter đã kiểm tra đầy đủ cặp trận. |
| Fold 1: 13 features và target | True | X chỉ có 13 features theo thứ tự; y=xg giữ nguyên, không chứa metadata hoặc thống kê hiện trận. |
| Fold 1: imputer mới | True | Tạo instance mới cho fold; không dùng chung trạng thái đã fit. |
| Fold 1: fit median Train-only | True | Fit đúng 1520 dòng Train; tám median khớp phép tính độc lập trên Train. |
| Fold 1: toàn vẹn Train | True | 1520 dòng × 13 features hữu hạn; index, ô hợp lệ và năm features còn lại giữ nguyên. |
| Fold 1: toàn vẹn Validation | True | 760 dòng × 13 features hữu hạn; index, ô hợp lệ và năm features còn lại giữ nguyên. |
| Fold 1: Validation không cập nhật median | True | Sau transform và dịch phân phối Validation thêm 1.000.000, statistics_ và giá trị điền vẫn dùng median Train. |
| Fold 1: dự báo và metric Historical Baseline | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 1: tham số Linear Regression | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 1: fit Linear Regression chỉ nhận Train | True | fit(X_train_processed, y_train), 1520 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 1: đầu vào estimator Linear Regression | True | Estimator đã fit nhận đúng 13 features. |
| Fold 1: dự báo và metric Linear Regression | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 1: tham số Decision Tree | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 1: fit Decision Tree chỉ nhận Train | True | fit(X_train_processed, y_train), 1520 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 1: đầu vào estimator Decision Tree | True | Estimator đã fit nhận đúng 13 features. |
| Fold 1: dự báo và metric Decision Tree | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 1: tham số Random Forest | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 1: fit Random Forest chỉ nhận Train | True | fit(X_train_processed, y_train), 1520 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 1: đầu vào estimator Random Forest | True | Estimator đã fit nhận đúng 13 features. |
| Fold 1: dự báo và metric Random Forest | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 1: tham số XGBoost | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 1: fit XGBoost chỉ nhận Train | True | fit(X_train_processed, y_train), 1520 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 1: đầu vào estimator XGBoost | True | Estimator đã fit nhận đúng 13 features. |
| Fold 1: dự báo và metric XGBoost | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 2: mùa, ngày và cặp trận | True | Train (2019, 2020, 2021), 2019-08-16 → 2022-05-22; Validation 2022, 2022-08-12 → 2023-06-04; splitter đã kiểm tra đầy đủ cặp trận. |
| Fold 2: 13 features và target | True | X chỉ có 13 features theo thứ tự; y=xg giữ nguyên, không chứa metadata hoặc thống kê hiện trận. |
| Fold 2: imputer mới | True | Tạo instance mới cho fold; không dùng chung trạng thái đã fit. |
| Fold 2: fit median Train-only | True | Fit đúng 2280 dòng Train; tám median khớp phép tính độc lập trên Train. |
| Fold 2: toàn vẹn Train | True | 2280 dòng × 13 features hữu hạn; index, ô hợp lệ và năm features còn lại giữ nguyên. |
| Fold 2: toàn vẹn Validation | True | 760 dòng × 13 features hữu hạn; index, ô hợp lệ và năm features còn lại giữ nguyên. |
| Fold 2: Validation không cập nhật median | True | Sau transform và dịch phân phối Validation thêm 1.000.000, statistics_ và giá trị điền vẫn dùng median Train. |
| Fold 2: dự báo và metric Historical Baseline | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 2: tham số Linear Regression | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 2: fit Linear Regression chỉ nhận Train | True | fit(X_train_processed, y_train), 2280 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 2: đầu vào estimator Linear Regression | True | Estimator đã fit nhận đúng 13 features. |
| Fold 2: dự báo và metric Linear Regression | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 2: tham số Decision Tree | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 2: fit Decision Tree chỉ nhận Train | True | fit(X_train_processed, y_train), 2280 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 2: đầu vào estimator Decision Tree | True | Estimator đã fit nhận đúng 13 features. |
| Fold 2: dự báo và metric Decision Tree | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 2: tham số Random Forest | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 2: fit Random Forest chỉ nhận Train | True | fit(X_train_processed, y_train), 2280 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 2: đầu vào estimator Random Forest | True | Estimator đã fit nhận đúng 13 features. |
| Fold 2: dự báo và metric Random Forest | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 2: tham số XGBoost | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 2: fit XGBoost chỉ nhận Train | True | fit(X_train_processed, y_train), 2280 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 2: đầu vào estimator XGBoost | True | Estimator đã fit nhận đúng 13 features. |
| Fold 2: dự báo và metric XGBoost | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 3: mùa, ngày và cặp trận | True | Train (2019, 2020, 2021, 2022), 2019-08-16 → 2023-06-04; Validation 2023, 2023-08-11 → 2024-05-26; splitter đã kiểm tra đầy đủ cặp trận. |
| Fold 3: 13 features và target | True | X chỉ có 13 features theo thứ tự; y=xg giữ nguyên, không chứa metadata hoặc thống kê hiện trận. |
| Fold 3: imputer mới | True | Tạo instance mới cho fold; không dùng chung trạng thái đã fit. |
| Fold 3: fit median Train-only | True | Fit đúng 3040 dòng Train; tám median khớp phép tính độc lập trên Train. |
| Fold 3: toàn vẹn Train | True | 3040 dòng × 13 features hữu hạn; index, ô hợp lệ và năm features còn lại giữ nguyên. |
| Fold 3: toàn vẹn Validation | True | 760 dòng × 13 features hữu hạn; index, ô hợp lệ và năm features còn lại giữ nguyên. |
| Fold 3: Validation không cập nhật median | True | Sau transform và dịch phân phối Validation thêm 1.000.000, statistics_ và giá trị điền vẫn dùng median Train. |
| Fold 3: dự báo và metric Historical Baseline | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 3: tham số Linear Regression | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 3: fit Linear Regression chỉ nhận Train | True | fit(X_train_processed, y_train), 3040 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 3: đầu vào estimator Linear Regression | True | Estimator đã fit nhận đúng 13 features. |
| Fold 3: dự báo và metric Linear Regression | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 3: tham số Decision Tree | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 3: fit Decision Tree chỉ nhận Train | True | fit(X_train_processed, y_train), 3040 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 3: đầu vào estimator Decision Tree | True | Estimator đã fit nhận đúng 13 features. |
| Fold 3: dự báo và metric Decision Tree | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 3: tham số Random Forest | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 3: fit Random Forest chỉ nhận Train | True | fit(X_train_processed, y_train), 3040 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 3: đầu vào estimator Random Forest | True | Estimator đã fit nhận đúng 13 features. |
| Fold 3: dự báo và metric Random Forest | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Fold 3: tham số XGBoost | True | Clone giữ nguyên cấu hình cố định qua các fold. |
| Fold 3: fit XGBoost chỉ nhận Train | True | fit(X_train_processed, y_train), 3040 dòng × 13 features; không eval_set hoặc y_validation. |
| Fold 3: đầu vào estimator XGBoost | True | Estimator đã fit nhận đúng 13 features. |
| Fold 3: dự báo và metric XGBoost | True | MAE/RMSE hữu hạn; 0 dự báo âm trước clipping, không còn âm sau clipping. |
| Đủ kết quả và bảo vệ Final Test | True | 15 tổ hợp, 5 model; chỉ dùng Train 2019–2022 và Validation 2021–2023. |

Tái lập hai lượt: **Đạt, giống chính xác từng dự báo, metric và byte CSV**. Kiểm tra chính xác DataFrame metrics, summary, tham số, audit, medians, mọi mảng dự báo và byte CSV; không dùng tolerance cho so sánh giữa hai lượt.

| file | sha256 |
|---|---|
| cv_fold_results.csv | 559ae9fc455516ab207b17cff72a9b66b69cb0e2bbc7a44a8fb80922aadd1185 |
| cv_summary.csv | f756d0e5830d70365b13f1dcdb6c5416998cab5133f3c6f5b140570900f5e9ac |

Hai CSV đã được ghi bằng code và đọc lại kiểm tra schema, số dòng và giá trị. Dùng 17 chữ số có nghĩa khi ghi; đối chiếu lần đọc mặc định cho phép sai số phân tích số thực 1e-14. Không chỉnh tay kết quả.

### Kiểm thử độc lập đã thực thi

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_training.py -v
```

Kết quả thực tế: **19/19 kiểm thử đạt**, mã thoát 0. Các estimator nhân tạo trong bài kiểm thử chỉ ghi nhận đối số fit và chạy trên dữ liệu Train/Validation đúng cấu hình; không thay thế các model thật trong kết quả thí nghiệm.

- Xác nhận số dòng ba fold đúng mốc kỳ vọng, cặp trận nguyên vẹn, không dùng mùa 2024 hoặc 2025.
- Xáo thứ tự CSV trong bản sao không làm thay đổi tập trận hoặc thứ tự thời gian trả về; giao diện splitter scikit-learn trả về indices đúng.
- Chặn trường hợp thiếu một phía của trận, cùng trận thuộc hai mùa, ngày Train trong tương lai, cấu hình dùng Final Test hoặc không mở rộng Train.
- Ghi nhận thực tế ba lệnh fit imputer và 12 lệnh fit estimator nhân tạo: indices đều thuộc đúng Train; target/index khớp và tên cột đúng 13 features.
- Kiểm chứng clipping bằng dự báo âm nhân tạo, RMSE bằng giá trị tính giải tích và standard deviation tổng thể ddof=0.
- Chặn dự báo NaN/vô hạn, thiếu tổ hợp model-fold; phát hiện mảng dự báo bị thay đổi khi đối chiếu tái lập.
- Đọc/ghi CSV qua thư mục tạm; khi validation đầu ra thất bại, các CSV đã có được giữ nguyên từng byte.
- Kiểm tra cấu hình và random_state nhất quán, DataFrame nguồn không bị sửa.

### Đối chiếu cuối trên CSV đã lưu

Đã đọc độc lập cả hai CSV từ ổ đĩa và tính lại Mean MAE, Std MAE, Mean RMSE, Std RMSE bằng NumPy với ddof=0; kết quả khớp trong sai số phân tích số thực 1e-14. Xác nhận đủ 15 dòng chi tiết, 5 dòng tổng hợp, mỗi model đủ ba fold, rank tăng theo Mean MAE và dự báo sau clipping không âm. SHA-256 của cả chín file có sẵn được đối chiếu lại với giá trị chụp trước khi bắt đầu chỉnh sửa: tất cả giữ nguyên. Không tạo file model hoặc báo cáo trùng vị trí.

## 11. Bảo toàn file và tóm tắt thay đổi

Tạo hai module training, package marker, requirements và một file kiểm thử độc lập. Tạo/cập nhật hai CSV trong outputs/training/ và chính báo cáo này trong Phases/. Không di chuyển file cũ, không tạo outputs/models/, outputs/figures/, app/ hoặc thư mục rỗng.

| File có sẵn | SHA-256 trước thực thi | Sau thực thi |
|---|---|---|
| `data/matches_laliga.csv` | `3cfeb29ea2e76d6a8a411f31af6182c6951fd477903b8b6d0401b58e10b415e2` | Giữ nguyên |
| `data/laliga_processed.csv` | `666661b49f4055104bd73b8ceb53f50407bf6e90cae6551dbbee820fe9fd6a3a` | Giữ nguyên |
| `data/laliga_processed.xlsx` | `47023b9efd583783c35b0b45030c3c747ca1fd09519164631f46543574540ab3` | Giữ nguyên |
| `data/laliga_processed_normalized.csv` | `90000ce22f42abe5eb5b5bfa38ad1ed5ef7b1c1c75cd4d39e749e7b324e0e5ca` | Giữ nguyên |
| `data/preprocess_laliga.py` | `fb5e35f268c7b205dc4d5854c5eba75ad74d903fcc08ae1cb5fdaf9f9963aadb` | Giữ nguyên |
| `scripts/normalize_laliga_numeric.py` | `1d40c912a1c4df9c765cbbd3e0ff6ddbe03da767697531c7be058ea9914aa726` | Giữ nguyên |
| `scripts/prepare_training_features.py` | `59da3125592544ea1c958e7550e57b53d94b3b0c3facf570ec91d4efa8364b7d` | Giữ nguyên |
| `Phases/Normalize Numeric Formats in the La Liga Dataset.md` | `628ef4057a4ed505c59f83d2467ce2b0cf67bc9e747848c1300532e06f1b5979` | Giữ nguyên |
| `Phases/Prepare Leakage-Safe Median Imputation for La Liga.md` | `e158bf9016c4ded33e2e0c993a74f5c677d875550d6e0a653c26d2c99424b885` | Giữ nguyên |

## 12. Cảnh báo và vấn đề

XGBoost ban đầu chưa có trong interpreter hệ thống. Lần tải trong sandbox bị chặn kết nối; đã cài thành công XGBoost 3.4.1 vào .venv sau khi được cấp quyền tải. Kiểm tra tương thích fit/predict trên dữ liệu nhân tạo đã chạy trước thí nghiệm chính; không thay thế thuật toán. Thí nghiệm chính dùng đúng cấu hình cố định nêu trên.

Không có cảnh báo từ các lệnh fit/predict estimator trong thí nghiệm.

Không có vấn đề chặn hoàn thành trong phạm vi thí nghiệm. Hạn chế: chỉ ba mùa Validation, hai dòng cùng trận có tương quan, không báo khoảng tin cậy hoặc kiểm định thống kê. Chưa có kết quả Final Test. Kiểm tra rolling giới hạn ở logic code và bảo toàn nguồn, không tái tính toàn bộ features.

### Sửa lỗi quyền đọc CSV trên Windows

Phát hiện hai CSV bị tắt kế thừa ACL và chỉ cho SYSTEM, Administrators cùng OWNER RIGHTS truy cập; owner là tài khoản sandbox của Codex. Đây là nguyên nhân VS Code và Git chạy dưới tài khoản người dùng báo Permission denied. Chẩn đoán ban đầu về file bị ứng dụng khác khóa chưa đúng với nguyên nhân thực tế.

Đã bật kế thừa ACL cho đúng cv_fold_results.csv và cv_summary.csv bằng icacls /inheritance:e. Đã sửa export_results() để dùng NamedTemporaryFile trực tiếp trong outputs/training/ thay cho file bên trong TemporaryDirectory riêng tư; file được tạo mới kế thừa quyền từ thư mục đích. Vẫn kiểm chứng CSV trước khi thay thế và dọn file tạm khi lỗi.

Đã bổ sung test_windows_exports_inherit_directory_permissions và chạy lại bộ kiểm thử: **19/19 kiểm thử đạt**, mã thoát 0. Kiểm thử kiểm tra trực tiếp AreAccessRulesProtected=False trên các CSV xuất ra ở Windows.

Đã đọc kết quả đã lưu với float_precision="round_trip" và xuất lại bằng hàm mới, không huấn luyện lại. SHA-256 của cả hai CSV khớp hoàn toàn trước và sau: nội dung, metrics và cấu hình thí nghiệm không đổi. File đầu ra thực tế được kiểm tra ACL sau khi xuất lại. Không commit hoặc push.

Lệnh tái xuất phục vụ sửa quyền có phát Pandas4Warning vì float_precision đang được đánh dấu deprecated trong Pandas hiện tại. Đây là cảnh báo của lệnh kiểm chứng một lần; không có tham số này trong code huấn luyện hoặc hàm xuất CSV. Lệnh hoàn tất thành công và SHA-256 xác nhận dữ liệu không đổi.

Kiểm tra git hash-object đọc thành công cả hai CSV sau sửa quyền. Lệnh git add --dry-run từ tiến trình Codex không hoàn tất vì sandbox chỉ được đọc thư mục .git và không tạo được .git/index.lock; đây là giới hạn của môi trường kiểm chứng, không phải lỗi đọc CSV còn tồn tại. Chưa thực hiện stage, commit hoặc push. Người dùng cần chạy git add trong terminal VS Code để xác nhận từ tài khoản Windows của mình.

## 13. Tài liệu kỹ thuật đối chiếu

API và cấu hình XGBRegressor: [tài liệu XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html#xgboost.XGBRegressor).
RMSE dùng API căn sai số bình phương: [tài liệu scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.root_mean_squared_error.html).

## 14. Kết luận và hướng tiếp theo

Đã hoàn tất framework Expanding Window, so sánh đủ năm phương pháp trên ba fold, xuất 15 kết quả và bảng tổng hợp, đồng thời xác minh tái lập. Các dataset, preprocessing và báo cáo cũ được giữ nguyên. Không lưu estimator đã fit hoặc chọn Final Model.

Giai đoạn sau có thể xây dựng kế hoạch Hyperparameter Tuning trên chính các fold Train/Validation này và giữ Final Test tách biệt; chưa thực hiện tuning hoặc bước tiếp theo khi chưa có yêu cầu rõ ràng của người dùng.
