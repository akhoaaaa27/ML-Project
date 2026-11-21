# Giao diện suy luận La Liga xG

Phase 8 chỉ triển khai Python và CLI. Các giá trị trả về là **tổng xG liên tục của từng đội trong một trận**, không phải xác suất ghi bàn của một cú sút hoặc xác suất thắng trận.

## Khởi tạo và gọi từ Python

Chạy từ repository root với Python trong môi trường đã pin. Khởi tạo một lần khi backend bắt đầu; không export/train trong startup hoặc request.

```python
from scripts.inference.history_store import HistoryStore
from scripts.inference.predict_fixture import FixturePredictor

history = HistoryStore()  # data/history/laliga_history.sqlite3, chỉ đọc
predictor = FixturePredictor(history)  # models/, kiểm tra hash và môi trường
result = predictor.predict(
    "Athletic Club", "Getafe", "2024-08-15", 2024, mode="replay"
)
```

Facade dùng cho một lần gọi:

```python
from scripts.inference.predict_fixture import predict_fixture
result = predict_fixture(
    home_team="Athletic Club", away_team="Getafe", match_date="2024-08-15",
    season=2024, history=history, mode="replay", prediction_cutoff=None,
)
```

`FixturePredictor.__init__(history, *, model_directory=MODEL_DIR, trusted_model_directory=MODEL_DIR)` chỉ nhận cấu hình đường dẫn từ quản trị backend. Hai đường dẫn phải resolve cùng thư mục được tin cậy. Người dùng/frontend không được truyền chúng. `predict_fixture` hỗ trợ hai keyword tương tự để backend sử dụng artifact đã được quản trị phê duyệt.

Constructor và các API thấp hơn có thể ném `InferenceError`; facade và `predictor.predict()` trả object lỗi. `InferenceError.result()` chuyển lỗi khởi tạo thành JSON-safe. Không lấy đường dẫn model, database, provider policy hoặc raw features từ HTTP body.

## Đầu vào

| Trường | Kiểu | Quy tắc |
|---|---|---|
| home_team, away_team | string | Tên, alias tường minh hoặc canonical ID; phải khác nhau |
| match_date | string | Ngày ISO `YYYY-MM-DD`, phải tồn tại |
| season | int | Năm bắt đầu mùa, không nhận bool/float; ngày thuộc năm đó hoặc năm sau |
| mode | string | `replay` hoặc `upcoming` |
| prediction_cutoff | string/null | Ngày ISO, không sau ngày fixture; không phải dữ liệu kỹ thuật 13 features |
| history | HistoryStore | Đối tượng do backend quản lý; không deserialize từ request |

Mapping tại `scripts/inference/common.py`: ví dụ `Atletico Madrid`, `Atlético Madrid`, `atletico-madrid` cùng canonical identity; `Betis` → `Real Betis`. Không fuzzy matching. Đội mới cần bổ sung mapping có review, không tự tạo ID.

## Replay và upcoming

Replay đòi hỏi fixture completed đúng home/away/season/date đã có trong store. Cutoff mặc định bằng ngày fixture. Lịch sử chỉ gồm ngày **nhỏ hơn cutoff**, bỏ chính canonical fixture key và mùa tương lai. Các bản ghi nguồn có giờ chưa xác minh vẫn dùng date-only; không sắp thứ tự trong cùng ngày. `temporal_policy="kickoff"` chưa hỗ trợ và bị từ chối; timestamp mới chỉ lưu provenance để review riêng sau này.

Replay 2019–2023 là chức năng minh họa bằng model đã train trên Development, **không phải đánh giá out-of-sample**. Parity độc lập chỉ đối chiếu các dự báo holdout đã lưu, không tính lại Test performance.

Upcoming cutoff phải bằng ngày nhỏ hơn giữa ngày fixture và ngày UTC hiện tại; không cho truyền cutoff cũ để vượt freshness. Không nhận fixture quá khứ hoặc cutoff tương lai. Phải qua toàn bộ gates: từng đội không quá 45 ngày từ trận lịch sử gần nhất đến ngày fixture; provider đã review tương thích xG; target có lịch `scheduled` được xác minh; coverage từng đội đầy đủ đến ngày trước cutoff; danh sách trận và đầu stint khớp; không có trận trước target còn chưa hoàn tất/hoãn hoặc completed nhưng thiếu thống kê. Ngưỡng 45 ngày là chính sách vận hành thận trọng, không phải hyperparameter được tối ưu trên Test. Giai đoạn nghỉ dài có thể bị chặn dù hợp lệ; chưa có cơ chế tự miễn trừ.

Không dùng max(date) toàn database để suy ra form từng đội. Dữ liệu tháng 9/2025 sẽ trả `STALE_DATA` cho yêu cầu cuối 2026. Coverage là xác nhận có trách nhiệm của nguồn/người review, không phải bằng chứng chương trình có thể tự xác nhận với một API chưa kết nối. Lịch không xác minh sẽ không tạo dự báo mang nhãn production.

Schedule fetched_at và coverage reviewed_at phải có ngày UTC bằng cutoff hoặc ngày trước đó, không có timestamp tương lai. verified_through cũng phải trong khoảng ngày trước cutoff đến cutoff. Một lịch/attestation cũ không được dùng để tự tuyên bố đã biết các trận hoãn hoặc kết quả mới nhất.

