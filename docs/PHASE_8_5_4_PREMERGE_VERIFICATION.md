# Phase 8.5.4 — Independent Pre-Merge Verification

Ngày xác minh: **22/11/2026, Asia/Saigon**. Đây là nhiệm vụ chỉ kiểm chứng. Không sửa implementation, unit test hoặc bằng chứng validation đã có; chỉ bổ sung hai báo cáo pre-merge.

## 1. Executive Summary

**Chưa nên tạo PR sẵn sàng merge hoặc merge Phase 8.5.4 vào main.** Full suite hiện có pass 264/264 và frozen artifacts nguyên vẹn, nhưng probe độc lập tái hiện được việc publish thống kê từ sai fixture/sai scope nguồn qua adapter archive. Provenance của completion mới cũng gắn sai version/timestamp. Có **3 finding chặn merge** và **1 finding mức thấp**; không tự sửa trong lượt kiểm chứng này.

Phân biệt kết quả: 264 test repository pass; 147 lượt test mục tiêu chạy lại pass; 15 kiểm tra bổ sung có 10 invariant pass và 5 invariant fail, quy về 4 finding. Không cộng các lượt chạy lại thành số test repository duy nhất. Báo cáo PASS của runner cũ phản ánh các test mà runner thực thi, không bác bỏ counterexample mới.

## 2. Verification Verdict

**FAIL — Phase 8.5.4 Merge Blocked by Defects**

Đây là lỗi implementation đã tái hiện, không phải thiếu dataset bắt buộc. Việc không có snapshot thật mới là giới hạn được chấp nhận trong scope nghiên cứu và không phải lý do kết luận FAIL. Bằng chứng đầy đủ dạng cấu trúc nằm trong [JSON report](PHASE_8_5_4_PREMERGE_VERIFICATION.json).

## 3. Repository and Git State

Đã `git fetch origin`, kiểm tra workspace sạch, đọc remote refs và tìm PR bằng GitHub connector với query `head:phase8.5.4-controlled-data-refresh`, state `all`: **0 PR** tại thời điểm xác minh.

| Hạng mục trước commit báo cáo này | Quan sát độc lập |
|---|---|
| Repository | `akhoaaaa27/ML-Project` |
| `origin/main` | `11e46aa61b7aaf6bf381c14dba0e5e83e1700e39` |
| Branch và HEAD được kiểm chứng | `phase8.5.4-controlled-data-refresh` — `f359d2c989700e92a4793dfd7701b7b4623599b2` |
| Implementation commit | `f31162d35f41bf2b09cfa58be2652f40d15b612c` |
| Merge-base | `11e46aa61b7aaf6bf381c14dba0e5e83e1700e39` |
| Ahead / behind main | 2 / 0 |
| Diff implementation và validation cũ | 13 file: 12 thêm, 1 sửa |
| Thay đổi remote ngoài reference | Không |

Phase 8.5.2 commit `2ae0f8920ca0435b8c32c1b4763bc30ec370ba5b` và Phase 8.5.3 commit `68234d5c481009d077bf607fe579a0d54845cb2e` đều là ancestor. Không có merge/cherry-pick mới. Commit chứa riêng hai báo cáo này dự kiến làm branch thành 3 ahead / 0 behind, diff tổng 15 file; phần tăng đó là tài liệu kiểm chứng, không phải thay đổi implementation.

## 4. Changed-File Audit

Đã đọc code, docs, JSON, test và lưu patch đầy đủ trong ignored workspace; quét nội dung toàn bộ 13 Git blobs, không chỉ tên file. Danh sách và checksum từng blob có trong `changed_file_audit` của JSON:

| Nhóm | File |
|---|---|
| Publisher sửa | `scripts/multisource/composite_history.py` |
| CLI/validation/review mới | `refresh_composite.py`, `refresh_validation.py`, `revision_review.py` |
| Adapter/demo/runner mới | `fixture_catalogue.py`, `refresh_demo.py`, `validate_refresh.py` |
| Test mới | `tests/test_multisource_refresh.py` |
| Docs mới | `CONTROLLED_DATA_REFRESH.md`, `FIXTURE_DATA_CONTRACT.md`, `PHASE_8_5_4_VALIDATION.md`, `PHASE_8_5_4_VALIDATION.json`, phase log 8.5.4 |

