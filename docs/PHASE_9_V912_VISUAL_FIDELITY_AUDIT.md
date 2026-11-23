# XPECTA V9.12 — Visual Fidelity Audit

**Audit hoàn tất trên cấu hình Synthetic Demo.** Bản tích hợp giữ khung V9.12, hình nền sân, logo, Montserrat, glass navigation và hai panel xG trong ca dự báo thành công. Khoảng cách đáng sửa nhất nằm ở bố cục trạng thái bị chặn, phần Match Insights bị bỏ, và việc mất kết quả khi quay lại từ Match Analysis. Chênh lệch 6 so với 4 fixture đến từ catalogue và bộ lọc, còn cách căn hàng cuối là lựa chọn bố cục có thể cải thiện. Phase 9 ở trạng thái đề xuất.

## Bản tham chiếu và môi trường đã kiểm tra

| Hạng mục | Bằng chứng |
|---|---|
| Git | Working tree `ded88cad1ecad32fe97035ed9e4a0cafb3cd0ba2` có cùng nội dung với `origin/main` tại `c3ea47017e71dea8577a3ccdcc8495cba6397b33`, merge PR #5. |
| HTML gốc | `D:/Downloads/XPECTA_V9_12_Glass_Navigation (2).html`. SHA-256 `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4` khớp yêu cầu và bản sao `reference.html`. |
| HTML tích hợp | SHA-256 `ffbff2be5620c920e10efb99a47a1f16e29640cef3a44fd7cfde319ac74f82fb`. CSS gốc là tiền tố nguyên vẹn sau chuẩn hóa newline. Bản chuẩn bị thêm 6 dòng CSS, chuyển font sang local, thay copy và thay renderer. Ảnh logo, ảnh xG guide và 28 khai báo crest được bảo toàn. |
| Localhost | `http://127.0.0.1:8765/`, `/api/v1/health/ready` trả `READY`. `SYNTHETIC_DEMO / defense-local-check / updated`, frozen LR 1.0.0, không bật operator writes, `production_approved=false`. SHA-256 snapshot đang phục vụ khớp file namespace `ff15939973c3079d046ae56e61ba31c1a7cdfa6aa6491840f1a0f83a73098242`. |
| Browser | Edge 158.0.4370.33, desktop 1440×900, tablet 820×1180, mobile 390×844, DPR 1, zoom 100%, UTC, locale en-GB. Cả hai bản dùng Montserrat variable local cùng file. |

Cổng 8765 chưa có listener khi bắt đầu. Audit khởi động một instance dùng namespace sẵn có. Playwright mở trực tiếp HTML gốc và localhost, phục vụ font của bản gốc từ cùng TTF local, chặn mạng ngoài, đợi network idle, font, ảnh và vùng loading ổn định, rồi chụp cùng vị trí cuộn. Ảnh full page ghi từ đầu trang, ảnh section có cùng selector hoặc được cắt theo tọa độ DOM. Animation bị tắt khi chụp. So sánh kết hợp kiểm kê DOM, computed CSS, kích thước, ảnh và pixel.

Ca dự báo thành công dùng **Custom Matchup Valencia–Real Madrid** ở cả hai bản để giữ cùng đội và panel. Bản gốc chạy mô phỏng sẵn có, localhost chạy Frozen LR. Một ca Preset thành công được kiểm riêng trên localhost. `WAITING_DATA`, `UNAVAILABLE`, loading chậm có kiểm soát và phản hồi API sai schema được chụp riêng. Không thay dự báo để căn ảnh. Không ghi forecast hoặc sửa namespace trong quá trình audit.

## Kiểm kê sáu trang

