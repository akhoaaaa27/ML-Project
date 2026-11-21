# Bàn giao cho đội website Phase 9

Phase 8 chưa có web server, routes chạy thật, FastAPI/Flask/Streamlit hoặc frontend. Những routes bên dưới là hợp đồng đề xuất để đội website triển khai, không phải dịch vụ đang hoạt động.

## Luồng backend

1. Thiết lập môi trường theo DEPLOYMENT_GUIDE.md và mount artifact/metadata trusted chỉ đọc.
2. Tạo `HistoryStore` theo cấu hình backend. Với provider đã review, dùng `load_provider_policy(path)` do quản trị kiểm soát.
3. Khởi tạo một `FixturePredictor` ở startup; lỗi artifact/env là lỗi readiness, không gọi export/fit để tự chữa.
4. Validate request theo INFERENCE_API.md, chỉ truyền identity/ngày/mùa/mode/cutoff, không nhận 13 features từ người dùng.
5. Gọi `predictor.predict(...)`, trả nguyên cấu trúc status/error và provenance phù hợp UI.
6. Refresh chạy bởi tác vụ ingestion riêng. Sau refresh, inference query read-only lấy store mới; không reload/train model trừ khi quản trị chuyển một artifact đã review riêng.

```python
from scripts.inference.history_store import HistoryStore, load_provider_policy
from scripts.inference.predict_fixture import FixturePredictor

# Cấu hình server, không lấy đường dẫn từ request body:
history = HistoryStore()
predictor = FixturePredictor(history)

def handle_prediction(body):
    return predictor.predict(
        body["home_team"], body["away_team"], body["match_date"], body["season"],
        mode=body.get("mode", "replay"),
        prediction_cutoff=body.get("prediction_cutoff"),
    )
```

Backend phải bổ sung kiểm tra required fields/body object trước đoạn gọi ví dụ. Không cho request tùy ý chọn database, policy, model path hoặc upload `.joblib`. Frontend không load model và không sao chép công thức rolling.

## Routes đề xuất

| Route | Request | Response/nguồn Python |
|---|---|---|
| GET /api/teams | Không có body | Array `{id,name,aliases}` từ TEAM_IDS/ALIASES; chỉ những đội mapping đã review |
| GET /api/fixtures | Query `mode`, `season` tùy backend | Replay: metadata completed trong matches; upcoming: schedule verified. Không trả fixtures tự bịa từ cặp đội được gõ tay |
| GET /api/data-status | Không có body | `history.data_status()` + kiểm tra readiness artifact; UI phải giữ cảnh báo chưa đủ provider/coverage |
| POST /api/predict | JSON theo INFERENCE_API.md | Object success hoặc error cùng schema thư viện, không thay thiếu dữ liệu bằng xG=0 |

Request tối thiểu:

```json
{"home_team":"Athletic Club","away_team":"Getafe","match_date":"2024-08-15","season":2024,"mode":"replay"}
```

`/api/fixtures` là adapter cần xây ở Phase 9; có thể query metadata `matches` và `schedule` qua HistoryStore.query bằng SQL cố định/parameterized. Không expose SQL tùy ý. `/api/teams` dùng ID ổn định dạng `athletic-club`, tên canonical hiển thị và alias tường minh. Mapping mới cần review ingestion và kiểm thử.

Đề xuất HTTP mapping: 200 cho success; 422 cho request/unknown team/identity; 409 cho incomplete/stale/unverified/provider chưa phù hợp; 503 cho artifact/env/history store chưa sẵn sàng. Đây là convention gợi ý, chưa phải web implementation. Giữ `error.code` ổn định cho frontend dù chọn HTTP status khác.

## UX và dữ liệu không khả dụng

Replay phải gắn nhãn mô phỏng trước trận từ snapshot; actual xG nếu hiển thị cần panel sau trận tách biệt. Upcoming chỉ hiển thị dự báo nếu status=success và data_status=verified. `STALE_DATA`, `COVERAGE_UNVERIFIED`, `FIXTURE_UNVERIFIED` hoặc provider lỗi cần thông báo lý do và tắt dự báo; không fallback sang form tháng 9/2025 cho lịch cuối 2026.

Ngày dùng ISO date-only. Ngày fixture theo nguồn được review, cutoff mặc định upcoming dựa ngày UTC hiện tại. Không tự đổi múi giờ của normalized date hoặc suy diễn giờ từ CSV cũ. Kickoff mới được lưu nhưng chưa thay đổi replay. API không có confidence interval cho từng dự báo, xác suất thắng, scoreline hoặc shot probability; không diễn giải hai giá trị xG thành những đại lượng đó.

Global max date trong data-status chỉ là thông tin snapshot, không là readiness của một fixture. Upcoming gate kiểm tra từng đội, từng coverage và lịch trận. Manual request không trở thành lịch chính thức chỉ vì người dùng nhập đúng định dạng.

## Bàn giao và trách nhiệm còn lại

Đã có model, Python/CLI offline, feature reconstruction, trusted loader, validation, import transaction và tài liệu. Đội website cần triển khai routes/UI, auth/access control, quản lý cấu hình trusted, readiness/observability, lựa chọn provider và lịch refresh được phê duyệt. Chưa có nguồn API thật hoặc scheduler để kết nối ngay. Không dùng XGBoost cho deployment; chỉ LR được chỉ định production.
