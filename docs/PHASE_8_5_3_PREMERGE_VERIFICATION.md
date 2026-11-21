# Pre-Merge Verification — Phase 8.5.2 và Phase 8.5.3

**Kết luận: PASS — Research Merge Ready.** Nhánh đủ điều kiện đề nghị merge ở mức tích hợp nghiên cứu. Kết luận này không phê duyệt production, deployment hoặc chất lượng dự đoán trên nguồn xG mới.

Xác minh mới được thực hiện ngày **22/11/2026, 04:58:21–05:04:44, UTC+07:00**; tương ứng 21/11/2026, 21:58:21–22:04:44 UTC. Báo cáo này đánh giá implementation commit `68234d5c481009d077bf607fe579a0d54845cb2e`, trước commit chỉ chứa báo cáo pre-merge. Không sửa implementation, không merge hoặc tạo Pull Request.

## 1. Git preflight và ancestry — PASS

Đã `git fetch origin`, kiểm tra working tree sạch và đọc SHA remote thực tế. Các giá trị vẫn khớp reference của lần review trước:

| Ref đã xác minh | SHA |
|---|---|
| `origin/main` | `84f14fd0638661c44933f917ce69effe518252ff` |
| `origin/phase8.5.2-multisource-dataset` | `2ae0f8920ca0435b8c32c1b4763bc30ec370ba5b` |
| `origin/phase8.5.3-composite-history-integration` và HEAD | `68234d5c481009d077bf607fe579a0d54845cb2e` |

`merge-base(main, phase853)` bằng đúng SHA main; `merge-base(phase852, phase853)` bằng đúng SHA phase852. Nhánh chứa hai commit nghiên cứu sau main: `2ae0f89` rồi `68234d5`. Hai nhánh StrikerAPI chưa merge không phải ancestor của implementation được kiểm tra; không cherry-pick/merge chúng trong lượt xác minh.

Diff `origin/main...68234d5`: **21 file thêm, 0 sửa, 0 xóa; 3.525 dòng thêm**. Toàn bộ 129 file trong tree main giữ nguyên Git blob. Phạm vi:

| Nhóm | File thêm |
|---|---:|
| `scripts/multisource/` | 11 |
| `tests/test_multisource.py`, `tests/test_composite_history.py` | 2 |
| `docs/` | 4 |
| `Phases/` | 2 |
| Ignore rules riêng ở `data/external/`, `data/history/` | 2 |

Đã lưu toàn bộ patch local và rà soát các file được đưa vào main. Không có chỉnh sửa ngoài phạm vi, unexpected binary, production module hoặc frozen artifact. `git diff --check` không báo lỗi. Hai file báo cáo pre-merge bổ sung sau review được kiểm tra riêng trước publication.

## 2. Full suite chạy lại — PASS

Sử dụng `.venv` hiện có, **Python 3.14.0**. Đối chiếu 10 dependency pins từ requirements và trusted model loader; không cài đặt, nâng cấp hoặc đổi dependency.

Lệnh thực tế:

```powershell
.venv\Scripts\python.exe data/external/multisource/premerge_20261121T215821Z/run_full_suite.py
```

Wrapper chỉ phục vụ xác minh local: chạy `unittest.defaultTestLoader.discover(<repo>/tests)` và `TextTestRunner(verbosity=2)`, chặn socket/DNS, bỏ API key khỏi environment của tiến trình. Các test client cũ chỉ dùng credential/session giả lập. Không gọi API thật.

**Kết quả mới: 208 test chạy, 208 pass, 0 failures, 0 errors, 0 skipped; 71.966 giây gồm discovery/load.** Không sao chép kết quả cũ.

| Nhóm test | Số test |
|---|---:|
| Composite History / Registry / Option B | 37 |
| Multi-source mapping / coverage / feature feasibility | 21 |
| Evaluation | 13 |
| Final Test | 18 |
| History Store | 14 |
| Phase 8 inference | 23 |
| Model export | 10 |
| StrikerAPI client, compatibility, normalization — mock/offline | 41 |
| Training / tuning | 31 |
| **Tổng** | **208** |

Các test training/tuning sẵn có chạy trong phạm vi kiểm thử; không thay hoặc refit frozen artifact được bàn giao. Log và JSON fresh results nằm trong thư mục verification đã Git-ignore.

## 3. Frozen artifacts — PASS

Đã hash file thực tế, kiểm tra trusted loader, đối chiếu Git blob với main và cả hai protected-file manifests:

- `outputs/inference/protected_files.json`: **77/77** khớp.
- `outputs/provider_poc/reports/protected_files.json`: **107/107** khớp. Hai danh sách có phần trùng, không cộng thành số file độc lập.

| File | SHA-256 thực tế |
|---|---|
| `models/laliga_lr_pipeline.joblib` | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| `models/model_metadata.json` | `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c` |
| `data/matches_laliga.csv` | `3cfeb29ea2e76d6a8a411f31af6182c6951fd477903b8b6d0401b58e10b415e2` |
| `data/laliga_processed_normalized.csv` | `90000ce22f42abe5eb5b5bfa38ad1ed5ef7b1c1c75cd4d39e749e7b324e0e5ca` |
| `data/history/laliga_history.sqlite3` | `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982` |

Model SHA khớp giá trị frozen đã ghi nhận. Coefficients/intercept và fitted imputer statistics khớp chính xác metadata; imputer vẫn fit trên **3.800 dòng**. Tên/thứ tự 13 feature, preprocessing, Phase 7 artifacts, Phase 8 Feature Builder và production History Store không đổi. Các thông số fitted cũng giữ nguyên sau inference kiểm tra mới.

Cuối xác minh, **150 file tracked có sẵn** giữ nguyên byte so với baseline đầu lượt. Cả 6 file SQLite/manifest của V1/V2/V3 có sẵn cũng giữ nguyên hash.

## 4. Security và phạm vi công bố dữ liệu — PASS

Đã quét nội dung 21 file được giới thiệu: giá trị credential local được đối chiếu trong bộ nhớ, mẫu token/private key/credential URL, file nhị phân và phần mở rộng dữ liệu nhạy cảm. Không in giá trị secret. **0 phát hiện** trong phạm vi này.

Không có raw third-party CSV, SQLite nghiên cứu, `.env`, private logs hoặc prediction records trong diff. Hai JSON manifest public chỉ chứa metadata, hashes và aggregates. Dataset/report được nhận diện theo vai trò, không kết luận an toàn chỉ dựa vào phần mở rộng.

Đã xác minh Git-ignore và trạng thái untracked cho `.env`, raw/staging, SQLite research, detailed inference records. Không có production code hoặc frozen binary được sửa.

PASS ở đây là an toàn của **phạm vi publication đang review**. Không xác nhận giấy phép tái phân phối raw data hoặc sử dụng thương mại; các quyền đó vẫn chưa được cấp bởi việc merge. Không tải lại Football-Data hoặc nguồn khác, không dùng paid API.

## 5. Input snapshot và rebuild — PASS

Đã xác minh acquisition manifest, 9 raw CSV và 4 cached HTML, staging CSV, historical coverage, expected completed catalogue và independent completion evidence.

- **13/13 acquisition files** khớp SHA manifest.
- **17/17 input hashes** khớp core manifest V3, gồm raw/staging/reference feature/prediction/evidence và normalized source.
- **160 dòng coverage season/team** khớp ngữ nghĩa với Registry dựng lại.
- **5.566 perspective identities** trong expected completed catalogue khớp Registry; không chỉ so số dòng.
- Không thiếu essential input, không tải lại dữ liệu, không sửa input snapshot.

Lệnh thực tế để rebuild:

```powershell
.venv\Scripts\python.exe data/external/multisource/premerge_20261121T215821Z/rebuild_offline.py
```

Wrapper chặn network và gọi module hiện có với các tham số tương đương:

```powershell
.venv\Scripts\python.exe -m scripts.multisource.build_composite `
  --version premerge_20261121T215821Z `
  --parent data/history/research/phase853_v3_20261122/laliga_composite.sqlite3
```

Database xác minh mới: `data/history/research/premerge_20261121T215821Z/laliga_composite.sqlite3`. Không overwrite V3 hoặc version cũ. Rebuild hoàn tất trong **42.710 giây**, gồm validation và parity callback.

Kiểm tra độc lập bằng connection SQLite read-only: `PRAGMA integrity_check = ok`, `foreign_key_check = []`. So sánh toàn bộ business Registry payload (bỏ timestamp review hợp lệ), canonical statistics, catalogues, team coverage, source versions và input hashes với V3 đều bằng nhau. Source revision delta: **0 added / 0 modified / 0 removed**.

Database bytes có hash khác nhau như dự kiến:

| Database | SHA-256 |
|---|---|
| V3 gốc | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| Bản rebuild xác minh | `93309da5adf561302f3f8686e555d92a25b7c3771dc77b46498cf5fd396d90d6` |