| Trang | Thành phần giữ được | Khác biệt về nội dung và cấu trúc |
|---|---|---|
| Overview | Hero và CTA, fixture grid, bảng xếp hạng có chọn mùa, thẻ Data Overview, khối giải thích xG, modal hướng dẫn, footer | Thẻ fixture dùng lịch snapshot và tình trạng forecast. Thứ hạng thêm nguồn. Modal xG hướng dẫn ngắn hơn. Số fixture và đội ít hơn nên chiều dài nội dung thay đổi. |
| Prediction | Preset và Custom, chọn đội, nút quay lại, hai panel xG, so sánh, tổng/chênh lệch, summary, thông tin và hai CTA ở ca thành công | Bỏ nhóm vòng giả, thêm tình trạng lịch và cutoff thật. Ca bị chặn hoặc lỗi chuyển sang bố cục rút gọn. |
| Match Analysis | Bộ chọn hai đội, Last 5/10, matchup, attack/defense, form, hai trend SVG, venue và H2H | Thêm bộ lọc mùa, thiếu Match Insights và CTA cuối, thiếu hai mini-card xG H2H, đổi cột H2H và màu đường trend. |
| Team Statistics | Bộ lọc, bốn chỉ số, nhóm Average Metrics, trend SVG, venue, comparison | Metadata nguồn đầy đủ hơn. Cặp crest đối chiếu biến mất trong comparison, còn crest đội chính lặp vào các ô venue. Trend dùng ngày. |
| Prediction History | Search, filter, sort, CSV, bảng và modal | Dùng forecast đã publish và immutable revision. Thêm so sánh revision; Clear filters chỉ làm sạch bộ lọc. Ledger đang chạy có 0 bản ghi. |
| AI Model | Hero, Task & Data, grid feature, bốn thẻ metric, hai khung chart, Limitations | Linear Regression và 13 feature thay cho nội dung XGBoost dự kiến. Biểu đồ minh họa được thay bằng hai khối aggregate đã kiểm chứng, chiều cao panel giảm. |

Logo, màu chủ đạo, lớp nền, overlay, kích thước thanh điều hướng và font giữ được ở các viewport kiểm tra. Ví dụ, thanh điều hướng cao **79/79 px** trên desktop và tablet, **66/66 px** trên mobile. Font hero là **64 / 36,9 / 31,2 px**, weight **800** ở cả hai bản. Hero Overview có hình học đúng nhau ở cả ba kích thước. Không thấy tràn ngang toàn trang trong bộ viewport này.

## Bốn vấn đề được nêu

### D-01 — Số thẻ và bố cục hàng cuối

HTML gốc có **20 fixture giả**, Home lấy **6**. Snapshot demo trả **24 fixture** qua hai mùa. Mùa 2026 có **12** gồm **7 completed** và **5 scheduled**. Điều kiện `upcoming=true` loại một scheduled đã qua ngưỡng kickoff và API trả **4/4**, giới hạn trang **100**. Client lấy toàn bộ trang rồi áp trần `.slice(0, 6)` trên Home, còn Preset hiển thị cả 4. DOM có đúng 4 thẻ. Desktop giữ ba cột rộng khoảng **397,3 px** với thẻ cao **234,8 px**, tạo hàng **3 + 1**. Tablet dùng hai cột, mobile một cột. Kích thước card và CSS không làm mất fixture.

Phase 9 nên căn giữa một hoặc hai thẻ ở hàng cuối desktop bằng bố cục chỉ tác động vị trí, giữ kích thước thẻ, thứ tự đọc và tab order. Với 0 fixture, dùng một vùng thông báo toàn hàng. Giữ các breakpoint tablet/mobile và đúng số bản ghi.

### D-02 — Thông tin trên từng thẻ

Thẻ tham chiếu có `SAMPLE ROUND 14`, ngày kiểu `23/11/2026`, hai số xG mô phỏng và CTA `VIEW PREDICTION`. Bản tích hợp dùng mùa `2026/27`, timestamp UTC, dấu gạch khi chưa publish và cùng CTA. Bỏ vòng giả và số xG minh họa là hiệu chỉnh bắt buộc. Cú pháp ISO dài, cách đặt badge mùa và chuỗi `Availability on selection` là lựa chọn trình bày. Có thể khôi phục bố cục ngày–badge gọn của V9.12, giữ timezone và nhãn synthetic, và dùng giá trị xG trên card chỉ với bản ghi published khớp fixture.

### D-03 — Thành công, chờ dữ liệu và lỗi

Trong ca Custom Matchup thành công, cả hai bản đều có **2 panel, 2 số xG, 2 thanh so sánh**, hai thẻ tổng/chênh lệch, Summary, Information và hai CTA. Hai panel gộp có cùng kích thước **1226×212,6 px** ở desktop, **768×166,7 px** ở tablet và **356×367 px** ở mobile. Bản tích hợp rút khoảng **66 px** ở chiều cao toàn khối kết quả desktop do bỏ bớt mô tả và thông tin bổ trợ.

