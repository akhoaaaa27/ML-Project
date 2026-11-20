# Chuẩn bị Median Imputation an toàn trước Data Leakage cho La Liga

## 1. Mục tiêu và phạm vi

Chuẩn bị cơ chế khôi phục Fixed Prior về NaN và Median Imputation chỉ học từ Train của từng fold. Chỉ kiểm chứng bộ xử lý; không huấn luyện, tối ưu hoặc đánh giá mô hình; không chạy Cross-Validation chính thức và không đánh giá Final Test.

## 2. Repository và Preprocessing

Đã đọc `data/preprocess_laliga.py`, `scripts/normalize_laliga_numeric.py` và CSV chuẩn hóa. Repository có Git trên nhánh main; không có module chuẩn bị features tương đương khi bắt đầu. Module mới tái sử dụng FEATURES, REQUIRED_COLUMNS và TEXT_COLUMNS từ script chuẩn hóa, không sửa script đó.

`add_history_features()` nhóm theo team/stint; stint được tính lại khi có khoảng trống mùa > 1. Rolling sử dụng shift(1), window 5, min_periods=1. matches_seen là cumcount; short_history đánh dấu số trận < 5. `.fillna(DEFAULT_PRIOR[dst])` điền các hằng số khi chưa có lịch sử. Đã đối chiếu riêng counters theo team/stint và các cột đối thủ, không tính lại rolling averages.

**Fixed Prior** được khai báo sẵn trong mã nguồn, không phải median học tự động hoặc trung vị từ tương lai. **Median Imputation** ở module mới học từ những giá trị lịch sử hợp lệ của Train sau khi khôi phục prior. Kiểm tra trùng giá trị prior chỉ dùng xác minh các ô có counter bằng 0, không dùng để chọn mọi ô thiếu.

## 3. Dữ liệu và những ô được khôi phục

- Dữ liệu: 4700 dòng × 26 cột; không có missing ban đầu.
- matches_seen == 0: 38 dòng; opponent_matches_seen == 0: 38 dòng.
- Khôi phục tổng cộng **304 ô**; số stint kiểm chứng được: 38.
- Giữ nguyên 152 dòng có 0 < matches_seen < 5.

| Feature | Fixed Prior từ mã nguồn | Ô khôi phục | Ô có lịch sử hợp lệ trùng prior được giữ nguyên |
|---|---:|---:|---:|
| `xg_avg5` | 1.2 | 38 | 110 |
| `xga_avg5` | 1.24 | 38 | 95 |
| `gf_avg5` | 1.2 | 38 | 629 |
| `ga_avg5` | 1.2 | 38 | 654 |
| `shot_avg5` | 11.2 | 38 | 149 |
| `sot_avg5` | 3.6 | 38 | 333 |
| `opponent_xg_avg5` | 1.2 | 38 | 110 |
| `opponent_xga_avg5` | 1.24 | 38 | 95 |

### Mã mùa thực tế trong dữ liệu

| season | Số dòng | Ngày đầu | Ngày cuối |
|---|---:|---|---|
| 2019 | 760 | 2019-08-16 | 2020-07-19 |
| 2020 | 760 | 2020-09-12 | 2021-05-23 |
| 2021 | 760 | 2021-08-13 | 2022-05-22 |
| 2022 | 760 | 2022-08-12 | 2023-06-04 |
| 2023 | 760 | 2023-08-11 | 2024-05-26 |
| 2024 | 760 | 2024-08-15 | 2025-05-25 |
| 2025 | 140 | 2025-08-15 | 2025-09-30 |

### Danh sách và thứ tự 13 input features

| Thứ tự | Feature | Kiểu sau transform | Cách xử lý |
|---|---|---|---|
| 1 | `is_home` | `int64` | Giữ nguyên |
| 2 | `matches_seen` | `int64` | Giữ nguyên |
| 3 | `short_history` | `int64` | Giữ nguyên |
| 4 | `xg_avg5` | `float64` | Median chỉ học từ Train |
| 5 | `xga_avg5` | `float64` | Median chỉ học từ Train |
| 6 | `gf_avg5` | `float64` | Median chỉ học từ Train |
| 7 | `ga_avg5` | `float64` | Median chỉ học từ Train |
| 8 | `shot_avg5` | `float64` | Median chỉ học từ Train |
| 9 | `sot_avg5` | `float64` | Median chỉ học từ Train |
| 10 | `opponent_xg_avg5` | `float64` | Median chỉ học từ Train |
| 11 | `opponent_xga_avg5` | `float64` | Median chỉ học từ Train |
| 12 | `opponent_matches_seen` | `int64` | Giữ nguyên |
| 13 | `opponent_short_history` | `int64` | Giữ nguyên |

