# Phase 8.5.2A — Kiểm toán ngữ nghĩa FBref và StrikerAPI

Ngày kiểm toán: **21/11/2026**. Nhánh: `phase8.5.2-semantic-audit`.
Điểm xuất phát: `ee83689d117620b5085c389ce3266ed2a92cca77`, đã đối chiếu với remote `phase8.5.1-strikerapi-live-audit`.

## 1. Kết luận và mức độ bằng chứng

**Chưa đủ điều kiện chuẩn hóa SH/SOT StrikerAPI cho production.** Hai phép trừ là xác định khi có số penalty thực hiện, số penalty trúng đích và hợp đồng thống kê đã xác minh. `get_game` hiện chưa cung cấp đủ bằng chứng để áp dụng cho mọi trận. Một trận khớp sau khi trừ penalty không chứng minh khả năng tương thích trên toàn bộ lịch sử.

Báo cáo dùng bốn mức bằng chứng:

- **DOC**: đọc được nội dung tài liệu chính thức trong lần kiểm toán này.
- **LOCAL**: kiểm chứng trực tiếp từ dataset, mã hoặc cache cục bộ; không phải cam kết của nhà cung cấp.
- **CONDITIONAL**: kết luận toán học chỉ đúng nếu các điều kiện được nêu đã được xác minh.
- **UNVERIFIED**: thiếu tài liệu nguồn hoặc chưa chứng minh được; không dùng làm cổng phê duyệt production.

Không gọi endpoint tính phí, không mở rộng mẫu. Chỉ đọc tài liệu web công khai và cache đã có. Mã nghiên cứu mới không được import bởi adapter hay inference production.

## 2. Phạm vi dự án đã kiểm tra

Đã đọc `data/matches_laliga.csv`, `data/preprocess_laliga.py`, dữ liệu normalized, `scripts/prepare_training_features.py`, Phase 8 Feature Builder, History Store/schema, artifact loader và code/report/cache Phase 8.5.1.

**LOCAL:** preprocessing bỏ `pk`/`pkatt`, giữ nguyên `sh`/`sot` rồi tính rolling trung bình 5 trận bằng lịch sử đã `shift(1)`. Ghép một-một theo season, ngày, đội, đối thủ, sân nhà cho thấy cả **4.700 dòng** normalized giữ nguyên `sh`, `sot`, `xg`, `xga` của CSV gốc. Feature Builder Phase 8 cũng dùng trực tiếp các trường này. Không có bước cộng/trừ penalty trong feature engineering.

13 feature bất biến, theo đúng thứ tự:

```text
is_home, matches_seen, short_history, xg_avg5, xga_avg5,
gf_avg5, ga_avg5, shot_avg5, sot_avg5, opponent_xg_avg5,
opponent_xga_avg5, opponent_matches_seen, opponent_short_history
```

History Store lưu `sh`/`sot` nhưng không lưu số penalty hoặc phiên bản định nghĩa. Các mô tả cũ gọi `sh` là tổng cú sút không đủ để xác định có bao gồm penalty hay không. Trong phạm vi tương thích, giá trị mục tiêu là **đúng số đếm đã đi vào training**, không phải diễn giải lại nhãn cũ. Không sửa schema hoặc dữ liệu history để che lấp khác biệt.

Linear Regression, fitted imputer, Phase 7, Feature Builder và production History Store được giữ nguyên. SHA-256 artifact:

```text
0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69
```

## 3. FBref: định nghĩa, bằng chứng và giới hạn xác minh

### 3.1 Trạng thái định nghĩa từng trường

