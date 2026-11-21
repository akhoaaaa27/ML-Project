# Phase 8.5.2 — Multi-source La Liga Dataset Audit

Ngày nghiên cứu: **22/11/2026, Asia/Saigon**. Kết luận: **CONDITIONAL GO cho nghiên cứu**, chưa phê duyệt production hoặc xác nhận độ chính xác trên nguồn mới.

## 1. Kết quả thực tế

- Đã tải **9 CSV**, gồm 7 file fixture Understat qua xGTables (2019–2025), file 9.500 shot mùa 2025–26 và fixture Sportmonks qua xGTables mùa 2026–27. Không cần tài khoản hay request tính phí.
- Staging riêng có **2.779 trận / 5.558 dòng đội–trận**: giữ 2.350 trận FBref; thêm **309 trận 2025–26 và 120 trận 2026–27**. Không sửa dataset/history production.
- Thiếu **ít nhất 4 trận đã biết hoàn tất**: 1 trận 2025–26 có xG bị nguồn gắn cờ unreliable; 3 trận ngày 21/11/2026 được La Liga xác nhận kết thúc nhưng CSV chưa có xG/SH/SOT. Một fixture khác đang LIVE ở lần đối chiếu chưa được coi là completed.
- Dựng đúng 13 feature và tạo **222 dự đoán cho 111/123 fixture 2026–27 được xem xét**. 12 fixture bị chặn vì thiếu lịch sử Villarreal. Các dự đoán chỉ chứng minh chạy được mô hình frozen; không phải đánh giá predictive accuracy.

Tất cả coverage là theo snapshot và bằng chứng đã đọc, không phải khẳng định đã tìm thấy mọi trận hoàn tất đến hết ngày 22/11. Sự khác nhau giữa “đủ trường trong CSV” và “đã đầy đủ lịch sử thực tế” được giữ rõ xuyên suốt báo cáo.

## 2. Git và bảo toàn nghiên cứu cũ

Nhánh mới `phase8.5.2-multisource-dataset` được tạo trực tiếp từ `origin/main` sau fetch:

```text
base / merge-base: 84f14fd0638661c44933f917ce69effe518252ff
```

Workspace sạch lúc bắt đầu. Không merge/cherry-pick hai nhánh chưa merge, không reset, discard, force-push hoặc xóa nhánh. Hai ref được giữ nguyên:

| Nhánh nghiên cứu cũ | SHA |
|---|---|
| `phase8.5.1-strikerapi-live-audit` | `ee83689d117620b5085c389ce3266ed2a92cca77` |
| `phase8.5.2-semantic-audit` | `425c7736a83e29bac5d313ba1ae7f8f22c6b2e2b` |

Baseline ghi hash 129 file tracked trên main trước thay đổi. Cả 129 file giữ nguyên byte, bao gồm `.gitignore` gốc. Rule ignore mới nằm riêng trong `data/external/.gitignore`.

## 3. Nhu cầu raw và contract production

Đã đọc CSV gốc, preprocessing, normalized data, `prepare_training_features.py`, Feature Builder, History Store, importer, predictor, metadata và loader artifact.

Đầu vào lịch sử tối thiểu: `season,date,team,opponent,is_home,gf,ga,xg,xga,sh,sot`. Đây là raw outcomes của **các trận trước fixture**, không yêu cầu nguồn có sẵn 13 feature. XGA và GA là XG/GF phía đối thủ trong cùng fixture. Preprocessing và Feature Builder dùng trung bình tối đa 5 trận đã qua, tiếp nối stint ở các mùa liên tiếp; gián đoạn trên một mùa reset stint.

13 feature và thứ tự không đổi:

```text
is_home, matches_seen, short_history, xg_avg5, xga_avg5,
gf_avg5, ga_avg5, shot_avg5, sot_avg5, opponent_xg_avg5,
opponent_xga_avg5, opponent_matches_seen, opponent_short_history
```

History Store production còn yêu cầu provider thống nhất, provider match ID, status, timestamp/version, quality và policy; predictor upcoming kiểm tra schedule, coverage, freshness. Staging nghiên cứu không được gắn nhãn `quality_status=verified` để vượt các cổng đó. Không gọi importer hoặc ghi vào SQLite production.

