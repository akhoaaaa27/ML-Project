# XPECTA UI-01 Overview refinement

## Tóm tắt

Overview giữ sân vận động, logo, giao diện kính tối, typography, điểm nhấn xanh, thanh điều hướng và cấu trúc sáu trang của V9.12. Hero gọn hơn, thẻ trận hiển thị xG dự đoán khi preview hợp lệ, leaderboard dùng nhãn Observed xG và Footer dùng thống nhất thương hiệu XPECTA.

Nhánh `ui-01-overview-refinement` bắt đầu từ `main` tại `d42df9b`. Đợt rà soát đối chiếu website do FastAPI phục vụ, HTML V9.12, tài liệu `Overview_XPECTA.docx`, các tài liệu và bài kiểm thử Phase 9. HTML gốc được dùng làm tham chiếu bố cục. Dữ liệu trận, xG và thống kê của website đến từ API. [Setup V3 và logo](https://github.com/akhoaaaa27/ML-Project/pull/9) · [Setup REAL_RESEARCH](https://github.com/akhoaaaa27/ML-Project/pull/8) · [Phase 9](https://github.com/akhoaaaa27/ML-Project/pull/7)

## Hạng mục hoàn thành

| Hạng mục | Thay đổi |
| --- | --- |
| OV-01 · Hero | Bỏ hai chú thích kỹ thuật và ngày cutoff hiển thị cạnh Hero. Giữ ảnh, tiêu đề, mô tả, vị trí và kiểu của hai CTA. Cutoff vẫn thuộc dữ liệu và chính sách backend. |
| OV-03–06 · Upcoming Matches | Dùng thẻ trận hiện có và thay dòng trạng thái cũ trên Overview bằng vùng xG. Dùng tối đa sáu trận từ thứ tự hiện tại. Giữ nút mở chi tiết và View All Matches. Dùng nhãn mùa vì CSV lịch V3 và đối tượng `Fixture` của API chưa cung cấp vòng đấu đã xác minh. |
| OV-07–10 · The Numbers Behind the Game | Xóa đoạn liệt kê nguồn dài. Giữ tooltip nguồn từng đội, xếp hạng, biểu đồ, huy hiệu và bộ chọn mùa. Hai thẻ giữ bố cục song song trên desktop. Tổng số trận lịch sử lấy từ API có phạm vi rộng hơn phạm vi mùa của leaderboard. |
| OV-11–12 · Footer | Dùng lại logo XPECTA có tagline Expect the Unexpected. Explore có sáu trang. Information giữ About the Model và Understanding xG. Chỉ báo mode hiện hữu trên thanh điều hướng. |

## Tích hợp xG

1. Overview chọn tối đa sáu fixture theo catalogue hiện có, rồi gọi `GET /api/v1/eligibility` cho từng thẻ hiển thị.
2. Chỉ `READY` và `EARLY_READY` mở `POST /api/v1/forecasts/preview`. Endpoint này chạy suy luận theo cơ chế hiện có và trả preview, không ghi Forecast Ledger. Catalogue Prediction tiếp tục hiển thị dự báo đã công bố theo giao diện hiện có.
3. Trước khi hiển thị, client kiểm tra mã trận, thời điểm kickoff, cutoff, phiên bản model, phiên bản snapshot, SHA-256 của History Store và ngữ cảnh dữ liệu. Hai giá trị hợp lệ theo thứ tự chủ nhà rồi đội khách, với hai chữ số thập phân. `0.00` được hiển thị nguyên giá trị.
4. Preview trên lịch thật hết hạn tại mốc sớm nhất trong ba mốc gồm kickoff, giới hạn tuổi bằng chứng lịch từ API và kết thúc ngày cutoff UTC. Client hủy request khi rời Overview, bỏ phản hồi của lượt cũ và chỉ cập nhật vùng xG trong thẻ. Các lần render cùng lượt và cùng dữ liệu dùng chung nhóm request.

| Trạng thái | Thẻ hiển thị |
| --- | --- |
| READY | Hai giá trị và nhãn Predicted xG |
| EARLY_READY | Hai giá trị và nhãn Predicted xG · Early forecast |
| WAITING_DATA | — VS — và Prediction pending |
| UNAVAILABLE | Prediction unavailable |
| LOADING | Checking prediction… |
| FORECAST_ERROR | Could not load forecast |

## File thay đổi

| File | Phạm vi |
| --- | --- |
| [prepare_frontend.py](../scripts/xpecta_api/prepare_frontend.py) | Biến đổi Hero, nhãn dữ liệu và Footer khi tạo HTML tích hợp. |
| [api.js](../web/xpecta/api.js) | Bổ sung request eligibility và tín hiệu hủy request tùy chọn. |
| [app.js](../web/xpecta/app.js) | Điều phối request, kiểm tra ngữ cảnh và thời hạn preview của Overview. |
| [view.js](../web/xpecta/view.js) | Sáu trạng thái vùng xG, tooltip provenance ở leaderboard. |
| [phase9.css](../web/xpecta/phase9.css) | Vị trí CTA, vùng xG, hai thẻ thống kê và khung logo Footer. |
| [browser_ui01.py](../tests/browser_ui01.py) | Kiểm thử trình duyệt thực và mock API cô lập, ghi bằng chứng vào thư mục local. |
| [UI_01_OVERVIEW_REFINEMENT.md](UI_01_OVERVIEW_REFINEMENT.md) | Báo cáo triển khai và kiểm thử. |

## Visual QA và ảnh đối chiếu

Ảnh đầy đủ nằm trong `data/external/multisource/phase857/ui-01/` trên máy triển khai. Thư mục được Git bỏ qua. `comparison.png` ghép ảnh trước và sau. Thư mục `before/` cũng có ba ảnh tham chiếu `*-v912.png`.

| Viewport | Ảnh baseline | Ảnh sau | Kết quả |
| --- | --- | --- | --- |
| Desktop 1440 × 900 | [Trước](../data/external/multisource/phase857/ui-01/before/desktop-baseline.png) | [Sau](../data/external/multisource/phase857/ui-01/verified/desktop-overview.png) | Sáu thẻ, lưới 3 × 2, hai thẻ thống kê song song. |
| Tablet 820 × 1180 | [Trước](../data/external/multisource/phase857/ui-01/before/tablet-baseline.png) | [Sau](../data/external/multisource/phase857/ui-01/verified/tablet-overview.png) | Sáu thẻ, hai cột, thống kê xếp dọc. |
| Mobile 390 × 844 | [Trước](../data/external/multisource/phase857/ui-01/before/mobile-baseline.png) | [Sau](../data/external/multisource/phase857/ui-01/verified/mobile-overview.png) | Sáu thẻ, một cột, nội dung không tràn ngang. |

Chiều cao Hero lần lượt là 570, 550 và 575 px ở cả hai bản. Tiêu đề, mô tả và các CTA giữ nguyên kích thước và vị trí tương đối trong Hero, chênh lệch dưới 0,01 CSS px. Kiểm tra bàn phím gồm focus qua Footer và mở đúng chi tiết từ nút View Prediction ở cả ba viewport. Mock có nhãn `UI-01 MOCK` và ảnh `verified/mock-forecast-states.png`, `verified/mock-tablet-forecast-states.png` và `verified/mock-mobile-forecast-states.png`.

## Kết quả kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| `tests.test_phase857_api`, `tests.test_phase96_research`, `tests.test_forecast_eligibility`, `tests.test_forecast_integration` | 42/42 PASS. |
| `python -m unittest discover -s tests -v` | 366/367 PASS. `test_no_raw_data_in_public_reports_or_tracked_paths` FAIL do `main` đã theo dõi CSV lịch và snapshot V3 mà test cũ cấm. `git ls-tree` xác nhận cả hai đường dẫn trên base. UI-01 không thay đổi dữ liệu hay test đó. |
| `tests.browser_ui01` | PASS trên Edge 158, ba viewport. Công cụ kiểm tra UI thật, 0/4/8 fixture, giới hạn sáu lượt kiểm tra mỗi lần vào trang, số 0, READY/EARLY_READY, lỗi HTTP 503, digest sai, expiry, hủy request khi rời trang, đổi mùa và điều hướng Footer. |
| `tests.browser_phase9` | PASS, 18 cặp ảnh giữa sáu trang ở ba viewport. Catalogue, thống kê, detail và Custom Matchup hoạt động. Không có lỗi console hay request publish. |
| `tests.browser_phase857` | PASS, 18 cặp ảnh và 43 ảnh kiểm thử. |
| Cú pháp và bảo toàn dữ liệu | `node --check`, Python compile và `git diff --check` đạt. Đối chiếu 77 và 107 mục bảo vệ, 13 feature và tám hash DB/manifest của snapshot đạt. |

Runtime `REAL_RESEARCH` dùng snapshot `phase853_v3_20261122`. API báo `UNVERIFIED` do bằng chứng lịch hết hạn. Cả sáu thẻ đầu hiển thị `WAITING_DATA` trên cả ba viewport. Forecast Ledger ở mức 0 trước và sau kiểm thử thật. Các giá trị dương và `0.00` được kiểm tra riêng trong mock trình duyệt. Xác nhận bằng một forecast đủ điều kiện trên dữ liệu thật vẫn cần bằng chứng lịch hợp lệ.

## Ma trận nghiệm thu

| ID | Kết quả | Bằng chứng |
| --- | --- | --- |
| AC-01 | PASS | Hai phần tử chú thích đã được xóa khỏi HTML Overview. |
| AC-02 | PASS | Ảnh và số đo trước/sau xác nhận bố cục Hero và hai CTA. |
| AC-03 | PASS | Mock cô lập xác nhận UI hiển thị đúng xG nhận từ API và kiểm tra context. Các bài test forecast xác nhận API preview dùng model thật. Kiểm tra xG trên thẻ với trận thật hiện bị giới hạn bởi lịch hết hạn. |
| AC-04 | PASS | Sáu thẻ thật ở trạng thái pending, không có số giả. Mock kiểm tra pending, unavailable, lỗi preview và sai context. |
| AC-05 | PASS | Thẻ giữ nhãn mùa sau khi xác nhận dữ liệu và API chưa có vòng đấu đã xác minh. |
| AC-06 | PASS | Đã kiểm tra sáu trạng thái và số 0 hợp lệ. |
| AC-07 | PASS | Lưới 3/2/1 cột. Với 0/4/8 fixture, số thẻ là 0/4/6. |
| AC-08 | PASS | Đã bỏ đoạn nguồn dài, tooltip nguồn từng đội vẫn hiện diện. |
| AC-09 | PASS | UI dùng Selected season · Observed xG per match. |
| AC-10 | PASS | Ảnh xác nhận bố cục. Đổi mùa gọi API và cập nhật leaderboard. |
| AC-11 | PASS | Tổng lịch sử khớp API và giữ nguyên khi đổi mùa. |
| AC-12 | PASS | Logo khớp với thanh điều hướng. Sáu liên kết Explore mở đúng trang. |
| AC-13 | PASS | Đã bỏ chú thích thừa, About the Model và Understanding xG hoạt động. |
| AC-14 | PASS | Hai bộ hồi quy trình duyệt hiện có đều đạt trên ba viewport. |
| AC-15 | PASS | Kiểm tra hash, feature order và diff xác nhận các thành phần khoa học được giữ nguyên. |
| AC-16 | PASS | Không có request publish. Tổng Ledger thật giữ ở 0. |
| AC-17 | PASS | Lưu ảnh trước/sau và ghi rõ lỗi full suite có sẵn cùng giới hạn của dữ liệu thật. |

## Chạy localhost

Từ thư mục gốc, dùng Python trong `.venv` để tạo lại frontend từ HTML V9.12 có sẵn trên máy. Sửa đường dẫn HTML theo vị trí file của bạn.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.xpecta_api.prepare_frontend 'D:\Downloads\XPECTA_V9_12_Glass_Navigation (2).html'
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-xpecta.local.ps1
```

Mở Overview trên localhost. Nếu server đã chạy, script mở trình duyệt khi readiness khớp `REAL_RESEARCH` và snapshot V3. Với máy chưa có script local hoặc môi trường Python, làm theo các bước cài đặt và chạy API trong hướng dẫn tích hợp. [Overview trên localhost](http://127.0.0.1:8765/#home) · [Website Integration Guide](WEBSITE_INTEGRATION_GUIDE.md)

Để lặp lại UI test, giữ API trên cổng 8765, cài thư viện theo `scripts/xpecta_api/requirements-test.txt`, dùng Edge và chạy `python -m tests.browser_ui01 --run-id ui01-local-check`. Chọn run ID khác nếu thư mục kết quả đã tồn tại.
