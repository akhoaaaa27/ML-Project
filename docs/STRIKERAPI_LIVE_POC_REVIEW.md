# Review công khai: StrikerAPI Live PoC La Liga

Báo cáo dùng allowlist. Không công bố response, provider game ID, dataset từng dòng, shot records, auth headers hoặc numerical source comparisons.

Phiên bản code được chạy: `84f14fd0638661c44933f917ce69effe518252ff`; nhánh `phase8.5.1-strikerapi-live-audit`.

Bắt đầu UTC: `2026-11-21T11:39:09+00:00`; hoàn tất UTC: `2026-11-21T11:39:11+00:00`.

## Kết quả thực thi

| Câu hỏi | Quan sát |
|---|---|
| Đã chạy controlled live audit? | Có |
| Authentication đã được xác nhận? | Có |
| Reference fixture đã ghép đúng? | Có |
| get_game thành công? | Có |
| Đủ hai team perspectives? | Có |
| Normalization theo Phase 8 schema thành công? | Có |
| Comparison với FBref đã chạy? | Có |
| get_shot_map được gọi / cần thiết? | Không / Không |
| Có cấu trúc phù hợp để nghiên cứu tiếp? | Có |
| Đã approve production? | Không |

## Endpoint và credits

| Endpoint | HTTP status | Documented credits |
|---|---:|---:|
| list_games | 200 | 2 |
| get_game | 200 | 5 |

Số calls đã thử/reserve: **2**. Documented cost của lượt này: **7**; cumulative reserved: **7**; trần cộng dồn **25**.

Chỉ công bố documented/reserved credits; không suy diễn billing từ response headers chưa xác minh semantics.
Actual billed total: **chưa xác nhận độc lập**. Không đăng credit/auth headers.

## Field availability

| Field | Trạng thái kiểm chứng |
|---|---|
| xg | `available_both_teams` |
| xga | `derived_from_validated_opponent_xg` |
| goals | `available_both_teams` |
| sh | `available_both_teams` |
| sot | `available_both_teams` |

Nguồn xG đã xác minh ở mức phương thức: `published_team_match`. xGA có thể là opponent reversal đã validate, không nhất thiết là native field của provider.

Mã kiểm tra: `AUTHENTICATION_CONFIRMED`, `FIXTURE_MATCH_CONFIRMED`, `NORMALIZATION_SUCCEEDED`, `COMPARISON_COMPLETED`.

Missing fields: không ghi nhận trong evidence hiện có; xem trạng thái availability ở trên.

## Compatibility và giới hạn công bố

Principal blocker: `SINGLE_FIXTURE_INSUFFICIENT`.

Nếu comparison đã chạy, đó là source difference StrikerAPI − FBref, không phải predictive error/MAE của frozen LR. Exact metrics, thống kê và bảng từng phía được giữ trong private local evidence; báo cáo public không chứa toàn bộ statistical audit.

Một fixture không đủ để chấp nhận tính tương đương xG hoặc production compatibility. Cấu trúc đủ dùng chỉ là căn cứ để cân nhắc mẫu nghiên cứu lớn hơn, với review định nghĩa, as-of/revision behavior, completeness và quyền dữ liệu. `production_approved: false`.

## Kiểm thử và bảo toàn

Full suite: run=160, failures=0, errors=0, skipped=0.

File nghiên cứu giữ nguyên: Có; model và history store giữ nguyên: Có; .env ignored/untracked: Có.

## Bước tiếp theo

Cần mẫu compatibility lớn hơn theo phạm vi/budget được cho phép riêng. Nếu lần này chưa xác minh được dữ liệu, phải xử lý blocker trước; không tự retry, mở rộng mẫu hoặc bỏ qua validation. Không backfill, scheduler, retraining, migration production hoặc Phase 9 trong lượt này.

Lệnh đã dùng cho live attempt:

```powershell
.\.venv\Scripts\python.exe -m scripts.data_provider.compatibility_audit --execute --max-credits 25
```

[Báo cáo JSON public](../outputs/provider_poc/reports/live_review_public.json)
