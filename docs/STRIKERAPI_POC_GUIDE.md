# Chạy StrikerAPI PoC và đối chiếu FBref

Phase 8.5.1 đã có implementation offline và mock tests. **Chưa gọi endpoint tính phí hoặc thu mẫu trận thật.** Người dùng quyết định thời điểm chạy live bằng `--execute`. Không backfill, scheduler, retraining hoặc migration production trong phase này.

## 1. Môi trường và credentials

Chạy tại repository root, dùng `.venv` hiện có:

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts/data_provider/requirements.txt
```

Dependencies PoC: `python-dotenv==1.2.3`, `requests==2.34.2`, đã có trong môi trường kiểm tra; không cần cài lại và không sửa pins Phase 8. `zoneinfo` dùng dữ liệu timezone sẵn có với pandas trên môi trường hiện tại; đã kiểm tra Europe/Madrid.

Người dùng tự quản lý `.env` ở root với biến `STRIKERAPI_API_KEY`. Client dùng `python-dotenv`, không interpolate hoặc ghi file. Biến môi trường đã có ưu tiên hơn `.env`. Không đưa key vào command line, JSON body, URL hoặc log. `.env.example` chỉ giữ:

```dotenv
STRIKERAPI_API_KEY=
```

`.env` đang bị Git ignore và không tracked. `.env.example` được phép version-control, đã chuẩn hóa key rỗng. PoC chỉ in boolean credential_present; điều đó chưa xác nhận auth đúng. Key thật không được gửi đến schema URLs công khai.

## 2. Lệnh tiếp theo: dry-run không tốn credits

```powershell
.\.venv\Scripts\python.exe -m scripts.data_provider.test_connection
.\.venv\Scripts\python.exe -m scripts.data_provider.compatibility_audit
```

Hai lệnh mặc định không GET/POST mạng, không validate auth bằng API, không tạo reservation credit. Connection report kiểm tra root, `.env` presence, key presence, Git ignore, base URL và budget.

Fixture mặc định: `local_match_id=1521`, Almeria–Rayo Vallecano, 2023-08-11, mùa 2023, kết quả FBref 0–2. Đây là một fixture Development đã có đầy đủ dữ liệu. Chọn lại cùng đầu vào luôn ra cùng trận; không tìm ngẫu nhiên hoặc tự đổi trận nếu provider không ghép được.

Kế hoạch request, không tính cache:

| Bước | Endpoint | Credits | Cộng dồn tối đa |
|---|---|---:|---:|
| 1 | list_games | 2 | 2 |
| 2 | get_game | 5 | 7 |
| 3, chỉ khi cần khôi phục xG thiếu | get_shot_map | 10 | 17 |

Giá đã đối chiếu từ [catalogue công khai](https://mcp.strikerapi.com/v1/tools) và [OpenAPI](https://mcp.strikerapi.com/openapi.json) ngày 2026-11-21. Mỗi live client phải đọc lại hai schema không auth và so sánh contract/cost trước POST đầu tiên. Drift sẽ dừng, không tự sửa contract hoặc thử request tiếp.

## 3. Lệnh live chỉ khi người dùng chủ động cho phép chi credits

```powershell
.\.venv\Scripts\python.exe -m scripts.data_provider.compatibility_audit --execute --max-credits 25
```

Không cần chạy connection live trước: command audit đã bao gồm list_games. Nếu chỉ muốn thử riêng connection, command sau tối đa dùng một list_games 2 credits:

```powershell
.\.venv\Scripts\python.exe -m scripts.data_provider.test_connection --execute --max-credits 25
```

Connection và audit dùng cùng discovery params/cache, tránh tính phí trùng. Thành công connection chỉ chứng minh gọi được request đó, không chứng minh compatibility.

PoC giới hạn budget cấu hình từ 0 đến 25. Budget áp dụng **cộng dồn qua các lần chạy dùng cùng local ledger**, không reset mỗi process. Client giữ reservation ngay trước POST bằng SQLite transaction; lỗi/timeout vẫn giữ chi phí dự kiến vì chưa biết refund thực tế. Không suy diễn actual credits từ tên header chưa xác minh; chỉ lưu các credit headers có giá trị số. Đây không phải phép đo số dư tài khoản hoặc những request thực hiện bằng công cụ khác.

Request không đủ budget bị chặn trước POST; nếu bước shot_map thiếu budget, PoC dừng và giữ cache của các bước trước. Cache hợp lệ dùng lại không tốn credit. Không có retry tự động, không nhận redirect, timeout tường minh; fingerprint từng request đã lỗi/không chắc trạng thái không tự được gọi lại. PoC hiện không cung cấp lệnh retry. Không xóa/reset ledger để thử lấy kết quả đẹp; cần review trạng thái và ngân sách trước một chính sách retry tường minh ở bước phát triển sau.

Plan được in vào stderr trước request; JSON report ở stdout và reports/. Không in raw HTTP headers hoặc provider error body. Lỗi `BUDGET_UNVERIFIABLE`, `SCHEMA_DRIFT`, `CACHE_CORRUPT`, `PREVIOUS_ATTEMPT_UNRESOLVED` cần dừng review, không tự bypass. Live command cần quyền mạng khi chạy trong sandbox; quyền tải schema không đồng nghĩa đã cho phép chi credits.

## 4. Request shapes đã pin

Discovery lấy đúng một ngày, không query cả mùa:

```json
{"league":"laliga","season":2023,"date":"2023-08-11","timezone":"Europe/Madrid","status":"final","limit":20}
```

Sau khi ghép chắc chắn, game_id là giá trị nhận từ list_games, không phải local match_id:

```json
{"league":"laliga","game_id":"<ID đã ghép từ list_games>"}
```

Chỉ nếu box scores thiếu team xG nhưng các thống kê khác đủ:

```json
{"league":"laliga","game_id":"<cùng ID>","include_shots":true}
```

REST POST tới `https://mcp.strikerapi.com/v1/{tool_name}`, auth bằng header nội bộ x-api-key. Contract yêu cầu envelope `data`; ví dụ trang endpoint trình bày phần data bên trong. Không dùng query-string credential hoặc MCP envelope thay REST.

