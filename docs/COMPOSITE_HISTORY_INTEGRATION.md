# Phase 8.5.3 — Verified Match Registry và Composite History

Ngày: **22/11/2026, Asia/Saigon**. Nhánh: `phase8.5.3-composite-history-integration`.
Base sau fetch: `2ae0f8920ca0435b8c32c1b4763bc30ec370ba5b` từ `phase8.5.2-multisource-dataset`.

**Hoàn tất tích hợp ở mức nghiên cứu; không phê duyệt production.** Không gọi StrikerAPI, không tải lại dataset, không train/refit, không thay production History Store hoặc code Phase 8.

## 1. Kết quả đã chạy

| Hạng mục | Kết quả |
|---|---:|
| Fixture trong Registry, bao gồm lịch chưa xác minh hoàn tất | 3.040 |
| Verified completed | 2.783 |
| Completed đủ thống kê | 2.779 |
| Completed đang pending thống kê | 4 |
| Fixture chưa xác minh completed | 257 |
| Xung đột chưa giải quyết trong snapshot này | 0 |
| Target 2026–27 được kiểm tra | 123 |
| Dựng đủ 13 feature và predict thành công | 123 fixture / 246 dự đoán |
| Fixture từng bị chặn nay mở được | 12/12 |
| Parity với fixture thành công ở Phase 8.5.2 | 111/111 |
| Max absolute feature / raw prediction difference | 0.0 / 0.0 |
| Test toàn repository | 208 pass, 0 fail/error/skip |

3.040 dòng Registry không có nghĩa 3.040 trận đã chơi. Các lịch scheduled/LIVE/postponed không được đưa vào số completed. Nguồn current cũ chỉ ghi `unplayed` cho các fixture chưa có kết quả; không suy diễn từ ngày rằng chúng đã hoàn tất hoặc đoán fixture nào đang LIVE từ một số tổng hợp. State machine hỗ trợ LIVE riêng khi có observation xác định.

## 2. Kiến trúc và phạm vi tái sử dụng

```text
Phase 8.5.2 raw files + staging + official completion evidence
                    ↓ checksum / identity / score / provenance checks
Verified Match Registry + reviewed season catalogues
                    ↓ build temporary SQLite / validate / parity
Immutable Composite History version, opened read-only
                    ↓ registry coverage and continuous stint
All verified completed fixtures → true matches_seen
                    ↓ actual last five, not last five complete rows
Required-window completeness gate
                    ↓ Phase 8.5.2 rolling implementation
13 frozen features → existing trusted artifact loader → frozen LR
```

Các module mới nằm trong `scripts/multisource/`:

| Module | Trách nhiệm |
|---|---|
| `team_registry.py` | Alias đã review, stable IDs, nguồn xác nhận các đội mới |
| `match_registry.py` | Completion observations, identity/score conflicts, complete/pending statistics, calendar evidence |
| `composite_history.py` | SQLite versions, manifests, source revisions, immutable publication, read-only queries, coverage |
| `composite_features.py` | Option B và kiểm tra cửa sổ; tái sử dụng rolling/stint/config hiện có |
| `composite_inference.py` | Research CLI/API, trusted LR loader, provenance, cấm production mode |
| `build_composite.py` | Nhập snapshot cũ, dựng Registry/version, parity và đánh giá lại 12 fixture |

Không subclass hoặc sửa `HistoryStore`, không nới single-provider policy. `FixturePredictor` production vẫn từ chối CompositeHistory qua kiểm tra kiểu. Adapter mới dùng logical provider `laliga_composite_v1` nhưng giữ riêng provider thật cho từng nhóm thống kê.

## 3. Registry: completion tách biệt statistical completeness

Mỗi fixture có một canonical key giữ nguyên namespace của staging: `research:laliga:<season>:<canonical_home>:<canonical_away>`. Ngày không nằm trong key để thay đổi ngày của cùng pairing trở thành một conflict/revision cần review, thay vì tạo fixture thứ hai. Phạm vi là La Liga hai lượt; identity vẫn được kiểm tra cùng season/date/home/away khi nhập và dự đoán.

