# Fixture Catalogue và Data Status — contract 1.0

Adapter đọc: `fixture_catalogue(store)` và `data_status(store)` trong `scripts.multisource.fixture_catalogue`. `store` phải là `CompositeHistory` đã xác minh DB checksum và manifest embedded; SQL chỉ đọc. JSON export gồm `fixtures.json` và `data-status.json`; không cần server, credentials hoặc feature rebuild.

## Fixtures

`fixtures.json` có dạng `{"contract_version":"1.0","fixtures":[...]}`. Mỗi record có đúng các field sau:

| Field | Kiểu / ý nghĩa |
|---|---|
| `fixture_id` | string hoặc null; ID của provider đã chọn, không phải global primary key |
| `canonical_fixture_key` | string; `research:laliga:<season>:<canonical_home>:<canonical_away>` |
| `season` | integer, năm bắt đầu mùa |
| `home_team`, `away_team` | tên canonical từ team registry; hai đội khác nhau |
| `match_date` | `YYYY-MM-DD`, ngày theo source UTC-date contract |
| `kickoff_utc` | ISO-8601 UTC kết thúc `Z`, hoặc null khi không có nguồn xác nhận |
| `observed_status` | `scheduled`, `live`, `postponed`, `cancelled`, `completed`, `unverified` |
| `match_status` | `VERIFIED_COMPLETED`, `UNVERIFIED`, hoặc `SOURCE_CONFLICT` của store cũ |
| `statistics_status` | `COMPLETE_STATISTICS`, `PENDING_UPDATE`, `UNVERIFIED`, `SOURCE_CONFLICT` |
| `source_provider` | nguồn/provider của identity projection; legacy có thể là URL evidence |
| `source_version` | checksum/version của nguồn đã chọn; không suy ra từ ngày download |
| `snapshot_version` | immutable Composite History version |
| `verified_at` | timestamp có timezone của evidence/observation đã chọn |

Key loại trừ ngày để đổi lịch không sinh fixture mới. `VERIFIED_COMPLETED + PENDING_UPDATE` là hoàn thành được xác nhận nhưng thiếu thống kê, không phải scheduled. `UNVERIFIED` không được hiểu thành zero-history hoặc completed dựa trên ngày.

Thời gian được chuẩn hóa về UTC và ngày UTC phải trùng `match_date`. Timestamp thiếu timezone hoặc chênh ngày bị chặn; không tự đoán Europe/Madrid, bù ±1 ngày hoặc tạo kickoff nửa đêm. Nguồn cung cấp ngày theo timezone khác cần adapter đã review riêng. V3 chưa lưu kickoff inline: chỉ hydrate từ CSV local có đúng SHA đã attested trong manifest V3; không có file đúng hash thì kickoff null. Version mới lưu schedule projection trong metadata đã hash.

Ví dụ tổng hợp, không phải dữ liệu provider:

```json
{"fixture_id":"1000","canonical_fixture_key":"research:laliga:2026:Barcelona:Real Madrid","season":2026,"home_team":"Barcelona","away_team":"Real Madrid","match_date":"2026-07-01","kickoff_utc":null,"observed_status":"scheduled","match_status":"UNVERIFIED","statistics_status":"UNVERIFIED","source_provider":"synthetic://results","source_version":"synthetic-seed-v1","snapshot_version":"synthetic_parent","verified_at":"2026-11-22T00:00:00+00:00"}
```

## Data Status

Record thực tế được tính từ validated store; không hardcode số lượng:

| Field | Kiểu / ý nghĩa |
|---|---|
| `contract_version` | `"1.0"` |
| `snapshot_version`, `parent_version` | string, parent có thể null |
| `database_sha256` | SHA-256 của SQLite |
| `build_timestamp` | timestamp có timezone |
| `latest_verified_completed_date` | `YYYY-MM-DD` hoặc null |
| `registry_fixtures`, `verified_completed` | integer counts |
| `complete_statistics`, `pending_statistics` | integer counts |
| `conflicts`, `unverified` | integer counts |
| `source_versions` | array nguồn thống kê/version được chọn |
| `input_hashes` | map tên input tới SHA-256 |
| `coverage` | array per-season/team gồm count và `verified_before` |
| `research_validation_status` | chuỗi mô tả scope kiểm chứng của snapshot |
| `production_approved` | luôn `false` |
| `mode` | `RESEARCH_INFERENCE` |
| `temporal_policy` | `date_only_strict_before_cutoff_not_as_of_vintage` |

Backend sau này có thể lọc season/date/status và phân trang trên projection này. Giữ version rõ trong request/response, không đổi parent đang được đọc. Coverage là attestation của catalogue export nghiên cứu; không đại diện tính đầy đủ tuyệt đối của dữ liệu lịch sử hay availability theo thời gian thực. Muốn suy luận phải qua Composite Feature Builder để kiểm tra cutoff, stint và actual last-five; catalogue không cấp phép prediction hoặc production.

Exports chứa record provider thật vẫn là private local data; không đưa lên GitHub hoặc API công khai khi chưa xác minh quyền phân phối. Phase 8.5.7 còn cần authentication, quyền truy cập, hợp đồng nguồn và cơ chế chọn version; phase này chỉ cung cấp adapter/schema đọc ổn định.