Ca Preset `WAITING_DATA` thực tế chỉ render tiêu đề, badge, một dòng lý do; khối cao **219,8 px** trên desktop so với **1146,6 px** ở ca Preset thành công. `UNAVAILABLE` giữ tiêu đề và lý do, còn lỗi hợp đồng API được tiêm có kiểm soát chỉ trả một dòng alert. Không có số xG trong ba ca. Giữ nguyên điều kiện hiển thị số; Phase 9 nên dùng chung khung nhận dạng fixture và hai ô đội dạng trạng thái rỗng, nhãn `xG chưa có` và CTA phù hợp. Chỉ hiển thị thanh, tổng và chênh lệch khi có số hợp lệ.

### D-04 — Hình học, nhịp dọc và cuộn

Hero Overview desktop hai bản cùng vùng **[x=107, y=102, w=1226, h=572]**. Top grid Home lệch **−1 px** ở desktop và **−15 px** ở tablet/mobile do copy cao khác nhau. Vị trí bảng xếp hạng tablet dịch **−266,8 px**, phù hợp với mất một hàng card và −15 px copy. Đây là chênh lệch do nội dung và số hàng, không phải đổi gutter hay chiều rộng card.

Hai bộ lọc mùa/window trong Match Analysis giữ nguyên điểm đầu khối kết quả ở desktop và tablet. Trên mobile, khối controls tăng **82 px** và kết quả bắt đầu ở **817,2 px** thay vì **735,2 px**. Header Team Statistics desktop giữ điểm đầu trang kết quả, nhưng thêm dòng provenance làm grid metric bắt đầu thấp hơn **43,5 px**. Khi chọn ca chờ dữ liệu bằng thao tác thật, `scrollY=0`, topbar ở 0; điểm đầu kết quả là **398,2 / 335,4 / 453,1 px** ở desktop/tablet/mobile. Không tái hiện header che kết quả trong thao tác này. Ảnh cắt từ full page được dùng để đánh giá tiêu đề, vì locator screenshot tự cuộn có thể đưa topbar sticky vào ảnh section.

## Ma trận sai khác

Mỗi dòng bảo vệ dữ liệu, model, feature order, fitted preprocessing, provenance, eligibility, snapshot và ledger. Cột đề xuất giới hạn ở trình bày và kiểm thử với dữ liệu hợp lệ đang có. **A** là sai khác thị giác, **B** là sai khác chức năng, **C** là hiệu chỉnh khoa học, **D** là phụ thuộc dataset và **E** là chức năng tích hợp được chấp nhận. P1 ưu tiên cao, P2 trung bình và P3 tinh chỉnh. Không ghi nhận P0 trong các luồng đã kiểm tra.

