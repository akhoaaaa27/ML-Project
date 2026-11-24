# XPECTA UI-02 đến UI-06

## Tóm tắt

Nhánh `ui-02-06-website-refinement` bắt đầu từ `554769b`, commit đã tích hợp UI-01. Năm trang còn lại giữ bố cục V9.12 và dùng dữ liệu của FastAPI. Prediction có bộ lọc cặp đội và hiển thị xG hợp lệ ngay trên thẻ. Custom Matchup chạy mô hình Linear Regression V1.0.0 trên lịch sử đã xác minh. Prediction History hiển thị cả Forecast Ledger chính thức và các mô phỏng lưu trong trình duyệt. AI Model dùng một cohort duy nhất cho bốn KPI và hai biểu đồ chính.

Đã đối chiếu FastAPI với HTML V9.12 có SHA-256 `f5aada29…` và năm tài liệu trên máy gồm `Prediction_XPECTA.docx`, `Match Analysis_XPECTA.docx`, `Team Statistics_XPECTA.docx`, `Prediction History_XPECTA.docx` và `AI Model_XPECTA.docx`. [Pull request UI-01](https://github.com/akhoaaaa27/ML-Project/pull/10)

## UI-02 · Prediction

- **PR-01–03.** TEAM 1 và TEAM 2 dùng catalogue và ID của API. Có tìm kiếm bỏ dấu, chọn bằng chuột hoặc bàn phím và tùy chọn All teams. Cặp lọc đối xứng và giữ cả hai lượt thi đấu nếu thỏa điều kiện. Hai ô From và To dùng cùng lớp giao diện với các trường khác. To bao gồm trọn ngày UTC. Fixture Discovery được bỏ phần Schedule Evidence. Lý do eligibility vẫn có khi mở chi tiết.
- **PR-04.** Overview và Preset Fixture dùng chung cách hiển thị xG. Client chỉ kiểm tra trận thuộc nhóm thẻ đang hiện, giới hạn bốn tác vụ đồng thời, và chỉ gọi preview nếu eligibility trả READY hoặc EARLY_READY. Đổi bộ lọc hoặc rời trang hủy request của nhóm cũ. Preview được đối chiếu với model, snapshot, digest, fixture và thời hạn. Trận đã hoàn thành chỉ có thể hiển thị bản dự báo đã công bố phù hợp ngữ cảnh, có nhãn Published xG. Nhãn mùa được dùng khi thiếu vòng đấu đã xác minh.
- **PR-05–08.** GENERATE SIMULATION gọi `POST /api/v1/simulations` với hai ID đội. API chọn mùa chung gần nhất và một cutoff UTC chung theo ngày trong snapshot. Cutoff lấy mốc sớm nhất giữa ngày UTC hiện tại, ngày sau trận hoàn thành đã xác minh gần nhất trong mùa, và hai biên coverage theo đội. Dữ liệu ngay ngày cutoff bị loại. API từ chối cùng đội, đội lạ, không có mùa chung, hoặc lịch sử thiếu cho mô phỏng.

Custom Matchup dùng chung kiểm tra provenance, stint liên tiếp, cửa sổ tối đa năm trận, 13 feature và pipeline đóng băng với dự báo chính thức. Mô phỏng cần lịch sử hợp lệ cho cả hai đội. Trận đối đầu đã diễn ra có thể được dùng làm lịch sử nếu đứng trước cutoff, vì mô phỏng không có trận đích. API trả hai xG theo vai trò sân nhà và sân khách, thời điểm tạo, cutoff, model, snapshot và digest của dữ liệu, model, feature. Response không có mã fixture, stage hoặc revision. Không ghi Forecast Ledger.

Với V3, mô phỏng Málaga sân nhà gặp Barcelona trả **1.02 và 2.00 xG**. Đảo vai trò sân nhà cho Barcelona trả **2.35 và 0.66 xG** theo thứ tự mới. Đây là mô phỏng nghiên cứu dựa trên lịch sử, với diễn giải xG cấp đội.

## UI-03 · Match Analysis

**MA-01–07 và MA-09.** Rút gọn mô tả và heading, bỏ nhãn Historical Data, chú thích cutoff và các danh sách provider được chỉ định. Giữ mùa, kích thước cửa sổ, số quan sát có xG, bar chart, kiểm tra coverage, và provenance phía API. Chọn cùng đội báo `Select two different teams to analyze.` và xóa kết quả cũ.

**MA-08.** Match Insights so sánh observed xG, observed xGA và điểm trên mỗi trận trong cửa sổ đã chọn. Diễn giải đội tạo nhiều xG hơn, đội có xGA thấp hơn và kết quả gần đây dựa trên điểm. Vai trò Home/Away dùng để bố trí và tô màu. Insight xử lý giá trị bằng nhau và thể hiện rõ khi dữ liệu chưa đủ.

## UI-04 · Team Statistics

**TS-01–03.** Dùng màu xanh XPECTA cho số trung bình xG của Home và cam cho Away. Căn hai nội dung Home/Away và để thẻ dừng theo chiều cao nội dung, độc lập với thẻ Team Comparison cao hơn. Team Comparison giữ huy hiệu, xG/xGA, mùa và coverage. Các danh sách provider được bỏ khỏi phần chú thích hiển thị.

## UI-05 · Prediction History

**PH-01–03.** Dùng cùng dropdown tìm đội với Prediction. Bộ lọc Record type tách Official Match Forecast và Custom Simulation. Forecast Stage áp dụng cho bản dự báo chính thức. Sau một mô phỏng hợp lệ, trình duyệt ghi một mục `localStorage` có UUID, tách namespace real và synthetic, rồi hiển thị lại sau reload. Bản ghi lưu đủ metadata của API để đối chiếu lần chạy. Lỗi ledger, lỗi storage và từng mục hỏng có thông báo riêng. Chi tiết và so sánh revision chính thức tiếp tục truy cập API hiện có. Export ghi thêm `record_type` và `simulation_id` để phân biệt loại bản ghi, cùng các trường revision và digest đã dùng cho forecast.

Mô phỏng local thuộc origin và hồ sơ trình duyệt hiện tại. Ví dụ dữ liệu trên cổng 8766 thuộc origin khác với cổng 8765. Không yêu cầu migration cơ sở dữ liệu.

## UI-06 · AI Model

**MLUI-01–04.** Backend dùng `main_final_test` từ [metrics Phase 7](../outputs/final_test/final_test_metrics.csv) và [kết quả cấp đội](../outputs/final_test/final_test_predictions.csv). Backend đối chiếu checksum theo [manifest](../outputs/final_test/final_test_manifest.json) và tính lại MAE, RMSE từ chính các điểm gửi cho hai chart.

| KPI | Main Final Test · FBref |
| --- | ---: |
| MAE | 0.5665 |
| RMSE | 0.7497 |
| BASELINE MAE | 0.6368 |
| MAE IMPROVEMENT | 11.03% |

Main Final Test có 380 trận, 760 quan sát cấp đội, từ 15 Aug 2024 đến 25 May 2025. Mức cải thiện dùng MAE chưa làm tròn, theo công thức `(baseline − model) / baseline × 100`. Scatter dùng toàn bộ 760 quan sát, cùng phạm vi trên hai trục và đường `y = x`. Biểu đồ residual dùng `observed − predicted`. Để các cột đọc được, biểu đồ lấy 85 quan sát bằng quy tắc lấy mỗi quan sát thứ chín sau khi sắp theo ngày, trận và Home/Away, bắt đầu tại quan sát đầu tiên. Quy tắc cố định theo thứ tự thời gian, độc lập với dấu và độ lớn sai số.

Evaluation evidence trong trang vẫn có các cohort Main, Supplemental, Understat và Sportmonks cùng giới hạn của phép đánh giá. [Protocol](../outputs/final_test/evaluation_protocol.json) · [Metadata mô hình](../models/model_metadata.json) · [Báo cáo retrospective](PHASE_8_5_6_VALIDATION.md)

## UTC+0

Giao diện hiển thị timestamp theo mẫu `28 Nov 2026 · 15:15 UTC+0` bằng chuyển đổi instant có offset sang UTC. Các trường ngày lịch sử, ngày cutoff và ngày của điểm đánh giá giữ dạng ngày. Card không có kickoff đã xác minh hiển thị ngày, kèm trạng thái Kickoff unverified. Bộ lọc so sánh ngày UTC của kickoff thực, loại bản ghi không có kickoff khi lọc theo ngày và bao gồm đến hết To. API và CSV tiếp tục dùng timestamp ISO cho dữ liệu có giờ.

## File thay đổi

| Thành phần | File |
| --- | --- |
| Feature engineering và inference | `scripts/multisource/composite_features.py`, `composite_history.py`, `composite_inference.py`, `features.py` |
| FastAPI và tái lập frontend | `scripts/xpecta_api/app.py`, `schemas.py`, `services.py`, `evaluation.py`, `prepare_frontend.py` |
| Frontend | `web/xpecta/api.js`, `app.js`, `view.js`, `fixtures.js`, `team-picker.js`, `simulations.js`, `evaluation-charts.js`, `phase9.css` |
| Kiểm thử | `tests/test_website_refinement.py`, `test_phase857_api.py`, `browser_ui0206.py`, `browser_ui01.py`, `browser_phase857.py`, `browser_phase9.py` |
| Báo cáo | `docs/UI_02_06_WEBSITE_REFINEMENT.md` |

## Kiểm thử và visual QA

| Phạm vi | Kết quả |
| --- | --- |
| API, xG, eligibility, lịch sử, Composite History | **82/82 PASS**. Có kiểm thử độc lập với fixture, hai hướng sân, thiếu rolling statistics, ràng buộc mô hình và API lịch sử. |
| Phase 7 evaluation | **18/18 PASS** với `python -m unittest discover -s tests -p test_final_test.py`. |
| Toàn bộ `unittest discover -s tests -v` | **369/370 PASS**. `test_no_raw_data_in_public_reports_or_tracked_paths` đã lỗi từ baseline UI-01 vì `main` theo dõi CSV lịch và snapshot V3 mà bài test cũ yêu cầu không theo dõi. Các đường dẫn có trên `origin/main` và giữ nguyên trong diff UI-02–06. |
| Edge · `tests.browser_ui0206` | **PASS** trên desktop, tablet và mobile. Kiểm tra tìm đội, đảo cặp lọc, cả ngày To, cùng đội, inference thật với Málaga và Barcelona, lưu rồi reload, CSV, Match Insights, khoảng đệm và màu Home/Away, bốn KPI và hai chart. |
| Edge · `tests.browser_ui01` | **PASS** trên ba viewport. Kiểm tra Hero, Footer, forecast states Overview/Prediction, số 0, sai digest, lỗi preview, hết hạn, rời trang và đổi bộ lọc khi còn request. |
| Edge · `tests.browser_phase9` | **PASS** trên ba viewport, 18 cặp ảnh của sáu trang. Dữ liệu thật kiểm tra trạng thái chờ và không đủ điều kiện. Không có lỗi console ngoài các lỗi chủ động đưa vào phiên thử nghiệm. |
| Edge · `tests.browser_phase857` | **PASS**, 18 cặp ảnh và 43 ảnh. Snapshot synthetic chạy model đóng băng để kiểm tra forecast có số, ledger có revision, hai loại bản ghi cùng hiển thị và bộ lọc stage chỉ giữ forecast. |
| Múi giờ | **PASS** với trình duyệt cấu hình UTC, Asia/Ho_Chi_Minh, Europe/Madrid và America/New_York. Kiểm tra timestamp chuyển ngày, To bao gồm đến 23:59:59 UTC và loại kickoff lúc 00:00 UTC ngày sau. |
| Toàn vẹn và tái lập | **PASS**. Trình tạo HTML giữ đúng hash V9.12. JS qua `node --check`. Git không có diff ở dữ liệu, mô hình hoặc file kết quả đánh giá. Backend kiểm tra digest V3, model và evidence Phase 7. |

Ảnh nằm trong các thư mục local được Git bỏ qua. Ảnh baseline lấy từ UI-01 đã merge và dùng đúng các viewport của lượt nghiệm thu. Bộ ảnh sau có các trang đầy đủ, gồm phần chart, Team Statistics và Prediction History có mô phỏng thật.

| Viewport | Đối chiếu trước và sau | Ảnh sau |
| --- | --- | --- |
| Desktop 1440 × 900 | [Năm trang](../data/external/multisource/phase857/ui-02-06/desktop-comparison.png) | [AI Model](../data/external/multisource/phase857/ui-02-06/acceptance/desktop-model.png) · [Prediction History](../data/external/multisource/phase857/ui-02-06/acceptance/desktop-history.png) |
| Tablet 820 × 1180 | [Năm trang](../data/external/multisource/phase857/ui-02-06/tablet-comparison.png) | [Match Analysis](../data/external/multisource/phase857/ui-02-06/acceptance/tablet-analysis.png) |
| Mobile 390 × 844 | [Năm trang](../data/external/multisource/phase857/ui-02-06/mobile-comparison.png) | [Prediction](../data/external/multisource/phase857/ui-02-06/acceptance/mobile-predict.png) · [Team Statistics](../data/external/multisource/phase857/ui-02-06/acceptance/mobile-stats.png) |

## Ma trận nghiệm thu

| ID | Trạng thái | Bằng chứng |
| --- | --- | --- |
| AC-01 | PASS | Bốn múi giờ trình duyệt và các mốc UTC chuyển ngày. |
| AC-02 | PASS | Hai dropdown chọn được bằng bàn phím từ catalogue. |
| AC-03 | PASS | Hai thứ tự chọn có cùng tập fixture, gồm cả hai lượt khi đủ điều kiện. |
| AC-04 | PASS | Hai ô ngày cùng hàng desktop, cùng chiều cao, nền, bo góc, cỡ chữ. To bao gồm trọn ngày UTC. |
| AC-05 | PASS | Fixture Discovery đã bỏ Schedule Evidence. Detail vẫn có lý do trạng thái. |
| AC-06 | PASS | Trình duyệt synthetic xác nhận xG từ model thật tại mốc 48 giờ. Browser mock kiểm tra READY, EARLY_READY, số 0, sai digest và lỗi. V3 thật chưa có preview số trong mẫu kiểm thử vì lịch đã hết hạn. |
| AC-07 | PASS | Kiểm thử vô hiệu hóa lookup fixture vẫn mô phỏng được qua API. |
| AC-08 | PASS | Málaga–Barcelona qua snapshot V3 và đối chiếu output với predictor đóng băng. |
| AC-09 | PASS | Cùng đội bị chặn ở UI/API Custom Matchup và trên Match Analysis. |
| AC-10 | PASS | Mô phỏng xuất hiện sau khi reload ở ba viewport. |
| AC-11 | PASS | Heading, mô tả và setup đã đối chiếu các nhãn được yêu cầu. |
| AC-12 | PASS | Coverage vẫn hiển thị và API giữ provenance. Các ghi chú được chỉ định đã được bỏ. |
| AC-13 | PASS | Kịch bản đội nhà cao hơn, đội khách cao hơn, bằng nhau và thiếu dữ liệu đều đã kiểm tra. |
| AC-14 | PASS | Computed CSS khớp màu Home xanh và Away cam ở ba viewport. |
| AC-15 | PASS | Đo khoảng đệm dưới venue grid trên ba viewport và xem ảnh. |
| AC-16 | PASS | Team Comparison giữ coverage và đã bỏ chuỗi provider. |
| AC-17 | PASS | Dropdown History lọc theo đội xuất hiện ở Home hoặc Away. |
| AC-18 | PASS | Browser synthetic có đồng thời hai loại bản ghi. Mock lỗi ledger và storage xác nhận thông báo riêng. |
| AC-19 | PASS | Kiểm tra Forecast Stage, chi tiết, so sánh revision và CSV. |
| AC-20 | PASS | Bốn KPI khớp artifact Main Final Test ở ba viewport. |
| AC-21 | PASS | Scatter có 760 quan sát đã đối chiếu artifact, trục và tooltips dùng dữ liệu thật. |
| AC-22 | PASS | Residual là observed trừ predicted, lấy 85 quan sát theo quy tắc cố định, có cột âm và dương. |
| AC-23 | PASS | Ảnh trước và sau xác nhận logo, sân vận động, màu và bố cục sáu trang. |
| AC-24 | PASS | Hồi quy UI-01 giữ hình học Hero, giới hạn sáu trận, navigation và detail. |
| AC-25 | PASS | Hash model và dataset, 13 feature, window và output đánh giá qua kiểm tra. |
| AC-26 | PASS | Các suite eligibility, integration và Composite History qua kiểm tra cutoff và forecast chính thức. |
| AC-27 | PASS | V3 thật có 0 bản ghi trong Ledger trước và sau, và browser không gửi request publish. |
| AC-28 | PASS | Lưu ảnh, chạy kiểm thử browser/API và ghi rõ một lỗi baseline trong toàn bộ suite. |

## Giới hạn

- Snapshot V3 có lịch ở trạng thái `UNVERIFIED`. Overview và Fixture Discovery thật trả `WAITING_DATA` cho các trận chưa có bằng chứng lịch hợp lệ. Giá trị forecast chính thức dương được thử riêng bằng snapshot synthetic chạy model đóng băng.
- Các mô phỏng dùng thống kê lịch sử có sẵn và các nguồn có thể khác định nghĩa. Kết quả không thể hiện tỷ lệ thắng hoặc độ chính xác triển vọng.
- Một bài kiểm tra policy repository vẫn thất bại trên đường dẫn đã có ở `main`. Báo cáo giữ nguyên kết quả đó.

## Chạy localhost

Chuẩn bị Python và tài liệu V9.12 theo [hướng dẫn tích hợp](WEBSITE_INTEGRATION_GUIDE.md). Trên máy hiện tại, dùng phiên UI-02–06 tại [localhost:8766](http://127.0.0.1:8766/). Có thể tạo lại frontend rồi chạy trên cổng mặc định như sau.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.xpecta_api.prepare_frontend 'D:\Downloads\XPECTA_V9_12_Glass_Navigation (2).html'
.\.venv\Scripts\python.exe -X utf8 -m scripts.xpecta_api.app
```
