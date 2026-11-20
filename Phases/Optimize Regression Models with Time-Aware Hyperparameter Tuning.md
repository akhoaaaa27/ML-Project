# Tối ưu Regression bằng Hyperparameter Tuning theo thời gian

## 1. Mục tiêu và phạm vi Phase 5

Phân tích Training Error/Validation Error trước và sau tuning của Linear Regression, Decision Tree, Random Forest và XGBoost; giữ Historical Baseline cố định. Không thêm features, không dùng Final Test, không huấn luyện trên toàn bộ development để tạo Final Model và không lưu model.

## 2. Khảo sát repository và kết quả Phase 4

Đã đọc CSV chuẩn hóa, module chuẩn bị features, cross_validation.py, train_models.py, requirements.txt, hai CSV kết quả Phase 4, tests/test_training.py và báo cáo Phase 4. Không thay đổi các API hoặc file cũ. Các version đang cài khớp requirements của Phase 4.

| model | mean_mae | std_mae | mean_rmse | std_rmse | rank |
|---|---|---|---|---|---|
| Linear Regression | 0.558838 | 0.019846 | 0.724288 | 0.026048 | 1 |
| Random Forest | 0.592260 | 0.019649 | 0.744861 | 0.025194 | 2 |
| Historical Baseline | 0.616173 | 0.004226 | 0.796530 | 0.009327 | 3 |
| XGBoost | 0.646921 | 0.025285 | 0.822580 | 0.037641 | 4 |
| Decision Tree | 0.853947 | 0.018149 | 1.101368 | 0.025923 | 5 |

Bảng trên được đọc từ outputs/training/cv_summary.csv và đối chiếu tính lại từ từng fold. Validation metrics của cấu hình trước tuning cũng được fit/predict lại và đối chiếu từng model/fold với atol=1e-12, rtol=0; ngưỡng này chỉ bao phủ sai số số thực/parsing CSV, không che thay đổi thực nghiệm.

## 3. Tổ chức file

```text
scripts/training/tune_models.py
tests/test_tuning.py
outputs/tuning/tuning_trials.csv
outputs/tuning/tuning_summary.csv
outputs/tuning/best_params.json
outputs/tuning/overfitting_diagnostics.csv
Phases/Optimize Regression Models with Time-Aware Hyperparameter Tuning.md
```

Chỉ bổ sung module tuning, tests và đầu ra Phase 5. Tái sử dụng model_templates(), evaluate_predictions(), csv_bytes() và định dạng bảng từ train_models.py; dùng make_season_folds(), load_dataset(), prepare_features(), make_preprocessor() hiện có. Không di chuyển hoặc refactor code Phase 4; không ghi đè hai CSV hoặc báo cáo Phase 4.

## 4. Dataset, features và target

Nguồn có 4700 dòng × 26 cột, 2350 trận. Development chỉ có **3800 dòng**, season 2019–2023. Các mùa 2024 và 2025 chỉ được đọc khi kiểm tra schema/toàn vẹn CSV nguồn, sau đó bị loại trước prepare_features và search.

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

Target y=xg được giữ riêng. Không đưa metadata hoặc gf, ga, sh, sot, xga, xg hiện trận vào X. Không thay đổi dataset hoặc công thức rolling.

## 5. Fold và Median Imputation

Giữ ba fold Phase 4, chọn bằng season thay vì thứ tự CSV. Splitter kiểm tra ngày Train trước Validation, không chung match_id hoặc bản ghi, hai phía trận ở cùng tập. Indices iloc được tạo trên chính DataFrame development giữ cùng thứ tự X/y; tuyệt đối không tái dùng indices của CSV đầy đủ cho một X đã lọc.

| fold | train_seasons | validation_season | train_samples | validation_samples | train_start | train_end | validation_start | validation_end |
|---|---|---|---|---|---|---|---|---|
| 1 | 2019;2020 | 2021 | 1520 | 760 | 2019-08-16 | 2021-05-23 | 2021-08-13 | 2022-05-22 |
| 2 | 2019;2020;2021 | 2022 | 2280 | 760 | 2019-08-16 | 2022-05-22 | 2022-08-12 | 2023-06-04 |
| 3 | 2019;2020;2021;2022 | 2023 | 3040 | 760 | 2019-08-16 | 2023-06-04 | 2023-08-11 | 2024-05-26 |

prepare_features() chỉ khôi phục prior đã xác minh về NaN trong development, không học thống kê. Mỗi candidate/fold clone Pipeline([('preprocessing', make_preprocessor()), ('model', estimator)]). SimpleImputer vẫn được fit mới trên Train bên trong Pipeline. Scorer kiểm tra n_samples_fit_, tám median từ Train, đúng 13 tên cột, index, số hữu hạn và mọi ô hợp lệ sau transform.

Các median tính riêng bằng Pandas trên từng X_train chỉ dùng làm giá trị đối chiếu audit; không được đưa vào imputer hoặc dùng thay bước fit. Validation, season 2024/2025 và target không tham gia học median. Không xuất dataset impute toàn cục.

Dự báo tuần tự trước từng trận: có thể dùng kết quả những trận đã kết thúc trước đó trong cùng mùa Validation. Không dùng kết quả hiện trận/future; không giả định dự báo đồng thời cả mùa từ ngày đầu mùa. Giữ nguyên Feature Engineering đã kiểm chứng, không tính lại rolling.

## 6. Phương pháp search và ngân sách

Linear Regression dùng GridSearchCV với đúng bốn tổ hợp fit_intercept/positive. Các thuật toán còn lại dùng RandomizedSearchCV với seed 42, 25 cấu hình duy nhất lấy không hoàn lại từ không gian danh sách hữu hạn. Tạo lại ParameterGrid/ParameterSampler và đối chiếu từng cấu hình cùng id với cv_results_.

Tất cả search đều truyền rõ ba fold thời gian, return_train_score=True, refit=False, error_score='raise', n_jobs=1, pre_dispatch=1. Không dùng CV mặc định, early stopping, eval_set hoặc tuning thích nghi theo kết quả. RF/XGBoost và BLAS/OpenMP giới hạn một luồng như Phase 4.

### Không gian tham số cố định trước khi chạy

```json
{
  "Decision Tree": {
    "max_depth": [
      3,
      5,
      8,
      12,
      null
    ],
    "min_samples_leaf": [
      1,
      2,
      5,
      10,
      20
    ],
    "min_samples_split": [
      2,
      5,
      10,
      20
    ]
  },
  "Linear Regression": {
    "fit_intercept": [
      true,
      false
    ],
    "positive": [
      true,
      false
    ]
  },
  "Random Forest": {
    "max_depth": [
      4,
      8,
      12,
      null
    ],
    "max_features": [
      0.6,
      0.8,
      1.0
    ],
    "min_samples_leaf": [
      1,
      2,
      5,
      10
    ],
    "n_estimators": [
      100,
      200,
      300
    ]
  },
  "XGBoost": {
    "colsample_bytree": [
      0.7,
      0.85,
      1.0
    ],
    "learning_rate": [
      0.02,
      0.05,
      0.1,
      0.2
    ],
    "max_depth": [
      2,
      3,
      4,
      6
    ],
    "min_child_weight": [
      1,
      3,
      5,
      10
    ],
    "n_estimators": [
      100,
      200,
      350
    ],
    "reg_lambda": [
      1,
      5,
      10
    ],
    "subsample": [
      0.7,
      0.85,
      1.0
    ]
  }
}
```

