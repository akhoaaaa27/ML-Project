# Phase 8.5.4 — Controlled Data Refresh and Hybrid Review

Ngày kiểm chứng: 22/11/2026, Asia/Saigon. Phạm vi: research integration, offline, refresh thủ công.

Branch `phase8.5.4-controlled-data-refresh` được tạo từ `origin/main` tại `11e46aa61b7aaf6bf381c14dba0e5e83e1700e39`, sau khi Phase 8.5.2–8.5.3 được merge bằng PR #1. Workspace sạch trước triển khai. Chỉ một file đã tracked được mở rộng: `scripts/multisource/composite_history.py`; thay đổi bổ sung metadata tùy chọn cho publisher. Các file code/test/docs khác đều mới. Commit triển khai được ghi trong [validation JSON](../docs/PHASE_8_5_4_VALIDATION.json), commit giao cuối là HEAD của branch; không merge main hoặc tạo PR.

## Kết quả triển khai

- CLI: `prepare`, `review`, `publish`, `status`, `export`.
- Candidate/diff/review có checksum toàn nội dung; receipt lưu old/new values và provenance, không approve dữ liệu thật tự động.
- Review policy xác định rõ new completed, new pending, pending resolved, unreliable pending, corrections, schedule revisions và conflicts.
- Whole-candidate publication: có manual item chưa duyệt hoặc bị reject thì bị chặn. Approval không vượt invariant.
- Snapshot mới immutable, atomic, có kiểm tra SQLite và inference trước publish; lock/idempotency không tạo bản trùng.
- Catalogue giữ key không chứa ngày, provider ID, kickoff có timezone, status, source/snapshot version; adapter read-only phục vụ backend về sau.
- Không thay Phase 8/8.5.3 Feature Builders, frozen Linear Regression, fitted imputer, 13 feature, Phase 7 hoặc production History Store.

Code mới nằm trong `scripts/multisource/`: `refresh_validation.py`, `revision_review.py`, `refresh_composite.py`, `fixture_catalogue.py`, `refresh_demo.py`, `validate_refresh.py`. Có 56 test mới tại `tests/test_multisource_refresh.py`, gồm fixture nhỏ tổng hợp, catalogue 380 cặp đấu và CSV tổng hợp theo đúng định dạng provider.

## Kiểm chứng dữ liệu thật local

Parent: `phase853_v3_20261122`; candidate dự kiến: `phase854_local_20261122`.

| Chỉ số | Kết quả |
|---|---:|
| Registry fixtures | 3.040 |
| Verified completed | 2.783 |
| Complete statistics | 2.779 |
| Pending statistics | 4 |
| Unverified | 257 |
| Source conflicts | 0 |
| Business changes / auto accepted / manual items | 0 / 0 / 0 |
| Catalogue mùa 2026 | 380 fixtures, 20 đội, đủ mọi cặp có hướng |
| Kickoff có nguồn và khớp ngày UTC | 380 |
| Publication | `NO_CHANGE`; không tạo DB thật mới |

Không có snapshot mới ngoài dữ liệu local đã dùng cho V3. Không tải mạng, gọi StrikerAPI, cấp approval thật, backfill hoặc chuyển dữ liệu vào production. Hash nguồn được so với acquisition manifest của chính nó; V3 được dựng lại trong bộ nhớ và mọi fingerprint khớp. Không sửa raw source hoặc các snapshot cũ.

Baseline inference giữ 123/123 fixture thành công, 246 predictions; 111/111 fixture parity pass, max feature/prediction delta bằng 0. Kết quả 12 fixture được mở khóa từ phase trước vẫn giữ nguyên. Đây là tái lập inference nghiên cứu, không đánh giá lại Phase 7 Final Test.

## Demo tổng hợp A/B/C

| Demo | Kết quả đã thực thi |
|---|---|
| A — thêm completed hợp lệ | Một thay đổi `AUTO_ACCEPT`, publish successor; 5/12 target suy luận thành công, 7 target bị chặn do coverage; 4 feature input giữ nguyên đạt parity, 1 input thay đổi hợp lệ |
| B — sửa xG lịch sử | Một manual item; chỉ publish sau receipt APPROVE tường minh dành riêng fixture tổng hợp; 1 input giữ nguyên đạt parity, 4 input thay đổi hợp lệ |
| C — raw không khớp manifest | `BLOCKED / SOURCE_VERSION_MISMATCH`; parent nguyên vẹn, không successor |

Test cũng xác nhận prediction thực sự có thể đổi sau thay đổi xG hợp lệ; không ép parity với feature đã đổi. Tất cả demo dùng DB trong ignored demo workspace, nằm ngoài namespace History Store nghiên cứu thật.

## Kiểm thử và integrity

Full suite: **264 tests, 264 pass, 0 fail, 0 error, 0 skip**, chặn socket network và không yêu cầu API credentials. Bao gồm 208 test cũ và 56 test mới. Checksum 107 file đóng băng, cả 8 file DB/manifest của các version nghiên cứu cũ, model và production History Store đều không đổi. SQLite `integrity_check=ok`, không foreign-key violation.

Model SHA-256: `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69`.

V3 DB SHA-256: `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e`.

Production History Store SHA-256: `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982`.

Test kiểm chứng đúng actual last-five: thiếu bên trong thì chặn, thiếu bên ngoài vẫn đếm `matches_seen`, không skip hay impute raw outcome. Kiểm tra rollback, parent immutable, idempotency, stale receipt/candidate, 381st fixture, provider conflict, chronology, timestamp, read-only export và production disabled đều được thực thi.

## Bàn giao và giới hạn

Xem [hướng dẫn và CLI](../docs/CONTROLLED_DATA_REFRESH.md), [contract](../docs/FIXTURE_DATA_CONTRACT.md), [validation report và AC-01–15](../docs/PHASE_8_5_4_VALIDATION.md), [bằng chứng JSON](../docs/PHASE_8_5_4_VALIDATION.json).

Chỉ xuất bản safe code, synthetic tests và aggregate reports. Raw dataset, DB, private reviews, exports và logs đều giữ ignored local. Không kiểm chứng một lần download mạng thật hoặc publication của dữ liệu thật mới vì không có input mới được cấp. Download opt-in được kiểm thử bằng mock; publication và manual review được kiểm thử bằng dữ liệu tổng hợp, kể cả định dạng CSV provider.

Các sửa đổi archive cũ/frozen cần audit adapter riêng; nguồn ngày local cần timezone mapping đã review; lock còn sót sau process crash cần xử lý thủ công. Approval là audit JSON local, chưa có xác thực reviewer. Chưa kết luận tương đương định nghĩa FBref/Understat/Sportmonks hoặc chất lượng dự báo trên nguồn mới. Production vẫn tắt. Không triển khai phase tiếp theo.

**PASS — Phase 8.5.4 Research Integration Ready**
