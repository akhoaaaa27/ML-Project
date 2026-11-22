# Controlled Data Refresh — Phase 8.5.4

Luồng refresh thủ công chỉ tạo snapshot nghiên cứu. Không có server, scheduler, migration production hoặc cập nhật model. Branch: `phase8.5.4-controlled-data-refresh`, base `11e46aa61b7aaf6bf381c14dba0e5e83e1700e39` trên `origin/main` đã merge PR #1. Commit triển khai được ghi trong [báo cáo JSON](PHASE_8_5_4_VALIDATION.json); commit giao cuối cùng xem HEAD của branch.

## Kiến trúc

1. `refresh_validation.py` kiểm tra manifest riêng của nguồn, schema, provider, fixture ID, completion evidence, số liệu, roster và lịch; dựng diff theo dữ liệu nghiệp vụ.
2. `revision_review.py` phân loại bằng quy tắc cố định và ràng buộc review với toàn bộ checksum candidate.
3. `refresh_composite.py` cung cấp CLI `prepare`, `review`, `publish`, `status`, `export`.
4. `composite_history.publish_version(..., refresh_metadata=...)` bổ sung metadata tùy chọn vào SQLite và manifest hiện có. Callback validation hoàn tất trước atomic rename. Callers cũ không đổi hành vi.
5. `fixture_catalogue.py` cung cấp adapter đọc và contract JSON version `1.0` cho backend sau này.
6. `refresh_demo.py` tạo demo tổng hợp A/B/C; `validate_refresh.py` chạy kiểm chứng offline và xuất báo cáo tổng hợp.

Phase 8 Feature Builder, Composite Feature Builder, pipeline Linear Regression, imputer, 13 feature, Phase 7, production History Store và loader tái lập V3 được giữ nguyên. `2779` và `111` chỉ thuộc kiểm chứng baseline bằng loader cũ, không được dùng làm điều kiện chấp nhận số lượng của refresh mới.

## Nguồn và phạm vi

Mặc định đọc `data/external/multisource/` hiện có: acquisition manifest, 7 archive fixture CSV 2019–2025, shot events 2025, catalogue CSV 2026 và `independent_completed.json` nếu có. Không cần credentials. Chỉ nhận các URL export xGTables đã review, nguồn thống kê Understat/Sportmonks theo mapping nghiên cứu trước đó và evidence kết quả chính thức LaLiga. Không có lời gọi StrikerAPI.

Hash mới khác parent là bình thường nếu khớp manifest của chính nguồn mới. Từng file được kiểm tra SHA-256 và byte length, rồi hash lại sau khi đọc để phát hiện thay đổi giữa chừng. Tên file, đường dẫn và URL có scope rõ ràng; không nhận file traversal, credential URL hoặc query bí mật.

Adapter current CSV nhận đủ catalogue đã được parent attestation: với V3 thực tế là 20 đội, 380 cặp Home/Away có hướng. Roster được kế thừa từ catalogue đã review, không suy ra từ row count. Không thêm trận thứ 381 hoặc đổi provider ID sang cặp đấu khác. Key `research:laliga:<season>:<home>:<away>` không chứa ngày. Vì vậy đổi lịch là revision của cùng fixture.

Chỉ các thống kê Understat 2025 đang được chọn mới được cập nhật qua adapter archive. Các thay đổi archive 2019–2024 hoặc thay đổi 2025 chồng lên selection FBref đóng băng sẽ bị chặn để audit riêng. Shot events phải có cả hai perspective; không tự điền 0 cho phía vắng. Penalty/own-goal mapping kế thừa nghiên cứu trước, không khẳng định tương đương thống kê FBref/Opta.

## Cách dùng trong PowerShell

Chạy từ repository với Python/dependency versions đã pin. Mỗi candidate ID và version phải mới:

```powershell
.venv/Scripts/python.exe -m scripts.multisource.refresh_composite prepare --parent data/history/research/phase853_v3_20261122/laliga_composite.sqlite3 --candidate-id local-check --version phase854_local_check --as-of 2026-11-22
.venv/Scripts/python.exe -m scripts.multisource.refresh_composite status --candidate data/external/multisource/refresh/candidates/local-check
```