Publisher chỉ thêm tham số `refresh_metadata` tùy chọn, lưu payload vào bảng metadata và bind hash vào core manifest. SQLite schema version vẫn 1; caller cũ và reader V3 hoạt động. Không thêm writer vào production, không đổi Feature Builder, estimator hoặc imputer. Inference validator vẫn chạy trước atomic rename.

**Source revision audit:** cả 8 SHA-256 trong validation JSON khớp chính xác Git blobs của `f31162d`, file hiện tại và branch `f359d2c`. Cả 8 file không thay đổi giữa hai commit. Do đó giải thích validation trên working tree dựa ở `11e46aa`, rồi commit cùng source tại `f31162d`, là đúng; đây không phải finding. Không dùng các PASS claim cũ để suy ra tính đúng của validation mới.

## 5. Test Environment and Commands

Không cài/nâng cấp package. Python **3.14.0**, Windows 11; NumPy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, SciPy 1.18.1, joblib 1.6.0, threadpoolctl 3.8.0, requests 2.34.2. Trusted loader chấp nhận environment đã pin.

Workspace chi tiết, đã Git-ignore:

```text
data/external/multisource/premerge854_20261122_independent/
```

Các lệnh thực tế chính:

```powershell
git fetch origin
git rev-parse origin/main origin/phase8.5.4-controlled-data-refresh
git merge-base origin/main origin/phase8.5.4-controlled-data-refresh
git rev-list --left-right --count origin/main...origin/phase8.5.4-controlled-data-refresh
git diff --name-status origin/main...origin/phase8.5.4-controlled-data-refresh
.venv/Scripts/python.exe data/external/multisource/premerge854_20261122_independent/run_targeted.py
.venv/Scripts/python.exe -m scripts.multisource.validate_refresh --workspace data/external/multisource/premerge854_20261122_independent/runner --output data/external/multisource/premerge854_20261122_independent/runner-report.json
.venv/Scripts/python.exe data/external/multisource/premerge854_20261122_independent/adversarial.py
.venv/Scripts/python.exe data/external/multisource/premerge854_20261122_independent/integrity.py
```

Full runner, targeted wrapper và provider-format probes chặn socket network; các scope test bỏ API-key environment values, không cần data API credentials. Không gọi StrikerAPI/download provider. Git transport và PR lookup là thao tác repository được yêu cầu.

## 6. Independently Executed Test Results

| Nhóm thực thi | Chạy | Pass | Fail | Error | Skip |
|---|---:|---:|---:|---:|---:|
| Refresh | 56 | 56 | 0 | 0 | 0 |
| Composite History | 37 | 37 | 0 | 0 | 0 |
| Multi-source | 21 | 21 | 0 | 0 | 0 |
| Inference, lần chạy hợp lệ | 23 | 23 | 0 | 0 | 0 |
| Model export/integrity | 10 | 10 | 0 | 0 | 0 |
| Tổng lượt targeted hợp lệ | **147** | **147** | **0** | **0** | **0** |
| Full repository suite, bao gồm các nhóm trên | **264** | **264** | **0** | **0** | **0** |

Full runner exit **0**, unittest runtime **109.757 giây**; targeted groups hợp lệ đều exit 0. Full suite chạy thực tế, không sao chép kết quả cũ. Các test training/tuning/Final Test là test repository trên fixture kiểm thử; không retrain artifact bàn giao hoặc đánh giá lại Final Test thật.

**Lỗi harness được tách riêng:** targeted wrapper ban đầu thiếu `tests/` trong `sys.path`; import `tests.test_inference` trả `_FailedTest`, 1 loader error, wrapper exit 1; chưa test inference nào được chạy ở bước lỗi. Đã chạy lại riêng inference qua PowerShell here-string vào `.venv/Scripts/python.exe -`, thêm `sys.path.insert(0, str(Path.cwd()/'tests'))`, giữ socket guard và API-key clearing: **23/23 pass, exit 0**, log `inference-rerun.log`. Không sửa source hoặc test để xử lý lỗi harness. JSON giữ cả lần lỗi và lần chạy hợp lệ.

Các probe ngoài suite có **15 kiểm tra, 10 pass, 5 invariant fail**, không có execution error. Năm fail gồm duplicate archive ID/wrong shot join, đổi Understat ID không bị chặn, sai scope shot, sai completion provenance và score dư thành phần. Chi tiết ở mục 16; các lỗi này chưa có assertion tương ứng trong suite hiện tại.