| ID | Trang/khối | Gốc → tích hợp | Bằng chứng | Nguyên nhân | Loại | Mức | Đề xuất Phase 9 | Test đề xuất |
|---|---|---|---|---|---|---|---|---|
| D-01a | Overview/Preset • số thẻ | Home 6, Preset 20 → 4 ở cả hai | DOM Home/Preset; API 4/4 | Dataset và bộ lọc kickoff sắp diễn ra | D | P2 | Giữ count thật và giải thích snapshot khi ít fixture | Count DOM bằng API có tính cap Home, không có card giả |
| D-01b | Overview • hàng cuối desktop | Hai hàng đủ → hàng cuối một thẻ căn trái | desktop-home-*-section1.png | Grid ba cột chuẩn không có policy căn hàng thiếu | A | P2 | Căn giữa hàng thiếu ở desktop, giữ kích thước card và thứ tự | Fixture count 0–6 ở ba breakpoint, kiểm x của hàng cuối |
| D-02a | Fixture cards • số liệu | Vòng mẫu và xG mô phỏng → mùa, UTC, giá trị trống khi ledger rỗng | desktop-home-*-section1.png; fixtureCard | API không có round đã xác minh, render số từ ledger | C | P1 | Giữ provenance và chỉ dùng round đã xác minh; placeholder rõ trạng thái | Chụp card chưa publish và đã publish; kiểm không sinh giá trị số giả |
| D-02b | Fixture cards • metadata | Ngày ngắn và badge vòng → chuỗi ISO UTC dài và badge mùa | DOM .fixture-top; ảnh fixture section | Formatter và copy của renderer | A | P3 | Đặt ngày, giờ UTC và badge trong rãnh gọn; nút cùng dòng | So padding, số dòng, chiều cao CTA ở 390/820/1440 |
| OV-01 | Overview • rankings | 7 dòng → 4 với cùng cấu trúc bar | DOM .bar-row; Home section2 | Chỉ bốn đội synthetic đủ dữ liệu | D | P3 | Giữ thang thật, thêm chỉ dẫn coverage nhẹ | Count 0/1/4/7, chụp bar/empty |
| OV-02 | Overview • provenance và guide | Caption tĩnh, guide dài hơn → nguồn theo đội và guide rút gọn | desktop-guide-*.png; Home section2 | Copy mới và modal được viết lại | E | P3 | Giữ nguồn ở footer của card; phục hồi giải thích shot/team như ví dụ minh họa | Kiểm nguồn theo mùa và modal có định nghĩa ví dụ |
| PR-01 | Prediction • Preset | Hai nhóm vòng mẫu → một catalogue theo thời gian | desktop-predict-*-section2.png; presetFixtures | Dữ liệu thật theo fixture key, chưa có round đã xác minh | C | P2 | Giữ mật độ/heading nhóm; chỉ nhóm theo ngày khi cần và không gắn vòng giả | Nhóm đúng date, không có round suy diễn, thứ tự ổn định |
| PR-02 | Prediction • Custom | Cặp đội tùy chọn trong mock → lookup đúng fixture hiện tại | Custom success, unavailable; customPrediction | Forecast liên kết canonical fixture | E | P2 | Dùng cùng khung form và mô tả trường hợp không có fixture | Đội trùng, fixture có/không có và đã hoàn thành |
| D-03a | Prediction • ca thành công | Đủ panel và card với tóm tắt/caption dài → giữ block chính, copy ngắn hơn | desktop-success-*-custom-section-clean.png | Renderer thay narrative giả bằng source notice và metadata thật | C | P2 | Giữ text đúng nghĩa total team xG; thêm mô tả ngắn về ngữ nghĩa và cutoff trong các ô có sẵn | 2 panel, comparison, tổng/chênh lệch, summary, info và CTA theo thứ tự |
| D-03b | Prediction • xG khi bị chặn | Mock có thể sinh số → không có số khi WAITING_DATA/UNAVAILABLE | *-waiting-integrated-*, *-unavailable-integrated-* | Eligibility trả forecast null | C | P1 | Giữ forecast null và lý do rõ ràng | Assert 0 giá trị xG và không có thanh/tổng/chênh lệch |
| D-03c | Prediction • khung trạng thái | Khung kết quả nhiều phần → badge/alert ngắn, lỗi API mất định danh trong vùng kết quả | waiting/unavailable và desktop-api-error-integrated-injected-*.png | `prediction()` return sớm; lỗi/loading dùng `display()` | A | P1 | Khung nhận dạng chung, placeholder đội, CTA retry/chọn trận theo loại lỗi | Baseline riêng cho READY, waiting, unavailable, API error và loading; vị trí focus và CTA |
| D-04a | Overview • nhịp dọc | Nhiều hàng hơn và copy dài hơn → nội dung sau fixture lên sớm | Tọa độ Home trong DOM; hero bằng nhau | Chiều cao copy và số hàng | D | P3 | Cho chiều cao theo nội dung, giữ gap và anchor | Chụp 0/4/6 thẻ, đo quan hệ section thay vì y tuyệt đối |
| D-04b | Match Analysis • mobile | Controls 126,9 px → 208,9 px; kết quả thấp hơn 82 px | mobile-analysis-*-full.png; DOM .analysis-controls | Thêm season field trong stack mobile | E | P2 | Dồn mùa và Last 5/10 vào hàng khi đủ chỗ; giữ tap target và nhãn | So geometry và tab order ở 390 px, Last 5/10 chạy được |
| MA-01 | Match Analysis • Insights | Có Match Insights và CTA cuối → không render | DOM .analysis-insights-card; full page | matchAnalysis renderer kết thúc sau H2H | B | P1 | Khôi phục tóm tắt mô tả và CTA; ghi rõ coverage, không gọi là giải thích model | Assert heading/CTA sau H2H với đủ hoặc thiếu coverage |
| MA-02 | Match Analysis • quay lại dự báo | Giữ preview cùng cặp đang xem → reset Custom và ẩn kết quả | desktop-return-from-analysis-*.png; return-flow.json | Handler `data-to-custom` luôn gọi `resetPrediction("custom")` | B | P2 | Giữ trong bộ nhớ kết quả đúng fixture/snapshot khi quay lại; không tái publish | Prediction → Analysis → Prediction cùng fixture; cặp mới không thừa kế số cũ |
| MA-03 | Match Analysis • venue/H2H scope | Vai trò qua lịch sử và tối đa 5 đối đầu → split trong cửa sổ, H2H theo mùa | DOM venue/H2H; MatchAnalysis contract | Dữ liệu phục vụ đã khóa scope theo mùa và window | C | P2 | Thể hiện mẫu số Last N/season ngay trong card; giữ tuyến kiểm soát dữ liệu | Đủ/thiếu/zero coverage, kiểm phạm vi ngày và mẫu số |
| MA-04 | Match Analysis • H2H presentation | Hai mini-card xG, cột đội nhà/khách có crest → chỉ W/D/L, bảng Venue và score theo đội được chọn | analysis section5; H2H headers | Template rút gọn dù contract có mean xG/xGA, venue và đối thủ | A | P2 | Phục hồi hai mini-card và cột đối ứng bằng dữ liệu hiện có; hiện gạch khi null | H2H có/không có dòng; Home/Away score và xG đúng chiều |
| MA-05 | Match Analysis • trend | Lime/orange sáng → shared chart palette xanh đậm/cam | desktop-last10-trends-*.png; CSS/SVG stroke | Dùng chung `trend()` với Team Statistics | A | P2 | Truyền palette theo chart đã đối chiếu trên nền tối, giữ null gaps | Check stroke, legend, contrast và SVG geometry |
| ST-01 | Team Statistics • provenance | Mùa 2024/25, matchweek → mùa mặc định 2025/26, ngày và nguồn | stats full; DOM select và SVG text | Mùa hiện có khác và contract không xác minh matchweek | C | P2 | Giữ ngày và số trận quan sát; đặt provenance gần metadata | Kiểm mùa, nhãn ngày, mẫu số Goals−xG và null gap |
| ST-02 | Team Statistics • hierarchy | Có hai crest trong comparison, venue boxes đơn giản → bỏ cặp crest và lặp crest trong venue | stats full/section1; teamStats | Dùng lại `venue()` và thay layout comparison | A | P2 | Khôi phục crest pair đối chiếu; rút gọn vai trò venue | Assert vị trí crest, 4 metric cards và cặp chart qua breakpoint |
| HI-01 | History • nguồn và empty | Mock browser history → ledger immutable, thực tế 0 dòng | Desktop/tablet/mobile History; GET /forecasts | Preview chỉ đọc và namespace chưa publish | D | P2 | Giữ empty state có giải thích, không tự lưu preview | Chụp empty thật, xác nhận preview không đổi ledger |
| HI-02 | History • revision và phạm vi CSV | Type và xóa lịch sử local → stage filter, Clear filters, CSV theo bộ lọc, V1/V2 | *-history-integrated-replay-*.png; supplemental-evidence.json | Tính năng ledger và UI mới | E | P2 | Ghi rõ CSV của trang lọc, giữ thao tác so sánh riêng | Replay read-only: lọc, sort, reset, CSV scope, modal revisions |
| HI-03 | History • nhấn giá trị | XG xanh/cam in đậm từng bên → ô số đơn sắc trong bảng | Reference populated/replay table; historyTable | Renderer bỏ lớp nhấn numeric | A | P3 | Khôi phục màu/weight theo side và giữ contrast | So computed color/weight, kiểm container cuộn mobile |
| MO-01 | AI Model • dữ liệu | Planned XGBoost, 12 feature, scatter/residual giả → frozen LR, 13 feature, Phase 7/8.5.6 aggregate | model full, modelScatter/modelResidual, API model | Hiệu chỉnh model và metric bắt buộc | C | P1 | Giữ label period/provider riêng; dùng đúng aggregate | Assert thứ tự 13 feature, 2 nhóm metric và không dùng placeholder giả |
| MO-02 | AI Model • khung chart | 2 SVG cao 300,5 px desktop → 2 stack bar cao 160 px | desktop-model-*-section2/3; DOM | Chart form mới không dự trữ chiều cao cho plot/legend | A | P2 | Khôi phục khung chart cân chiều cao bằng aggregate bars có scale và chú giải | So khung/card, scale và label ở cả ba viewport |
| GL-01 | Navigation • badge | DEMO badge ẩn ở tablet/mobile → SYNTHETIC DEMO luôn hiện | *-menu-*.png; topbar geometry | Override responsive trong prepare_frontend | E | P3 | Giữ badge dễ thấy và menu/branding ở vị trí cũ | Kiểm badge, hamburger, focus và không tràn 390 px |