`prepare` không tải mạng. `--source-dir <local_snapshot>` chọn input khác. `--workspace <ignored_directory>` chọn nơi lưu bundle, report và receipt riêng tư. Mặc định as-of là ngày tại UTC+7; dùng `--as-of` để tái lập. Ngày hoàn thành sau as-of bị chặn.

Chỉ khi người vận hành chủ động thêm `--download`, CLI mới gọi acquisition đã có, vào thư mục `download` mới nằm bên trong workspace candidate. Không tái sử dụng raw directory. Download không có sẵn independent completion evidence: thiếu evidence cho kết quả mới sẽ chặn prepare. Khi đó bổ sung evidence local đã kiểm tra và prepare candidate khác từ thư mục download đã lưu. Không tự xác nhận hoàn thành từ nhãn `full_time` hoặc vì ngày đấu đã qua. Phase này không thực thi download thực tế; kiểm thử opt-in dùng mock.

Nếu có manual item, mở `candidate.json` và kiểm tra old/new values, nguồn cùng bằng chứng. Người vận hành tự quyết định:

```powershell
.venv/Scripts/python.exe -m scripts.multisource.refresh_composite review --candidate data/external/multisource/refresh/candidates/local-check --change-id <change_sha256> --decision APPROVE --reason "Ly do da doi chieu" --evidence-reference "<local_evidence_reference>"
.venv/Scripts/python.exe -m scripts.multisource.refresh_composite publish --candidate data/external/multisource/refresh/candidates/local-check
```

`REJECT` cũng được hỗ trợ. Receipt có `change_id`, fixture key, change types, parent/candidate versions, old/new values, provenance, evidence reference, decision, reason, timestamp có timezone và exact candidate-content SHA-256. Receipt đã ghi không sửa lại; muốn đổi quyết định phải prepare candidate mới. Đây là audit local, không phải hệ thống chữ ký hoặc phân quyền reviewer. Không có approval tự động cho dữ liệu thật.

## Hybrid Review

| Tình huống | Quyết định |
|---|---|
| Hoàn thành mới, evidence độc lập hợp lệ, đủ thống kê | `AUTO_ACCEPT` trong research |
| Có evidence hoàn thành, thiếu xG/SH/SOT | `NEW_PENDING`, lưu `PENDING_UPDATE`, giữ NULL |
| Pending thường nhận đủ số liệu | `PENDING_RESOLVED`, `AUTO_ACCEPT` |
| Pending từng bị gắn unreliable nhận đủ số liệu | `MANUAL_REVIEW` |
| Sửa xG, SH/SOT lịch sử hoặc kết quả cuối | `MANUAL_REVIEW` |
| Đổi ngày/kickoff, kể cả lịch chưa hoàn thành | `MANUAL_REVIEW` bảo thủ |
| Scheduled/live/postponed/cancelled chuyển trạng thái hợp lệ | Ghi revision; không suy ra hoàn thành |
| ID/source conflict, completion/statistics regression, số liệu sai | `BLOCKED` |
| Manifest không khớp file của chính nó | `BLOCKED` |
| Chỉ đổi timestamp/hash metadata, không đổi nghiệp vụ | `NO_CHANGE`, không tạo DB |

Toàn bộ candidate bị chặn nếu có manual item chưa duyệt hoặc bị từ chối. Không publish subset. Sau review, publish dựng lại candidate từ input, so checksum, kiểm tra parent và receipt, rồi chạy lại invariant. Approval không vượt qua thiếu evidence, số âm, SOT > SH, mirror sai, roster thiếu, duplicate hoặc chronology. Một đội có hai kết quả hoàn thành cùng ngày bị chặn theo chính sách cutoff theo ngày.

## Versioning, idempotency và rollback

Parent SQLite luôn read-only. Dữ liệu và review chi tiết chỉ tồn tại trong ignored workspace và metadata của DB nghiên cứu. Successor lưu parent SHA, input hashes kế thừa, source versions, full schedule projection, diff và receipt. Catalogue/coverage được tính lại từ trạng thái registry thực tế.