## 7. Frozen Model and Phase 7 Integrity

Đọc authoritative protected manifests từ **Git blob của origin/main**, rồi hash file thật: **107/107** entry trong provider-PoC manifest và **77/77** entry trong inference manifest khớp. Hai danh sách có overlap, không cộng thành 184 file độc lập. Không chỉ tin báo cáo cũ hoặc manifest ở working tree.

| Artifact | SHA-256 kiểm chứng |
|---|---|
| Frozen LR | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| Production History Store | `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982` |
| V3 research SQLite | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |

Trusted load và kiểm tra fitted object độc lập xác nhận `LinearRegression` V1 `1.0.0`, `HistoryMedianImputer` fit **3.800** sample, coefficients/intercept/medians khớp metadata chính xác. 13 feature đúng thứ tự:

```text
is_home, matches_seen, short_history, xg_avg5, xga_avg5,
gf_avg5, ga_avg5, shot_avg5, sot_avg5, opponent_xg_avg5,
opponent_xga_avg5, opponent_matches_seen, opponent_short_history
```

Phase 7 outputs, normalized data, preprocessing và production History Store không đổi. Không retrain/refit artifact, không chạy production importer.

## 8. Composite History and Registry Validation

Đếm trực tiếp qua SQLite read-only, đối chiếu core manifest và rebuild V3 trong bộ nhớ:

| Chỉ số V3 | Quan sát |
|---|---:|
| Registry | 3.040 |
| Verified completed | 2.783 |
| Complete statistics | 2.779 |
| Pending | 4 |
| Unverified | 257 |
| Conflicts | 0 |

SQLite integrity `ok`, không FK violation. Tất cả fingerprints của rebuild khớp V3. **8/8** file DB/manifest nghiên cứu có sẵn giữ nguyên SHA, gồm cả version kiểm chứng cũ. Bổ sung synthetic snapshots chỉ nằm trong ignored external/temp workspaces, không thay snapshot thật.

## 9. La Liga 2026–27 Fixture Catalogue Validation

Truy vấn thực tế và kiểm directed universe: **380 fixture / 20 đội / 380 cặp có hướng / 380 provider ID current duy nhất**. Các test duplicate, reassigned current ID, fixture thứ 381, schedule/key preservation và status được chạy lại. Key không chứa ngày; date/kickoff correction tạo manual item.

V3 chưa chứa kickoff inline. Adapter chỉ hydrate từ CSV local đúng SHA attested: hiện có **380 kickoff** hợp lệ theo UTC-date policy. Probe `legacy_directory` không có CSV và CSV sai hash đều cho kickoff **null**, không tự tạo giờ. Export không đổi DB. Các kết luận này áp dụng catalogue current; không được dùng để bỏ qua finding identity archive 2025.

Timezone: timestamp naive hoặc UTC day khác match_date bị chặn; aware offset được đổi về UTC; null được giữ. Ngày địa phương Tây Ban Nha có thể khác ngày UTC quanh nửa đêm. Adapter chỉ nhận UTC-date contract, không tự bù ngày hoặc suy đoán timezone; cần mapping được review nếu nguồn đổi quy ước.

## 10. Refresh Candidate Validation

Lặp local snapshot thật: `prepare → publish → status` trả **NO_CHANGE**, 0 business change, 0 review thật, giữ 4 pending, không tạo DB thật mới. Inventory local chỉ có một acquisition thật current với SHA `dbbd9d99526717a03af3548375340aaa7364c4699a0689bf9e0d1a6421cd3c0e`; không có input thật mới hơn được cấp.

Các đường đúng đã xác minh: default không gọi acquire; opt-in mock đi vào directory mới; own-manifest mismatch, missing source, unsupported current provider/schema, missing independent completion, contradictory score, negative/fractional SH/SOT, future completion, stale candidate đều bị chặn. Hash mới có manifest mới hợp lệ được chấp nhận, không so cứng với parent hash. Tuy nhiên kiểm tra archive identity và shot provenance có lỗ hổng F01/F02; score parsing có F04.

## 11. Hybrid Review and Approval Integrity