## Bằng chứng và giới hạn

Tất cả ảnh và DOM thô nằm trong `data/external/multisource/phase857/v912-audit-20261123/`. Tên ảnh trang là `{desktop|tablet|mobile}-{home|predict|analysis|stats|history|model}-{reference|integrated}-full.png`. Cùng tiền tố, `section1` trở đi tương ứng với các khối đã chọn trong [JSON của audit](PHASE_9_V912_VISUAL_FIDELITY_AUDIT.json). `dom-evidence.json` giữ headings, bảng, controls, geometry, màu, font và biểu đồ. `raster-evidence.json` là sai khác RGB tuyệt đối trung bình trong viewport đầu, chỉ để định vị vùng cần xem. Ví dụ desktop Overview là **1,57/255**, mobile Match Analysis là **15,20/255**; hai số gồm khác biệt về copy và dataset nên không dùng làm ngưỡng pass.

| Bằng chứng | Đường dẫn hoặc mẫu tên local |
|---|---|
| Tổng quan ảnh đã rà | [Desktop](../data/external/multisource/phase857/v912-audit-20261123/review-desktop.png), [tablet](../data/external/multisource/phase857/v912-audit-20261123/review-tablet.png), [mobile](../data/external/multisource/phase857/v912-audit-20261123/review-mobile.png) |
| D-01/D-02 | `desktop-home-*-section1.png`, `*-predict-*-section2.png` |
| D-03/D-04 | `*-success-*-custom-section-clean.png`, `*-success-integrated-preset-full.png`, `*-waiting-integrated-*`, `*-unavailable-integrated-*`, `desktop-api-error-integrated-injected-*`, `desktop-loading-integrated-injected-*` |
| Last 10, guide và quay lại | `desktop-last10-trends-*.png`, `desktop-guide-*.png`, `desktop-return-from-analysis-*.png` |
| History | `*-history-*-full.png` là empty state thực tế; `*-history-reference-demo.png` và `*-history-reference-details.png` là lịch sử mock của phiên browser; `*-history-integrated-replay-*.png` là render từ hai revision synthetic đã có |