`strikerapi_contract.json` chứa schema/cost chọn lọc đã bỏ mô tả, có hashes nguồn. OpenAPI response mới kiểm tra container; nhiều leaf objects là free-form, adapter kiểm tra tiếp field-level theo ví dụ chính thức. Đây không phải JSON Schema validator tổng quát hoặc bằng chứng La Liga response thực đã đủ fields.

## 5. Ghép FBref và adapter

Ghép season, ngày, canonical home/away và final score; không fuzzy matching. Alias dùng mapping Phase 8 hiện có, chưa hard-code provider IDs. Exact date phải khớp; nếu có starts_at aware thì ngày Europe/Madrid cũng phải khớp. Mâu thuẫn UTC/local date bị từ chối để review, không tự dùng cửa sổ ±1 ngày. Snapshot cũ chưa xác nhận timezone kickoff nên đây là quy tắc bảo thủ.

`list_games` có offset/next_offset trong machine schema và trang endpoint. PoC không tự phân trang; đoạn conventions chung hiện có mô tả khác nên không dùng nó để suy đoán pagination. Không có đúng một match chắc chắn thì dừng.

`get_game.team_stats` phải khớp hai team IDs và home flags. Adapter cần goals, xg, shots, shots_on_target hữu hạn; kiểm tra số nguyên, sh≥sot, score reversal và xG/xGA reversal. Tạo đúng hai team-match rows theo Phase 8 schema. `quality_status=verified` chỉ nghĩa là các thống kê bắt buộc của mẫu đã validate, **không phải** provider được phê duyệt production.

Nếu thiếu SOT, không suy đoán từ outcome hoặc get_team_stats trung bình mùa; không xuất CSV import-ready. Nếu xG thiếu, shot-map fallback chỉ chấp nhận đủ counts mỗi team, toàn bộ located shots, không unlocated/truncated/missing xG/duplicate, đúng game/date/team và tổng xG khớp dung sai làm tròn 0,011. Dùng abbrev đã lấy từ fixture, không gán tổng hai đội cho một đội. Giữ rõ xg_source là published team xG hay raw shot aggregation cho cả hai đội.

`statistics_version=response_sha256:...` là version snapshot local, không được coi là revision ID của provider. Không thay schema Phase 8 để chấp nhận record thiếu. Mẫu hợp lệ có thể được review/import vào **store staging riêng**; PoC command không ghi vào history snapshot thật và không bật provider production policy.

## 6. Outputs và quyền dữ liệu

| Đường dẫn | Nội dung | Git |
|---|---|---|
| reports/connection_report.json | Readiness và metadata an toàn | Có thể review |
| reports/poc_summary.json | Kế hoạch/kết quả và diagnostics sanitized | Có thể review |
| reports/protected_files.json | Hash file Phase 1–8 | Có thể review |
| reports/test_results.json | Kết quả kiểm thử offline | Có thể review |
| raw/ | Schema đã tải, sanitized response cache và credit ledger | Ignore |
| samples/reference_fixture.json | Fixture FBref local | Ignore |
| samples/expanded_sample_plan.csv | 24 trận dự kiến, không gọi mạng | Ignore |
| samples/*_team_matches.csv | Chỉ tạo nếu live sample đủ thống kê | Ignore |
| comparisons/*_fbref_comparison.csv | Sai khác theo từng phía | Ignore |

`.gitignore` riêng của PoC chặn raw/samples/comparisons/staging/logs/temp/SQLite. Không commit raw responses trước review quyền sử dụng/phân phối. [Chính sách dữ liệu của provider](https://strikerapi.com/docs/timing-and-rights) cần được kiểm tra trước khi đưa dữ liệu ra ngoài nghiên cứu nội bộ; không coi dịch vụ là dữ liệu giải đấu chính thức.

## 7. Đọc compatibility audit và bước sau

Audit ghi xG/xGA, goals, shots và SOT của mỗi nguồn, delta = StrikerAPI − FBref, mean absolute/signed/max source difference và exact agreement rates. Đây **không phải predictive MAE của LR**. Một trận/hai dòng không đủ chứng minh population compatibility; không có ngưỡng tự động approve.

Chưa có mẫu thật nên hiện chưa có compatibility metrics hoặc kết luận xG usable thực tế. Tài liệu mô tả get_game có các trường cần thiết, nhưng availability/null/coverage ở La Liga 2023 vẫn phải xác minh bằng response thật. Các khác biệt có thể do xG model, penalties, shot coverage, rounding, corrections hoặc cách tính shots/SOT.

Shot-map theo team/season có cap 2.000 shot records được mô tả và không có offset trong input schema hiện tại. Chưa xác minh coverage/missing games bằng live data; không thể tuyên bố một call đủ tái dựng cả mùa hoặc tính chi phí backfill hoàn chỉnh. Shot map cũng không tự cung cấp SOT match-level theo hai phía. Kế hoạch 24 trận chỉ để review, không có lệnh bulk-execute.

Bước sau Phase 8.5.1 cần mẫu overlapping thật, mở rộng có budget riêng, review source/model/time semantics và coverage, rồi mới cân nhắc connector/staging. Không tự migrate snapshot, đổi 13 features, retrain LR, backfill, scheduler hoặc website.
