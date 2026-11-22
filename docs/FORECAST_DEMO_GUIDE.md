# XPECTA Forecast Demo

Chạy từ repo với môi trường đã pin. Chọn một tên mới cho mỗi lần demo.

```powershell
.venv/Scripts/python.exe -m scripts.multisource.forecast_demo --name defense-855
```

Kết quả tổng hợp và `demo-manifest.json` nằm dưới `data/external/multisource/forecasts/demos/defense-855/`. Manifest ghi Git revision, policy, catalogue/model/snapshot binding, simulated timestamps, môi trường và kết quả. SQLite và forecast records nằm riêng trong cùng thư mục ignored.

| Demo | Kết quả cần xem |
|---|---|
| A | Snapshot đầu có trận trung gian chưa hoàn tất, forecast revision 1 là `INITIAL/EARLY_READY` |
| B | Workflow refresh Phase 8.5.4 chấp nhận một kết quả tổng hợp mới, forecast revision 2 là `UPDATED/EARLY_READY` |
| C | Snapshot control có cùng feature, trả `NO_CHANGE` và giữ đúng hai bản ghi |
| D | Thiếu thống kê ở actual last-five, trả `WAITING_DATA/MISSING_ROLLING_STATISTICS` |
| E | Fixture không tồn tại trả `UNAVAILABLE`; test có sẵn cũng kiểm kickoff đã đến |
| F | Replay V3 giữ parity của pipeline hiện có; cần local V3 và ba CSV tham chiếu Phase 8.5.2 |

A–E có clock mô phỏng và dữ liệu tổng hợp. F chạy replay nghiên cứu trên bộ tham chiếu local; nếu input riêng tư vắng mặt, manifest ghi `BLOCKED` cho F. Forecast thật dùng thời gian UTC thực tế, không cho truyền cutoff tùy ý.

Kiểm tra snapshot thật mà không ghi forecast bằng `data-status`, `eligibility` hoặc `list-fixtures`. Lấy key từ catalogue local. `generate` chỉ ghi khi forecast đủ điều kiện.

```powershell
.venv/Scripts/python.exe -m scripts.multisource.forecast_cli data-status --snapshot phase853_v3_20261122
.venv/Scripts/python.exe -m scripts.multisource.forecast_cli list-fixtures --snapshot phase853_v3_20261122 --season 2026 --include-unavailable
.venv/Scripts/python.exe -m scripts.multisource.forecast_cli eligibility --snapshot phase853_v3_20261122 --fixture "<canonical_fixture_key>"
.venv/Scripts/python.exe -m scripts.multisource.forecast_cli generate --snapshot phase853_v3_20261122 --fixture "<canonical_fixture_key>"
```

`get <forecast_id>`, `list-forecasts --fixture <key>` và `compare --fixture <key> <v1> <v2>` đọc ledger thật. Muốn trình bày V1/V2 tổng hợp, mở hai JSON trong thư mục demo hoặc gọi các phương thức đọc trên service synthetic có cấu hình giống runner.

Khi bảo vệ, trình bày xG là expected total team goals, khác xác suất thắng. Forecast sớm dùng cutoff tại lúc tạo, kết quả trận trung gian chưa vào history. Forecast cập nhật có thể cùng xG. Cutoff theo ngày, không chạy real-time hoặc backdate. Nguồn hỗn hợp chưa được đánh giá equivalence hay predictive accuracy mới. Freshness của snapshot thật thay đổi theo thời gian và production approval luôn tắt.