| Thuật toán | Kích thước không gian | Cấu hình được đánh giá | Lượt fit search |
|---|---:|---:|---:|
| Linear Regression | 4 | 4/4 | 12 |
| Decision Tree | 100 | 25/25 | 75 |
| Random Forest | 144 | 25/25 | 75 |
| XGBoost | 5184 | 25/25 | 75 |

Đã hoàn tất **79 cấu hình × 3 fold = 237 lượt fit search**. Ngoài search: 12 lượt cấu hình ban đầu, 12 lượt chẩn đoán cấu hình chọn và 12 lượt kiểm chứng lại cấu hình chọn; tổng cộng **273 lượt fit Regression trong thí nghiệm**, chưa kể các fits của unit tests. Baseline không fit Regression, chỉ có ba lần fit preprocessing theo fold. Không refit model trên toàn development.

positive=True trong LinearRegression ràng buộc các hệ số không âm; có thể không phù hợp khi một số features có quan hệ âm với target. Đây không phải bước clipping dự báo, và không có Ridge/Lasso trong search. Tham khảo [LinearRegression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LinearRegression.html).

### Scoring và luật chọn

AuditedClippedScorer gọi evaluate_predictions() Phase 4, tức clipping max(0,prediction) trước MAE và RMSE. Search nhận score âm để tối đa hóa; khi xuất chuyển dấu về lỗi dương. Chọn Mean Validation MAE thấp nhất; các candidate cách minimum không quá 1e-12 (rtol=0) được xét hòa MAE, sau đó dùng RMSE với cùng tolerance. Nếu vẫn hòa, chọn chuỗi JSON tham số theo thứ tự từ điển rồi candidate_id tăng dần. refit=False nên tự chọn từ cv_results_, không phụ thuộc best_params_. Trung bình các fold có trọng số bằng nhau; standard deviation dùng ddof=0.

## 7. Chẩn đoán trước và sau tuning

| model | configuration_stage | fold | train_mae | validation_mae | mae_gap | train_rmse | validation_rmse | rmse_gap |
|---|---|---|---|---|---|---|---|---|
| Historical Baseline | before | 1 | 0.620174 | 0.622037 | 0.001863 | 0.779016 | 0.807998 | 0.028982 |
| Historical Baseline | before | 2 | 0.620795 | 0.614235 | -0.006561 | 0.788795 | 0.796441 | 0.007646 |
| Historical Baseline | before | 3 | 0.619155 | 0.612246 | -0.006910 | 0.790713 | 0.785152 | -0.005561 |
| Historical Baseline | after | 1 | 0.620174 | 0.622037 | 0.001863 | 0.779016 | 0.807998 | 0.028982 |
| Historical Baseline | after | 2 | 0.620795 | 0.614235 | -0.006561 | 0.788795 | 0.796441 | 0.007646 |
| Historical Baseline | after | 3 | 0.619155 | 0.612246 | -0.006910 | 0.790713 | 0.785152 | -0.005561 |
| Linear Regression | before | 1 | 0.546876 | 0.575382 | 0.028506 | 0.696837 | 0.748049 | 0.051212 |
| Linear Regression | before | 2 | 0.552707 | 0.530931 | -0.021775 | 0.711393 | 0.688029 | -0.023364 |
| Linear Regression | before | 3 | 0.547947 | 0.570200 | 0.022253 | 0.705140 | 0.736786 | 0.031646 |
| Linear Regression | after | 1 | 0.546876 | 0.575382 | 0.028506 | 0.696837 | 0.748049 | 0.051212 |
| Linear Regression | after | 2 | 0.552707 | 0.530931 | -0.021775 | 0.711393 | 0.688029 | -0.023364 |
| Linear Regression | after | 3 | 0.547947 | 0.570200 | 0.022253 | 0.705140 | 0.736786 | 0.031646 |
| Decision Tree | before | 1 | 0.007618 | 0.869868 | 0.862250 | 0.077042 | 1.126189 | 1.049147 |
| Decision Tree | before | 2 | 0.005079 | 0.863421 | 0.858342 | 0.062905 | 1.112323 | 1.049418 |
| Decision Tree | before | 3 | 0.003809 | 0.828553 | 0.824743 | 0.054477 | 1.065592 | 1.011115 |
| Decision Tree | after | 1 | 0.549920 | 0.577458 | 0.027538 | 0.699336 | 0.757878 | 0.058542 |
| Decision Tree | after | 2 | 0.558818 | 0.576727 | 0.017909 | 0.718144 | 0.738452 | 0.020309 |
| Decision Tree | after | 3 | 0.560411 | 0.570410 | 0.009998 | 0.717119 | 0.733068 | 0.015949 |
| Random Forest | before | 1 | 0.215481 | 0.612738 | 0.397256 | 0.276496 | 0.775512 | 0.499016 |
| Random Forest | before | 2 | 0.219394 | 0.565754 | 0.346360 | 0.283681 | 0.713804 | 0.430123 |
| Random Forest | before | 3 | 0.213573 | 0.598288 | 0.384715 | 0.276641 | 0.745267 | 0.468625 |
| Random Forest | after | 1 | 0.524689 | 0.579769 | 0.055081 | 0.664105 | 0.750968 | 0.086864 |
| Random Forest | after | 2 | 0.539539 | 0.547493 | 0.007954 | 0.689450 | 0.704312 | 0.014862 |
| Random Forest | after | 3 | 0.538433 | 0.565524 | 0.027091 | 0.689152 | 0.724026 | 0.034874 |
| XGBoost | before | 1 | 0.066168 | 0.681006 | 0.614838 | 0.117221 | 0.875170 | 0.757948 |
| XGBoost | before | 2 | 0.129798 | 0.620515 | 0.490717 | 0.193212 | 0.789142 | 0.595931 |
| XGBoost | before | 3 | 0.149033 | 0.639241 | 0.490208 | 0.217073 | 0.803427 | 0.586355 |
| XGBoost | after | 1 | 0.532418 | 0.579321 | 0.046903 | 0.674778 | 0.750631 | 0.075853 |
| XGBoost | after | 2 | 0.544227 | 0.545561 | 0.001333 | 0.697478 | 0.700480 | 0.003002 |
| XGBoost | after | 3 | 0.540285 | 0.562027 | 0.021742 | 0.693137 | 0.721108 | 0.027971 |

30 dòng gồm 24 chẩn đoán Regression và 6 dòng benchmark trước/sau giống nhau. Mỗi bộ cấu hình trước/sau được fit bằng estimator và preprocessing mới theo từng fold; không lấy lại estimator đã fit trong search.

## 8. Cấu hình tốt nhất trong không gian đã xét

| model | candidate_id | best_params | mean_validation_mae | mean_validation_rmse |
|---|---|---|---|---|
| Linear Regression | 2 | {"fit_intercept": true, "positive": false} | 0.558838 | 0.724288 |
| Decision Tree | 10 | {"max_depth": 3, "min_samples_leaf": 1, "min_samples_split": 2} | 0.574865 | 0.743133 |
| Random Forest | 17 | {"max_depth": 4, "max_features": 1.0, "min_samples_leaf": 2, "n_estimators": 100} | 0.564262 | 0.726435 |
| XGBoost | 4 | {"colsample_bytree": 0.7, "learning_rate": 0.05, "max_depth": 2, "min_child_weight": 3, "n_estimators": 100, "reg_lambda": 10, "subsample": 0.85} | 0.562303 | 0.724073 |

