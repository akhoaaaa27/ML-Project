# Phase 8.5.4 — validation report

Ngày 22/11/2026 (Asia/Saigon). Branch: `phase8.5.4-controlled-data-refresh`. Base: `11e46aa61b7aaf6bf381c14dba0e5e83e1700e39`. Commit code được ghi trong trường `implementation_commit` của [JSON evidence](PHASE_8_5_4_VALIDATION.json); commit báo cáo cuối cùng là HEAD của branch. `code_revision` là Git HEAD lúc chạy cùng source checksums của working tree; không diễn giải base SHA thành code mới đã commit.

## Thực thi

```powershell
.venv/Scripts/python.exe -m scripts.multisource.validate_refresh --workspace data/external/multisource/phase854/final-verification
```

Runner chặn network bằng socket guard, xóa API-key environment values trong scope kiểm chứng và chạy full discovery suite. Log verbose và các record tái lập chỉ lưu ở workspace ignored. Thực thi lại cần một workspace ID mới và các input private gốc; runner không tải input. Tài liệu [CONTROLLED_DATA_REFRESH.md](CONTROLLED_DATA_REFRESH.md) có hướng dẫn chuẩn bị/review/publish/export.

**264 tests: 264 pass, 0 fail, 0 error, 0 skip.** Trong đó có 56 test mới về refresh; full suite vẫn bao gồm các test tổng hợp của phase cũ. Không thực hiện lại đánh giá Final Test của Phase 7.

## Kết quả thực tế

| Hạng mục | Bằng chứng |
|---|---|
| Input thật | Snapshot local cũ; acquisition manifest và nguồn CSV khớp SHA/byte length |
| Parent → candidate | `phase853_v3_20261122` → `phase854_local_20261122` |
| Business changes | 0; auto accepted 0; manual review 0; conflicts 0 |
| Publication | `NO_CHANGE`; không database thật mới, không thay parent |
| Registry | 3.040 fixtures; 2.783 verified; 2.779 complete; 4 pending; 257 unverified |
| Catalogue current | 380 fixture, 20 đội, exact directed universe; 380 kickoff khớp UTC-date |
| V3 reproduction | Tất cả fixture fingerprints khớp; 123/123 target thành công, 246 predictions |
| Baseline parity | 111/111 pass; max feature delta 0, max raw prediction delta 0 |
| Frozen files | 107/107 checksum nguyên vẹn; protected manifest gốc cũng được xác minh SHA |
| Snapshot cũ | 8/8 file DB/manifest không đổi; SQLite integrity/FK pass |
| Imputer/model | 3.800 dòng fitted, medians/coefficients/features được trusted loader xác minh; không refit |
| Network/provider API | 0 download thực tế, 0 StrikerAPI call/credit |
| Dữ liệu công khai | Chỉ aggregate và source checksums; raw/review/DB vẫn ignored |

Model SHA-256: `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69`.

V3 SHA-256: `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e`.

## Demo và test có ý nghĩa

- A: một verified completion mới có đủ số liệu/evidence được auto accept và publish; frozen inference thành công. Trên 12 target tổng hợp có 5 success, 7 coverage-blocked; 4 feature inputs không đổi đạt raw/clipped parity, 1 input được phép đổi.
- B: một historical xG correction phát sinh manual review; không publish khi chưa có receipt. Demo cấp approval rõ ràng chỉ cho fixture tổng hợp, rồi publish; 4 feature inputs đổi và 1 input giữ nguyên. Test riêng xác nhận raw predictions thực sự đổi khi xG lịch sử đổi.
- C: manifest sai bị BLOCKED, không successor và parent không đổi.
- Unit tests: receipt bind exact payload, stale source/receipt/candidate bị từ chối; unresolved/rejected candidate không publish subset; invalid statistics không được approval vượt qua; failed callback dọn temporary build và giữ parent; repeated publication trả `ALREADY_PUBLISHED`; metadata-only trả `NO_CHANGE`.
- Catalogue: exact 380 directed fixtures, không duplicate/ID reassignment/381st; schedule correction có old/new values và manual review; UTC conversion được kiểm tra cả lệch ngày và timestamp thiếu timezone.
- Option B: pending trong actual last-five bị chặn, pending ngoài cửa sổ vẫn đếm; `matches_seen` và target/future exclusion được kiểm tra với kết quả cụ thể.
- Provider-format synthetic CSVs: current completion có evidence, archive xG/SH/SOT correction, schema loss, missing shot perspective, unknown provider và unsupported older archive revisions.

## Acceptance criteria

PASS áp dụng cho khả năng tích hợp nghiên cứu đã kiểm chứng ở scope nêu trên. Không suy diễn demo tổng hợp thành một lần cập nhật dữ liệu thật mới.

| AC | Trạng thái | Kiểm chứng |
|---|---|---|
| AC-01 | PASS | Local prepare/publish NO_CHANGE, không cần API key |
| AC-02 | PASS | Mặc định không gọi acquire; opt-in gọi đúng acquisition vào directory mới, được kiểm thử bằng mock |
| AC-03 | PASS | New/pending/resolved/corrections/conflicts/no-change qua test và A/B/C |
| AC-04 | PASS | Hybrid rules, exact-content receipts, unresolved/rejected/stale approval bị chặn |
| AC-05 | PASS | A/B và CSV-generated cases publish successor immutable, SQLite/inference validator pass |
| AC-06 | PASS | Parent/source evidence/metadata được bảo tồn; regression/score/source conflict bị chặn |
| AC-07 | PASS | NULL raw giữ nguyên; actual-last-five không skip, inside/outside-window tests pass |
| AC-08 | PASS | 107 protected files, model, fitted median/3.800 samples, 13 features, Phase 7 nguyên vẹn |
| AC-09 | PASS | V3 parity 111/111 delta 0; raw/clipped parity cho equal feature input trong successor tests |
| AC-10 | PASS | Injected callback failure và invalid manifest không sửa parent, không để published successor |
| AC-11 | PASS | Full offline suite thực thi: 264 pass, 0 fail/error/skip |
| AC-12 | PASS | Safe reports/CLI reproduction; private paths ignored, không tracked provider records |
| AC-13 | PASS | Real current catalogue 380/20 exact universe; kickoff/status/revisions và 381st tests |
| AC-14 | PASS | Same candidate/parent và candidate ID khác trả ALREADY_PUBLISHED; NO_CHANGE không DB mới |
| AC-15 | PASS | Adapter và JSON contract 1.0, CLI export/read-only test, không cần backend rebuild registry |

## Giới hạn và bàn giao

Chưa có source snapshot mới hơn local V3 nên chưa kiểm chứng real-data incremental publication. Chưa chạy network download thực tế. Các thao tác đó không phải kết quả đã thực hiện của phase này. Source hash/version của input đã dùng được ghi trong JSON report. Các version và private data cũ được giữ nguyên.

Temporal policy vẫn theo ngày, strict-before; không có cam kết intraday hoặc as-of-vintage. Archive 2019–2024 và phần FBref đóng băng bị chặn khi đổi nguồn; timezone khác UTC cần adapter riêng. Không có automatic crash-lock recovery hay reviewer authentication. Không chứng minh thống kê các provider tương đương, không tính predictive MAE/RMSE mới, không production approval.

Chỉ code, tests, docs và aggregate JSON được stage/commit; không raw CSV, SQLite, review receipt hoặc logs. Commit/push ở branch riêng; không PR, merge, scheduler hoặc phase tiếp theo.

**PASS — Phase 8.5.4 Research Integration Ready**