Target `xg` có kiểu float64 trong dữ liệu hiện tại, được giữ riêng trong y và không tham gia imputer.

## 4. Thiết kế module và cách tái sử dụng

- `read_history_config()` đọc hằng số bằng AST và kiểm tra những thành phần chính của logic lịch sử; không chạy Feature Engineering.
- `load_dataset()` và `validate_source_frame()` kiểm tra tên cột, kiểu số, số hữu hạn, flags và hai phía của trận đấu. Nguồn cần còn nguyên Fixed Prior và đủ hai bản ghi mỗi trận; dữ liệu có missing sẵn chưa xác minh sẽ bị từ chối.
- `restore_fixed_priors()` trả về bản sao đầy đủ và RestorationAudit; không sửa metadata, target, counters, flags hoặc dữ liệu đầu vào.
- `prepare_features()` trả về X đúng 13 cột, y=xg và audit. Thứ tự 13 features được lấy từ mã chuẩn hóa hiện có.
- `HistoryMedianImputer` dùng SimpleImputer(strategy="median") trên đúng tám cột lịch sử; năm cột còn lại đi qua nguyên vẹn. Kết quả là DataFrame giữ index, thứ tự dòng và thứ tự features. Không có StandardScaler.
- `make_preprocessor()` trả về sklearn.pipeline.Pipeline chưa fit. Có thể clone và ghép vào pipeline huấn luyện sau này. Nếu một cột lịch sử của Train toàn NaN, module báo lỗi, không dùng zero hoặc làm mất cột.
- Khôi phục prior là phép biến đổi xác định theo dữ liệu của trận; không học thống kê. Lịch sử tích lũy hợp lệ từ các trận Validation đã diễn ra trước trận đang xét vẫn được giữ nguyên, phù hợp dự báo tuần tự trước từng trận; không phải dự báo đồng thời cả mùa từ ngày đầu mùa.

```python
from scripts.prepare_training_features import load_dataset, prepare_features, make_preprocessor

df = load_dataset()
train = df.loc[df['season'].isin([2019, 2020])]
validation = df.loc[df['season'].eq(2021)]
X_train, y_train, train_audit = prepare_features(train)
X_validation, y_validation, validation_audit = prepare_features(validation)
preprocessor = make_preprocessor()  # Tạo mới cho từng fold
preprocessor.fit(X_train)  # Chỉ Train
X_train_ready = preprocessor.transform(X_train)
X_validation_ready = preprocessor.transform(X_validation)
```

Không fit imputer trên toàn bộ dataset, Validation hoặc Final Test; không lưu một bộ median chung. API không tự xác định dữ liệu nào là Train: người gọi phải giữ quy tắc fit/transform nêu trên.

### Thư viện và thực thi

Python `3.14.0`; Pandas `3.1.0`; NumPy `2.5.4`; scikit-learn `1.9.1`. Các thư viện ast, dataclasses, hashlib, pathlib, platform và sys thuộc Python chuẩn; không cài thêm dependency.

Lệnh đã thực thi:

```powershell
python scripts/prepare_training_features.py
```

Chạy lại lệnh sẽ kiểm chứng và cập nhật chính báo cáo này; không xuất CSV hoặc lưu imputer đã fit.

## 5. Kết quả ba fold kiểm chứng

season biểu thị năm bắt đầu mùa: 2019 tương ứng 2019–2020. Mỗi fold dùng Train mở rộng và Validation mùa kế tiếp. Chỉ các mùa 2019–2023 tham gia kiểm chứng fit/transform; các mùa 2024–2025 và 2025–2026 chỉ được đọc trong kiểm tra toàn vẹn nguồn, không được dùng để fit hoặc đánh giá.

| Fold | season Train | season Validation | Dòng Train | Dòng Validation | Ô NaN khôi phục Train | Ô NaN khôi phục Validation |
|---|---|---|---:|---:|---:|---:|
| 1 | 2019, 2020 | 2021 | 1520 | 760 | 184 | 24 |
| 2 | 2019, 2020, 2021 | 2022 | 2280 | 760 | 208 | 24 |
| 3 | 2019, 2020, 2021, 2022 | 2023 | 3040 | 760 | 232 | 24 |

