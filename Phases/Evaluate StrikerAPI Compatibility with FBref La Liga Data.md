# Đánh giá StrikerAPI PoC và khả năng tương thích dữ liệu La Liga với FBref

## 1. Trạng thái và phạm vi

Phase 8.5.1 hoàn thành ở mức implementation sau kiểm thử, mặc định dry-run. **Chưa gọi endpoint trả phí, chưa thu response trận thật, chưa xác nhận research-level compatibility hoặc production integration.** Không đổi Linear Regression đã serialize, imputer, 13 features, frozen datasets, Phase 7 protocol/results hoặc history store Phase 8.

Snapshot local có 4.700 team-match rows/2.350 fixtures, mùa 2019–2025; Development chỉ 2019–2023. Trước triển khai đã ghi SHA-256 của 107 file tracked Phase 1–8, loại .env và .env.example khỏi danh sách nội dung cần lưu. Root .gitignore giữ nguyên để không thay đổi các integrity checks cũ. .env.example được chuẩn hóa key rỗng theo yêu cầu; .env không bị ghi hoặc hiển thị.

## 2. Những gì đã xác minh từ nguồn chính thức

Đã đọc ngày 2026-11-21:

- [Tổng quan REST/auth/envelope](https://strikerapi.com/docs).
- [list_games](https://strikerapi.com/docs/list-games).
- [get_game](https://strikerapi.com/docs/get-game).
- [get_shot_map](https://strikerapi.com/docs/get-shot-map).
- [get_schedule](https://strikerapi.com/docs/get-schedule).
- [get_team_stats](https://strikerapi.com/docs/get-team-stats).
- [Timing và quyền dữ liệu](https://strikerapi.com/docs/timing-and-rights).
- [Tool catalogue JSON](https://mcp.strikerapi.com/v1/tools).
- [OpenAPI JSON](https://mcp.strikerapi.com/openapi.json).

Đã GET hai machine schemas không dùng key, kiểm tra input schemas và costs khớp nhau, lưu subset functional tại scripts/data_provider/strikerapi_contract.json. Live client so sánh lại trước POST; drift dừng. Các GET schema/docs công khai không phải request lấy trận đấu tính credit.

REST dùng POST /v1/{tool_name}, base URL https://mcp.strikerapi.com, header auth nội bộ x-api-key và league=laliga. Machine response schema yêu cầu data wrapper. Ví dụ endpoint cho thấy game chứa identity và team_stats chứa xg/shots/shots_on_target; đây là thông tin tài liệu, chưa phải availability đã xác minh trên mẫu thật.

Costs đã đối chiếu: list_teams 1, list_games/get_schedule 2, get_game/get_team_stats 5, get_shot_map/get_events 10. PoC chỉ dùng list_games, get_game và có điều kiện get_shot_map.

Giới hạn quan trọng: provider mô tả xG là mô hình location được fit qua cả các mùa sau và refit có thể đổi giá trị cũ; không có as-of xG hoặc revision history từng record. Vì vậy dữ liệu lấy hôm nay không tự chứng minh giá trị đã biết trước trận lịch sử, và không được coi tương đương FBref/Opta. Snapshot local hash chỉ truy vết bản đã nhận, không tạo revision ID của provider. Nguồn: [Timing and rights](https://strikerapi.com/docs/timing-and-rights).

## 3. Kiến trúc implementation

Package mới scripts/data_provider gồm client REST, connection check, deterministic sample selector, isolated normalizer, compatibility audit, pinned functional contract và requirements. Không sửa scripts/inference hoặc tạo feature-engineering pipeline mới.

Client đọc .env bằng python-dotenv, biến môi trường có ưu tiên, không interpolate hoặc ghi file. Không dùng key trong URL/subprocess arguments, không log auth headers/provider error body/exception text. Timeout tường minh, không theo redirect, không retry tự động. HTTP 400/401/402/403/429/5xx, invalid JSON, schema drift và local validation có mã lỗi tách biệt.

Credits được reserve trước POST bằng SQLite transaction, cộng dồn qua các CLI invocations; mặc định và cap ban đầu 25. Failed/uncertain request giữ reservation, không giả định refund. Response cache hợp lệ ngăn gọi trùng; cache hỏng hoặc request đã lỗi không được tự retry. Chỉ ghi numeric credit headers, chưa gán ý nghĩa billing cho tên header chưa xác minh.

Root .gitignore vẫn bảo vệ .env. Thêm outputs/provider_poc/.gitignore để chặn raw/cache/samples/comparisons/staging/logs/temp/SQLite mà vẫn cho review sanitized reports. Chưa có raw match response nào để commit.

## 4. Mẫu được chọn và request chính xác dự kiến

Đã chọn đúng một fixture Development, ưu tiên mùa 2023–2024:

| Thuộc tính | Giá trị FBref local |
|---|---|
| local_match_id | 1521 |
| season | 2023 |
| date | 2023-08-11 |
| Home | Almeria |
| Away | Rayo Vallecano |
| Final score | 0–2 |

Hai phía dữ liệu nguồn:

| team | gf | ga | xg | xga | sh | sot |
|---|---:|---:|---:|---:|---:|---:|
| Almeria | 0 | 2 | 1.4 | 2.1 | 19 | 5 |
| Rayo Vallecano | 2 | 0 | 2.1 | 1.4 | 8 | 2 |

Chưa có provider game_id. Không dùng local_match_id như StrikerAPI ID. Discovery request:

```json
{"league":"laliga","season":2023,"date":"2023-08-11","timezone":"Europe/Madrid","status":"final","limit":20}
```

Sau khi ghép chắc chắn, get_game:

```json
{"league":"laliga","game_id":"<ID trả về từ list_games và đã ghép>"}
```

Chỉ khi thiếu xG và còn đủ mọi thống kê khác, get_shot_map:

```json
{"league":"laliga","game_id":"<cùng ID>","include_shots":true}
```

Kế hoạch tối đa 2+5+10=17 credits nếu không cache; có thể chỉ 7 khi get_game đủ dữ liệu. Không request list_teams/get_team_stats/get_events hoặc search cả mùa để thử tìm mẫu đẹp. Kế hoạch mở rộng 24 trận qua năm mùa Development và ba nhóm tổng xG đã xuất local, chưa execute.

## 5. Ghép fixture và kiểm tra thời gian

Ghép season/date/canonical home-away/final score, team IDs dùng đúng giá trị trả về. Alias tường minh kế thừa Phase 8; không fuzzy match hoặc tự đổi fixture. Exact date phải khớp FBref; starts_at aware nếu có còn phải khớp ngày Europe/Madrid. Mâu thuẫn ngày do timezone bị flag và dừng, không tự match ±1 ngày vì timestamp của nguồn FBref cũ chưa được xác nhận.

Máy schema và trang list_games có offset/next_offset; phần conventions chung có mô tả khác. Contract ưu tiên machine schema theo yêu cầu. PoC không tự phân trang; không có đúng một confident match thì dừng.

## 6. Normalization và shot coverage

Adapter tạo đúng hai perspective với provider=strikerapi và status=completed chỉ khi mọi mandatory statistic được validate. Đối chiếu team IDs, home flags, goals, xG/xGA reversal, sh≥sot, integer counts, xG hữu hạn không âm và provenance.

Không coi xG null là 0. Không lấy season-average get_team_stats làm match-level. Không suy đoán SOT từ outcome. Thiếu SOT hoặc thống kê bắt buộc khác: diagnostics chỉ rõ, không xuất import-ready CSV.

Fallback shot xG tách hai đội bằng abbrev đã xác minh trong game, kiểm tra game/date, tổng shots theo đội so với box scores, located/unlocated, thiếu xG, duplicate, response truncation và tổng cộng. Tổng xG chung không được gán cho một đội. Raw shot aggregation và published team xG giữ xg_source riêng; dung sai tổng làm tròn 0,011 được ghi rõ, không ép khác biệt về 0.

Quality_status=verified chỉ có nghĩa identity/statistics của mẫu đủ schema, không phải nguồn tương thích model hoặc approved production. statistics_version dùng response_sha256 local vì không có revision ID được xác minh. Chỉ mock tests đã chứng minh adapter có thể nhập một fixture hợp lệ vào temporary staging SQLite riêng; không import mẫu thật hoặc sửa snapshot hiện hữu.

## 7. Compatibility audit đã có và kết quả còn thiếu

Audit join theo season/date/team/opponent/is_home; kiểm tra đúng hai phía và score trước khi tính source differences. Xuất xG/xGA, goals, shots, SOT của hai nguồn; delta = StrikerAPI − FBref. Chỉ số gồm mean absolute/signed/max xG difference, exact agreement rates và missingness/coverage.

Đây không phải predictive MAE của LR. Một trận/hai dòng không chứng minh population compatibility, không có threshold tự approve. Khác biệt có thể do model, penalty handling, shot coverage, rounding, corrections hoặc định nghĩa shots/SOT.

**Không có compatibility metrics từ dữ liệu thật trong phase này.** Trường nào thiếu thực tế ở La Liga 2023 và team-match xG có usable hay không đều chưa xác nhận. Tài liệu mô tả get_game có xG/SOT; mock tests không thay thế response thật. Vì vậy không kết luận StrikerAPI xG tương đương FBref/Opta hoặc sẵn sàng cấp dữ liệu cho frozen LR.

## 8. Kiểm thử và bảo toàn

Các tests mới ở test_strikerapi_client.py, test_strikerapi_normalization.py, test_strikerapi_compatibility.py; fixtures tổng hợp ở strikerapi_fixtures.py. Không dùng credentials thật, internet hoặc credits. Bao phủ env/redaction, auth/HTTP/JSON, budget/persistence/cache/no retry, contract/envelope, league, identity/aliases/timezones, hai perspective, thiếu/invalid stats, shot coverage và metric correctness.

Kết quả cuối: **150 tests qua, failures=0, errors=0, skipped=0**; gồm 109 tests cũ và 41 tests mới: client 18, normalization 13, compatibility/workflow 10. Đã chạy unittest discovery riêng với `test_strikerapi*.py`, rồi chạy toàn bộ `tests/test_*.py` bằng Python unittest discovery/TextTestRunner. Log và thời gian thực tế được lưu tại [test_results.json](../outputs/provider_poc/reports/test_results.json).

Kiểm thử ledger hỏng đã bắt một handle SQLite chưa đóng trong nhánh lỗi Windows; đã sửa trước lần chạy cuối. Bằng chứng an toàn và nguyên trạng: [security_and_integrity.json](../outputs/provider_poc/reports/security_and_integrity.json). Không coi các mocked workflows thành bằng chứng kết nối live.

Hashes trước triển khai: [protected_files.json](../outputs/provider_poc/reports/protected_files.json). Verification cuối phải đối chiếu đủ 107 file, bao gồm model, metadata, history SQLite, frozen datasets và outputs/báo cáo Phase 1–8. Không ghi vào manifests cũ, không chạy Phase 7 evaluation hoặc production export.

## 9. Lệnh đã thực thi và lệnh tiếp theo

Đã kiểm tra môi trường có python-dotenv 1.2.3 và requests 2.34.2; không cài dependency mới hoặc sửa pins Phase 8. Đã đọc docs/schema công khai, chạy hai command dry-run và tests offline. Không chạy --execute cho endpoint dữ liệu: billable requests=0, credits consumed=0; actual credit headers chưa có.

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts/data_provider/requirements.txt
.\.venv\Scripts\python.exe -m scripts.data_provider.test_connection
.\.venv\Scripts\python.exe -m scripts.data_provider.compatibility_audit
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_strikerapi*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Lệnh pip là hướng dẫn cài khi cần, không phải đã cài lại trong lượt triển khai. Suite đầy đủ được chạy bằng unittest discovery/TextTestRunner tương đương command cuối và lưu log.

Khi người dùng quyết định chi credits cho mẫu thật, command riêng cần chủ động chạy:

```powershell
.\.venv\Scripts\python.exe -m scripts.data_provider.compatibility_audit --execute --max-credits 25
```

## 10. Giới hạn và bước tiếp theo

Chưa có kiểm chứng auth/live La Liga response/credit header semantics/field availability. Cần mẫu overlapping thật trước khi nghiên cứu compatibility. Không reset ledger để retry; PoC chưa có explicit retry command. Contract drift hoặc credit ledger không xác minh được phải dừng review.

Shot-map team/season có cap 2.000 trong mô tả và không có offset trong schema input hiện tại. Chưa kiểm chứng đầy đủ games, unlocated shots hoặc pagination nên chưa được kết luận có thể backfill cả mùa bằng một call, chưa ước lượng complete-season backfill cost. SOT match-level vẫn cần nguồn được xác minh riêng.

Không trộn provider trong snapshot store. Nếu mẫu về sau đạt validation, chỉ cân nhắc staging riêng và review compatibility/coverage có trách nhiệm; không bật production flags tự động. Không backfill, scheduler, model retraining, migration production hoặc Phase 9 website.

Hướng dẫn vận hành: [STRIKERAPI_POC_GUIDE.md](../docs/STRIKERAPI_POC_GUIDE.md). Nghiên cứu provider compatibility vẫn chưa được chấp nhận cho tới khi có và phân tích dữ liệu overlap thật.

## 11. File bàn giao

Thêm `scripts/data_provider/`: `__init__.py`, `strikerapi_client.py`, `test_connection.py`, `sample_selector.py`, `normalize_strikerapi.py`, `compatibility_audit.py`, `strikerapi_contract.json`, `requirements.txt`.

Thêm ba module tests được yêu cầu và `tests/strikerapi_fixtures.py`, hướng dẫn PoC này cùng đúng một báo cáo hiện tại. `outputs/provider_poc/reports/` giữ kế hoạch, kết quả tests, bảo toàn/security và manifest; raw/cache/samples/comparisons bị ignore bằng `.gitignore` riêng của PoC.

File tracked duy nhất thay đổi có chủ đích là `.env.example`, chuẩn hóa khai báo key rỗng. Không sửa `.env`, root `.gitignore`, module inference, datasets, artifacts hoặc kết quả/báo cáo cũ. Không commit/push.