Registry lưu đầy đủ key, season, ngày, đội home/away, observed status, match status, statistics status, final score, verification source, source version, verified-at và evidence payload. `verified_at` là thời điểm kiểm tra evidence, không giả làm thời điểm thống kê đã có trước trận.

| Evidence/trạng thái | `match_status` | `statistics_status` |
|---|---|---|
| Có chứng cứ hoàn tất, final score và identity hợp lệ, đủ stats | VERIFIED_COMPLETED | COMPLETE_STATISTICS |
| Có chứng cứ hoàn tất, thiếu xG hoặc SH/SOT | VERIFIED_COMPLETED | PENDING_UPDATE |
| Scheduled/LIVE/postponed hoặc completion chưa có evidence | UNVERIFIED | UNVERIFIED |
| Mâu thuẫn identity/ngày/final score | SOURCE_CONFLICT | SOURCE_CONFLICT |
| Identity/score đã biết nhưng candidate statistics chưa thống nhất | VERIFIED_COMPLETED | SOURCE_CONFLICT |

Observation trùng trong cùng source version bị từ chối. Hai nguồn có score khác nhau được giữ evidence và conflict; không chọn theo thứ tự đến. Statistics candidate khác số cũng được giữ conflict; candidate giống số không tự thay provenance đã chọn. Khác model xG đã được review trong Phase 8.5.2 được giữ semantics và quy tắc nguồn của staging, không coi mọi giá trị Understat khác FBref là lỗi.

Bốn fixture pending có records chứa **NULL thật**. Trận archive thiếu xG giữ goals và shots đã biết; ba trận mới có final score từ evidence La Liga nhưng xG/SH/SOT vẫn NULL. Không điền zero, median hoặc dự đoán model vào dữ liệu completed.

## 4. Coverage được xác minh trong phạm vi nào?

Coverage không suy ra chỉ từ số dòng. Build kiểm tra checksum nguồn, scope giải/mùa, roster canonical, đúng toàn bộ directed home/away pairings, uniqueness, ngày, các completion observations và score consistency. Snapshot FBref được giữ làm nguồn đã chọn trước 01/10/2025; archive overlap trước đó đã được đối chiếu ở Phase 8.5.2. Ba completion mới được nhập từ evidence độc lập đã lưu local, không tải thêm API.

Mỗi season catalogue giữ roster, verification source/version, reviewed-at và `verified_before_by_team`. Với từng đội, ngày đầu tiên có fixture chưa xác minh completed hoặc identity conflict giới hạn cutoff được phép. Ví dụ chưa biết trạng thái một fixture ngày 21/11 thì cutoff ngày 21/11 còn hợp lệ theo chính sách strict-before; cutoff sau ngày đó không được mặc định bỏ qua fixture ấy.

Đối với mỗi request, reader xác minh các season catalogue liên quan và roster để xác định stint. Mùa liên tiếp tiếp tục lịch sử; vắng một mùa tạo gap và reset. Nếu không có roster/calendar evidence hoặc không xác định được toàn bộ completed trước cutoff, trả `REGISTRY_COVERAGE_UNVERIFIED`.

Zero-history chỉ được phép khi membership và calendar chứng minh không có trận hợp lệ trong stint trước cutoff. Năm 2019 là giới hạn lịch sử nghiên cứu theo frozen snapshot, không phải tuyên bố đội chưa từng chơi trước năm đó. Đội mới/mùa trở lại có bằng chứng từ roster các mùa; không đồng nhất “không tìm thấy stats” với “được phép zero-history”.

Đây là **coverage của catalogue nguồn đã review**, không phải xác nhận độc lập toàn bộ lịch sử bằng một feed thứ hai, không phải dữ liệu as-of-vintage, và không phải production coverage/freshness SLA. Không tuyên bố snapshot đã đầy đủ mọi trận đến hết ngày 22/11.