### Median thực tế học từ Train sau khi khôi phục prior

| Feature | Fold 1 | Fold 2 | Fold 3 |
|---|---:|---:|---:|
| `xg_avg5` | 1.18 | 1.18 | 1.18 |
| `xga_avg5` | 1.22 | 1.2 | 1.22 |
| `gf_avg5` | 1.2 | 1.2 | 1.2 |
| `ga_avg5` | 1.2 | 1.2 | 1.2 |
| `shot_avg5` | 10.6 | 10.8 | 11.0 |
| `sot_avg5` | 3.4 | 3.4 | 3.6 |
| `opponent_xg_avg5` | 1.18 | 1.18 | 1.18 |
| `opponent_xga_avg5` | 1.22 | 1.2 | 1.22 |

## 6. Các kiểm chứng đã thực thi

| Kiểm chứng | Kết quả | Bằng chứng |
|---|---|---|
| Lịch sử và đối thủ | Đạt | Đã đối chiếu counters theo team/stint, flags và hai bản ghi cùng match_id; không tính lại rolling averages. |
| Khôi phục đúng ô | Đạt | 304 ô; xác định bằng lịch sử và đối chiếu Fixed Prior. |
| Bảo toàn ô hợp lệ | Đạt | Mọi ô ngoài mask giữ nguyên giá trị. |
| Không sửa DataFrame đầu vào | Đạt | DataFrame nguồn không bị sửa tại chỗ. |
| Metadata, target và thứ tự | Đạt | Metadata, xg, năm features giữ nguyên, không đổi dòng/index. |
| Short history không đồng nghĩa missing | Đạt | Giữ nguyên 152 dòng 0 < matches_seen < 5. |
| Không thay mọi giá trị trùng prior | Đạt | 2175 ô có lịch sử hợp lệ trùng Fixed Prior đã được giữ lại. |
| Fold 1: ranh giới thời gian | Đạt | Train 2019-08-16 → 2021-05-23; Validation 2021-08-13 → 2022-05-22; không chung trận. |
| Fold 1: median chỉ từ Train | Đạt | 8 median khớp phép tính độc lập trên Train sau khôi phục; SimpleImputer chỉ nhận 8 cột. |
| Fold 1: toàn vẹn Train | Đạt | 1520 dòng × 13 features; hữu hạn, không missing, giữ nguyên ô hợp lệ và năm features còn lại. |
| Fold 1: điền Train/xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Train/xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Train/gf_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Train/ga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Train/shot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Train/sot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Train/opponent_xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Train/opponent_xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: toàn vẹn Validation | Đạt | 760 dòng × 13 features; hữu hạn, không missing, giữ nguyên ô hợp lệ và năm features còn lại. |
| Fold 1: điền Validation/xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Validation/xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Validation/gf_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Validation/ga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Validation/shot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Validation/sot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Validation/opponent_xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: điền Validation/opponent_xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 1: Validation không cập nhật median | Đạt | Dịch phân phối Validation thêm 1.000.000; statistics_ và giá trị điền ô thiếu không đổi. |
| Fold 1: input và target | Đạt | X nguồn và y giữ nguyên sau fit/transform. |
| Fold 1: Pipeline có thể clone | Đạt | Clone tạo bộ xử lý chưa fit, không mang median cũ. |
| Fold 2: ranh giới thời gian | Đạt | Train 2019-08-16 → 2022-05-22; Validation 2022-08-12 → 2023-06-04; không chung trận. |
| Fold 2: median chỉ từ Train | Đạt | 8 median khớp phép tính độc lập trên Train sau khôi phục; SimpleImputer chỉ nhận 8 cột. |
| Fold 2: toàn vẹn Train | Đạt | 2280 dòng × 13 features; hữu hạn, không missing, giữ nguyên ô hợp lệ và năm features còn lại. |
| Fold 2: điền Train/xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Train/xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Train/gf_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Train/ga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Train/shot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Train/sot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Train/opponent_xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Train/opponent_xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: toàn vẹn Validation | Đạt | 760 dòng × 13 features; hữu hạn, không missing, giữ nguyên ô hợp lệ và năm features còn lại. |
| Fold 2: điền Validation/xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Validation/xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Validation/gf_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Validation/ga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Validation/shot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Validation/sot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Validation/opponent_xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: điền Validation/opponent_xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 2: Validation không cập nhật median | Đạt | Dịch phân phối Validation thêm 1.000.000; statistics_ và giá trị điền ô thiếu không đổi. |
| Fold 2: input và target | Đạt | X nguồn và y giữ nguyên sau fit/transform. |
| Fold 2: Pipeline có thể clone | Đạt | Clone tạo bộ xử lý chưa fit, không mang median cũ. |
| Fold 3: ranh giới thời gian | Đạt | Train 2019-08-16 → 2023-06-04; Validation 2023-08-11 → 2024-05-26; không chung trận. |
| Fold 3: median chỉ từ Train | Đạt | 8 median khớp phép tính độc lập trên Train sau khôi phục; SimpleImputer chỉ nhận 8 cột. |
| Fold 3: toàn vẹn Train | Đạt | 3040 dòng × 13 features; hữu hạn, không missing, giữ nguyên ô hợp lệ và năm features còn lại. |
| Fold 3: điền Train/xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Train/xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Train/gf_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Train/ga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Train/shot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Train/sot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Train/opponent_xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Train/opponent_xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: toàn vẹn Validation | Đạt | 760 dòng × 13 features; hữu hạn, không missing, giữ nguyên ô hợp lệ và năm features còn lại. |
| Fold 3: điền Validation/xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Validation/xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Validation/gf_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Validation/ga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Validation/shot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Validation/sot_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Validation/opponent_xg_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: điền Validation/opponent_xga_avg5 | Đạt | Ô thiếu được điền đúng median Train của cột. |
| Fold 3: Validation không cập nhật median | Đạt | Dịch phân phối Validation thêm 1.000.000; statistics_ và giá trị điền ô thiếu không đổi. |
| Fold 3: input và target | Đạt | X nguồn và y giữ nguyên sau fit/transform. |
| Fold 3: Pipeline có thể clone | Đạt | Clone tạo bộ xử lý chưa fit, không mang median cũ. |
| Từ chối Fixed Prior không khớp | Đạt | Đã chặn đúng yêu cầu: Fixed Prior không khớp: cột xg_avg5, vị trí dòng 22, index=21, nhận np.float64(1.325), cần 1.2. |
| Từ chối đối thủ không nhất quán | Đạt | Đã chặn đúng yêu cầu: Đối chiếu đối thủ: opponent_xg_avg5: vị trí dòng 1, index=0, giá trị np.float64(1.6), cần np.float64(0.6). |
| Từ chối thiếu cột nguồn | Đạt | Đã chặn đúng yêu cầu: Thiếu cột bắt buộc: ['matches_seen']. |
| Từ chối dữ liệu vô hạn | Đạt | Đã chặn đúng yêu cầu: Cột xg_avg5, vị trí dòng 1: giá trị không hữu hạn. |
| Từ chối thứ tự features sai | Đạt | Đã chặn đúng yêu cầu: X phải có đúng 13 features theo thứ tự quy định; không chứa target hoặc metadata. |
| Từ chối Train không có median | Đạt | Đã chặn đúng yêu cầu: Train thiếu toàn bộ dữ liệu ở các cột ['xg_avg5']; không có median để học, không tự điền hoặc bỏ cột. |
| Không impute ngoài tám cột | Đạt | Đã chặn đúng yêu cầu: Feature is_home không thuộc nhóm được phép impute. |
| Median nhân tạo Train-only | Đạt | Train có median 5, 6, ..., 12; Validation cực lớn không tham gia fit và các ô thiếu nhận đúng median Train. |
| Không sửa dataset hoặc script được bảo vệ | Đạt | SHA-256 của sáu file được bảo vệ giống trước khi thực thi. |

