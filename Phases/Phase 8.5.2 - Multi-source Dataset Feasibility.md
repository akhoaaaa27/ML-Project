# Phase 8.5.2 — Multi-source Dataset Feasibility

Ngày: **22/11/2026 — Asia/Saigon**. Trạng thái: **CONDITIONAL GO cho nghiên cứu**.

## Nhánh và phạm vi

Tạo `phase8.5.2-multisource-dataset` từ `origin/main` sau fetch, base/merge-base `84f14fd0638661c44933f917ce69effe518252ff`. Không kế thừa commit chưa merge của hai nhánh StrikerAPI, không merge/cherry-pick/reset/force-push. Workspace sạch khi bắt đầu. Hai nhánh cũ giữ nguyên.

Đã nghiên cứu kiến trúc raw data → rolling history → 13 feature → fitted imputer → frozen Linear Regression. Chỉ dựng staging độc lập; không cập nhật history production, retrain, scheduler hoặc website.

## Data discovery đã thực hiện

Tải 9 CSV thực tế từ các link công khai xGTables: fixture Understat của 7 mùa 2019–2025, 9.500 shot mùa 2025, fixture Sportmonks 2026. Đã đọc đủ schema, checksum, missingness, duplicate và coverage. Nguồn original/provider được giữ riêng cho từng nhóm field.

Football-Data đã được xem xét nhưng không tải CSV vì điều kiện hiện tại nêu hạn chế automated bots/scrapers/AI; không tuyên bố schema SP1 đã được kiểm tra. Understat trực tiếp không trả dataset ở trang đã đọc. La Liga chính thức được dùng để kiểm tra độ mới kết quả, không dùng để đoán xG thiếu.

Inventory chi tiết: [báo cáo kỹ thuật](../docs/MULTISOURCE_LALIGA_DATASET_AUDIT.md) và [manifest metadata](../docs/MULTISOURCE_LALIGA_DATASET_MANIFEST.json).

## Coverage và tích hợp

| Phạm vi | Kết quả |
|---|---|
| FBref giữ nguyên đến 30/09/2025 | 2.350 trận |
| Bổ sung 2025–26 từ 01/10/2025 | 309/310 trận; thiếu 1 unreliable xG |
| Toàn mùa 2025–26 trong staging | 379/380 trận |
| Mùa 2026–27 | 120 trận đủ raw fields; ít nhất 123 completed được biết |
| Thiếu thống kê 2026–27 | Ít nhất 3 trận 21/11 đã kết thúc nhưng CSV chậm |
| Tổng staging | **2.779 trận / 5.558 dòng** |
| Tổng thêm mới | **429 trận** |
| Completed còn thiếu đã xác định | **Ít nhất 4 trận** |
| Overlap FBref–archive | 2.350 identities khớp, 0 score conflict |

Không đồng nhất 380 fixture scheduled với 380 completed. Current CSV có 260 dòng chưa có kết quả, trong đó 3 đã được xác nhận completed ở nguồn chính thức; các dòng còn lại không tự coi là completed vì ngày đã qua. Một trận LIVE chưa được tính vào mẫu số completed. Không khẳng định đã bao phủ hết ngày 22/11.

SH/SOT 2025 được tái tạo từ shot events theo rule nghiên cứu non-penalty/non-own-goal. Current dùng reported shots/SOT vì thiếu penalty metadata. XG Understat/Sportmonks được chấp nhận để nghiên cứu, có nhãn semantic difference với training FBref. Không buộc các giá trị bằng nhau và không tuyên bố normalization exact khi metadata chưa đủ.

## Feature feasibility và LR offline

Adapter nghiên cứu dùng lại rolling/stint rules và được test parity với Feature Builder production. Alias đội mới chỉ thêm vào research mapping. Fixture current/future bị loại khỏi prior history; không impute raw outcomes hoặc lấy model output thay số liệu thiếu.

Trên 123 target 2026–27: **111 fixture dựng đủ 13 feature và sinh 222 dự đoán**, 12 fixture bị chặn vì lịch sử Villarreal thiếu. 12 fixture thành công có short history, 2 có zero history; dùng fitted imputer đã có. 37 fixture có rolling window chuyển nguồn Understat/Sportmonks. 35 target liên quan đội chưa có trong registry production, nên chưa tương thích vận hành trực tiếp.

Không fit/refit. Model nhận schema đúng, dự đoán hữu hạn, checksum giữ nguyên. Ba target chưa có outcomes vẫn có thể được dự đoán từ prior history; không append dự đoán làm xG thật. Chưa xác minh predictive accuracy/calibration trên nguồn mới hoặc replay với data vintage đúng ngày.

## Kiểm thử và bảo toàn

| Kiểm tra thực sự đã chạy | Kết quả |
|---|---|
| 21 test mới multisource trong full suite | **21/21 pass** |
| Full suite của nhánh main + tests mới | **171/171 pass**, 0 failures, 0 errors, 0 skipped |
| Mạng trong full suite | Socket/DNS bị chặn, API key bị bỏ khỏi environment; 59.976 giây gồm load/discovery |
| Staging + frozen LR experiment | Dựng 2.779 fixture; 111 target/222 dự đoán thành công; 12 target bị chặn có lý do |
| SHA-256 baseline 129 file có sẵn | Tất cả byte-identical |
| Manifest frozen 107 file và artifact/imputer | Khớp toàn bộ; không refit |
| Hai ref nghiên cứu StrikerAPI cũ | SHA giữ nguyên |
| Raw/staging/evidence/log | Git-ignore, không tracked |

Test mới dùng synthetic data và frozen files; không phụ thuộc CSV third-party hay API credentials. Full log và JSON kết quả lưu local ở `data/external/multisource/`. Root `.gitignore`, original/normalized datasets, Phase 7, production Feature Builder, metadata/model và SQLite history đều không bị sửa.

## File bàn giao và dữ liệu local

- `scripts/multisource/`: acquisition theo link thật, explicit schema/semantic mapping, fixture checks, research features, coverage/staging/LR audit.
- `tests/test_multisource.py`: offline tests cho các contract cần thiết.
- Hai báo cáo và manifest metadata trong `docs/`, `Phases/`.
- `data/external/.gitignore`: giữ toàn bộ raw/staging local.

Staging ở `data/external/multisource/processed/laliga_multisource_staging.csv`. Cùng thư mục có exclusions, expected completed history, per-team coverage, features và predictions. Raw files, evidence La Liga và log không đưa lên GitHub khi chưa xác minh redistribution rights.

## Kết luận và bước tiếp

**CONDITIONAL GO:** có dataset lớn, mapping và inference nghiên cứu chạy được, nhưng còn thiếu ít nhất 4 fixture, current CSV chậm cập nhật, shot completeness/current penalty semantics và performance trên nguồn mới chưa được xác minh. Không phải production approval.

Tiếp theo nên giải quyết gaps và freshness, xác nhận semantics/quyền sử dụng, rồi thiết kế đánh giá nguồn mới độc lập và integration contract cho đội mới/mixed providers. Không điều chỉnh model bằng Phase 7. **StrikerAPI calls = 0, credits = 0.** Dừng sau safe GitHub publication của phase này.