## 5. Option B và 13 feature không thay đổi

Quy trình cho từng đội:

1. Xác minh fixture identity, cutoff `<= fixture_date` và registry coverage.
2. Lấy mọi VERIFIED_COMPLETED với `date < cutoff`, loại current key và season tương lai.
3. Gọi `stint_history` hiện có để chọn continuous stint và chặn thứ tự cùng ngày không xác định.
4. `matches_seen = len(eligible_registry_records)`; `short_history` giữ ngưỡng config cũ.
5. Chọn đúng tối đa 5 trận cuối từ Registry, rồi yêu cầu COMPLETE_STATISTICS ở toàn bộ cửa sổ.
6. Gọi lại `scripts.multisource.features.build_features` trên các window đã kiểm tra để tính rolling và assembly. Khôi phục bốn count/short-history field của home/opponent bằng số đếm Registry đầy đủ.

Không thay công thức rolling, cấu hình, feature order hoặc định nghĩa. Không tự tính một bộ Feature Engineering mới. Trường hợp toàn bộ history đầy đủ được test parity trực tiếp với Phase 8 Feature Builder, ngoài parity thực tế với Phase 8.5.2.

```text
is_home, matches_seen, short_history, xg_avg5, xga_avg5,
gf_avg5, ga_avg5, shot_avg5, sot_avg5, opponent_xg_avg5,
opponent_xga_avg5, opponent_matches_seen, opponent_short_history
```

Missing/conflicting statistics nằm **ngoài** cửa sổ có thể chấp nhận nếu completion/coverage vẫn đáng tin. Missing statistics **trong** cửa sổ trả `MISSING_ROLLING_STATISTICS`; không lấy trận thứ 6/7 thay thế. History 1–4 trận phải đủ thống kê ở toàn bộ các trận đó. NaN chỉ được giữ đúng pattern zero-history của fitted imputer cũ.

## 6. Đánh giá lại 12 fixture Villarreal

Fixture pending archive nằm ở vị trí **260** trong stint Villarreal. Không tạo xG cho trận này. Tại 12 cutoff theo thứ tự thời gian:

| Case | `matches_seen` | Vị trí trận thiếu tính từ gần nhất | Rolling đầy đủ | Kết quả |
|---|---:|---:|---|---|
| 1 | 266 | 7 | 5/5 | Mở được |
| 2 | 267 | 8 | 5/5 | Mở được |
| 3 | 268 | 9 | 5/5 | Mở được |
| 4 | 269 | 10 | 5/5 | Mở được |
| 5 | 270 | 11 | 5/5 | Mở được |
| 6 | 271 | 12 | 5/5 | Mở được |
| 7 | 272 | 13 | 5/5 | Mở được |
| 8 | 273 | 14 | 5/5 | Mở được |
| 9 | 274 | 15 | 5/5 | Mở được |
| 10 | 275 | 16 | 5/5 | Mở được |
| 11 | 276 | 17 | 5/5 | Mở được |
| 12 | 277 | 18 | 5/5 | Mở được |

Kết quả **12/12** đến từ vị trí thực tế ngoài cửa sổ, không phải bỏ cổng kiểm tra. Canonical keys, từng target/cutoff, window keys và nguồn nằm trong report local `reevaluated_12.json` cùng `inference_records.json` và SQLite. Bảng public chỉ công bố các count/vị trí dẫn xuất.

Kiểm tra thêm trên fixture lịch sử Villarreal–Celta Vigo ngày 26/04/2026 vẫn trả `MISSING_ROLLING_STATISTICS`: tại cutoff đó trận thiếu còn nằm trong actual last five. Các trận pending mới cũng không bị coi như chưa từng diễn ra; nếu đi vào cửa sổ của target sau này, chúng chặn inference.