## Kết quả thành công

Schema chính:

```text
status: "success"
mode: "replay" | "upcoming"
home_team, away_team, home_team_id, away_team_id: string
match_date, history_cutoff: YYYY-MM-DD
season: integer
canonical_fixture_key: string
home_xg, away_xg: finite number >= 0
model: "Linear Regression"
model_version: "1.0.0"
target: "total_team_match_xg"
data_status: "verified_historical_snapshot" | "verified"
temporal_policy: "date_only_strict_before_cutoff"
provider, artifact_sha256: string
schedule_status: "historical_completed_fixture" | "verified_scheduled"
schedule_provider_fixture_id: string | null
history_summary: object theo canonical team
history_provenance: array các trận trong hai rolling windows
clipping_applied: boolean
```

Kết quả thật của replay fixture `legacy-local:1901`:

```json
{
  "status": "success",
  "mode": "replay",
  "home_team": "Athletic Club",
  "away_team": "Getafe",
  "home_xg": 1.3493648382441854,
  "away_xg": 1.2037992600673975,
  "model": "Linear Regression",
  "model_version": "1.0.0",
  "data_status": "verified_historical_snapshot",
  "history_cutoff": "2024-08-15"
}
```

Ví dụ trên rút gọn các trường provenance, không phải dữ liệu mô phỏng. Actual xG không được trả trong đường suy luận. Nếu UI muốn hậu kiểm, phải dùng luồng đọc kết quả thực tế riêng, gắn nhãn sau trận và tuyệt đối không nối vào X.

## Kết quả lỗi

```json
{"status":"error","mode":"upcoming","error":{"code":"STALE_DATA","message":"Lịch sử đội quá cũ cho yêu cầu upcoming.","details":{}}}
```

`details` có thể có team, last_match_date, history_cutoff, age_days và max_age_days. Lỗi không kèm home_xg/away_xg; frontend không được thay bằng 0 hoặc dự báo cũ.

| Nhóm mã lỗi | Ý nghĩa |
|---|---|
| UNKNOWN_TEAM, DUPLICATE_TEAM | Tên không có mapping hoặc cùng đội |
| INVALID_DATE, INVALID_SEASON, INVALID_MODE, INVALID_CUTOFF | Request không hợp lệ |
| INVALID_FIXTURE, FIXTURE_UNVERIFIED | Sai identity/ngày/trạng thái hoặc chưa có lịch xác minh |
| HISTORY_MISSING, INVALID_HISTORY, INCOMPLETE_HISTORY | Kho thiếu/sai hoặc thiếu các trận bắt buộc |
| STALE_DATA, COVERAGE_UNVERIFIED, AMBIGUOUS_HISTORY | Quá cũ, chưa xác nhận đủ hoặc không rõ thứ tự lịch sử |
| UNSUPPORTED_PROVIDER, INCOMPATIBLE_PROVIDER | Chưa có policy/review hoặc khác nguồn xG |
| ARTIFACT_MISSING, ARTIFACT_CORRUPT, ARTIFACT_INCOMPATIBLE | Thiếu, checksum/trạng thái sai hoặc schema không tương thích |
| ENVIRONMENT_INCOMPATIBLE, UNTRUSTED_ARTIFACT | Sai môi trường hoặc nguồn artifact không được tin cậy |
| INVALID_NUMERIC, FEATURE_SCHEMA_MISMATCH | Số không hợp lệ hoặc sai schema X |
| INVALID_SCHEMA, MISSING_STATISTICS, INCONSISTENT_PAIR | Dữ liệu import không hợp lệ |
| DUPLICATE_FIXTURE, CORRECTION_REQUIRES_REVIEW, REFRESH_FAILED | Trùng định danh, cần review correction hoặc refresh rollback |
| ARTIFACT_EXISTS, TRAINING_DATA_MISMATCH, PARAMETER_MISMATCH, SERIALIZATION_MISMATCH, PARITY_FAILED | Lỗi export/kiểm toán; không tự retrain để xử lý |
| UNSUPPORTED_TEMPORAL_POLICY | Chưa bật semantics kickoff |

## CLI

```powershell
.\.venv\Scripts\python.exe -m scripts.inference.predict_fixture replay --match-id 1901
.\.venv\Scripts\python.exe -m scripts.inference.predict_fixture replay --home "Athletic Club" --away "Getafe" --date 2024-08-15 --season 2024
.\.venv\Scripts\python.exe -m scripts.inference.predict_fixture upcoming --home "Barcelona" --away "Real Madrid" --date 2026-11-28 --season 2026
```

Lệnh upcoming cuối là fixture minh họa, **không xác nhận lịch thật** và sẽ bị chặn bởi dữ liệu snapshot cũ. CLI in JSON, exit code 0 khi thành công, 2 khi lỗi nghiệp vụ/validation. `--match-id` chỉ là legacy-local ID của snapshot, không dùng cho provider mới. `--store`, `--provider-config` chỉ do quản trị thiết lập. HTTP authentication/rate limit thuộc backend Phase 9, chưa triển khai ở đây.