Không có best_params cho Historical Baseline. JSON lưu thêm seed, không gian, budget, folds, phiên bản, source SHA-256, feature order, quy tắc scoring/chọn và các tham số giữ cố định. Marker missing=nan của XGBoost được mô tả bằng chuỗi 'nan' trong metadata để JSON hợp lệ; không có metric NaN.

## 9. So sánh trước/sau và độ ổn định

### Validation MAE

| model | mean_validation_mae_before | std_validation_mae_before | mean_validation_mae_after | std_validation_mae_after | mae_improvement | mae_improvement_percent | rank_before | rank_after |
|---|---|---|---|---|---|---|---|---|
| Linear Regression | 0.558838 | 0.019846 | 0.558838 | 0.019846 | 0.000000 | 0.000000 | 1 | 1 |
| XGBoost | 0.646921 | 0.025285 | 0.562303 | 0.013784 | 0.084618 | 13.080107 | 4 | 2 |
| Random Forest | 0.592260 | 0.019649 | 0.564262 | 0.013207 | 0.027997 | 4.727216 | 2 | 3 |
| Decision Tree | 0.853947 | 0.018149 | 0.574865 | 0.003165 | 0.279082 | 32.681448 | 5 | 4 |
| Historical Baseline | 0.616173 | 0.004226 | 0.616173 | 0.004226 | 0.000000 | 0.000000 | 3 | 5 |

### Validation RMSE

| model | mean_validation_rmse_before | std_validation_rmse_before | mean_validation_rmse_after | std_validation_rmse_after |
|---|---|---|---|---|
| Linear Regression | 0.724288 | 0.026048 | 0.724288 | 0.026048 |
| XGBoost | 0.822580 | 0.037641 | 0.724073 | 0.020581 |
| Random Forest | 0.744861 | 0.025194 | 0.726435 | 0.019123 |
| Decision Tree | 1.101368 | 0.025923 | 0.743133 | 0.010656 |
| Historical Baseline | 0.796530 | 0.009327 | 0.796530 | 0.009327 |

### Overfitting, Underfitting và khác biệt mùa

**Linear Regression:** Mean Train MAE 0.549177 → 0.549177; Mean Validation MAE 0.558838 → 0.558838. Mean MAE gap (Validation−Train) 0.009661 → 0.009661; RMSE gap 0.019831 → 0.019831. Validation MAE sau tuning trải từ 0.530931 đến 0.575382, std=0.019846. Cải thiện MAE trung bình 0.000000 (0.00%).
Không có cải thiện MAE đáng kể trong không gian đã xét; không coi tuning là bắt buộc phải tốt hơn cấu hình ban đầu.

**Decision Tree:** Mean Train MAE 0.005502 → 0.556383; Mean Validation MAE 0.853947 → 0.574865. Mean MAE gap (Validation−Train) 0.848445 → 0.018482; RMSE gap 1.036560 → 0.031600. Validation MAE sau tuning trải từ 0.570410 đến 0.577458, std=0.003165. Cải thiện MAE trung bình 0.279082 (32.68%).
Training Error thấp hơn rõ rệt trong cả ba fold và Validation Error cao hơn, gợi ý cấu hình ban đầu có xu hướng quá khớp. Đây là dấu hiệu từ nhiều fold, không phải kết luận chỉ từ một metric.
Validation MAE và gap cùng giảm sau tuning, phù hợp với việc giảm mức quá khớp ở cấu hình được chọn; chưa chứng minh nguyên nhân duy nhất của thay đổi.

**Random Forest:** Mean Train MAE 0.216149 → 0.534221; Mean Validation MAE 0.592260 → 0.564262. Mean MAE gap (Validation−Train) 0.376110 → 0.030042; RMSE gap 0.465921 → 0.045533. Validation MAE sau tuning trải từ 0.547493 đến 0.579769, std=0.013207. Cải thiện MAE trung bình 0.027997 (4.73%).
Training Error thấp hơn rõ rệt trong cả ba fold và Validation Error cao hơn, gợi ý cấu hình ban đầu có xu hướng quá khớp. Đây là dấu hiệu từ nhiều fold, không phải kết luận chỉ từ một metric.
Validation MAE và gap cùng giảm sau tuning, phù hợp với việc giảm mức quá khớp ở cấu hình được chọn; chưa chứng minh nguyên nhân duy nhất của thay đổi.

**XGBoost:** Mean Train MAE 0.115000 → 0.538977; Mean Validation MAE 0.646921 → 0.562303. Mean MAE gap (Validation−Train) 0.531921 → 0.023326; RMSE gap 0.646745 → 0.035609. Validation MAE sau tuning trải từ 0.545561 đến 0.579321, std=0.013784. Cải thiện MAE trung bình 0.084618 (13.08%).
Training Error thấp hơn rõ rệt trong cả ba fold và Validation Error cao hơn, gợi ý cấu hình ban đầu có xu hướng quá khớp. Đây là dấu hiệu từ nhiều fold, không phải kết luận chỉ từ một metric.
Validation MAE và gap cùng giảm sau tuning, phù hợp với việc giảm mức quá khớp ở cấu hình được chọn; chưa chứng minh nguyên nhân duy nhất của thay đổi.

Training metrics là in-sample diagnostics, không phải ước lượng tổng quát hóa độc lập. Train và Validation cùng cao có thể liên quan giới hạn biểu diễn, nhiễu xG hoặc khác biệt phân phối mùa; chưa đủ để kết luận underfitting. Gap nhỏ hoặc âm ở một mùa không chứng minh hết overfitting. So sánh RMSE, độ lệch chuẩn và từng mùa cùng MAE; không thêm kiểm định thống kê hoặc khoảng tin cậy từ ba fold.

## 10. Toàn bộ candidate thực tế

tuning_trials.csv lưu từng candidate/fold, cấu hình JSON, mùa, số dòng, Train/Validation MAE/RMSE, gaps, số dự báo âm, hash dự báo và trạng thái. Không lưu mảng dự báo hoặc model. Bảng dưới tóm tắt tất cả cấu hình đã hoàn tất; bản chi tiết từng fold nằm trong CSV.