Đã chạy lại new completed/new pending/ordinary pending/unreliable pending, xG/SH/SOT/score/date/kickoff corrections. Receipt bind exact candidate content và các field change ID, parent/candidate, old/new values, provenance. Missing/rejected review, source thay sau approval, checksum bị sửa và payload candidate bị sửa đều bị chặn. Probe riêng xác nhận:

- Duplicate approval: `REVIEW_EXISTS`.
- Unknown change: `INVALID_REVIEW`.
- Sửa old score trong receipt: `STALE_APPROVAL`.
- Unsafe candidate ID `../escape`: `INVALID_VERSION`.

Không tạo approval cho dữ liệu thật. Approval tổng hợp trong probe được cấp rõ ràng để kiểm tra invariant. **F01/F02 cho thấy structural/source conflict chưa được nhận diện nên bị coi là correction có thể review, rồi publish sau approval.** Binding checksum vẫn đúng; lỗi không phải tái sử dụng approval cho payload khác.

## 12. Immutable Publication, Rollback, and Idempotency

Code và test xác nhận build temporary directory, integrity/FK checks, inference callback, sidecar/core checks, atomic rename và chống overwrite version đã tồn tại. Callback fail trước rename không để published directory, dọn đúng `.building-*`, nhả lock và giữ parent. Root guard chặn production namespace.

Lặp publish cùng effect trả `ALREADY_PUBLISHED`; candidate ID khác và retrieval timestamp khác vẫn dùng cùng business version. Metadata-only và NO_CHANGE không sinh DB. Probe gây lỗi ghi report **sau rename** giữ một version hợp lệ; retry trả `ALREADY_PUBLISHED`, parent không đổi. Đây là failure recovery khác với rollback trước rename.

Lock còn sót do process crash và partial `.writing` vẫn cần người vận hành kiểm tra thủ công; không tự xóa lock của process khác. Giới hạn đó chấp nhận cho nghiên cứu thủ công. Atomicity không ngăn được dữ liệu sai đi qua validation bị thiếu ở F01/F02.

## 13. Feature Engineering and Prediction Parity

Đọc lại Option B: registry lấy verified-completed, strict `date < cutoff`, loại target, xác minh stint/coverage, lấy đúng `.tail(5)` rồi kiểm completeness. Count vẫn dùng toàn registry stint, không chỉ các dòng có stats. Các tests inside/outside-window, matches_seen và future/target exclusion pass.

Đã tái hiện thêm case thật có pending trong window, nhận `MISSING_ROLLING_STATISTICS`; không điền raw và không thay bằng trận thứ 6. Rebuild/evaluate V3 mới đạt **123/123** fixture suy luận, **246** team predictions, **111/111** parity fixture, max feature/raw prediction delta **0**; 12 case đã mở khóa từ phase trước vẫn giữ kết quả.

Case A raw/clipped parity khi 13 feature không đổi pass; Case B test xác nhận xG lịch sử thay đổi hợp lệ làm feature/prediction đổi. Validator chỉ cho ba nhóm blocked code đã định nghĩa, unexpected candidate error khác sẽ raise trước rename. Nó không chứng minh nguồn mới tương đương FBref hoặc dữ liệu có sẵn tại lịch sử as-of-vintage.

## 14. Real versus Synthetic Verification Evidence

| Phạm vi | Kết quả quan sát mới |
|---|---|
| Real local | NO_CHANGE; nguyên parent; không real incremental publication |
| Synthetic demo A | AUTO_ACCEPT → PUBLISHED; inference thành công; có cả unchanged/changed feature cohort |
| Synthetic demo B | Manual item → explicit synthetic approval → PUBLISHED |
| Synthetic demo C | Manifest mismatch → BLOCKED; parent nguyên vẹn |
| Independent adversarial | Invalid archive identity/scope vẫn PUBLISHED sau synthetic approvals; provenance mismatch tái hiện |

Không coi synthetic publication là real-data update. Probe có prefix dataset-format “real” trong helper chỉ nhằm chạy adapter CSV thực tế; **toàn bộ nội dung là generated fixtures**, ở TemporaryDirectory ngoài namespace history thật. CLI demo vào namespace thật bị từ chối `INVALID_SCOPE` trước khi tạo directory. Không gọi network để lấy snapshot mới.

## 15. Read-Only Data Contract Assessment