Publisher dùng lock độc quyền, build vào `.building-*`, kiểm tra SQLite integrity/FK, gọi inference validator, ghi manifest có DB hash và atomic rename tới version directory mới. Lỗi trước rename xóa đúng temporary directory của builder và giữ parent. Không replace version cũ hoặc tạo con trỏ production. Nếu process dừng đột ngột để lại lock/build directory, cần người vận hành kiểm tra và xử lý; không tự xóa lock có thể đang được dùng.

Effect SHA dựa trên parent DB hash, policy và toàn bộ business snapshot, bỏ candidate ID và retrieval timestamps. Lặp cùng input/parent sẽ trả `ALREADY_PUBLISHED` từ manifest của snapshot đã xuất bản; không tạo version nữa. `NO_CHANGE` trả về ngay, không dựng DB. Report local có thể ghi lại từ version manifest nếu receipt báo cáo bị lỗi sau rename.

## Inference và tính toàn vẹn

Không refit imputer, đổi estimator hoặc làm lại Phase 7. Trusted loader kiểm tra model checksum, dependency versions, fitted medians, 3.800 dòng fit và feature schema. Option B tiếp tục đếm mọi trận verified trong stint; đúng 5 trận cuối cần thống kê. Pending ngoài cửa sổ vẫn được đếm; pending trong cửa sổ chặn inference, không lấy trận cũ hơn thay thế.

Validator mới dùng cohort động của mùa mới nhất với ngày không sau as-of. Với target mà cả hai snapshot suy luận được: 13 feature bằng nhau thì raw và clipped predictions phải lệch tối đa `1e-12`; feature thay đổi hợp lệ được phép làm prediction đổi. Lỗi coverage/pending/ambiguous đã biết được đếm riêng, không tính là dự đoán thành công. Checksum V3 và parity 111 fixture cũ được kiểm tra riêng bằng evaluator baseline.

Cutoff giữ nguyên `date < cutoff`, loại target/future; không chứng minh availability theo thời điểm thực tế của từng lịch sử snapshot. Chất lượng MAE/RMSE và tương đương định nghĩa giữa các provider chưa được giải quyết.

## Contract, lỗi và tái lập

[FIXTURE_DATA_CONTRACT.md](FIXTURE_DATA_CONTRACT.md) mô tả schema và chính sách null/timezone. Xuất local bằng:

```powershell
.venv/Scripts/python.exe -m scripts.multisource.refresh_composite export --database data/history/research/phase853_v3_20261122/laliga_composite.sqlite3 --output data/external/multisource/refresh/export-local-check
.venv/Scripts/python.exe -m scripts.multisource.refresh_demo --directory data/external/multisource/refresh/demo-new-id
.venv/Scripts/python.exe -m scripts.multisource.validate_refresh --workspace data/external/multisource/refresh/validation-new-id
```

Validation runner chặn socket network, xóa các API-key environment values trong scope chạy, thực thi full unittest suite, tái lập V3, prepare/publish NO_CHANGE local, demo tổng hợp A/B/C và kiểm tra file đóng băng. Cần có private snapshot V3 và nguồn local gốc; fresh clone không kèm restricted data phải được cấp các input này hợp lệ trước khi tái lập phần real-data. Thư mục đích phải mới.

Các lỗi chính: `SOURCE_VERSION_MISMATCH`, `SOURCE_CONFLICT`, `IDENTITY_CONFLICT`, `DUPLICATE_FIXTURE`, `INVALID_SCHEMA`, `UNVERIFIED_COMPLETION`, `STATISTICS_REGRESSION`, `FUTURE_COMPLETION`, `INVALID_KICKOFF`, `REGISTRY_COVERAGE_UNVERIFIED`, `FROZEN_SOURCE_SCOPE`, `STALE_CANDIDATE`, `STALE_APPROVAL`, `REVIEW_REQUIRED`, `REVIEW_REJECTED`, `VERSION_EXISTS`, `INVALID_SCOPE`. CLI trả exit 1 và JSON `BLOCKED` khi thất bại. `status` kiểm tra lại candidate và receipt; nó không kích hoạt publish.

Raw provider rows, DB, exports, logs và review payloads nằm trong ignored directories. Chỉ commit code, test tổng hợp và báo cáo aggregate. Không có PR, merge hoặc bước production trong phase này.