| model | candidate_id | hyperparameters | mean_validation_mae | mean_validation_rmse | std_validation_mae | std_validation_rmse |
|---|---|---|---|---|---|---|
| Linear Regression | 1 | {"fit_intercept": true, "positive": true} | 0.571242 | 0.725047 | 0.014276 | 0.018487 |
| Linear Regression | 2 | {"fit_intercept": true, "positive": false} | 0.558838 | 0.724288 | 0.019846 | 0.026048 |
| Linear Regression | 3 | {"fit_intercept": false, "positive": true} | 0.571817 | 0.724722 | 0.015114 | 0.019631 |
| Linear Regression | 4 | {"fit_intercept": false, "positive": false} | 0.564895 | 0.724614 | 0.021218 | 0.027823 |
| Decision Tree | 1 | {"max_depth": null, "min_samples_leaf": 1, "min_samples_split": 20} | 0.713687 | 0.920378 | 0.002110 | 0.018098 |
| Decision Tree | 2 | {"max_depth": 8, "min_samples_leaf": 10, "min_samples_split": 5} | 0.607191 | 0.783767 | 0.010780 | 0.023995 |
| Decision Tree | 3 | {"max_depth": 12, "min_samples_leaf": 5, "min_samples_split": 10} | 0.699536 | 0.892127 | 0.005817 | 0.014843 |
| Decision Tree | 4 | {"max_depth": 8, "min_samples_leaf": 2, "min_samples_split": 5} | 0.642807 | 0.844330 | 0.021134 | 0.025113 |
| Decision Tree | 5 | {"max_depth": 8, "min_samples_leaf": 2, "min_samples_split": 2} | 0.645464 | 0.847734 | 0.017798 | 0.021005 |
| Decision Tree | 6 | {"max_depth": 5, "min_samples_leaf": 20, "min_samples_split": 20} | 0.587000 | 0.755211 | 0.017826 | 0.025618 |
| Decision Tree | 7 | {"max_depth": 5, "min_samples_leaf": 1, "min_samples_split": 10} | 0.595750 | 0.780218 | 0.012706 | 0.021546 |
| Decision Tree | 8 | {"max_depth": null, "min_samples_leaf": 1, "min_samples_split": 2} | 0.853947 | 1.101368 | 0.018149 | 0.025923 |
| Decision Tree | 9 | {"max_depth": 3, "min_samples_leaf": 5, "min_samples_split": 10} | 0.574865 | 0.743133 | 0.003165 | 0.010656 |
| Decision Tree | 10 | {"max_depth": 3, "min_samples_leaf": 1, "min_samples_split": 2} | 0.574865 | 0.743133 | 0.003165 | 0.010656 |
| Decision Tree | 11 | {"max_depth": 3, "min_samples_leaf": 20, "min_samples_split": 10} | 0.575526 | 0.743746 | 0.003784 | 0.011505 |
| Decision Tree | 12 | {"max_depth": 5, "min_samples_leaf": 5, "min_samples_split": 10} | 0.586662 | 0.757641 | 0.013237 | 0.020733 |
| Decision Tree | 13 | {"max_depth": 12, "min_samples_leaf": 10, "min_samples_split": 5} | 0.629151 | 0.806118 | 0.007833 | 0.028337 |
| Decision Tree | 14 | {"max_depth": 5, "min_samples_leaf": 10, "min_samples_split": 5} | 0.585249 | 0.754956 | 0.009555 | 0.017185 |
| Decision Tree | 15 | {"max_depth": null, "min_samples_leaf": 5, "min_samples_split": 10} | 0.710557 | 0.907195 | 0.007098 | 0.016008 |
| Decision Tree | 16 | {"max_depth": 3, "min_samples_leaf": 2, "min_samples_split": 2} | 0.574865 | 0.743133 | 0.003165 | 0.010656 |
| Decision Tree | 17 | {"max_depth": 12, "min_samples_leaf": 20, "min_samples_split": 2} | 0.620797 | 0.794521 | 0.017684 | 0.030978 |
| Decision Tree | 18 | {"max_depth": 12, "min_samples_leaf": 20, "min_samples_split": 5} | 0.620797 | 0.794521 | 0.017684 | 0.030978 |
| Decision Tree | 19 | {"max_depth": 3, "min_samples_leaf": 10, "min_samples_split": 2} | 0.574865 | 0.743133 | 0.003165 | 0.010656 |
| Decision Tree | 20 | {"max_depth": 5, "min_samples_leaf": 5, "min_samples_split": 20} | 0.584410 | 0.753284 | 0.010682 | 0.017555 |
| Decision Tree | 21 | {"max_depth": 8, "min_samples_leaf": 10, "min_samples_split": 20} | 0.607191 | 0.783767 | 0.010780 | 0.023995 |
| Decision Tree | 22 | {"max_depth": null, "min_samples_leaf": 5, "min_samples_split": 2} | 0.710557 | 0.907195 | 0.007098 | 0.016008 |
| Decision Tree | 23 | {"max_depth": 5, "min_samples_leaf": 2, "min_samples_split": 10} | 0.593514 | 0.776439 | 0.012460 | 0.019681 |
| Decision Tree | 24 | {"max_depth": 8, "min_samples_leaf": 1, "min_samples_split": 10} | 0.637339 | 0.836941 | 0.024343 | 0.032376 |
| Decision Tree | 25 | {"max_depth": 12, "min_samples_leaf": 5, "min_samples_split": 5} | 0.699536 | 0.892127 | 0.005817 | 0.014843 |
| Random Forest | 1 | {"max_depth": null, "max_features": 0.6, "min_samples_leaf": 10, "n_estimators": 100} | 0.567151 | 0.727662 | 0.018590 | 0.022871 |
| Random Forest | 2 | {"max_depth": 4, "max_features": 0.8, "min_samples_leaf": 5, "n_estimators": 200} | 0.564798 | 0.727222 | 0.012424 | 0.017784 |
| Random Forest | 3 | {"max_depth": 12, "max_features": 0.6, "min_samples_leaf": 10, "n_estimators": 200} | 0.566746 | 0.727697 | 0.018678 | 0.022974 |
| Random Forest | 4 | {"max_depth": 12, "max_features": 1.0, "min_samples_leaf": 1, "n_estimators": 200} | 0.584582 | 0.737799 | 0.021083 | 0.026123 |
| Random Forest | 5 | {"max_depth": 8, "max_features": 0.8, "min_samples_leaf": 5, "n_estimators": 300} | 0.568793 | 0.728569 | 0.019493 | 0.023896 |
| Random Forest | 6 | {"max_depth": 4, "max_features": 0.8, "min_samples_leaf": 1, "n_estimators": 100} | 0.565622 | 0.727238 | 0.011458 | 0.017483 |
| Random Forest | 7 | {"max_depth": null, "max_features": 1.0, "min_samples_leaf": 1, "n_estimators": 100} | 0.592260 | 0.744861 | 0.019649 | 0.025194 |
| Random Forest | 8 | {"max_depth": 8, "max_features": 1.0, "min_samples_leaf": 2, "n_estimators": 300} | 0.571435 | 0.729289 | 0.019390 | 0.024590 |
| Random Forest | 9 | {"max_depth": 8, "max_features": 1.0, "min_samples_leaf": 5, "n_estimators": 100} | 0.571479 | 0.732410 | 0.018130 | 0.023449 |
| Random Forest | 10 | {"max_depth": 4, "max_features": 0.8, "min_samples_leaf": 5, "n_estimators": 100} | 0.565171 | 0.727695 | 0.012714 | 0.017822 |
| Random Forest | 11 | {"max_depth": 8, "max_features": 0.8, "min_samples_leaf": 2, "n_estimators": 100} | 0.574436 | 0.732621 | 0.015454 | 0.021534 |
| Random Forest | 12 | {"max_depth": 12, "max_features": 0.6, "min_samples_leaf": 5, "n_estimators": 100} | 0.569486 | 0.729798 | 0.018578 | 0.023474 |
| Random Forest | 13 | {"max_depth": 12, "max_features": 0.8, "min_samples_leaf": 10, "n_estimators": 200} | 0.568178 | 0.728570 | 0.018050 | 0.022294 |
| Random Forest | 14 | {"max_depth": null, "max_features": 1.0, "min_samples_leaf": 1, "n_estimators": 200} | 0.589247 | 0.742080 | 0.019823 | 0.025714 |
| Random Forest | 15 | {"max_depth": 12, "max_features": 1.0, "min_samples_leaf": 2, "n_estimators": 200} | 0.577926 | 0.734069 | 0.019765 | 0.025293 |
| Random Forest | 16 | {"max_depth": 8, "max_features": 1.0, "min_samples_leaf": 2, "n_estimators": 200} | 0.570994 | 0.729276 | 0.019371 | 0.024635 |
| Random Forest | 17 | {"max_depth": 4, "max_features": 1.0, "min_samples_leaf": 2, "n_estimators": 100} | 0.564262 | 0.726435 | 0.013207 | 0.019123 |
| Random Forest | 18 | {"max_depth": 8, "max_features": 1.0, "min_samples_leaf": 10, "n_estimators": 100} | 0.567723 | 0.729831 | 0.017559 | 0.022048 |
| Random Forest | 19 | {"max_depth": null, "max_features": 0.8, "min_samples_leaf": 2, "n_estimators": 300} | 0.580488 | 0.736165 | 0.019819 | 0.024861 |
| Random Forest | 20 | {"max_depth": 12, "max_features": 0.6, "min_samples_leaf": 1, "n_estimators": 200} | 0.582079 | 0.736780 | 0.019942 | 0.025104 |
| Random Forest | 21 | {"max_depth": 4, "max_features": 0.6, "min_samples_leaf": 10, "n_estimators": 300} | 0.565458 | 0.727349 | 0.012520 | 0.017635 |
| Random Forest | 22 | {"max_depth": null, "max_features": 0.6, "min_samples_leaf": 10, "n_estimators": 300} | 0.566676 | 0.727945 | 0.018677 | 0.022292 |
| Random Forest | 23 | {"max_depth": null, "max_features": 0.6, "min_samples_leaf": 1, "n_estimators": 300} | 0.586962 | 0.738472 | 0.021447 | 0.027441 |
| Random Forest | 24 | {"max_depth": null, "max_features": 0.6, "min_samples_leaf": 2, "n_estimators": 300} | 0.574819 | 0.732061 | 0.021995 | 0.025888 |
| Random Forest | 25 | {"max_depth": 8, "max_features": 0.8, "min_samples_leaf": 5, "n_estimators": 200} | 0.569219 | 0.729412 | 0.020161 | 0.024526 |
| XGBoost | 1 | {"colsample_bytree": 0.7, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 10, "n_estimators": 350, "reg_lambda": 5, "subsample": 1.0} | 0.584790 | 0.759844 | 0.021198 | 0.036148 |
| XGBoost | 2 | {"colsample_bytree": 1.0, "learning_rate": 0.02, "max_depth": 4, "min_child_weight": 10, "n_estimators": 350, "reg_lambda": 1, "subsample": 0.85} | 0.570231 | 0.733695 | 0.022369 | 0.031672 |
| XGBoost | 3 | {"colsample_bytree": 0.85, "learning_rate": 0.2, "max_depth": 2, "min_child_weight": 5, "n_estimators": 200, "reg_lambda": 5, "subsample": 1.0} | 0.572696 | 0.743898 | 0.021697 | 0.032462 |
| XGBoost | 4 | {"colsample_bytree": 0.7, "learning_rate": 0.05, "max_depth": 2, "min_child_weight": 3, "n_estimators": 100, "reg_lambda": 10, "subsample": 0.85} | 0.562303 | 0.724073 | 0.013784 | 0.020581 |
| XGBoost | 5 | {"colsample_bytree": 1.0, "learning_rate": 0.1, "max_depth": 2, "min_child_weight": 10, "n_estimators": 350, "reg_lambda": 10, "subsample": 0.85} | 0.576353 | 0.746281 | 0.022623 | 0.031165 |
| XGBoost | 6 | {"colsample_bytree": 0.85, "learning_rate": 0.2, "max_depth": 6, "min_child_weight": 10, "n_estimators": 200, "reg_lambda": 10, "subsample": 0.7} | 0.624002 | 0.804773 | 0.018369 | 0.024612 |
| XGBoost | 7 | {"colsample_bytree": 0.85, "learning_rate": 0.2, "max_depth": 3, "min_child_weight": 3, "n_estimators": 200, "reg_lambda": 5, "subsample": 0.7} | 0.612694 | 0.787924 | 0.027820 | 0.033475 |
| XGBoost | 8 | {"colsample_bytree": 0.85, "learning_rate": 0.1, "max_depth": 6, "min_child_weight": 1, "n_estimators": 100, "reg_lambda": 5, "subsample": 0.7} | 0.586175 | 0.755010 | 0.026497 | 0.033321 |
| XGBoost | 9 | {"colsample_bytree": 0.7, "learning_rate": 0.02, "max_depth": 3, "min_child_weight": 1, "n_estimators": 350, "reg_lambda": 5, "subsample": 0.85} | 0.562942 | 0.725883 | 0.019747 | 0.027887 |
| XGBoost | 10 | {"colsample_bytree": 0.7, "learning_rate": 0.2, "max_depth": 6, "min_child_weight": 5, "n_estimators": 200, "reg_lambda": 1, "subsample": 1.0} | 0.624407 | 0.807961 | 0.014516 | 0.035113 |
| XGBoost | 11 | {"colsample_bytree": 0.7, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 1, "n_estimators": 200, "reg_lambda": 5, "subsample": 0.85} | 0.577895 | 0.746323 | 0.017842 | 0.025217 |
| XGBoost | 12 | {"colsample_bytree": 0.85, "learning_rate": 0.05, "max_depth": 4, "min_child_weight": 1, "n_estimators": 200, "reg_lambda": 10, "subsample": 0.7} | 0.574437 | 0.740989 | 0.024142 | 0.028562 |
| XGBoost | 13 | {"colsample_bytree": 0.85, "learning_rate": 0.05, "max_depth": 4, "min_child_weight": 5, "n_estimators": 100, "reg_lambda": 5, "subsample": 0.7} | 0.565683 | 0.729262 | 0.022315 | 0.027745 |
| XGBoost | 14 | {"colsample_bytree": 1.0, "learning_rate": 0.2, "max_depth": 4, "min_child_weight": 10, "n_estimators": 100, "reg_lambda": 1, "subsample": 1.0} | 0.595733 | 0.775476 | 0.022261 | 0.039714 |
| XGBoost | 15 | {"colsample_bytree": 0.7, "learning_rate": 0.1, "max_depth": 4, "min_child_weight": 10, "n_estimators": 350, "reg_lambda": 5, "subsample": 1.0} | 0.596782 | 0.777169 | 0.025922 | 0.042630 |
| XGBoost | 16 | {"colsample_bytree": 1.0, "learning_rate": 0.1, "max_depth": 4, "min_child_weight": 1, "n_estimators": 350, "reg_lambda": 1, "subsample": 0.85} | 0.619310 | 0.794163 | 0.024581 | 0.038200 |
| XGBoost | 17 | {"colsample_bytree": 0.85, "learning_rate": 0.2, "max_depth": 6, "min_child_weight": 3, "n_estimators": 200, "reg_lambda": 1, "subsample": 0.85} | 0.639308 | 0.821277 | 0.011086 | 0.020738 |
| XGBoost | 18 | {"colsample_bytree": 1.0, "learning_rate": 0.05, "max_depth": 4, "min_child_weight": 1, "n_estimators": 200, "reg_lambda": 5, "subsample": 0.85} | 0.573175 | 0.738905 | 0.021115 | 0.028771 |
| XGBoost | 19 | {"colsample_bytree": 1.0, "learning_rate": 0.2, "max_depth": 2, "min_child_weight": 10, "n_estimators": 200, "reg_lambda": 1, "subsample": 0.85} | 0.586355 | 0.755138 | 0.023293 | 0.033545 |
| XGBoost | 20 | {"colsample_bytree": 0.85, "learning_rate": 0.1, "max_depth": 4, "min_child_weight": 10, "n_estimators": 200, "reg_lambda": 10, "subsample": 0.7} | 0.588966 | 0.757091 | 0.027617 | 0.033171 |
| XGBoost | 21 | {"colsample_bytree": 0.7, "learning_rate": 0.05, "max_depth": 2, "min_child_weight": 3, "n_estimators": 200, "reg_lambda": 10, "subsample": 0.7} | 0.564440 | 0.726640 | 0.018362 | 0.025111 |
| XGBoost | 22 | {"colsample_bytree": 0.7, "learning_rate": 0.1, "max_depth": 4, "min_child_weight": 1, "n_estimators": 100, "reg_lambda": 1, "subsample": 1.0} | 0.572237 | 0.743271 | 0.016684 | 0.031492 |
| XGBoost | 23 | {"colsample_bytree": 0.85, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 5, "n_estimators": 350, "reg_lambda": 1, "subsample": 1.0} | 0.596598 | 0.772549 | 0.016777 | 0.035836 |
| XGBoost | 24 | {"colsample_bytree": 0.85, "learning_rate": 0.02, "max_depth": 4, "min_child_weight": 10, "n_estimators": 350, "reg_lambda": 5, "subsample": 0.85} | 0.566523 | 0.730688 | 0.021621 | 0.029578 |
| XGBoost | 25 | {"colsample_bytree": 0.85, "learning_rate": 0.1, "max_depth": 3, "min_child_weight": 3, "n_estimators": 350, "reg_lambda": 1, "subsample": 1.0} | 0.605864 | 0.781525 | 0.014625 | 0.039326 |

