# XPECTA Phase 8.5.5 — Rolling Pre-Match Forecast

Option B thêm bước kiểm tra eligibility, điều phối inference và lưu phiên bản dự báo JSON. `CompositePredictor` tiếp tục gọi đúng Feature Builder và Linear Regression V1. Forecast là xG tổng kỳ vọng của từng đội trong trận. Prediction dùng nguồn hỗn hợp ở chế độ `RESEARCH_INFERENCE` và có `production_approved=false`.

## Quy tắc eligibility 1.0

Ứng dụng chọn Composite History đã xác minh từ kho nghiên cứu bằng snapshot version. Nó lấy UTC hiện tại từ đồng hồ hệ thống và truyền `min(UTC-date, match_date)` cho Composite Feature Builder. Chỉ trận đã xác minh có ngày nhỏ hơn cutoff được đưa vào lịch sử. Lượt tính vượt sang ngày UTC mới hoặc tới kickoff sẽ trả lỗi để đánh giá lại.

| Điều kiện | Kết quả |
|---|---|
| Fixture tồn tại, còn scheduled, kickoff UTC ở tương lai và đủ dữ liệu | `READY` |
| Đủ dữ liệu hiện tại, còn fixture của một trong hai đội trước target có thể bổ sung lịch sử sau cutoff | `EARLY_READY` |
| Thiếu proof về kickoff, lịch, freshness, coverage, hoặc có trận thiếu thống kê trong actual last-five | `WAITING_DATA` |
| Không tìm thấy fixture, fixture ngoài roster, conflict, đã bắt đầu, completed hoặc không còn scheduled | `UNAVAILABLE` |

Forecast yêu cầu kickoff UTC xác minh được, kể cả target ngày tương lai. Nếu fixture trung gian cùng ngày cần giờ để xác lập thứ tự mà thiếu kickoff, eligibility chờ dữ liệu. Trận cùng ngày cutoff luôn ngoài cửa sổ, kể cả khi snapshot có kết quả. Calendar coverage, continuous stint, số trận đã xác minh, actual last-five và zero-history do Feature Builder hiện có xác định. Chính sách 45 ngày áp dụng cho ngày trận gần nhất của đội có lịch sử. Với zero-history đã xác minh, membership và calendar là điều kiện để tiếp tục.

Schedule freshness v1.0 dùng **48 giờ kể từ lần quan sát nguồn**, theo chính sách bảo thủ của lớp forecast. Vì thiết kế không ấn định số giờ, giá trị này được chọn để vận hành demo và được version hóa cùng policy. Observation phải có trong provenance fixture của snapshot, hoặc được khôi phục từ manifest và CSV legacy khớp checksum đã attested. Thời gian dựng lại DB không gia hạn freshness. Lần refresh chỉ đổi metadata có thể trả `NO_CHANGE` và giữ nguyên observation cũ. Snapshot không đủ proof mới vẫn trả `WAITING_DATA`.

Snapshot thật phải đã được dựng tại thời điểm yêu cầu. Proof hoàn tất và thời điểm lấy thống kê được kiểm tra khi dùng. Ngoại lệ cho timestamp fetch chưa biết chỉ áp dụng cho nguồn FBref đóng băng đã attested. Historical replay V3 là workflow riêng; cutoff theo ngày không chứng minh dữ liệu của snapshot hiện tại đã có sẵn trong quá khứ. Clock mô phỏng chỉ có trong cấu hình synthetic và ghi `SYNTHETIC_DEMO`.

## Versioning và diễn giải

Mỗi lần ghi tạo record mới qua writer lock và atomic create. Dữ liệu forecast được tách khỏi kho Composite History. Việc chọn lại cùng history hoặc chọn successor có lineage hợp lệ cho phép tính lại. Nếu target date/kickoff, model và feature input khớp bản gần nhất, ledger kiểm tra parity rồi trả ID đó. Forecast đổi lịch là một revision kể cả khi xG giống nhau. `INITIAL`/`UPDATED` chỉ thứ tự bản ghi, độc lập với `READY`/`EARLY_READY`.

So sánh V1/V2 trình bày thay đổi feature, cửa sổ lịch sử, provenance và xG. Hiệu số không xác định quan hệ nhân quả. Research inference thành công chưa xác nhận accuracy trên nguồn hỗn hợp hay tính tương đương FBref/Understat/Sportmonks.

Xem cấu hình và giao diện Python trong [Forecast Data Contract](FORECAST_DATA_CONTRACT.md), cách chạy trong [Forecast Demo Guide](FORECAST_DEMO_GUIDE.md).