## 7. SQLite, version và rollback

Version cuối local:

```text
data/history/research/phase853_v3_20261122/
  laliga_composite.sqlite3
  manifest.json
```

Hai version thử `phase853_v1_20261122` và `phase853_v2_20261122` được giữ nguyên. V3 có cùng business data, không có source correction: **0 added / 0 modified / 0 removed** so với parent V2. V2 bổ sung validation/parity gate trước publication; V3 bổ sung SQL authorizer để chặn cả ATTACH/VACUUM ngoài database. Các test refresh dùng synthetic data để kiểm chứng pending → complete và revised statistics; không tạo số liệu giả trong database thực tế.

Schema version 1 gồm `registry`, `statistics`, `evidence`, `catalogues`, `conflicts`, `revisions`, `metadata`. Raw statistical pair và provenance lưu JSON trong bảng statistics; key/team có uniqueness và FK về Registry. Manifest core được nhúng trong SQLite và so với sidecar. Sidecar lưu database SHA-256; reader mở `mode=ro&immutable=1`, kiểm hash trước inference. Query authorizer chỉ cho phép đọc, không cho ATTACH/VACUUM tạo file khác hoặc ghi dữ liệu.

Manifest chứa version/build time, input hashes, source dataset versions, counts complete/pending/conflicts, coverage theo season/team, git code revision, working code hashes, schema version, parent/revision counts, validation status và `production_approved=false`.

Build dùng writer lock, thư mục tạm, xác minh completeness/provenance lại từ giá trị thật, SQLite integrity/FK checks, sau đó chạy callback parity/inference. Chỉ khi thành công mới rename thư mục tạm sang version chưa tồn tại. Thất bại xóa đúng thư mục tạm của build, nhả lock và giữ nguyên version cũ. Không overwrite version đang dùng, không có phương thức cập nhật DB tại chỗ. Không ghi vào `data/history/laliga_history.sqlite3`.

Manifest ghi code revision lúc dựng là commit base `2ae0f89` và hash từng module mới; hash module đã được kiểm tra khớp với source bàn giao. Đây là build trước commit publication, không giả mạo rằng database đã được dựng từ một commit chưa tồn tại.

## 8. Team identities mới