## 11. Model-selection bias và giới hạn phương pháp

Ba fold này đồng thời dùng chọn hyperparameters và mô tả cấu hình được chọn, nên score tốt nhất có thể lạc quan do quá trình lựa chọn. Đây là kết quả development, không phải ước lượng hiệu năng độc lập sau chọn hoặc bằng chứng chắc chắn cho dữ liệu tương lai. Fit lại để kiểm chứng tái lập vẫn dùng chính folds cũ và không tạo một phép đánh giá độc lập. Final Test 2024/2025 được giữ nguyên cho giai đoạn sau. Không thực hiện Nested Cross-Validation trong tác vụ này. Xem [giải thích selection bias của scikit-learn](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html).

Ngân sách 25 cấu hình ngẫu nhiên mỗi thuật toán cây không bảo đảm tối ưu toàn bộ không gian. Không thay fold, budget, features hoặc thêm model sau khi xem kết quả. Hai bản ghi cùng trận có tương quan; không báo độ tin cậy thống kê quá mức.

## 12. Kiểm chứng đã thực thi và tái lập

| Kiểm chứng | Kết quả | Bằng chứng |
|---|---|---|
| Kiểm thử Phase 4 và Phase 5 | Đạt | Đã chạy 31 tests; failures=0, errors=0, skipped=0. |
| Kiểm chứng tham chiếu Phase 4 | Đạt | Đọc 15 kết quả thật và tính lại summary; khớp CSV Phase 4 với atol=1e-12, rtol=0. |
| Development và Final Test | Đạt | 3800 dòng mùa 2019–2023; chỉ ba fold cũ, mùa 2024/2025 không tham gia fit/score. |
| Thứ tự và schema | Đạt | X/y/metadata giữ cùng thứ tự; đúng 13 features và target tách riêng. |
| Tham chiếu Historical Baseline/fold 1 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Historical Baseline/fold 2 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Historical Baseline/fold 3 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Linear Regression/fold 1 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Linear Regression/fold 2 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Linear Regression/fold 3 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Decision Tree/fold 1 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Decision Tree/fold 2 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Decision Tree/fold 3 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Random Forest/fold 1 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Random Forest/fold 2 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu Random Forest/fold 3 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu XGBoost/fold 1 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu XGBoost/fold 2 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Tham chiếu XGBoost/fold 3 | Đạt | Validation MAE/RMSE tính lại khớp Phase 4; Train-only, cùng clipping. |
| Linear Regression: mẫu candidate tái lập | Đạt | 4 cấu hình duy nhất, seed=42; không đổi ngân sách. |
| Linear Regression: search theo thời gian | Đạt | Truyền rõ indices iloc khớp X/y; Pipeline chứa preprocessing, refit=False, error_score=raise, n_jobs=1. |
| Linear Regression: search và audit hoàn tất | Đạt | 12 candidate-fold; median Train-only, 13 features, ô hợp lệ giữ nguyên, metric hữu hạn; ledger kiểm tra cả Train và Validation. |
| Linear Regression: fit mới sau chọn | Đạt | Train/Validation metrics và hash mọi dự báo khớp candidate được chọn trong search. |
| Linear Regression: tái lập cấu hình chọn | Đạt | Fit lại bằng các Pipeline mới; metric và hash dự báo Train/Validation giống chính xác ở cả ba fold. |
| Decision Tree: mẫu candidate tái lập | Đạt | 25 cấu hình duy nhất, seed=42; không đổi ngân sách. |
| Decision Tree: search theo thời gian | Đạt | Truyền rõ indices iloc khớp X/y; Pipeline chứa preprocessing, refit=False, error_score=raise, n_jobs=1. |
| Decision Tree: search và audit hoàn tất | Đạt | 75 candidate-fold; median Train-only, 13 features, ô hợp lệ giữ nguyên, metric hữu hạn; ledger kiểm tra cả Train và Validation. |
| Decision Tree: fit mới sau chọn | Đạt | Train/Validation metrics và hash mọi dự báo khớp candidate được chọn trong search. |
| Decision Tree: tái lập cấu hình chọn | Đạt | Fit lại bằng các Pipeline mới; metric và hash dự báo Train/Validation giống chính xác ở cả ba fold. |
| Random Forest: mẫu candidate tái lập | Đạt | 25 cấu hình duy nhất, seed=42; không đổi ngân sách. |
| Random Forest: search theo thời gian | Đạt | Truyền rõ indices iloc khớp X/y; Pipeline chứa preprocessing, refit=False, error_score=raise, n_jobs=1. |
| Random Forest: search và audit hoàn tất | Đạt | 75 candidate-fold; median Train-only, 13 features, ô hợp lệ giữ nguyên, metric hữu hạn; ledger kiểm tra cả Train và Validation. |
| Random Forest: fit mới sau chọn | Đạt | Train/Validation metrics và hash mọi dự báo khớp candidate được chọn trong search. |
| Random Forest: tái lập cấu hình chọn | Đạt | Fit lại bằng các Pipeline mới; metric và hash dự báo Train/Validation giống chính xác ở cả ba fold. |
| XGBoost: mẫu candidate tái lập | Đạt | 25 cấu hình duy nhất, seed=42; không đổi ngân sách. |
| XGBoost: search theo thời gian | Đạt | Truyền rõ indices iloc khớp X/y; Pipeline chứa preprocessing, refit=False, error_score=raise, n_jobs=1. |
| XGBoost: search và audit hoàn tất | Đạt | 75 candidate-fold; median Train-only, 13 features, ô hợp lệ giữ nguyên, metric hữu hạn; ledger kiểm tra cả Train và Validation. |
| XGBoost: fit mới sau chọn | Đạt | Train/Validation metrics và hash mọi dự báo khớp candidate được chọn trong search. |
| XGBoost: tái lập cấu hình chọn | Đạt | Fit lại bằng các Pipeline mới; metric và hash dự báo Train/Validation giống chính xác ở cả ba fold. |
| 237 trial và bốn thuật toán | Đạt | 79 cấu hình × 3 fold; đủ 4 Linear Regression và 25 cấu hình cho mỗi thuật toán còn lại. |
| Benchmark cố định | Đạt | Baseline không tuning, không có best_params; mọi dự báo trước/sau giống nhau và khớp Phase 4. |
| Không thay file Phase 4 | Đạt | SHA-256 của 17 file hiện có không đổi. |
| Đọc lại đầu ra | Đạt | Ba CSV và một JSON đã đọc lại, kiểm tra schema và giá trị trước khi thay thế file đích; file tạm kế thừa quyền thư mục đích. |

