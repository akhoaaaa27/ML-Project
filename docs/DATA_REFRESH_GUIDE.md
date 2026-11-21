# Nhập dữ liệu lịch sử và chuẩn bị refresh

Đã hoạt động: bootstrap offline, CSV import, validation, dedup, transaction rollback, SQLite audit logs và JSON manifests. Chưa hoạt động: connector API thật, thu thập tự động hoặc scheduler. Không cần API credentials để replay. Refresh không train hoặc thay artifact.

## Bootstrap snapshot có sẵn

```powershell
.\.venv\Scripts\python.exe -m scripts.inference.data_refresh bootstrap-snapshot
.\.venv\Scripts\python.exe -m scripts.inference.data_refresh status
```

Bootstrap đọc normalized CSV đã validated, ghi kho riêng, không sửa file nguồn. Chạy lần hai giữ nguyên 2.350 fixtures, inserted_matches=0. Log có thể tăng và fetched_at lần import mới không làm completed records thay đổi.

## Nhập CSV đã review

```powershell
.\.venv\Scripts\python.exe -m scripts.inference.data_refresh import-csv --csv "C:\approved-data\completed_matches.csv" --store "data/history/provider_staging.sqlite3"
```

Đường dẫn CSV ở trên là ví dụ, cần thay bằng file thực đã được phép sử dụng, đúng [schema](HISTORY_DATA_SCHEMA.md). Không có dữ liệu live giả được cung cấp. Nhập provider mới vào store staging riêng; mặc định chưa được dùng để dự báo production. Không nhập nguồn xG khác vào snapshot store rồi coi tương đương.

Nếu đã có lịch và attestation được review:

```powershell
.\.venv\Scripts\python.exe -m scripts.inference.data_refresh import-csv --csv "C:\approved-data\completed_matches.csv" --store "data/history/provider_staging.sqlite3" --schedule "C:\approved-data\schedule.json" --coverage "C:\approved-data\coverage.json"
```

Schema JSON tại HISTORY_DATA_SCHEMA.md. Trong thiết kế hiện tại command cần một CSV completed hợp lệ để gắn cùng provider; schedule/coverage có thể cập nhật cùng batch bằng cách nhập lại CSV completed không đổi. Không truyền secrets qua CSV hoặc command line. `refresh_runs` trong SQLite và `outputs/inference/refresh_runs/<run_id>.json` chứa source hash, counts, trạng thái và mã lỗi, không ghi nội dung credentials.

## Provider interface

`CompletedMatchProvider` trong `scripts/inference/data_refresh.py`:

```python
class CompletedMatchProvider:
    def fetch_completed(self): ...  # pandas.DataFrame schema hai phía
    def source_identity(self): ...  # metadata/hash nguồn, không chứa secrets
```

`CSVProvider` và `FrozenSnapshotProvider` đã thực thi interface. Backend có thể gọi `refresh_history(provider, store_path, schedule=None, coverage=None, manifest_dir=None)`. Batch phải commit hoặc rollback toàn bộ fixtures/team_records/schedule/coverage. Writer lấy SQLite `BEGIN IMMEDIATE` trước kiểm tra provider/dedup. Refresh thất bại vẫn ghi audit lỗi; completed records hợp lệ trước đó giữ nguyên. Không sửa trực tiếp database để bỏ qua gate.

## Review nguồn trước production

Quản trị cần cung cấp policy JSON tin cậy, không nhận từ frontend:

```text
{
  "<provider-đã-review>": {
    "replay_approved": true,
    "production_approved": true,
    "compatible_with_training": true,
    "reviewed_by": "<người/nhóm phê duyệt>",
    "compatibility_review": "<bằng chứng/biên bản tương thích xG với FBref/Opta training>",
    "xg_family": "<định nghĩa/version xG thực của nguồn>"
  }
}
```

Đây là cấu trúc cần hoàn tất, **không phải policy đã được phê duyệt**. Phải kiểm tra quyền truy cập/giấy phép dữ liệu, mapping IDs và teams, timezone/date, final status, đầy đủ xG/xGA/gf/ga/sh/sot, coverage per team, correction policy và khác biệt xG model. Việc đặt cờ true không thay thế việc review. Provider snapshot chỉ cho replay; không production_approved.

Connector API còn thiếu: lựa chọn nhà cung cấp và quyền truy cập, tài liệu/schema thật, credentials nếu cần, xác nhận metric compatibility, fixture postponement/completeness, retry/rate limit và lịch refresh đã thử nghiệm. Không có endpoint tự bịa, scraper hoặc request ra ngoài trong Phase 8.

## Scheduler opt-in

Sau khi chọn nguồn và chạy thử import/gates thành công, đội backend có thể gọi đúng lệnh `import-csv` ở trên bằng scheduler của tổ chức. Lịch chạy phải được bật tường minh bởi quản trị; repository không cài scheduled task, background service hoặc automatic retraining. Scheduler cần kiểm tra exit code 0/2, đọc manifest, tránh chồng tác vụ, giữ bản sao store trước correction và cảnh báo khi provider/coverage stale. Nếu CSV chưa được cập nhật bởi nguồn thật, lặp scheduler không làm dữ liệu mới hơn.