[Danh sách đội La Liga 2026–27](https://www.laliga.com/en-GB/laliga-easports/clubs) đã được đối chiếu với roster current CSV. Các trang đội chính thức xác nhận [Málaga CF](https://www.laliga.com/en-GB/clubs/malaga-cf/squad), [R. Racing Club](https://www.laliga.com/en-GB/clubs/r-racing-club/squad) và [RC Deportivo](https://www.laliga.com/en-GB/clubs/rc-deportivo/squad).

| Alias nguồn/chính thức | Canonical nghiên cứu | Stable ID |
|---|---|---|
| Málaga / Málaga CF | Malaga | malaga |
| Racing Santander / R. Racing Club | Racing Santander | racing-santander |
| Deportivo A Coruña / RC Deportivo | Deportivo La Coruna | deportivo-la-coruna |

Mapping tường minh, không fuzzy. ID của các đội trong frozen snapshot dùng lại `TEAM_IDS` gốc. Production common.py và team registry không đổi.

## 9. Research inference và provenance

```powershell
.venv\Scripts\python.exe -m scripts.multisource.composite_inference `
  --database data/history/research/phase853_v3_20261122/laliga_composite.sqlite3 `
  --home "Racing Santander" --away "Villarreal" --date 2026-08-16 --season 2026
```

CLI đã chạy thành công. API trả `RESEARCH_INFERENCE`, `total_team_match_xg`, xG home/away, raw/clipped predictions, 13 feature, cutoff, Registry count/window audit, composite version, artifact hash, source provenance và research data-quality status. `PRODUCTION_UPCOMING` bị từ chối bằng `PRODUCTION_NOT_APPROVED`.

Mỗi rolling record giữ `fixture_source,xg_source,shots_source,source_dataset_version,fetched_at,statistical_semantics`. Ba nhóm nguồn thống kê chính vẫn là FBref snapshot, Understat và Sportmonks. Pending source được ghi rõ flagged/unavailable, không mạo nhận có xG. Timestamp fetch gốc của FBref chưa biết vẫn ghi unknown theo Phase 8.5.2; không bịa timestamp provider.

Trusted artifact loader cũ xác nhận LR, fitted imputer, environment, metadata, 13 feature và checksum. Model output không được ghi lại vào statistics. Clipping giữ nguyên `max(0,raw)`. Mọi dự đoán của 111 fixture tham chiếu và từng feature đều khớp với snapshot cũ ở tolerance `1e-12`, thực tế delta **0.0**.

Artifact SHA-256 giữ nguyên:

```text
0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69
```

## 10. Reproducibility và file local

Không download lại: đã kiểm tra đủ local raw/staging của Phase 8.5.2 và checksum acquisition. Build từ cùng snapshot bằng version ID mới:

```powershell
.venv\Scripts\python.exe -m scripts.multisource.build_composite --version my_research_version
# Tạo successor từ input snapshot đã được review/cập nhật riêng:
# thêm --parent data/history/research/<old_version>/laliga_composite.sqlite3
```

Không tự động đổi active version. Phải review nguồn/corrections trước khi chọn successor. Missing input trả `MISSING_INPUT_FILES` kèm danh sách, không âm thầm tái gọi API. Generic builder còn kiểm source hashes, scope và baseline 2.779 complete fixture; thay đổi baseline ở tương lai cần review riêng.

Các report riêng ở `data/external/multisource/phase853/phase853_v3_20261122/`: `summary.json`, `prediction_parity.csv`, `reevaluated_12.json`, `inference_records.json`, `features.csv`, `predictions.csv`, `coverage_by_team.csv`, `missing_history.csv`, `source_provenance_manifest.json`. Raw provider records, SQLite, manifests chi tiết, predictions và log đều Git-ignore. Không công bố third-party datasets khi chưa xác minh redistribution rights.

## 11. Kiểm thử, integrity và giới hạn

Đã chạy **37 test mới** về completion states, pending xG/SH/SOT, LIVE/scheduled/postponed, duplicate/conflict, coverage, true rolling window, matches_seen, short/zero history, stint continuity/gap, cùng ngày, temporal leakage, provenance, immutable versions, revisions, failed-build/parity rollback, corruption, path protection, SQL read-only authorizer, frozen model/imputer và production gates.

Full suite **208/208 pass**, 0 failures/errors/skipped, với socket/DNS bị chặn và API key bị bỏ khỏi environment; thời gian chạy chính xác được lưu trong validation JSON. Không phụ thuộc raw third-party local khi chạy unit/integration tests synthetic. Test thực tế trên snapshot và CLI được chạy riêng như kết quả ở trên.

**139 file tracked có sẵn giữ nguyên byte**, bao gồm Phase 1–8, model/metadata, production SQLite, preprocessing, toàn bộ Phase 8.5.2 code/reports. Hai nhánh StrikerAPI và nhánh multisource base giữ nguyên SHA. Không nới production gate nào.

Giới hạn còn lại: 4 pending vẫn chưa được sửa; các trạng thái nguồn mới ngoài snapshot chưa được cập nhật; coverage chỉ theo catalogue đã review; source revisions không bảo đảm as-of-vintage; xG khác model và SH/SOT penalty semantics vẫn là rủi ro tương thích. Không suy ra predictive accuracy từ parity hoặc inference thành công.

Phase 8.5.4 nên ưu tiên verified refresh để giải quyết pending/freshness, review provider semantics/quyền sử dụng và chính sách vận hành, rồi đánh giá predictive performance theo protocol riêng. Scheduler, website deployment, retraining và production migration không được thực hiện trong phase này.