Unit tests thực tế: 31 đã chạy; failures=0, errors=0, skipped=0.

```text
test_actual_fold_counts_and_reserved_seasons (test_training.TrainingTests.test_actual_fold_counts_and_reserved_seasons) ... ok
test_csv_roundtrip_and_protection_on_failed_validation (test_training.TrainingTests.test_csv_roundtrip_and_protection_on_failed_validation) ... ok
test_every_estimator_fit_receives_only_training_indices (test_training.TrainingTests.test_every_estimator_fit_receives_only_training_indices) ... ok
test_fixed_model_configuration_and_seeds (test_training.TrainingTests.test_fixed_model_configuration_and_seeds) ... ok
test_imputer_fit_receives_only_training_indices (test_training.TrainingTests.test_imputer_fit_receives_only_training_indices) ... ok
test_metrics_use_clipped_predictions_and_rmse (test_training.TrainingTests.test_metrics_use_clipped_predictions_and_rmse) ... ok
test_reject_future_dates_in_training_season (test_training.TrainingTests.test_reject_future_dates_in_training_season) ... ok
test_reject_incomplete_match (test_training.TrainingTests.test_reject_incomplete_match) ... ok
test_reject_match_crossing_seasons (test_training.TrainingTests.test_reject_match_crossing_seasons) ... ok
test_reject_missing_model_fold (test_training.TrainingTests.test_reject_missing_model_fold) ... ok
test_reject_non_expanding_configuration (test_training.TrainingTests.test_reject_non_expanding_configuration) ... ok
test_reject_non_finite_predictions (test_training.TrainingTests.test_reject_non_finite_predictions) ... ok
test_reject_reserved_season_configuration (test_training.TrainingTests.test_reject_reserved_season_configuration) ... ok
test_reproducibility_detects_changed_prediction (test_training.TrainingTests.test_reproducibility_detects_changed_prediction) ... ok
test_sklearn_splitter_interface (test_training.TrainingTests.test_sklearn_splitter_interface) ... ok
test_source_dataframe_preserved (test_training.TrainingTests.test_source_dataframe_preserved) ... ok
test_split_is_independent_of_csv_order (test_training.TrainingTests.test_split_is_independent_of_csv_order) ... ok
test_summary_population_std_and_equal_fold_weights (test_training.TrainingTests.test_summary_population_std_and_equal_fold_weights) ... ok
test_windows_exports_inherit_directory_permissions (test_training.TrainingTests.test_windows_exports_inherit_directory_permissions) ... ok
test_budget_unique_and_reproducible_candidates (test_tuning.TuningTests.test_budget_unique_and_reproducible_candidates) ... ok
test_development_positions_align_with_search_inputs (test_tuning.TuningTests.test_development_positions_align_with_search_inputs) ... ok
test_every_candidate_fits_only_its_training_partition (test_tuning.TuningTests.test_every_candidate_fits_only_its_training_partition) ... ok
test_exported_csv_json_roundtrip_and_failed_validation_preserves_outputs (test_tuning.TuningTests.test_exported_csv_json_roundtrip_and_failed_validation_preserves_outputs) ... ok
test_linear_search_exhausts_exact_four_combinations (test_tuning.TuningTests.test_linear_search_exhausts_exact_four_combinations) ... ok
test_output_validation_rejects_missing_trial_or_artificial_baseline_params (test_tuning.TuningTests.test_output_validation_rejects_missing_trial_or_artificial_baseline_params) ... ok
test_pipeline_clones_without_fitted_state (test_tuning.TuningTests.test_pipeline_clones_without_fitted_state) ... ok
test_search_does_not_refit_full_development (test_tuning.TuningTests.test_search_does_not_refit_full_development) ... ok
test_search_scores_have_correct_sign_and_clip (test_tuning.TuningTests.test_search_scores_have_correct_sign_and_clip) ... ok
test_selected_evaluation_comparison_detects_prediction_change (test_tuning.TuningTests.test_selected_evaluation_comparison_detects_prediction_change) ... ok
test_selection_uses_mae_then_rmse_tolerance_and_stable_params (test_tuning.TuningTests.test_selection_uses_mae_then_rmse_tolerance_and_stable_params) ... ok
test_tuning_json_and_csv_inherit_directory_permissions (test_tuning.TuningTests.test_tuning_json_and_csv_inherit_directory_permissions) ... ok

----------------------------------------------------------------------
Ran 31 tests in 3.906s

OK
```

