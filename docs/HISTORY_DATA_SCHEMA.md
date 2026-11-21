# Schema kho lịch sử và lịch thi đấu

## Ba nguồn tách biệt

1. Frozen training/evaluation: toàn bộ `data/*.csv`, tham số và outputs Phase 1–7; chỉ đọc và giữ hash. Refresh không thay đổi chúng.
2. History store: `data/history/laliga_history.sqlite3`; 2.350 completed fixtures/4.700 góc nhìn trong bootstrap hiện tại. Chỉ chứa outcomes đã hoàn tất dùng để dựng lịch sử.
3. Fixture schedule: bảng `schedule` riêng trong store, không được nhập như completed outcomes. Bảng `coverage` chứa attestations cho từng team/season. Không có lịch/attestation production thật đi kèm snapshot.

SQLite nằm ngoài dữ liệu nghiên cứu đóng băng; inference mở URI `mode=ro`. `data_refresh` là writer riêng. Có index team/date. Mọi insertion fixtures, team perspectives, schedule và coverage trong một batch commit cùng transaction. `refresh_runs` lưu thành công/thất bại; file JSON manifest được lưu riêng cho CLI.

## CSV nhập completed matches

Mỗi trận phải có đúng hai dòng Home/Away. Các cột bắt buộc:

```csv
provider,provider_match_id,season,date,team,opponent,is_home,status,gf,ga,xg,xga,sh,sot,fetched_at,statistics_version,quality_status
```

`kickoff_utc` là cột tùy chọn duy nhất. Không thêm cột API key, token hoặc trường không có trong schema.

| Cột | Kiểu/quy tắc |
|---|---|
| provider | Tên nguồn ổn định, chỉ chữ/số/underscore/hyphen; một provider mỗi import/store |
| provider_match_id | String ID trong namespace của provider, khác legacy-local snapshot ID |
| season | Năm bắt đầu mùa; int |
| date | YYYY-MM-DD theo ngày thi đấu được nguồn xác nhận |
| team, opponent | Mapping canonical tường minh tại common.py, không tự fuzzy match |
| is_home | 1 hoặc 0, đúng một mỗi trận |
| status | Chỉ `completed` |
| gf, ga | Số nguyên không âm; đối chiếu chéo hai phía |
| xg, xga | Số hữu hạn không âm; đối chiếu chéo atol=1e-9, rtol=0 |
| sh, sot | Tổng cú sút và cú sút trúng đích, int không âm, sh≥sot |
| fetched_at | ISO timestamp có timezone; thống nhất hai phía |
| statistics_version | Version thống kê nguồn, không rỗng, thống nhất hai phía |
| quality_status | Chỉ `verified`, chịu trách nhiệm bởi quy trình nhập/review |
| kickoff_utc | Tùy chọn, ISO timestamp có timezone đã được nguồn xác nhận; chưa dùng để thay date-only replay |

Không chấp nhận xG rỗng/NaN/vô hạn hoặc impute outcome. Hai phía phải cùng season/date, team↔opponent đúng, goals và xG/xGA khớp. Mapping alias được chuẩn hóa trước dedup. Thông tin provenance bắt buộc không được tự điền từ số liệu giả.

## Định danh và corrections

Canonical key: `laliga:{season}:{home-team-id}:{away-team-id}`. Ví dụ `laliga:2024:athletic-club:getafe`. Giả định một lượt sân nhà cho mỗi cặp trong một mùa La Liga; không dùng schema này cho cúp hoặc giải khác. Ngày không thuộc key nên đổi lịch không sinh fixture mới. Completed fixture đã có ngày khác phải được xử lý như correction có review.

`UNIQUE(provider, provider_match_id)` và canonical primary key ngăn một match ID gán nhiều trận hoặc nhân bản fixture. Nguồn cũ tạo match_id bằng thứ tự dữ liệu; bootstrap gắn `provider_match_id="legacy-local:<id>"` và provider `fbref_opta_snapshot`. Đây **không phải ID FBref/Opta gốc đã được xác minh**.

Lưu `semantic_sha256` của identity/outcomes/version/provenance quan trọng, bỏ fetched_at khỏi semantic hash. Import lại nội dung giống nhau giữ record và thời điểm fetch đầu tiên, chỉ thêm refresh log. Mọi thay đổi completed stats, date, source ID, version hoặc kickoff bị chặn `CORRECTION_REQUIRES_REVIEW`. Chính sách hiện tại: review correction bên ngoài, tạo store phiên bản mới, chạy kiểm toán và quản trị mới chuyển backend sang store đó; không có lệnh ghi đè ngầm. Thay provider cũng cần store staging riêng, không hòa trộn xG tự động.

## Schedule JSON

`--schedule` nhận JSON array. Mỗi object có:

```text
provider, provider_fixture_id, home_team, away_team,
date (YYYY-MM-DD), season (int),
status (scheduled | postponed | cancelled | completed),
quality_status (verified), verified_by,
fetched_at (ISO có timezone), kickoff_utc (optional)
```

Không có lịch thật trong repository. Provider phải thống nhất với store trong implementation hiện tại. Schedule không cập nhật outcomes. Chỉnh lịch là cập nhật có provenance qua import tường minh; khác với chính sách immutable của completed matches. Các trạng thái hoãn/hủy không được gắn nhãn verified upcoming forecast.

## Coverage JSON

`--coverage` nhận JSON array theo team/season:

```text
team, season, provider, stint_start_season,
verified_through (YYYY-MM-DD),
eligible_match_keys (array canonical keys đầy đủ của stint),
verified_by, reviewed_at (ISO có timezone)
```

Coverage không được sinh tự động bằng cách đếm những hàng hiện có trong store rồi tự tuyên bố đủ. Connector/người review phải xác minh cả lịch, các trận hoãn, completed fixtures và thống kê bắt buộc. Import kiểm tra keys tồn tại đúng team, từ mùa đầu stint và không sau verified_through. Gate upcoming còn đối chiếu toàn bộ key set, đầu stint, ngày xác nhận và schedule.

Zero-history hợp lệ cần attestation explicit stint_start_season bằng mùa hiện tại, danh sách trận rỗng. Điều đó khác thiếu dữ liệu chưa biết. Store hiện tại chứa lịch sử từ 2019; dùng cho production tương lai cần xác nhận phần đầu stint đầy đủ theo convention nghiên cứu hoặc reset do lên hạng. Không giả tạo counter cho các mùa chưa thu thập.

## Thời gian và provenance gốc

Snapshot normalized chỉ bảo đảm ngày, không bảo đảm múi giờ/giờ khai cuộc. Dùng `historical_date < cutoff_date`, không nhận thứ tự giữa hai trận cùng ngày. Nếu lịch sử một đội chứa nhiều trận cùng ngày và thứ tự cửa sổ không xác định, builder trả `AMBIGUOUS_HISTORY`. Season gap >1 reset; mùa liên tiếp tiếp tục count toàn stint, không chỉ năm trận.

`fetched_at` của bootstrap là thời điểm nhập snapshot vào kho mới, **không phải thời điểm fetch FBref/Opta ban đầu**. `statistics_version` tham chiếu SHA-256 normalized CSV. Nguồn được ghi FBref/Opta-derived theo hồ sơ dự án; live source URL/ID và timestamp gốc chưa được xác minh. Độ tươi phải căn theo ngày trận/coverage từng đội, không căn theo ngày import mới.