Đã chạy `export` trên V3 vào ignored workspace: exit 0. `fixtures.json` có đúng 14 field đã mô tả; `data-status.json` có version/hash/build time/counts/source versions/research status/production flag. Counts khớp SQL trực tiếp, không hardcode; DB SHA trước/sau bằng nhau. SQL writer/production mode bị từ chối trong test.

Schema/adapter bàn giao backend về cấu trúc là hợp lệ. Tuy nhiên không nên tin tuple evidence version/time của completion mới trước khi sửa **F03**. Không triển khai FastAPI, frontend, Docker hoặc production integration.

## 16. Security and Publication Safety Findings

Diff 13 file được quét token/private key/credential patterns: **0 phát hiện**. Không raw CSV, SQLite, model binary mới, `.env`, private review hoặc detailed predictions trong diff. Git argument lists cố định, không shell interpolation từ candidate; ID/path traversal tests pass. Root/read-only guards và callback cleanup được kiểm tra. Data network guard giữ offline; không StrikerAPI/paid credits.

### PM854-F01 — HIGH / P1 — chặn merge: Có

**Vị trí:** [`refresh_validation.py:225–242`](../scripts/multisource/refresh_validation.py#L225), `archive_updates`.

Archive kiểm uniqueness canonical key nhưng không kiểm uniqueness/mapping `fixture_id` hoặc đối chiếu `understat_id`. Join shots dùng trực tiếp `raw["fixture_id"]`, trong khi registry giữ provider ID cũ. Probe đổi fixture tổng hợp đầu tiên từ ID 1000 sang ID 1001 đã dùng bởi fixture khác; làm SOT nhóm 1001 thành 5. Kết quả **PREPARED, 2 manual items → sau synthetic approvals PUBLISHED**; fixture 1000 nhận SOT 5 của fixture 1001. Đổi riêng Understat ID thành 999999 còn trả NO_CHANGE.

**Ảnh hưởng:** đưa số liệu sai trận vào successor gắn nhãn đã validate; approval không bảo vệ được identity invariant chưa được kiểm tra.

**Đề nghị:** kiểm tra IDs duy nhất, canonical mapping với parent/baseline, Understat ID và cross-file fixture/shot identity **trước** review/join. ID conflict phải BLOCKED, không approval override. Thêm regression tests sau khi được giao nhiệm vụ sửa.

Tái hiện độc lập, chỉ generated fixtures và fake IDs:

```python
from tests.test_multisource_refresh import ProviderFormatTests
from scripts.multisource.refresh_composite import review, publish
from scripts.multisource.refresh_validation import read_json

t = ProviderFormatTests("test_generated_csv_baseline_no_change")
t.setUp()
try:
    t.alter("archive_2025_fixtures.csv", "fixture_id", 1001)
    t.alter("archive_2025_shots.csv", "result", "SavedShot", index=24)
    result = t.prepare()  # PREPARED, expected BLOCKED
    candidate = t.base / "work/csv"
    for change in read_json(candidate / "candidate.json")["changes"]:
        if change["decision"] == "MANUAL_REVIEW":
            review(candidate, change["change_id"], "APPROVE",
                   "Synthetic audit only", "synthetic://proof")
    result = publish(candidate, root=t.root)  # PUBLISHED, expected rejection
finally:
    t.doCleanups()
```

### PM854-F02 — HIGH / P1 — chặn merge: Có

**Vị trí:** [`refresh_validation.py:216`](../scripts/multisource/refresh_validation.py#L216), shot loading/join/metadata trong `archive_updates`; generic mapper chỉ kiểm năm field shot cần đếm.

Probe gán shot CSV tổng hợp `provider=unreviewed_provider`, `competition=other-league`, `season=2099`, `understat_id=999999`, rồi sửa một outcome để có correction. Manifest của chính file hợp lệ. Kết quả **PREPARED → sau synthetic approval PUBLISHED**, provenance lại được đóng dấu `Understat`. Provider/competition/season của fixture CSV được kiểm, nhưng các field tương ứng của shot CSV bị bỏ qua.

**Ảnh hưởng:** dữ liệu sai scope/nguồn được nhận dưới provenance của nguồn được chấp nhận. Đây là thiếu validation trước review, không phải chỉ kiểm checksum yếu.

**Đề nghị:** yêu cầu schema shot-export đã review; xác minh provider, giải, mùa và IDs phù hợp fixture export, chặn scope conflict trước conversion. Có thể tái hiện bằng helper trên, thêm các cột sai vào shot frame và sửa outcome index 4; gọi `t.prepare`, review tổng hợp và publish. Bằng chứng mới: `shot-scope-probe.json` trong ignored workspace.

### PM854-F03 — MEDIUM / P2 — chặn merge: Có

**Vị trí:** [`refresh_validation.py:181–185`](../scripts/multisource/refresh_validation.py#L181), `current_updates`.

Với new completion có evidence độc lập, `verification_source` dùng URL official, nhưng `source_version` vẫn là hash CSV fixture và `verified_at` là retrieval time CSV. Probe đặt `reviewed_at` của evidence khác retrieval time: cả hash và timestamp ở row đều không khớp evidence. **Hash evidence vẫn có trong input manifest toàn snapshot**; finding không khẳng định evidence bị mất hoàn toàn.

**Ảnh hưởng:** tuple nguồn/version/thời gian completion sai, làm audit theo fixture/export gây hiểu nhầm, trái ý nghĩa `verified_at` đã mô tả.

**Đề nghị:** gắn completion với `independent["version"]` và `independent["verified_at"]`; giữ identity CSV provenance riêng. Test phải assert từng field, không chỉ assert hash tồn tại trong manifest. Bằng chứng: probe `INDEPENDENT_COMPLETION_PROVENANCE`.

### PM854-F04 — LOW / P3 — tự nó chặn merge: Không

**Vị trí:** [`refresh_validation.py:237–241`](../scripts/multisource/refresh_validation.py#L237).

Score `2-1-99` được parse thành ba số nhưng chỉ hai số đầu được dùng; prepare trả NO_CHANGE. Kết quả nguồn sai định dạng không bị từ chối; case này chưa làm đổi final score đã chọn. Đề nghị yêu cầu chính xác hai thành phần integer không âm, thêm malformed-score tests. Finding này nên sửa cùng validation archive, nhưng F01/F02/F03 đã đủ chặn merge.

## 17. AC-01 through AC-15 Status Table

Đường dẫn evidence viết ngắn dưới đây đều nằm trong ignored workspace mục 5; JSON chứa method, observed result, evidence location và limitations riêng cho từng AC.

| AC | Trạng thái | Phương pháp / quan sát mới | Evidence | Giới hạn |
|---|---|---|---|---|
| AC-01 | PASS | Local NO_CHANGE không API key | `runner-report.json` | Chưa có dữ liệu thật mới |
| AC-02 | PASS | Default offline, explicit opt-in mock | refresh test log, code | Không chạy live download |
| AC-03 | FAIL | Archive ID conflict/score malformed không bị chặn | adversarial results, F01/F04 | Normal current cases pass |
| AC-04 | FAIL | Structural/source conflict thành manual correction, approve rồi publish | adversarial/shot-scope, F01/F02 | Receipt checksum binding vẫn pass |
| AC-05 | FAIL | Immutable successor có thể chứa nguồn/identity chưa validate đúng | F01/F02 publication | Valid-path atomicity pass |
| AC-06 | FAIL | Wrong-fixture/wrong-source stats và completion provenance sai tuple | F01/F02/F03 | Evidence hash còn trong manifest |
| AC-07 | PASS | Actual-last-five, NULL, count và cutoff đúng | refresh log, negative-window | Không chứng minh input nguồn đúng |
| AC-08 | PASS | 107/77 hashes, LR/imputer/13 features/Phase 7 giữ nguyên | integrity results | Không retrain model thật |
| AC-09 | PASS | V3 111/111 delta 0, dynamic Case A/B pass | fresh runner, refresh log | Không đánh giá accuracy |
| AC-10 | PASS | Parent nguyên, failed callback cleanup, retry report failure đúng | refresh/adversarial logs | Source được chấp nhận sai thuộc F01/F02 |
| AC-11 | PASS | Full 264/264 và targeted hợp lệ 147/147 | full/targeted logs | Loader error ban đầu tách riêng; extra probes phát hiện lỗi |
| AC-12 | PASS | Rà đủ diff, source hashes, docs, không private data | scope/source audit | PASS cũ bị phản chứng bởi review mới |
| AC-13 | PASS | Current 380/20, IDs/kickoff, schedule tests/fallback | integrity results | Phạm vi catalogue 2026; UTC-date policy |
| AC-14 | PASS | Lặp effect/timestamp, ALREADY_PUBLISHED/NO_CHANGE | extra/refresh logs | Không xác nhận archive provider-ID validation |
| AC-15 | PASS | Read-only export schema/counts và DB hash đúng | integrity results | Cần sửa F03 trước khi tin provenance completion mới |

## 18. Known Limitations

- Chỉ một acquisition thật local; không real incremental publication hoặc live download mới. Đây là kiểm chứng tùy chọn chưa thực thi, không phải mandatory BLOCKED.
- Cutoff theo ngày; không intraday/as-of-vintage. UTC-date policy cần review nếu backend dùng ngày Tây Ban Nha.
- Legacy kickoff phụ thuộc exact local CSV; thiếu/sai hash phải null.
- Crash lock/partial `.writing` cần người vận hành xử lý; receipt là local audit JSON, chưa có chữ ký/authentication reviewer.
- Không chứng minh provider statistical equivalence, predictive accuracy hoặc redistribution rights.
- Không phát hiện secret trong diff không có nghĩa đã cấp quyền xuất bản raw dataset; dữ liệu thật, exports và receipt vẫn private.

Không còn mandatory verification area chưa kiểm tra; kết luận là **defects confirmed**, không dùng BLOCKED thay cho FAIL. Không sửa code/test, không overwrite validation cũ, không migrate production hoặc làm phase sau.

## 19. Merge Readiness Recommendation

Sửa F01/F02/F03 trong một nhiệm vụ implementation được giao riêng, bổ sung test trực tiếp cho những counterexample ở đây và chạy lại kiểm chứng độc lập. Sau đó mới cân nhắc PR và merge research integration; production approval vẫn là vấn đề riêng. Không nên merge branch hiện tại chỉ vì 264 test hiện có pass.

Publication chỉ gồm **hai file báo cáo pre-merge mới**, trên branch 8.5.4 hiện tại; không PR, không merge, không force-push. Tất cả **164 file tracked có sẵn** và 8 file snapshot cũ được hash trước/sau để bảo đảm không đổi. SHA commit báo cáo lấy bằng `git log -1 --format=%H -- docs/PHASE_8_5_4_PREMERGE_VERIFICATION.md`; không tự nhúng SHA của chính commit vào nội dung.

## 20. Reproduction Instructions

Checkout `f359d2c989700e92a4793dfd7701b7b4623599b2` để tái hiện implementation được kiểm chứng. Có dependency pins và private local V3/input hợp lệ trước khi chạy real-data portion. Dùng workspace và output mới, luôn redirect `--output` để không sửa validation cũ:

```powershell
.venv/Scripts/python.exe -m scripts.multisource.validate_refresh --workspace data/external/multisource/premerge854_recheck_unique --output data/external/multisource/premerge854_recheck_unique_report.json
```

Chạy targeted suite bằng Python snippet dưới, PowerShell here-string pipe vào `.venv/Scripts/python.exe -`; `tests/` trong sys.path cần cho helper import của inference:

```python
import os, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path.cwd() / "tests"))
modules = ["tests.test_multisource_refresh", "tests.test_composite_history",
           "tests.test_multisource", "tests.test_inference", "tests.test_model_export"]
cleared = {k: "" for k in os.environ
           if any(s in k.upper() for s in ("API_KEY", "API_TOKEN", "STRIKER"))}
with patch.dict(os.environ, cleared), patch("socket.socket.connect",
        side_effect=AssertionError("Offline verification")):
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames(modules))
raise SystemExit(0 if result.wasSuccessful() else 1)
```

Snippet F01 tái hiện sai join chỉ dùng generator của tests và tự cleanup tempdir. Để kiểm tra F02, thêm provider/competition/season/understat_id sai vào shot DataFrame trước `t.prepare`. F03: tạo completed mới trong current generated CSV, thêm independent evidence với reviewed_at khác retrieved_at, rồi assert row source_version/verified_at so với evidence. F04: `t.alter("archive_2025_fixtures.csv", "score", "2-1-99")`; prepare hiện trả NO_CHANGE.

Log chi tiết và payload riêng tư không được commit. JSON báo cáo chỉ lưu aggregate, code checksums và kết quả counterexample tổng hợp; không raw match records hoặc private approval receipts.