Tests mới kiểm chứng budget/mẫu seed, đúng bốn cấu hình Linear Regression, alignment của development, clone Pipeline, fit mới đúng Train trong search, refit=False, score âm/clipping, luật hòa, dấu vết dự báo, schema/JSON và bảo toàn quyền ACL khi xuất. Số liệu nhân tạo trong tests chỉ phục vụ fixtures, không được dùng làm kết quả Phase 5.

Phạm vi tái lập: tạo lại đủ mẫu 79 candidate và so khớp với search; với từng cấu hình chọn, fit mới ba fold để kiểm tra khớp search, sau đó chạy lại thêm ba fold để đối chiếu metric và hash mọi dự báo Train/Validation chính xác. Không chạy lại toàn bộ search lần hai và không tuyên bố đã xác minh từng candidate qua hai lần full search.

| file | sha256 |
|---|---|
| tuning_trials.csv | 9d072e4a7e631ac1e3521e2b1d5a532bcf7f97da770e4592d689b086d0158099 |
| tuning_summary.csv | a0472aeea2d48d8aec8d989b3ceb8398d9b4d3020c34067123036e97fa9a0907 |
| overfitting_diagnostics.csv | a645d0e2b416f64799b708f693854b528c3cf946f49642ee9e83257049dc37e4 |
| best_params.json | c664b9844986dd80bdef1de7ab16a8a136c29cc0dc7c18bc77d674e51cc10115 |

Các file CSV được ghi 17 chữ số có nghĩa và đọc lại với atol/rtol=1e-14 để bao phủ sai số parser; JSON được đối chiếu đầy đủ. Trước khi ghi, kiểm tra lựa chọn best từ trials, summary từ diagnostics, đủ 237 dòng/79 cấu hình/30 diagnostics/5 dòng summary và không có duplicate ngoài ba folds chủ đích.

### Đối chiếu độc lập sau xuất file

Đã đọc lại trực tiếp 237 dòng trials, 5 dòng summary, 30 dòng diagnostics và best_params.json từ ổ đĩa. Kiểm tra độc lập bằng NumPy xác nhận mean/std ddof=0, các gaps, cải thiện MAE và metadata cấu hình chọn khớp dữ liệu gốc trong sai số parser 1e-14. Kiểm tra riêng trước tuning khớp toàn bộ 15 metric pairs của Phase 4 với atol=1e-12. Tái tạo từng cấu hình bằng seed, kiểm tra ranh giới mùa, trạng thái success và không trùng candidate-fold.

