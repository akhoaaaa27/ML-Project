# Phase 8.5.4 — Targeted Remediation

Ngày: **22/11/2026, Asia/Saigon**. Phạm vi: sửa đúng PM854-F01–F04 và kiểm chứng local, không thiết kế lại ingestion hoặc thay model.

**PASS — Phase 8.5.4 Remediation Implemented and Locally Verified**

Đây không thay thế một lượt Pre-Merge Verification độc lập mới. [Báo cáo FAIL lịch sử](PHASE_8_5_4_PREMERGE_VERIFICATION.md) và JSON tương ứng giữ nguyên byte; không đổi kết luận cũ thành PASS. Không PR, merge hoặc production approval.

## 1. Git, phạm vi sửa và bằng chứng lịch sử

Đã fetch remote trước khi sửa. Workspace sạch; remote không có commit mới hơn reference. Base và merge-base: `11e46aa61b7aaf6bf381c14dba0e5e83e1700e39`. Starting HEAD: `514ca623b7c03d3013937a1a62dfde67135f036c`; branch hơn main 3 commit, không behind. Ancestry Phase 8.5.2/8.5.3 giữ nguyên.

Branch: `phase8.5.4-controlled-data-refresh`. Fix chính: [`b556d285acaa4a5191cc0d65129cddc4cf210d22`](https://github.com/akhoaaaa27/ML-Project/commit/b556d285acaa4a5191cc0d65129cddc4cf210d22). Commit hoàn thiện F03 cho diff/review: [`7b43bed97e3face8c888311d9dd3b6d1dbfe011c`](https://github.com/akhoaaaa27/ML-Project/commit/7b43bed97e3face8c888311d9dd3b6d1dbfe011c). Full validation cuối kiểm chứng source khớp commit sau. Commit báo cáo tiếp theo chỉ thêm hai tài liệu này; lấy SHA bằng `git log -1 --format=%H -- docs/PHASE_8_5_4_REMEDIATION.md`.

| File | Thay đổi |
|---|---|
| `scripts/multisource/refresh_validation.py` | Kiểm tra archive/shot identity, schema và scope trước aggregation; strict score; sửa completion provenance, giữ dữ liệu parent khi CSV stale |
| `scripts/multisource/fixture_catalogue.py` | Với row mới có provenance tách biệt, export tuple verification nhất quán; giữ nhánh đọc legacy |
| `tests/test_multisource_refresh.py` | Generator cung cấp đủ schema thực tế, numeric shot IDs và hai provider-ID namespace khác nhau; không bỏ test hoặc nới assertion |
| `tests/test_multisource_refresh_security.py` | **35 test mới**, offline, generated fixtures |
| `docs/PHASE_8_5_4_REMEDIATION.md`, `.json` | Hai báo cáo remediation mới |

Không sửa `mapping.py`, Match Registry, Composite Feature Builder, inference/model code, publisher, SQLite schema, dependency pins hoặc các báo cáo phase cũ. Bốn checksum source/test khớp implementation commit; xem [JSON evidence](PHASE_8_5_4_REMEDIATION.json).

## 2. Tái hiện trước khi sửa

Đã chạy lại counterexamples bằng helper provider-format ở trạng thái vulnerable, lưu log/payload tại ignored workspace:

```text
data/external/multisource/remediation854_20261122/
```

Đã thêm bốn assertion trọng tâm trước code fix. Chạy explicit bốn method tương ứng F01 duplicate ID, F02 wrong provider, F03 exact completion tuple và F04 three-component score: **4 test fail như dự kiến, 0 error, exit 1**. Nguồn synthetic được nâng lên schema thực tế trước red run, nên counterexample không phụ thuộc thiếu cột giả lập.

| Counterexample đã xác nhận | Trước sửa | Sau sửa đã thực thi |
|---|---|---|
| Duplicate fixture ID và wrong-fixture shot join | PREPARED → sau synthetic approval PUBLISHED, nhận SOT của fixture khác | BLOCKED / `IDENTITY_CONFLICT`, không candidate/successor |
| Understat ID remap dù số liệu không đổi | NO_CHANGE | BLOCKED / `IDENTITY_CONFLICT` |
| Shot provider/competition/season/Understat ID sai | PREPARED → sau synthetic approval PUBLISHED | BLOCKED / `SOURCE_CONFLICT`, parent giữ nguyên |
| Independent completion provenance | URL official nhưng CSV hash/time | Khớp chính xác evidence URL, SHA và reviewed_at; CSV/statistical provenance vẫn được giữ riêng |
| Score `2-1-99` | NO_CHANGE | BLOCKED / `INVALID_SCORE` |

Năm invariant fail của audit cũ đều có kết quả đúng sau remediation. Các kết quả trước/sau được ghi riêng trong JSON, không sửa evidence cũ. Không có real-data approval hoặc số liệu thật được tạo để làm test pass.

## 3. PM854-F01 — FIXED

**Mức gốc: HIGH/P1, merge-blocking.** Root cause: canonical key được kiểm tra nhưng chưa chứng minh provider IDs duy nhất và còn thuộc đúng fixture trước join shots.

`archive_identities()` kiểm tra toàn bộ export 2025, kể cả các row chọn FBref đóng băng: schema 19 cột, provider/giải/mùa, canonical identity, positive integer IDs, uniqueness riêng của `fixture_id` và `understat_id`, strict score. Mapping `canonical_key → (fixture_id, understat_id)` phải bằng mapping của archive gốc có SHA attested trong parent manifest/refresh metadata. Không so hai ID của hai provider như cùng một namespace.

ID columns được đọc dưới dạng text và kiểm tra bằng Decimal trước chuẩn hóa integer để không làm tròn fractional ID thành một ID hợp lệ. Join dùng ID đã được xác minh/chuẩn hóa, bao gồm lookup row frozen. Provider remap không có migration được review sẽ bị chặn.

Tests bao phủ duplicate fixture ID, duplicate Understat ID, unique-ID swap, Understat remap, wrong shot join, identity đổi nhưng business values không đổi, frozen-row invalid identity, missing/zero/negative/fractional IDs, baseline hash mismatch và fractional identity gần integer. Positive controls xác nhận hai namespace khác nhau vẫn hợp lệ, unchanged → NO_CHANGE, và valid correction vẫn review/publish được trong khi frozen statistics giữ nguyên.

## 4. PM854-F02 — FIXED

**Mức gốc: HIGH/P1, merge-blocking.** Root cause: generic mapper chỉ cần vài field để đếm; caller chưa xác minh scope/provenance trước khi mapper bỏ các cột khác.

Refresh caller nay yêu cầu đầy đủ **18 cột** của reviewed shot export:

```text
provider, competition, season, fixture_id, understat_id, shot_id,
side, minute, player_id, player, result, x, y, understat_xg,
situation, shot_type, assisted_by, last_action
```

Trước aggregation: kiểm provider Understat, competition la-liga, season 2025; kiểm positive integer IDs, global shot-ID uniqueness trong export, đúng fixture universe và Understat ID tương ứng từng fixture. Chỉ sau đó mới gọi `understat_shots()` hiện có. Cả nguồn không tạo business change và phần frozen selection cũng được kiểm tra. Nullable player/action fields không sử dụng vẫn được phép NULL; không bịa giá trị để lấp metadata. Cột của schema phải có mặt.

Không đổi shot classification, penalty/own-goal handling hoặc cách tính SH/SOT. Tests tách riêng wrong provider/competition/season, unknown fixture, mismatched Understat ID, duplicate/invalid shot ID, missing identity value/column, incomplete schema và invalid metadata đi kèm correction hợp lệ. Một test giữ approval hợp lệ rồi thay nguồn thành sai provider với manifest mới: publish vẫn bị `SOURCE_CONFLICT`; approval không vượt invariant.

## 5. PM854-F03 — FIXED

**Mức gốc: MEDIUM/P2, merge-blocking.** Root cause: đã chọn independent evidence URL nhưng vẫn truyền CSV SHA/retrieval time cho Match Registry.

Khi evidence độc lập xác nhận completion, tuple `verification_source`, `source_version`, `verified_at` lấy đúng từ evidence URL, content SHA và review timestamp. Nếu chỉ có CSV stale cho một kết quả parent đã verified và identity/date/score còn khớp, giữ completion proof và statistical pair đã được xác minh trong parent; không đổi raw values thành NULL hoặc tạo thống kê mới. Kết quả mới thiếu mandatory evidence vẫn bị chặn, score conflict vẫn là source conflict.

JSON payload registry/evidence của row mới lưu riêng `fixture_provenance`:

```text
fixture_source
source_url
source_dataset_version
fetched_at
provider_fixture_id
```

Statistical pair vẫn giữ xG source, shots source, statistical source version và fetched_at của CSV. Không đổi SQLite schema. Flat fixture export vẫn có đúng 14 field; đối với row mới có `fixture_provenance`, `source_provider/source_version/verified_at` thể hiện một tuple verification nhất quán. CSV identity provenance được giữ riêng trong payload, không nên suy ra provider-ID namespace từ URL completion evidence. Row legacy tiếp tục dùng nhánh đọc cũ; không sửa snapshot đã xuất bản.

Test assert trực tiếp row fields, published SQLite payload, statistical provenance và export, với evidence SHA/time khác CSV. Có controls new completed, new pending, stale CSV, missing mandatory evidence và contradictory score. Candidate diff và receipt cũng giữ đúng verification source/version/time, kèm CSV provenance riêng; không tiếp tục trộn tuple trong phần review. Assertion bổ sung cho phần này đã fail trước khi hoàn thiện F03, sau đó pass trong 35 regression và full suite cuối.

## 6. PM854-F04 — FIXED

**Mức gốc: LOW/P3, tự nó không merge-blocking.** Root cause: split score ra nhiều thành phần rồi chỉ dùng hai phần đầu.

Parser chỉ nhận hai nonnegative integer dạng ASCII, một dấu `-`; không tự strip whitespace, nhận dấu cộng hoặc bỏ suffix. Parser chạy trên mọi row archive liên quan trước review/frozen branch. `2-1-99`, `2`, `2-`, `-1`, `1--2`, `abc`, `1.5-2`, missing/NaN, infinity, leading whitespace, internal whitespace và dấu `+` bị chặn. Score đúng, kể cả `0-0`, vẫn đi qua review hợp lệ khi là correction.

## 7. Kiểm thử, môi trường và lệnh

Môi trường không đổi: Python **3.14.0**, NumPy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, SciPy 1.18.1, joblib 1.6.0, threadpoolctl 3.8.0, requests 2.34.2. Không thêm package; Decimal thuộc standard library.

| Kết quả được dùng làm evidence cuối | Executed | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|---:|
| Regression mới, final targeted run | 35 | 35 | 0 | 0 | 0 |
| Refresh tests có sẵn, targeted subset | 56 | 56 | 0 | 0 | 0 |
| Composite/Multi-source/Inference/Model tests targeted | 91 | 91 | 0 | 0 | 0 |
| Full suite trên code cuối | **299** | **299** | **0** | **0** | **0** |

Full suite gồm 264 test có sẵn và 35 method mới. Targeted rows có overlap với full suite; không cộng lượt chạy thành unique repository tests. Subtests kiểm nhiều invalid variants cũng không được tính thành nhiều method. Generator được import qua module để unittest không discover lặp class test được import. Các preliminary runs không được dùng làm số test cuối.

Lệnh full validation thực tế, exit **0**, unittest runtime **134.867 giây**:

```powershell
.venv/Scripts/python.exe -m scripts.multisource.validate_refresh --workspace data/external/multisource/remediation854_20261122/complete-verification --output data/external/multisource/remediation854_20261122/complete-report.json
```

Targeted runs được thực thi bằng PowerShell here-string pipe vào `.venv/Scripts/python.exe -`, dùng `unittest.defaultTestLoader.loadTestsFromName(s)` và `TextTestRunner`, log vào ignored workspace. Các module: `tests.test_multisource_refresh_security`, `tests.test_multisource_refresh`, `tests.test_composite_history`, `tests.test_multisource`, `tests.test_inference`, `tests.test_model_export`. Thêm `tests/` vào sys.path cho inference helper. Final targeted runs exit 0; red test-first exit 1 là kết quả dự kiến trước fix.

Full và targeted wrappers chặn `socket.socket.connect`, bỏ API-key environment values trong scope test. Không có test bắt buộc chưa chạy. Các test training/tuning có sẵn chỉ dùng fixtures; không retrain/refit frozen artifact hoặc đánh giá lại Phase 7 Final Test thật. Log chi tiết: `security-complete.log`, `targeted-refresh.log`, `targeted-existing.log`, `complete-verification/unittest.log`.

## 8. Demo A/B/C/D, Hybrid Review và publication

| Demo | Quan sát sau fix |
|---|---|
| A — new verified completion | AUTO_ACCEPT → PUBLISHED, frozen inference thành công |
| B — valid correction | MANUAL_REVIEW → explicit synthetic APPROVE → PUBLISHED |
| C — manifest sai | BLOCKED, parent nguyên vẹn |
| D — archive shot provenance sai | BLOCKED / SOURCE_CONFLICT; review/publish không vượt được; không successor; parent nguyên vẹn |

Các counterexample và demo chỉ dùng generated data trong TemporaryDirectory hoặc ignored external workspace, ngoài research history thật. Controls valid xG correction, valid SH/SOT correction và frozen-selection preservation đều pass. Callback rollback, idempotency, stale receipts, content checksum binding, production disabled và report-failure recovery được full suite kiểm lại. Không thay logic publish/lock/atomic rename.

## 9. Dữ liệu thật, model và tính toàn vẹn

Actual real-data refresh vẫn **NO_CHANGE**: 0 business changes, 0 auto-accept, 0 manual approval thật, 0 conflict; không DB thật mới. Không có snapshot thật mới hơn local để chứng minh real incremental publication. Không dùng demo tổng hợp thay cho bằng chứng đó.

| Hạng mục | Quan sát mới |
|---|---|
| V3 counts | 3.040 registry; 2.783 verified; 2.779 complete; 4 pending; 257 unverified; 0 conflict |
| V3 rebuild | Fingerprints khớp toàn bộ |
| Inference/parity | 123/123 fixture, 246 team predictions; 111/111 parity, max feature/raw prediction delta 0 |
| Current catalogue | 380 fixture, 20 đội, exact directed universe; 380 source-backed UTC kickoffs |
| Protected manifests từ Git baseline | 107/107 và 77/77 entry khớp; hai tập có overlap |
| Input/version history | 17 input attested V3 khớp manifest; 13 file raw local và 8 file DB/manifest cũ nguyên SHA |
| Model | Linear Regression V1; fitted imputer 3.800 sample; coefficients/intercept/medians đúng metadata |
| Feature/temporal policy | 13 feature, actual last-five, stint, matches_seen, strict-before cutoff và cold start không đổi |

SHA-256 thực tế:

```text
Frozen LR:
0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69
Production History Store:
d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982
Original V3:
110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e
```

SQLite integrity/FK checks pass. Ba file tracked được sửa đúng scope; mọi file tracked có sẵn khác, gồm validation/pre-merge reports, giữ nguyên checksum. Không thay raw dataset, production store hoặc research versions đã công bố.

## 10. Acceptance Criteria sau remediation

| AC | Trạng thái local | Evidence đã thực thi |
|---|---|---|
| AC-01 | PASS | Local NO_CHANGE, không API key |
| AC-02 | PASS | Default offline, opt-in mock tests giữ nguyên |
| AC-03 | PASS | F01/F02/F04 invalid source/identity/score → BLOCKED |
| AC-04 | PASS | Invalid source không thành reviewable correction; approval không vượt invariant |
| AC-05 | PASS | Valid controls publish immutable; invalid Demo D không successor |
| AC-06 | PASS | Cross-file identity/scope và exact evidence tuple; CSV/statistics provenance giữ riêng |
| AC-07 | PASS | Existing actual-last-five/NULL/count/cutoff tests pass |
| AC-08 | PASS | Protected hashes, LR/imputer/13 features/Phase 7 không đổi |
| AC-09 | PASS | V3 111/111 zero delta và dynamic parity tests |
| AC-10 | PASS | Rollback, parent hashes và report-failure recovery pass |
| AC-11 | PASS | Full suite 299/299, final regression 35/35 |
| AC-12 | PASS | Safe new reports; historical FAIL evidence nguyên vẹn |
| AC-13 | PASS | Real 380/20 catalogue, schedule/kickoff tests pass |
| AC-14 | PASS | Idempotency/metadata-only/NO_CHANGE tests pass |
| AC-15 | PASS | Read-only contract shape giữ nguyên; new completion export tuple được assert |

Đây là reassessment từ kết quả local mới, không phải thay đổi bảng AC trong audit cũ. Cần một reviewer độc lập kiểm lại branch HEAD mới trước quyết định merge.

## 11. Publication safety, giới hạn và bước tiếp theo

Đã rà full staged diff và kiểm source SHA với implementation commit. Chỉ commit code, synthetic tests và hai remediation reports. Không raw provider CSV, research SQLite, secret, private review hoặc detailed log/prediction được stage. Pattern scan không phát hiện credential; không gọi StrikerAPI, không download provider mới, không dùng paid credits. Git push không force, không tạo PR hoặc merge.

Không còn finding F01–F04 chưa sửa trong local regression scope. Các giới hạn còn lại:

- Chưa thực thi real incremental publication vì không có input mới; không phải một implementation failure.
- Original attested archive vẫn cần để đối chiếu IDs; provider remap phải qua migration review riêng.
- Không rewrite snapshot cũ. Candidate/review đang pending cần prepare và review lại sau cập nhật code; không chuyển approval cũ tự động.
- Date-only UTC policy không chứng minh intraday/as-of-vintage availability; thống kê/accuracy giữa provider và quyền phân phối raw vẫn là câu hỏi nghiên cứu riêng.
- Cơ chế xử lý crash-lock thủ công và receipt local không chữ ký/authentication giữ nguyên; không mở rộng scope thành hệ thống production.

**Bước khuyến nghị:** thực hiện một lượt **Independent Pre-Merge Verification mới trên HEAD cuối của branch**, chạy lại đủ bốn finding và các adversarial scenarios; giữ nguyên báo cáo FAIL lịch sử. Chỉ sau lượt đó mới cân nhắc PR/merge research integration. Không triển khai phase tiếp theo trong remediation này.