Run so sánh chính hoàn thành **18 cặp full page**, cùng ảnh section và trạng thái, không có lỗi console, promise hoặc request ghi nhận. Ảnh loading được tạo bằng trì hoãn browser fetch; ca API error dùng phản hồi sai schema được tiêm chỉ trong browser. Trên Last 10, bản gốc có 20 dòng form, còn demo có 9 dòng do giới hạn dữ liệu. Hai đường trong chart dùng `#86ef70 / #ff8a57` ở gốc và `#2f8601 / #ff5f25` ở bản tích hợp.

History populated, filters, CSV và V1/V2 dùng replay response từ ledger synthetic cũ đã xác minh qua reader, giữ dữ liệu nguyên giá trị. Đây là bằng chứng renderer, khác với live endpoint của namespace đang audit. Trên mobile cả hai bảng giữ vùng cuộn ngang riêng rộng 318 px. Nội dung bảng rộng 759 px ở gốc và 709 px ở replay tích hợp.

- **BLOCKED tại live namespace** cho kiểm tra History có revision thật và card có xG published. GET của namespace hiện tại có 0 bản ghi; ảnh replay là bằng chứng bổ sung. Không publish để lấp dữ liệu.
- **BLOCKED** cho tái hiện đúng viewport của ảnh desktop do người dùng mô tả. Không có file ảnh hoặc kích thước viewport hiệu dụng trong đầu vào audit này. Đã kiểm tra desktop chuẩn 1440×900 và xác nhận độc lập D-01/D-02 bằng DOM/API.