### Bằng chứng Train-only

Mỗi fold tạo Pipeline mới, chỉ gọi fit(X_train). Tám statistics_ được đối chiếu phép tính median độc lập trên chính Train sau khôi phục; số dòng fit bằng số dòng Train. Sau transform Validation và sau khi dịch phân phối Validation thêm 1.000.000, statistics_ không thay đổi. Kiểm chứng nhân tạo có median Train biết trước 5–12 và Validation rất lớn xác nhận các ô thiếu vẫn nhận đúng median Train. Không đưa y hoặc metadata vào SimpleImputer.

Ngoài lệnh CLI, đã thực thi import từ `scripts.prepare_training_features` trong một tiến trình Python riêng; ghép bộ xử lý vào Pipeline lồng, fit riêng Train season 2019–2020 và transform Validation season 2021. Kết quả giữ đúng 760 dòng × 13 features, index và feature names; mọi giá trị hữu hạn, target không đổi. Clone Pipeline lồng tạo instance chưa fit. Kiểm chứng import và tích hợp Pipeline này đã đạt.

## 7. Bảo toàn file và thay đổi repository

- Tạo `scripts/prepare_training_features.py`.
- Tạo/cập nhật duy nhất báo cáo `Prepare Leakage-Safe Median Imputation for La Liga.md`; giữ nguyên báo cáo chuẩn hóa trước đó.
- Không tạo dataset đã impute toàn cục, không lưu model hoặc medians dùng chung.
- Không commit, push hoặc tái cấu trúc repository. File Excel tạm `data/~$laliga_processed.xlsx` có sẵn ở trạng thái untracked khi bắt đầu; không chỉnh sửa hoặc xóa file này.