## 4. Nguồn đã điều tra và giới hạn quyền sử dụng

| Nguồn | Thực hiện | Kết quả |
|---|---|---|
| [xGTables downloads](https://www.xgtables.io/data/) | Đọc HTML, theo đúng link CSV được công bố | Download thành công; trang hướng dẫn dùng CSV cho truy cập tự động |
| [Understat archive downloads](https://www.xgtables.io/understat-data/) | Đọc schema và tải CSV fixture/shot | Understat là nguồn gốc lịch sử; khác model mùa hiện tại |
| [La Liga 2026–27](https://www.xgtables.io/data/la-liga/2026/) | Tải fixture CSV thực tế | Có đủ goals/xG/SH/SOT ở 120 dòng full_time |
| [xGTables sources](https://www.xgtables.io/sources/) | Đọc attribution và quyền nguồn | xG hiện tại Sportmonks; historical Understat. Không suy ra quyền tái phân phối bulk từ việc tải được |
| [Football-Data Spain](https://football-data.co.uk/spainm.php) | Đọc trang giới thiệu qua link chính thức; lần đầu www trả 429 | Không tải CSV; xem hạn chế bên dưới |
| [Football-Data usage](https://football-data.co.uk/data.php) | Đọc điều kiện hiện tại | Nêu chỉ dành cá nhân, không dành sản phẩm thương mại/data training dùng automated bots/scrapers/AI; nguồn này không được sử dụng để tích hợp trong lượt làm việc |
| [Understat trực tiếp](https://understat.com/league/La_liga/2025) | Đọc trang công khai | Chỉ trả thông báo sẽ trở lại; không thu được dataset trực tiếp |
| [La Liga results](https://www.laliga.com/en-GB/laliga-easports/results) | Đối chiếu thủ công trang kết quả và 3 trang trận liên kết | Phát hiện CSV chậm 3 kết quả hoàn tất; không có xG trong nội dung trang trận đã đọc |

Không vượt chặn/rate limit, không dùng mirror Football-Data để né điều kiện. Schema SP1 thực tế **chưa được tải/kiểm tra**; các tên `HS/HST/FTHG` trong test là dữ liệu giả lập cho generic mapping, không được báo là quan sát từ CSV thật.

Chỉ metadata, aggregates và mã nghiên cứu được công bố. Raw CSV, completed-fixture evidence, staging, feature inputs, predictions và log đều ignored. Quyền tái phân phối dữ liệu Understat/Sportmonks qua bên thứ ba chưa được xác minh. Công bố sau này cần review quyền riêng; không coi miễn phí truy cập là giấy phép redistribution.

## 5. Download URLs và inventory

URL được tìm từ anchor thực tế của các trang directory, không đoán đường dẫn:

| File local | URL thực tế | Dòng | Fixture duy nhất |
|---|---|---:|---:|
| `archive_2019_fixtures.csv` | [CSV 2019](https://www.xgtables.io/history/la-liga/2019/fixtures.csv) | 380 | 380 |
| `archive_2020_fixtures.csv` | [CSV 2020](https://www.xgtables.io/history/la-liga/2020/fixtures.csv) | 380 | 380 |
| `archive_2021_fixtures.csv` | [CSV 2021](https://www.xgtables.io/history/la-liga/2021/fixtures.csv) | 380 | 380 |
| `archive_2022_fixtures.csv` | [CSV 2022](https://www.xgtables.io/history/la-liga/2022/fixtures.csv) | 380 | 380 |
| `archive_2023_fixtures.csv` | [CSV 2023](https://www.xgtables.io/history/la-liga/2023/fixtures.csv) | 380 | 380 |
| `archive_2024_fixtures.csv` | [CSV 2024](https://www.xgtables.io/history/la-liga/2024/fixtures.csv) | 380 | 380 |
| `archive_2025_fixtures.csv` | [CSV 2025](https://www.xgtables.io/history/la-liga/2025/fixtures.csv) | 380 | 380 |
| `archive_2025_shots.csv` | [Shots 2025](https://www.xgtables.io/history/la-liga/2025/shots.csv) | 9.500 | 380 |
| `current_2026_fixtures.csv` | [CSV 2026](https://www.xgtables.io/data/v1/la-liga/2026/fixtures.csv) | 380 | 380 |

Tất cả HTTP 200; 4 trang HTML nguồn cũng được lưu local. Retrieval CSV: **2026-11-21 20:20:23–20:20:29 UTC**, tức **22/11/2026 03:20 giờ Việt Nam**. Format CSV UTF-8. Mỗi file có SHA-256, timestamp, byte size, toàn bộ tên cột, min/max date, completed count, missingness theo từng cột và duplicate count trong [manifest công khai](MULTISOURCE_LALIGA_DATASET_MANIFEST.json). Không có duplicate bản ghi hoặc primary ID trong 9 CSV.

Download manifests gốc còn lưu URL trang phát hiện link, ETag/Last-Modified nếu có. Version nghiên cứu là content hash, không giả làm revision ID của nhà cung cấp. Acquisition từ chối ghi đè thư mục có manifest; lần tải mới phải dùng thư mục version khác.

## 6. Schema thực tế đã đọc

### Archive fixture: 19 cột

```text
provider, competition, season, fixture_id, understat_id, date,
home, away, score, home_xg, away_xg, home_published_xg,
away_published_xg, home_win_probability, draw_probability,
away_win_probability, totals_unreliable, xg_note, result_note
```

### Archive shots: 18 cột

```text
provider, competition, season, fixture_id, understat_id, shot_id,
side, minute, player_id, player, result, x, y, understat_xg,
situation, shot_type, assisted_by, last_action
```

### Current fixture: 37 cột

```text
fixture_id, date, kickoff_utc, phase, stage_id, stage, state_id,
status, home_id, home, away_id, away, home_goals, away_goals,
home_xg, away_xg, home_xpts, away_xpts, home_shots, away_shots,
home_shots_on_target, away_shots_on_target, home_goals_90,
away_goals_90, home_penalties, away_penalties, home_played_goals,
away_played_goals, awarded_winner, result_note, source,
home_derived, away_derived, divergence_status, review_basis,
review_cohort, team_xg_source
```

Current có 260 dòng chưa thi đấu thiếu đồng thời goals/xG/shots/SOT; không đổi blank thành zero. Các trường penalty ở current đều trống, không dùng chúng như số penalty trong trận. SH/SOT không thể tự chuyển thành non-penalty một cách chính xác từ file này.

## 7. Schema mapping và ngữ nghĩa

Mỗi fixture được mở rộng thành đúng 2 perspective. Các mapping đều dựa vào vai trò Home/Away, kiểu giá trị và nguồn, không dựa riêng vào tên tương tự.

| Canonical | Archive / current | Phân loại | Quy tắc |
|---|---|---|---|
| `season` | Archive `season`; current context directory 2026 | DIRECT / DERIVED_MAPPING | Năm bắt đầu, validate ngày thuộc năm đó hoặc năm sau |
| `date` | `date`; current có `kickoff_utc` riêng | DIRECT_MAPPING | ISO date; không tự dịch ngày hay fuzzy join |
| `team`,`opponent` | `home`,`away` | DIRECT_MAPPING | Alias tường minh; đảo vai trò theo perspective |
| `is_home` | Vị trí home/away trong fixture | DERIVED_MAPPING | Home=1, away=0 |
| `gf`,`ga` | Archive parse `score`; current `home_goals/away_goals` | DERIVED / DIRECT_MAPPING | Parse score có cấu trúc, đảo phía cho GA; chỉ completed |
| `xg` | `home_xg/away_xg` | SEMANTIC_DIFFERENCE | Giữ xG nguồn; Understat và Sportmonks không bị buộc bằng FBref |
| `xga` | XG phía đối thủ trong cùng fixture | DERIVED_MAPPING + SEMANTIC_DIFFERENCE | Không lấy season-average xGA thay match xGA |
| `sh` archive | Đếm shot events theo side, bỏ `situation=Penalty` và `result=OwnGoal` | DERIVED_MAPPING | Quy tắc nghiên cứu dựa trên các nhãn event đã quan sát; chưa chứng minh toàn bộ phân loại giống FBref |
| `sot` archive | Trong tập trên, đếm `Goal` hoặc `SavedShot` | DERIVED_MAPPING / SEMANTIC_DIFFERENCE | Không tính ShotOnPost/BlockedShot/MissedShots là SOT theo mapping nghiên cứu |
| `sh`,`sot` current | `home_shots/away_shots`, `home_shots_on_target/away_shots_on_target` | SEMANTIC_DIFFERENCE | Giữ nguyên reported counts; penalty inclusion chưa xác minh, không giả vờ đã chuẩn hóa chính xác |
| Penalty outcome current | Không có metadata đủ | MISSING_OR_UNVERIFIED | Không trừ tất cả attempts/goals; không impute |

Archive shot dictionary liệt kê các outcome trong [trang download chính thức của xGTables](https://www.xgtables.io/understat-data/). Cả 6 nhãn đều xuất hiện trong file. Các nhãn không biết, thiếu side, thiếu metadata hoặc duplicate shot ID làm helper từ chối chuyển đổi. Tập shot export phủ 380 fixture và cả hai side; độ đầy đủ **chưa được kiểm chứng độc lập bằng box-score thứ hai**.

Mapping archive và current khác nhau được giữ trong `statistical_semantics`. Không coi sự khác biệt này là lý do tự động loại nguồn, nhưng cũng không coi inference chạy được là chứng minh model miễn nhiễm với distribution shift.

## 8. Đối chiếu và xung đột nguồn

Giữ nguyên toàn bộ snapshot FBref đến 30/09/2025. Đối chiếu archive theo `(season,date,canonical_home,canonical_away)` khớp **2.350/2.350** fixture tham chiếu: 380 ở mỗi mùa 2019–2024, 70 ở 2025; **0 score conflict**. Provider IDs không được dùng để join hai nguồn khác nhau.

XG khác số giữa hai nguồn ở hầu hết overlap; đây không phải lỗi mặc định và không dùng để tuning. Trong 70 fixture overlap 2025, SH tái tạo phía home khớp 69, SOT phía home khớp 70. Kết quả này hỗ trợ khả năng mapping, chưa chứng minh toàn bộ phân loại cú sút giống nhau. Không lấy số liệu external ghi đè số training.

Sum shot xG so với archive team xG lệch quá 0.01 ở **156 fixture 2025–26**. Không áp đặt một phép hiệu chỉnh để làm chúng khớp. Khác phiên bản/revision có thể là nguyên nhân nhưng **chưa được xác minh**; giữ team xG export làm nguồn đã chọn, shot events dùng để nghiên cứu SH/SOT. Riêng fixture được nguồn gắn cờ unreliable không được hợp thức hóa bằng tổng shot xG: chưa đủ bằng chứng giải thích cờ và xác nhận phiên bản/coverage để tuyên bố đã sửa chính xác.

Generic supplementary matcher kiểm tra ngày/đội/mùa và score/stat conflicts; khác ngày cần chứng cứ kickoff/timezone, không tự dịch ±1 ngày. Không chọn ngẫu nhiên giữa hai giá trị tương đương nhưng xung đột. Không có supplementary numeric source thứ hai được nhập trong lượt này.

## 9. Coverage 2019–2027

Mỗi file fixture có 20 đội và đủ 380 cặp Home/Away của lịch hai lượt, đã kiểm tra identity, không suy ra completed từ số scheduled. “Đủ SH/SOT” ở bảng là có số hợp lệ về cấu trúc theo semantics nghiên cứu đã ghi; không phải exact FBref equivalence.

| Mùa | Fixture liệt kê | Completed CSV | Completed đã biết tối thiểu | XG external hợp lệ | SH đủ | SOT đủ | Tích hợp đủ trường | Thiếu completed đã biết |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019–20 | 380 | 380 | 380 | 379 | 380 | 380 | 380 | 0 |
| 2020–21 | 380 | 380 | 380 | 380 | 380 | 380 | 380 | 0 |
| 2021–22 | 380 | 380 | 380 | 380 | 380 | 380 | 380 | 0 |
| 2022–23 | 380 | 380 | 380 | 380 | 380 | 380 | 380 | 0 |
| 2023–24 | 380 | 380 | 380 | 380 | 380 | 380 | 380 | 0 |
| 2024–25 | 380 | 380 | 380 | 380 | 380 | 380 | 380 | 0 |
| 2025–26 | 380 | 380 | 380 | 379 | 380 | 380 | 379 | 1 |
| 2026–27 | 380 | 120 | **≥123** | 120 | 120 | 120 | 120 | **≥3** |

2019 external có một xG gap nhưng staging không bị mất vì dùng snapshot gốc đầy đủ. Sau 01/10/2025 có 310 fixture mùa 2025 cần bổ sung, lấy được 309. Fixture unreliable còn thiếu một raw pair xG. Không lấy 260 dòng chưa có kết quả trong CSV làm 260 trận missing completed.

Theo đội, mùa 2025–26 Oviedo và Villarreal mỗi đội có 37/38 trận tích hợp; 18 đội khác đủ 38. Sau đối chiếu chính thức 2026–27, sáu đội của ba fixture mới có thêm một completed chưa có thống kê trong staging. Danh sách chi tiết nằm local ở `coverage_by_team.csv`; manifest public chỉ chứa aggregate coverage gaps.

CSV current mới nhất có completed date **20/11/2026**. [Trang kết quả La Liga](https://www.laliga.com/en-GB/laliga-easports/results) và ba trang trận liên kết xác nhận thêm ba completed 21/11: [Alaves–Deportivo](https://www.laliga.com/en-GB/match/temporada-2026-2027-laliga-ea-sports-deportivo-alaves-rc-deportivo-13), [Rayo–Valencia](https://www.laliga.com/en-GB/match/temporada-2026-2027-laliga-ea-sports-rayo-vallecano-valencia-cf-13), [Sevilla–Betis](https://www.laliga.com/en-GB/match/temporada-2026-2027-laliga-ea-sports-sevilla-fc-real-betis-13). Các trang trận đã đọc có total shots nhưng không thấy xG; không suy SOT từ tỷ lệ accuracy đã làm tròn hoặc đoán xG từ commentary. Đây là kiểm tra độ mới có phạm vi, không phải một bản export toàn bộ lịch La Liga độc lập. Một trận LIVE và các fixture trong ngày 22/11 vẫn chưa được xác nhận kết thúc.

## 10. Staging, exclusions và provenance

Các file local nằm trong `data/external/multisource/processed/`:

```text
laliga_multisource_staging.csv       5.558 dòng, đủ 11 raw fields + metadata
excluded_fixtures.csv               mọi fixture không được append và lý do
expected_completed_history.csv      danh mục completed đã biết để kiểm tra gap
coverage_by_team.csv                expected/integrated/missing theo đội và mùa
feature_inputs.csv                 222 dòng feature nghiên cứu
frozen_lr_predictions.csv           222 dự đoán offline, không thay xG bị thiếu
feature_exclusions.csv              12 target bị chặn vì lịch sử thiếu
```

Exclusions theo loại: 70 overlap giữ snapshot; 1 unreliable xG; 3 official completed nhưng export thiếu thống kê; 257 dòng còn lại chưa được xác nhận completed trong snapshot/evidence, gồm LIVE/unplayed, không bị coi là missing-history outcomes.

Metadata từng dòng gồm `fixture_source,xg_source,shots_source,source_dataset_version,fetched_at,statistical_semantics,canonical_key`. Archive ghép fixture/shot cùng Understat `fixture_id` trong **cùng export**, đã kiểm tra FK/season/competition và uniqueness; điều này khác join IDs giữa hai provider. Version ghép cả hai SHA-256.

## 11. Feature Builder và frozen LR

Research adapter tái sử dụng `stint_history`, `ROLLING_SOURCES` và history config production, với phép assembly 13 feature được test parity với Feature Builder gốc. Nó hỗ trợ alias tường minh cho Malaga, Racing Santander và Deportivo La Coruna trong nghiên cứu; production registry không đổi. Có **35/123 target** liên quan tên đội chưa có trong registry production, cần xử lý ở phase tích hợp sau.

Mỗi target lọc `date < fixture_date`, season không vượt target; không dùng own outcomes hoặc future fixtures. `matches_seen` đếm cả stint và `short_history` theo ngưỡng 5; rolling dùng đúng tối đa 5 trận cuối. Zero-history được phép NaN theo semantics cũ và đi qua fitted imputer sẵn có; không impute raw outcomes thiếu.

Đối soát danh sách lịch sử với completed catalogue trước khi dựng X: thiếu dù ở ngoài rolling 5 vẫn bị chặn vì `matches_seen` sẽ sai. Nhờ vậy 12 target liên quan Villarreal bị chặn, không âm thầm tính lại trên 37 trận. Promoted teams reset khi có gap mùa; zero-history được kiểm tra với catalogue thay vì nhầm “không tìm được data” thành đội mới.

| Kết quả experiment | Số lượng |
|---|---:|
| Target 2026–27 đã biết completed | 123 |
| Dựng X / predict thành công | 111 fixture / 222 dòng |
| Bị chặn vì lịch sử thiếu | 12 fixture |
| Target thành công có ít nhất một đội short-history | 12 |
| Target thành công có ít nhất một đội zero-history | 2 |
| Target có rolling window trộn Understat/Sportmonks | 37 |

Ba target cuối chưa có raw outcomes vẫn có thể được dự đoán bằng **lịch sử trước trận**. Dự đoán đó không được dùng thay các thống kê/xG đang thiếu để append history.

Frozen pipeline nhận schema đúng, trả kết quả hữu hạn; clipping giữ `max(0,raw)`. Không `fit`, không refit imputer hoặc đổi feature/coefficient. Hash artifact giữ nguyên:

```text
0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69
```

Đây là technical operability. Chưa kiểm định accuracy/calibration trên nguồn mới; không dùng Phase 7 Final Test chọn nguồn/hyperparameter. Latest snapshots có thể chứa revisions xuất hiện sau ngày dự đoán: date cutoff ngăn target/future-match leakage, nhưng không chứng minh replay as-of-vintage chính xác.

## 12. Refresh feasibility và bước tiếp

Có thể refresh nghiên cứu bằng bulk CSV không dùng StrikerAPI credits. Mỗi lần lưu version mới, kiểm tra schema/hash, join canonical fixture, phát hiện mới/sửa/mất, đối soát completed catalogue và per-team gaps. URL v1 mô tả column definitions ổn định theo [directory xGTables](https://www.xgtables.io/data/), không phải cam kết file bytes bất biến hoặc SLA.

Pipeline đã có checksum, schema validation, duplicate/conflict detection và provenance; acquisition tránh overwrite evidence. Chưa triển khai scheduler, production refresh, revision database hoặc deployment. Độ chậm CSV vừa phát hiện phải được coi là blocker freshness thực tế.

Đề nghị phase kế tiếp: giải quyết 4 fixture thiếu đã biết và xác minh trạng thái LIVE/các trận mới; xác nhận version/coverage shot data và penalty semantics current; review quyền sử dụng và registry đội mới; sau đó đánh giá predictive performance trên dữ liệu nguồn mới với protocol riêng. Chưa migration mixed providers vào History Store. Model frozen vẫn giữ nguyên; nếu sau này cần model mới phải là phase khác.

## 13. Tái lập và test

```powershell
# Acquisition mới vào một thư mục version riêng; có network nhưng không API key
.venv\Scripts\python.exe -m scripts.multisource.acquire --download --directory data/external/multisource/new_version

# Với bộ file snapshot đã tải ở thư mục mặc định
.venv\Scripts\python.exe -m scripts.multisource.run_audit --as-of 2026-11-22
.venv\Scripts\python.exe -m unittest discover -s tests -p test_multisource.py -v
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Acquisition tự động tải CSV/HTML; `independent_completed.json` là evidence review thủ công từ La Liga, giữ local. Thiếu file đó, runner chỉ biết completed trong CSV và không được dùng kết quả để tuyên bố coverage thực tế đến hiện tại. Reproduction đúng snapshot cần giữ cả manifests và file evidence có hash trong manifest public. Các phiên bản nguồn tương lai có thể cho coverage khác.

Test dùng dữ liệu giả lập cho mapping, hai perspective, derivation, alias, duplicate, missing, conflict, identity, provenance, season, calendar, rolling, temporal leakage, completeness và frozen artifact. Không cần file third-party local để chạy unit tests. Kết quả cuối ghi ở [báo cáo phase](../Phases/Phase%208.5.2%20-%20Multi-source%20Dataset%20Feasibility.md).