| Trường gốc | Diễn giải cần kiểm toán | Trạng thái trong phase này |
|---|---|---|
| `sh` | Số cú sút ngoài penalty trong bảng shooting lịch sử | LOCAL hỗ trợ rất mạnh; tooltip lịch sử chưa xác minh lại được |
| `sot` | Số cú trúng đích ngoài penalty trong bảng shooting lịch sử | LOCAL hỗ trợ rất mạnh; tooltip lịch sử chưa xác minh lại được |
| `pk` | Penalty ghi bàn | Diễn giải hợp lý của trường; chưa đọc lại được định nghĩa chính thức gắn với snapshot |
| `pkatt` | Penalty thực hiện, gồm thành công và không thành bàn | Diễn giải hợp lý; scope, retake và shootout của snapshot còn thiếu xác nhận nguồn |
| `xg` | Expected goals của đội, không tự đổi thành npxG | LOCAL: đây là target training; cách cộng penalty và công thức lịch sử chưa xác minh lại được |
| `xga` | Expected goals của đối thủ | LOCAL: bằng `xg` phía đối thủ ở toàn bộ 2.350 trận |

Nguồn định nghĩa dự kiến là [FBref glossary](https://fbref.com/en/about/glossary) và [bảng shooting La Liga 2020–2021](https://fbref.com/en/comps/12/10731/shooting/2020-2021-La-Liga-Stats). Công cụ web không đọc được; GET thông thường tới glossary trả **HTTP 403**. Không vượt chặn, không dùng bản sao bên thứ ba để gắn nhãn DOC. Vì vậy, **không có xác nhận mới từ tooltip FBref cho sáu trường trên**. Tuyên bố quen thuộc “Sh/SoT loại penalty” được coi là giả thuyết lịch sử được dữ liệu hỗ trợ, chưa phải xác minh tài liệu hoàn tất.

Sports Reference đã thông báo gỡ dữ liệu nâng cao trong năm 2026; không nên lấy bảng hiện tại làm bằng chứng tự động cho snapshot training cũ. Đây là thông tin từ [thông báo chính thức được công cụ tìm kiếm lập chỉ mục](https://www.sports-reference.com/blog/category/advanced-stats/); không phải chứng minh nguyên nhân của HTTP 403 hay định nghĩa SH/SOT.

Để phân biệt outcome, [Opta Event Definitions](https://www.statsperform.com/opta-event-definitions/) mô tả cú ghi bàn và cú bị thủ môn cứu là on target; bóng chạm khung thành rồi không vào là off target; một số pha chặn ở tuyến cuối cũng tính on target. **DOC của Opta, không tự động là hợp đồng của StrikerAPI hoặc bằng chứng lineage của toàn CSV.**

### 3.2 Thống kê theo dòng đội–trận

Dataset có **4.700 dòng / 2.350 trận**. `season` là năm bắt đầu mùa. Các mùa 2019–2024 có 380 trận/mùa; 2025 chỉ có 70 trận, là snapshot chưa đủ mùa.

Trong các bảng sau, `pkatt-pk` được gọi là **không thành bàn**. Chỉ từ hai cột này không biết penalty bị cản, sút rộng, trúng khung thành, hay loại outcome khác. Cột thành công và không thành bàn có thể cùng đúng trong một dòng.

| Season | Dòng | Không PK (`pkatt=0`) | Có PK thành công (`pk>0`) | Có PK không thành bàn (`pkatt>pk`) | Lượt PK | PK ghi bàn | Lượt không thành bàn |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 760 | 626 | 113 | 25 | 149 | 124 | 25 |
| 2020 | 760 | 633 | 101 | 36 | 141 | 105 | 36 |
| 2021 | 760 | 642 | 91 | 32 | 132 | 99 | 33 |
| 2022 | 760 | 658 | 76 | 32 | 115 | 83 | 32 |
| 2023 | 760 | 661 | 75 | 27 | 107 | 80 | 27 |
| 2024 | 760 | 638 | 100 | 23 | 130 | 106 | 24 |
| 2025 | 140 | 120 | 16 | 4 | 20 | 16 | 4 |
| **Tổng** | **4.700** | **3.978** | **572** | **179** | **794** | **613** | **181** |

Phân nhóm dòng không chồng lặp: 3.978 không PK; 543 có PK và tất cả thành công; 150 có PK nhưng tất cả không thành bàn; 29 có cả hai loại. Như vậy có 722 dòng thực hiện penalty. Không dùng 179 dòng thay cho 181 lượt không thành bàn.

### 3.3 Thống kê trận duy nhất

Ghép hai góc nhìn theo `(season, date, canonical_home, canonical_away)`, xác minh đúng hai dòng Home/Away mỗi trận, không đếm hai lần penalty.

| Season | Trận | Không PK ở cả hai đội | Có PK thành công ở ít nhất một đội | Có PK không thành bàn ở ít nhất một đội |
|---|---:|---:|---:|---:|
| 2019 | 380 | 266 | 98 | 24 |
| 2020 | 380 | 269 | 88 | 35 |
| 2021 | 380 | 273 | 85 | 32 |
| 2022 | 380 | 290 | 69 | 29 |
| 2023 | 380 | 291 | 70 | 26 |
| 2024 | 380 | 267 | 93 | 23 |
| 2025 | 70 | 51 | 15 | 4 |
| **Tổng** | **2.350** | **1.707** | **518** | **173** |

Hai cột cuối có giao nhau: có 643 trận có penalty, trong đó 48 trận có cả penalty thành công và không thành bàn. Không suy ra outcome chi tiết từ giao này.

### 3.4 Trường hợp SH/SOT bằng 0

| Season | `sh=0, pkatt>0` | `sot=0, pkatt>0` | `sot=0, pk>0` |
|---|---:|---:|---:|
| 2019 | 0 | 3 | 3 |
| 2020 | 0 | 12 | 10 |
| 2021 | 1 | 4 | 2 |
| 2022 | 0 | 4 | 3 |
| 2023 | 0 | 3 | 2 |
| 2024 | 0 | 10 | 9 |
| 2025 | 0 | 0 | 0 |
| **Tổng** | **1** | **36** | **29** |

Các số ở bảng này đồng thời là số dòng và số trận duy nhất: không có trận nào cả hai đội cùng thỏa một điều kiện được liệt kê. Ví dụ từ **CSV gốc đã nằm trong repo**: Real Sociedad gặp Real Madrid ngày 05/03/2022 có `sh=0, sot=0, pk=1, pkatt=1, xg=0.8, xga=2.0` ở góc nhìn Sociedad. Đây là phản ví dụ trực tiếp đối với cách hiểu SH/SOT bao gồm mọi penalty. Không trừ penalty thêm lần nữa khỏi CSV này.

### 3.5 Kiểm tra sáu trường

| Trường | Missing | Min | Max |
|---|---:|---:|---:|
| `sh` | 0 | 0 | 40 |
| `sot` | 0 | 0 | 17 |
| `pk` | 0 | 0 | 3 |
| `pkatt` | 0 | 0 | 3 |
| `xg` | 0 | 0.0 | 5.9 |
| `xga` | 0 | 0.0 | 5.9 |

SH/SOT/PK/PKatt đều nguyên không âm; mọi dòng thỏa `sot<=sh`, `pk<=pkatt`. `xg`/`xga` hữu hạn, không âm, đảo chiều chính xác giữa hai đội; không có `xg=0` khi `pkatt>0`. Những kiểm tra này không chứng minh cách định giá xG cho penalty. Giữ nguyên `xg`/`xga`; không trừ một hằng số 0.76, 0.78 hay tỷ lệ penalty tự chọn, không chuyển target thành npxG.

## 4. StrikerAPI: tài liệu chính thức và cache

### 4.1 Những gì được xác nhận

[Tài liệu `get_game`](https://strikerapi.com/docs/get-game) công bố box score với `shots`, `shots_on_target`, `penalty_attempts`, `penalty_goals`; key events có `penalty`, `outcome`, `shootout`. Tài liệu không đưa hợp đồng rõ về việc SH/SOT có tính penalty và cách xử lý retake. Tên trường không đủ để xác nhận tương thích FBref.

**LOCAL:** chỉ có một cache `get_game` thành công từ live PoC; checksum nội dung cache khớp. Cả hai đội có hai aggregate penalty, nhưng không có `penalty_shots_on_target`, số penalty bị cứu hoặc tập shot events đầy đủ. Dòng cầu thủ chỉ có các số cú sút/cứu thua tổng, không có breakdown penalty. Không lấy tổng saves của thủ môn làm penalty saves.

Mẫu cache thuộc trường hợp tất cả penalty thực hiện đều thành bàn. Đối chiếu riêng tư cho thấy phép trừ ứng viên khớp SH/SOT CSV ở cả hai góc nhìn; mapping trực tiếp trước đó không khớp ở phía có penalty. Đây là **LOCAL + CONDITIONAL**, không phải xác nhận toàn bộ định nghĩa hoặc khả năng tổng quát hóa. Không công bố payload, provider IDs hoặc số thống kê provider trong repo.

`key_events` là danh sách sự kiện chính, không có cam kết là danh sách đầy đủ mọi cú sút. Có cờ penalty/outcome không đồng nghĩa đã biết tất cả penalty trúng đích. Outcome quan sát được ở một mẫu không đại diện mọi giá trị có thể xuất hiện.

### 4.2 Các endpoint chỉ được đọc tài liệu, không thực thi

| Endpoint | Cấu trúc DOC hữu ích | Khoảng trống cần xác nhận |
|---|---|---|
| [`get_events`](https://strikerapi.com/docs/get-events) | Lọc `game_id`, `kind=shots`, `league`; phân trang `limit/offset`, `next_offset`; event có `seq`, `period`, `team_id`, `shot.penalty`, `shot.outcome`, `shootout` | Không có boolean on-target mỗi shot hay bảng ánh xạ outcome đầy đủ trong trang đã đọc; phải kiểm tra đủ trang, deduplicate, cùng scope |
| [`get_shot_map`](https://strikerapi.com/docs/get-shot-map) | Lọc trận/đội, `include_shots`; shot có `penalty`, `outcome`, `team`; `totals` và `zones` có `shots/on_target` | Danh sách tối đa 2.000, cần đối soát shot thiếu vị trí/cắt cụt; aggregate cả hai đội nếu không lọc; không có on-target mỗi shot trong schema mẫu |

[Glossary shot map](https://strikerapi.com/glossary/shot-map) mô tả các outcome ghi bàn, bị cứu, bị chặn, trượt và nhóm penalty. Có thể nghiên cứu aggregate `on_target` của **nhóm penalty riêng, đúng đội**, nếu nhà cung cấp xác nhận nhãn nhóm, tính tách biệt và coverage; chưa chứng minh rằng nhóm đó tồn tại/đầy đủ cho La Liga trong mọi response.

Không suy luận on-target từ tọa độ, tên zone hoặc chuỗi mô tả tự do. Cần `on_target` rõ ràng hoặc mapping outcome chính thức bao gồm saved, off-target, woodwork, blocked, annulled, retaken; giá trị không biết phải dừng chuyển đổi.

### 4.3 xG và thời điểm

[Glossary xG](https://strikerapi.com/glossary/expected-goals) mô tả mô hình theo vị trí, góc và header; penalty dùng tỷ lệ thành công của giải. Đây là định nghĩa DOC của StrikerAPI, không bảo đảm bằng xG nguồn training. `xga` trong adapter hiện tại là xG của đối thủ được đảo chiều.

[Timing and rights](https://strikerapi.com/docs/timing-and-rights) nêu xG không phải dữ liệu as-of, có refit trên cả các mùa sau và không lưu revision history theo record. Sửa SH/SOT không giải quyết khác biệt mô hình xG hoặc rủi ro thời điểm. Không dùng pilot này để tuyên bố Phase 7 được tái kiểm chứng bằng nguồn mới.

## 5. Quy tắc chuyển đổi và điều kiện từ chối

Chỉ khi đã xác minh nguồn **bao gồm penalty**, đích **loại penalty**, định nghĩa SOT tương thích và mọi số đếm cùng đội/trận/scope đầy đủ:

```text
non_penalty_shots = total_shots - penalty_attempts
non_penalty_sot   = total_sot   - penalty_shots_on_target
```

Scope phải thống nhất thời gian chính thức/hiệp phụ, loại shootout, không đếm lại cú bị hủy/retake ngoài box score; rebound là cú sút mới theo định nghĩa nguồn, không trừ như penalty thứ hai.

| Trường hợp tổng hợp giả lập | Penalty attempts | Penalty goals | Penalty SOT | SH bị trừ | SOT bị trừ |
|---|---:|---:|---:|---:|---:|
| Không penalty, đã biết chắc số 0 | 0 | 0 | 0 | 0 | 0 |
| Thành công | 1 | 1 | 1 | 1 | 1 |
| Thủ môn cứu, không vào | 1 | 0 | 1 | 1 | 1 |
| Ra ngoài/trúng khung rồi không vào | 1 | 0 | 0 | 1 | 0 |
| Một thành công, một bị cứu, một ra ngoài | 3 | 1 | 2 | 3 | 2 |
| Outcome chưa biết | 1 | 0 | **Không biết** | Có thể tính SH nếu hợp đồng đủ | **Từ chối tính SOT** |

Không được đặt penalty SOT bằng attempts hoặc goals một cách tổng quát. Hai trận có cùng `(total_shots=10,total_sot=4,attempts=1,goals=0)` vẫn có thể cho non-penalty SOT bằng 3 (bị cứu) hoặc 4 (ra ngoài).

**CONDITIONAL:** nếu `A=penalty_attempts`, `G=penalty_goals`, số penalty SOT `P` phải thỏa `G<=P<=A` theo phân loại đã thống nhất. Với `T=total_shots, S=total_sot`, còn cần `max(G,S-(T-A))<=P<=min(A,S)`. Chỉ khi miền khả thi có đúng một giá trị mới xác định được P từ aggregates. `A=0` và `A=G` là hai trường hợp đặc biệt thường gặp; không phải giấy phép thay `P=G` cho mọi trận. Cache hiện tại chỉ minh họa trường hợp đặc biệt tất cả thành công.

Helper `scripts/data_provider/penalty_semantics.py` cố ý yêu cầu P được cung cấp rõ kể cả các trường hợp đặc biệt; không tự suy diễn outcome từ aggregates. `CountContract` mặc định đóng cả năm điều kiện. Đây là attestation nghiên cứu do người gọi chịu trách nhiệm chứng minh, không phải cơ chế tự xác minh nhà cung cấp. Chưa có bằng chứng để mở contract cho StrikerAPI production.

Helper từ chối metadata thiếu, kiểu boolean/string/float thay cho integer, số âm, NaN/inf, `S>T`, `P>A`, `G>P`, kết quả âm hoặc non-penalty SOT lớn hơn non-penalty SH. Không clamp về 0, không dùng fitted imputer cho penalty metadata. Hàm trả cả cặp hoặc báo lỗi; không trả cặp một phần. Nếu nguồn đã loại penalty, không chạy phép trừ lần nữa.

## 6. `get_game` một mình có đủ không?

**Không đủ cho chuyển đổi tổng quát đã được xác minh.** `penalty_attempts` có thể đủ cho SH sau khi xác nhận quy ước; `penalty_goals` không đủ xác định penalty SOT khi có penalty không thành bàn. Key events và tổng saves không bù được khoảng trống nếu thiếu bằng chứng đầy đủ và mapping outcome.

Thông tin còn thiếu:

1. Định nghĩa FBref lịch sử gắn với snapshot gốc: loại penalty ở SH/SOT, scope PK/PKatt và cách cộng penalty trong xG/xGA.
2. Cam kết StrikerAPI theo La Liga/mùa rằng box-score SH/SOT bao gồm penalty, cùng scope, xử lý retake/hủy/shootout, và định nghĩa SOT tương thích.
3. `penalty_shots_on_target` theo đội/trận, hoặc đầy đủ shot events kèm penalty flag và on-target boolean/mapping outcome được xác nhận.
4. Bằng chứng coverage, uniqueness, identity, phiên bản dữ liệu; xử lý shot không có vị trí và mọi trang phân trang.

Một endpoint bổ sung hoặc field mới là cần thiết cho các trường hợp P chưa xác định từ aggregate hiện có. `get_events` là ứng viên ưu tiên vì có scope sự kiện và phân trang; `get_shot_map` là ứng viên thay thế nếu nhóm penalty/shot coverage đủ. **Đọc schema chưa chứng minh rằng endpoint nào chắc chắn lấp được thiếu hụt.** Không gọi đồng loạt cả hai trước khi biết câu hỏi cần trả lời.

## 7. Khuyến nghị Phase 8.5.2B

Pilot tiếp theo chỉ nên bắt đầu sau một yêu cầu/ủy quyền mới. Ưu tiên xác nhận hợp đồng thống kê bằng tài liệu/giải đáp chính thức; chưa gửi câu hỏi ra ngoài trong phase này. Sau đó chọn một tập kiểm soát nhỏ bao phủ không PK, PK thành công, PK bị cứu, PK ra ngoài/trúng khung và nhiều PK; có thể dùng CSV gốc để tìm candidate nhưng không gán outcome saved/wide từ `pkatt-pk`.

Đề xuất đầu tiên: `get_events(kind=shots)` cho đúng fixture, `league=laliga`, cache và hạn mức được duyệt riêng. Đọc hết trang; đối soát IDs/đội/thời gian/seq và số penalty với aggregate; chỉ phân loại outcome có định nghĩa được xác nhận. Nếu thiếu coverage/mapping, dừng và đánh giá shot map hoặc yêu cầu metadata mới. Không thể chấp nhận tỷ lệ “khớp phần lớn” để đoán các penalty thiếu.

Tiêu chí qua cổng pilot: đủ metadata, không outcome chưa biết, tổng số đếm đối soát chính xác, tái tạo được từng loại case và SH/SOT gốc; ghi riêng sai khác không do penalty. Tiếp tục đánh giá xG và as-of độc lập. Chưa mở rộng sample, backfill, retrain, scheduler hoặc migration khi cổng này chưa qua.

## 8. Tái lập offline, kiểm thử và bảo toàn

Trong môi trường dependencies đã có:

```powershell
.venv\Scripts\python.exe -m scripts.data_provider.audit_fbref_penalties
.venv\Scripts\python.exe -m unittest discover -s tests -p test_penalty_semantics.py -v
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Auditor chỉ đọc CSV và in aggregates, không ghi source. Test mới dùng counts giả lập và CSV gốc, không đọc cache riêng, không cần `.env` hoặc key. Test bảo toàn pin SHA-256 manifest gốc và xác minh 107 file đã frozen, cộng kiểm tra fitted Linear Regression, imputer fit 3.800 dòng và 13 feature. Kiểm tra cuối phase so sánh thêm toàn bộ 133 file tracked ở thời điểm bắt đầu, ledger và `.env` riêng.

Kết quả chạy được ghi trong [báo cáo phase](../Phases/Phase%208.5.2A%20-%20Data%20Semantics%20Audit.md). Toàn bộ suite được chạy thêm với socket/DNS bị chặn và API key bị bỏ khỏi environment của tiến trình test.

## 9. Ranh giới công bố

Chỉ xuất bản hai báo cáo, hai helper độc lập và unit test. Tất cả con số dataset ở đây tính từ CSV vốn đã tracked; bảng minh họa chuyển đổi là số giả lập. Chỉ công bố trạng thái/schema của cache, không sao chép thống kê provider hoặc dữ liệu sự kiện.

Cache, so sánh số liệu riêng, baseline và test log giữ trong `outputs/provider_poc/raw/semantic_audit_20261121/`, đã được ignore. Theo [hướng dẫn quyền sử dụng](https://strikerapi.com/docs/timing-and-rights), không phân phối provider dataset/feed/file. Không đưa `.env`, header, credential, raw response hay CSV provider vào commit. Kiểm tra staged diff và allowlist trước khi push. Không merge tự động.