## Khoảng trống bộ test Phase 8.5.7

`tests/browser_phase857.py` có kiểm tra sáu trang, font, tràn ngang document, menu mobile, badge, preview, WAITING_DATA/live, lịch sử, CSV và xử lý lỗi. Với 18 cặp ảnh, hàm `geometry()` chỉ so chiều ngang/cao topbar, background, backdrop filter và `object-fit` logo. `await_page()` chờ một phần tử chính trên mỗi trang. Không có so sánh tự động về section inventory, vị trí/kích thước controls, card count và hàng cuối, panel trước/sau loading, layout so sánh chart, table clipping, số điểm/legend, nav che nội dung hay section thiếu như Match Insights. Kết quả PASS của suite đó xác nhận phạm vi kiểm tra này.

## Luồng implementation đề xuất cho Phase 9

1. **Khung dự báo và điều hướng.** Dùng cùng shell cho success/loading/waiting/unavailable/error, cả Preset và Custom. Giữ kết quả cùng fixture khi quay lại từ Analysis trong phiên browser. Chỉ render giá trị xG cho trạng thái đủ điều kiện và giữ nguồn, cutoff, synthetic badge.
2. **Fixture và nhịp dọc.** Căn hàng cuối theo breakpoint; rút gọn metadata ngày/UTC, trạng thái; giữ 0/1/2/4/6 thẻ và đúng thứ tự. Giữ chiều rộng tuyệt đối của thẻ và xử lý copy dài bằng layout thay vì dữ liệu bổ sung.
3. **Analysis và Team Statistics.** Khôi phục Match Insights có nhãn mô tả, CTA và H2H panel, dùng đúng season/window và available coverage. Căn gọn controls mobile. Khôi phục crest pair, palette và chart legend.
4. **History, Model và regression.** Khôi phục nhấn số Home/Away và ghi rõ phạm vi CSV, giữ revision và quyền read-only. Dàn lại aggregate chart với khung V9.12, giữ 13 feature và provenance. Chốt baseline theo trạng thái, desktop/tablet/mobile bằng dữ liệu test có schema rõ ràng.

### Tiêu chí nghiệm thu hình ảnh đề xuất

- Kiểm kê theo page/section và thứ tự các khối ở cả ba viewport. Các phần giữ gốc có computed geometry và font khớp trong dung sai **2 px** ở vùng ổn định; ghi lý do cho vùng có copy hoặc control mới. Ảnh chuẩn có full-page, section, visible controls, font ready và dữ liệu cố định theo trạng thái.
- Home/Preset hiển thị đúng số lượng API, không placeholder fixture, không tự tạo xG. Với hàng 1/2 thẻ ở desktop giữ chiều rộng thẻ và thứ tự đọc. Kiểm tab order, layout 3/2/1 cột, caption dài và empty state.
- Ca eligible có đúng hai giá trị, đúng đội, đầy đủ comparison/summary/information. Ca blocked/API error không có số hay bar suy đoán. Đo vị trí panel, trạng thái focus và điểm đầu kết quả so với sticky nav tại các viewport.
- Match Analysis có Insights và CTA; đúng Last 5/10, scope H2H và venue. Trên Team Statistics kiểm crest pair, SVG viewBox, màu đường, legend, khoảng null, clamp label và vùng overflow riêng của table.
- Chụp History empty/live hoặc replay có nhãn, table/detail/compare và export scope. Kiểm AI Model đủ 13 feature đúng thứ tự và nhãn provider/cohort; không dùng lại điểm scatter/residual giả.
- Mỗi visual baseline phải có kết quả kiểm DOM, so ảnh hai phía và triage sai khác. Dữ liệu thiếu phải hiện trạng thái đúng. Giữ `production_approved=false` và mọi ranh giới ML hiện hành.