SHA-256 của 17 file được bảo vệ đã đối chiếu lại sau xuất: tất cả giữ nguyên. Cả bốn file đầu ra thực tế đều có AreAccessRulesProtected=False trên Windows, tức đang kế thừa quyền thư mục đích; không còn tình huống ACL riêng của thư mục tạm. Chỉ có đúng bốn file yêu cầu trong outputs/tuning/.

Hash dùng đối chiếu tái lập là SHA-256 trên mảng dự báo sau clipping đã chuyển sang float64 little-endian. Phạm vi xác nhận là metrics và dự báo sau xử lý; không khẳng định đã chạy lại toàn bộ 79 cấu hình.

### Số dự báo âm trước clipping trong search

| Model | Train | Validation |
|---|---:|---:|
| Linear Regression | 0 | 0 |
| Decision Tree | 0 | 0 |
| Random Forest | 0 | 0 |
| XGBoost | 0 | 10 |

Có tổng cộng 10 lượt dự báo âm ở Validation trước clipping trên các tổ hợp candidate–fold; đây không phải số trận phân biệt. Tất cả được cắt về 0 trước tính cả hai metric, đúng scorer dùng để chọn hyperparameters. Các tổng này không bao gồm những lượt chẩn đoán hoặc tái lập ngoài search.

### Khoảng cách giữa hai cấu hình đứng đầu

Mean Validation MAE của Linear Regression thấp hơn XGBoost 0.003465. Đây là khoảng cách nhỏ so với mức biến động theo mùa đã báo cáo; không có kiểm định ý nghĩa thống kê và không kết luận ưu thế chắc chắn trên dữ liệu tương lai. Thứ hạng này chỉ áp dụng cho không gian và ngân sách Phase 5.

## 13. Môi trường và cách chạy

Python 3.14.0, NumPy 2.5.4, Pandas 3.1.0, SciPy 1.18.1, scikit-learn 1.9.1, threadpoolctl 3.8.0. XGBoost dùng version cài sẵn trong .venv: 3.4.1. Không thêm dependency; tái sử dụng scripts/training/requirements.txt.

Lệnh đã thực thi:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_tuning.py -v
.\.venv\Scripts\python.exe -m scripts.training.tune_models
```

Lệnh tuning tự chạy lại cả tests Phase 4/5 trước search, sau đó thực hiện full budget và cập nhật đúng bốn output cùng báo cáo này. Có thể chạy python -m scripts.training.tune_models nếu interpreter hiện hành đã có đủ dependency. Không cần quyền Administrator; file tạm nằm trực tiếp cạnh output để kế thừa ACL.

Thời gian thực thi của lệnh tuning này (gồm tests và diagnostics): 122.63 giây.

## 14. Bảo toàn file, thay đổi và vấn đề

Tạo scripts/training/tune_models.py, tests/test_tuning.py, bốn file outputs/tuning/ và duy nhất báo cáo Phase 5 này. Không thay preprocessing, training Phase 4, requirements, tests Phase 4, dataset hoặc báo cáo cũ. Không commit/push, không lưu model, không tạo bản sao phiên bản hoặc thư mục không cần thiết.

| File có sẵn | SHA-256 trước thực thi | Sau thực thi |
|---|---|---|
| `data/laliga_processed.csv` | `666661b49f4055104bd73b8ceb53f50407bf6e90cae6551dbbee820fe9fd6a3a` | Giữ nguyên |
| `data/laliga_processed.xlsx` | `47023b9efd583783c35b0b45030c3c747ca1fd09519164631f46543574540ab3` | Giữ nguyên |
| `data/laliga_processed_normalized.csv` | `90000ce22f42abe5eb5b5bfa38ad1ed5ef7b1c1c75cd4d39e749e7b324e0e5ca` | Giữ nguyên |
| `data/matches_laliga.csv` | `3cfeb29ea2e76d6a8a411f31af6182c6951fd477903b8b6d0401b58e10b415e2` | Giữ nguyên |
| `data/preprocess_laliga.py` | `fb5e35f268c7b205dc4d5854c5eba75ad74d903fcc08ae1cb5fdaf9f9963aadb` | Giữ nguyên |
| `outputs/training/cv_fold_results.csv` | `559ae9fc455516ab207b17cff72a9b66b69cb0e2bbc7a44a8fb80922aadd1185` | Giữ nguyên |
| `outputs/training/cv_summary.csv` | `f756d0e5830d70365b13f1dcdb6c5416998cab5133f3c6f5b140570900f5e9ac` | Giữ nguyên |
| `Phases/Implement Expanding Window Cross-Validation and Initial Model Training.md` | `87fe153470e428e8515b68185a6a666cb143a505f1c45c9ed9857ecacb5d32ea` | Giữ nguyên |
| `Phases/Normalize Numeric Formats in the La Liga Dataset.md` | `628ef4057a4ed505c59f83d2467ce2b0cf67bc9e747848c1300532e06f1b5979` | Giữ nguyên |
| `Phases/Prepare Leakage-Safe Median Imputation for La Liga.md` | `e158bf9016c4ded33e2e0c993a74f5c677d875550d6e0a653c26d2c99424b885` | Giữ nguyên |
| `scripts/normalize_laliga_numeric.py` | `1d40c912a1c4df9c765cbbd3e0ff6ddbe03da767697531c7be058ea9914aa726` | Giữ nguyên |
| `scripts/prepare_training_features.py` | `59da3125592544ea1c958e7550e57b53d94b3b0c3facf570ec91d4efa8364b7d` | Giữ nguyên |
| `scripts/training/__init__.py` | `82e333be83e2d170340311e2da982cefa24e00af3c9aa30909348e0aab927d03` | Giữ nguyên |
| `scripts/training/cross_validation.py` | `b240eee03801efc8139ec0a2e24fc51620e3bb00f8bdc98ab0adef62a8abc13f` | Giữ nguyên |
| `scripts/training/requirements.txt` | `0b67a255ac089bdb86250f8fdc1db7b8ac6e772ad3d06c743edc62bb08fea06d` | Giữ nguyên |
| `scripts/training/train_models.py` | `2cba8f2053b8742bea671671d67d41d35f64a4d3e73801596da37323456f10d2` | Giữ nguyên |
| `tests/test_training.py` | `53a2a3928b50ae666775c36bd97768e2ce03aca082502e29015edae6816cbc3b` | Giữ nguyên |

Không ghi nhận cảnh báo từ các lệnh search đã hoàn tất.
Không có lỗi hoặc vấn đề chưa giải quyết chặn hoàn thành Phase 5 trong phạm vi đã nêu.

## 15. Tài liệu API

Search lấy mẫu từ danh sách hữu hạn và hỗ trợ multi-metric: [RandomizedSearchCV](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.RandomizedSearchCV.html). Scorer callable trả dictionary metrics theo [hướng dẫn scikit-learn](https://scikit-learn.org/stable/modules/model_evaluation.html#using-multiple-metric-evaluation).

## 16. Kết luận và đề xuất Phase 6

Đã hoàn tất đúng ngân sách search, chẩn đoán trước/sau, kiểm chứng và bốn file kết quả. Linear Regression có Mean Validation MAE sau tuning thấp nhất trong so sánh development (0.558838); đây chưa phải Final Model hoặc hiệu năng Final Test.

Phase 6 có thể lập kế hoạch kiểm tra độ bền của cấu hình và đánh giá độc lập theo phạm vi được phê duyệt; chưa thực hiện Ablation Study, Feature Importance, Final Test, serialization hoặc triển khai. Dừng sau Phase 5 và chờ yêu cầu tiếp theo.