| File được bảo vệ | SHA-256 trước thực thi | Đối chiếu sau thực thi |
|---|---|---|
| `data/matches_laliga.csv` | `3cfeb29ea2e76d6a8a411f31af6182c6951fd477903b8b6d0401b58e10b415e2` | Giống hoàn toàn |
| `data/laliga_processed.csv` | `666661b49f4055104bd73b8ceb53f50407bf6e90cae6551dbbee820fe9fd6a3a` | Giống hoàn toàn |
| `data/laliga_processed.xlsx` | `47023b9efd583783c35b0b45030c3c747ca1fd09519164631f46543574540ab3` | Giống hoàn toàn |
| `data/laliga_processed_normalized.csv` | `90000ce22f42abe5eb5b5bfa38ad1ed5ef7b1c1c75cd4d39e749e7b324e0e5ca` | Giống hoàn toàn |
| `data/preprocess_laliga.py` | `fb5e35f268c7b205dc4d5854c5eba75ad74d903fcc08ae1cb5fdaf9f9963aadb` | Giống hoàn toàn |
| `scripts/normalize_laliga_numeric.py` | `1d40c912a1c4df9c765cbbd3e0ff6ddbe03da767697531c7be058ea9914aa726` | Giống hoàn toàn |

## 8. Cảnh báo, vấn đề và giới hạn

Không phát hiện bất nhất giữa Fixed Prior và các ô không có lịch sử; các tình huống lỗi nhân tạo trong bảng là kiểm chứng có chủ đích và đã bị chặn. Không có lỗi chưa giải quyết trong phạm vi nhiệm vụ.

Giới hạn: AST chỉ kiểm tra các thành phần chính của logic lịch sử; khi thay đổi công thức Feature Engineering cần xem xét lại module. Việc đối chiếu counters giả định đầu vào audit là toàn bộ lịch sử hiện có, bắt đầu từ mùa 2019. Module khôi phục yêu cầu mỗi trận còn đủ hai phía và nguồn chưa được khôi phục NaN trước đó.

Tính an toàn được xác nhận cho bước học median trong ba fold đã kiểm chứng; không thay thế một cuộc kiểm toán Data Leakage toàn bộ hệ thống hoặc đánh giá chất lượng mô hình.

## 9. Tài liệu đối chiếu

SimpleImputer học giá trị thay thế theo từng cột; module cấu hình strategy=median. Tham khảo [tài liệu SimpleImputer của scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.impute.SimpleImputer.html).

Nguyên tắc fit trên Train và chỉ transform dữ liệu kiểm chứng tuân theo [hướng dẫn tránh Data Leakage của scikit-learn](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).

## 10. Kết luận

Đã hoàn tất chuẩn bị và kiểm chứng với 85 kiểm tra đạt. Khôi phục đúng 304 ô prior trong bộ nhớ, giữ nguyên các ô lịch sử hợp lệ và học median riêng từ Train của ba fold. Sau transform, mỗi tập giữ nguyên số bản ghi, đúng 13 features số hữu hạn và target không đổi.

Dừng tại chuẩn bị và kiểm chứng Median Imputation. Chưa huấn luyện mô hình, chưa chạy Cross-Validation chính thức, chưa đánh giá Final Test; các bước tiếp theo cần yêu cầu rõ ràng của người dùng.