Khác version ID, build timestamp và manifest metadata không được coi là sai business data. Không ép hai checksum database phải bằng nhau.

## 6. Counts quan sát từ Registry mới

| Chỉ tiêu | Thực tế | So với reference |
|---|---:|---|
| Registry fixtures | 3.040 | Khớp |
| VERIFIED_COMPLETED | 2.783 | Khớp |
| COMPLETE_STATISTICS | 2.779 | Khớp |
| PENDING_UPDATE | 4 | Khớp |
| UNVERIFIED completion | 257 | Khớp |
| Unresolved conflicts | 0 | Khớp |

Counts được kiểm tra cả từ table/payload thực tế, không chỉ đọc summary. Statistics table có 5.566 perspective records, trong đó 8 records của 4 pending vẫn giữ NULL ở trường chưa biết. Fixture UNVERIFIED không có completed statistics bị gán thêm.

## 7. Feature, frozen LR và parity — PASS

Trên database rebuild:

- **123/123 target** dựng đúng 13 feature và predict thành công, **246 team predictions**.
- **12/12 fixture trước đây bị chặn** vẫn mở được theo Option B.
- Parity với Phase 8.5.2: **111/111**, max feature/raw prediction difference **0.0** tại tolerance `1e-12`.
- So sánh toàn bộ 123 fixture với output V3: max feature/raw prediction difference **0.0**.

Đã kiểm tra độc lập **246 cửa sổ đội–target**: tái chọn continuous stint từ completed Registry trước cutoff, đối chiếu toàn bộ eligible keys và `matches_seen`, lấy đúng actual last five, rồi tính lại sáu trung bình và các opponent/count fields. Cả 13 feature khớp, max difference **0.0**. Không sử dụng outcomes current/future fixture.

Negative control bằng dữ liệu thực: Villarreal–Celta Vigo ngày 26/04/2026 bị chặn `MISSING_ROLLING_STATISTICS` vì pending còn trong cửa sổ. Không lấy complete fixture thứ 6/7 thay thế, không dùng model output điền xG thiếu. Unit suite kiểm tra thêm missing ngoài window, short/zero history, season gaps, cùng ngày, coverage chưa xác minh và leakage.

## 8. Production isolation — PASS

- `PRODUCTION_UPCOMING` bị từ chối với `PRODUCTION_NOT_APPROVED`.
- `FixturePredictor` cũ từ chối CompositeHistory với `INVALID_HISTORY`.
- Default provider policy không tự thêm composite provider; production approval vẫn false.
- DELETE và ATTACH qua research query interface bị từ chối; không tạo database ngoài và không thay hash database.
- Schedule/freshness/provider gates, trusted model loader và toàn bộ production code có cùng Git blob với main; test Phase 8 tiếp tục pass.
- Không thay production SQLite, không deploy, không retrain hoặc refit frozen imputer.

## 9. Giới hạn còn lại và khuyến nghị

Không có blocker pre-merge được tìm thấy trong các kiểm tra bắt buộc đã thực hiện. Bốn pending, độ mới dữ liệu ngoài snapshot, xG/SH/SOT semantics khác nguồn, as-of-vintage và quyền sử dụng production vẫn là giới hạn đã biết. Predictive accuracy trên nguồn mới chưa được chứng minh. Các cổng snapshot-specific của builder không được coi là một refresh workflow tổng quát.

**Đề nghị người dùng tạo Pull Request từ `phase8.5.3-composite-history-integration` vào `main` để review và merge ở mức nghiên cứu.** Không cần merge Phase 8.5.2 riêng vì nó đã là ancestor. Không tự tạo PR hoặc merge trong lượt này; không bắt đầu Phase 8.5.4.

## 10. Evidence và ranh giới thay đổi

Evidence local nằm ở `data/external/multisource/premerge_20261121T215821Z/`: baseline/diff, fresh full-suite log, rebuild log, input/artifact/security checks, independent business/parity/window checks và completion checks. Detailed rebuild outputs nằm dưới `data/external/multisource/phase853/premerge_20261121T215821Z/`. Tất cả đều ignored; không đưa raw records vào báo cáo public.

Trong lượt này chỉ thêm hai báo cáo pre-merge vào Git. Các verification wrappers/logs và database mới chỉ là evidence local, không phải feature hoặc source change được merge. Xem [JSON evidence summary](PHASE_8_5_3_PREMERGE_VERIFICATION.json) để đọc kết quả có cấu trúc.
