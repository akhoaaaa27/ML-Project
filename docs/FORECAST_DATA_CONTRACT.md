# XPECTA Forecast Data Contract 1.0

Ứng dụng khởi tạo `ForecastService()` một lần trong phần cấu hình tin cậy. Request truyền fixture key, snapshot version hoặc forecast ID. Dịch vụ chọn file dưới `data/history/research/<version>/laliga_composite.sqlite3` và model cố định qua trusted loader. CLI và API Python cho dữ liệu thật dùng đồng hồ hệ thống. Cấu hình fixture tổng hợp dùng namespace riêng và clock mô phỏng được truyền khi khởi tạo service, nằm ngoài request.

| Phương thức trên ForecastService | Đầu ra |
|---|---|
| `list_eligible_fixtures(snapshot_version, season=None, include_unavailable=False)` | Danh sách READY/EARLY_READY; tùy chọn trả cả các lý do bị chặn |
| `evaluate_forecast_eligibility(canonical_fixture_key, snapshot_version)` | Trạng thái, reason code, cutoff, fixture, timestamp và intermediate keys khi đủ proof |
| `generate_forecast(canonical_fixture_key, snapshot_version)` | `PUBLISHED`, `NO_CHANGE`, `WAITING_DATA`, `UNAVAILABLE` hoặc `FORECAST_ERROR` |
| `get_forecast(forecast_id)` | Bản ghi có checksum và lineage hợp lệ |
| `list_fixture_forecasts(canonical_fixture_key)` | Các revision theo thứ tự tăng dần |
| `compare_forecasts(fixture_key, forecast_v1_id, forecast_v2_id)` | Delta xG, thay đổi feature/window/provenance, cutoff và snapshot hai phía |
| `get_forecast_data_status(snapshot_version)` | Data Status hiện có kèm dataset kind và policy version |

`NO_CHANGE` trả forecast ID cũ với binding nguyên bản. `evaluated_snapshot_version` và `evaluated_eligibility_status` mô tả lần đánh giá hiện tại. Lỗi vận hành như `LEDGER_BUSY`, `STALE_FORECAST_WRITE`, `STALE_FORECAST_SNAPSHOT`, `LEDGER_CORRUPT` và `SNAPSHOT_BINDING_MISMATCH` raise `InferenceError`. Lỗi lưu file hệ điều hành truyền `OSError`; CLI ánh xạ sang exit 1. Các hàm ledger ghi chỉ dành cho orchestration tin cậy.

## Bản ghi

| Nhóm | Trường |
|---|---|
| Schema và lineage | `schema_version`, `forecast_id`, `forecast_revision`, `previous_forecast_id`, `forecast_stage`, `record_sha256` |
| Target và thời gian | `canonical_fixture_key`, `target_match_date`, `target_kickoff_utc`, `target_semantics`, `generated_at_utc`, `forecast_as_of_date`, `history_cutoff`, `fixture_reviewed_at_utc` |
| Model và snapshot | `history_snapshot_version`, `history_database_sha256`, `model_version`, `model_artifact_sha256` |
| Feature và prediction | `feature_schema_version`, `features`, `features_sha256`, `home_xg`, `away_xg`, `raw_predictions` theo thứ tự home/away |
| Provenance và policy | `history_provenance`, `history_windows`, `dataset_kind`, `demo_label` riêng synthetic, `eligibility_status`, `eligibility_policy_version`, `inference_mode`, `production_approved`, `source_semantics`, `source_notice` |

`features` có ba trường `order`, `home`, `away`. Hai mảng giá trị theo cùng 13 tên trong `order`; slot thiếu hợp lệ của zero-history biểu diễn bằng JSON `null`. Các số dự báo phải hữu hạn, xG bằng `max(0, raw)`. Kiểm tra parity dùng sai số tuyệt đối tối đa `1e-12` khi cùng model, target semantics và feature.

Checksum tái dùng `semantic_hash` của Composite History. UTF-8, Unicode nguyên vẹn, object keys sắp xếp, separator compact, mảng giữ nguyên thứ tự, float theo cách biểu diễn JSON của Python đã pin, không chấp nhận NaN/Infinity. `features_sha256` băm object `features`. `record_sha256` băm toàn bộ record trừ chính trường này. Dấu xuống dòng và định dạng file ngoài canonical serialization không tham gia checksum. Ledger so sánh feature theo giá trị, một timestamp hoặc snapshot mới riêng lẻ không sinh revision.

## Kho và so sánh

Real ledger ở `data/external/multisource/forecasts/real/records/`. Demo tổng hợp ghi vào `forecasts/demos/<name>/ledger/synthetic/records/`. Writer lock độc quyền; file tạm được flush và fsync rồi publish bằng hard link cùng volume, từ chối ghi đè. Filesystem local phải hỗ trợ hard link. Revision nối bằng ID trước đó và được kiểm tra trong lúc ghi, kể cả sau khi một writer khác đã tính forecast song song. Luồng đọc xác minh checksum và thứ tự lineage. Hash kiểm tra toàn vẹn nội dung; quyền hệ thống tệp kiểm soát sửa trực tiếp. Nếu process chết và để lại lock, xác minh writer đã dừng trước khi xử lý lock thủ công.

So sánh chỉ nhận hai revision theo thứ tự lineage của cùng canonical fixture và cùng định nghĩa feature/target. Nếu date hoặc kickoff đổi, `schedule_notice=SCHEDULE_REVISED`. So sánh trả trước/sau cho xG hai đội, lịch sử đã chọn, nguồn và feature. `changed_features` chỉ mô tả quan sát dữ liệu.

Handoff Python không có HTTP route. Backend Phase 8.5.7 sẽ sở hữu quyền đọc, trusted configuration và lọc provenance trước khi public. Record thật, review receipts và chi tiết provider vẫn thuộc kho ignored.
