# XPECTA Phase 8.5.6 — Final Merge Gate

**Merge-readiness `PASS` cho phạm vi research-only.** `implementation_verdict = PASS`, `scientific_conclusion = SUPPORTED_WITH_LIMITATIONS`, `production_approved = false`. Gate được thực hiện ngày 22/11/2026 theo giờ Việt Nam.

## Git và phạm vi review

| Mốc | Commit |
|---|---|
| Base `main`, merge Phase 8.5.5 | `6c1d0614558d6904185beb8346d6c0dfd31e516c` |
| Implementation đã chạy test | `3355580782cdde75a4df2f40b55033343f04eef5` |
| HEAD được đánh giá trong gate | `e99b94246706f44288f56f6f4570b8e15683cf84` |

Đã xác minh SHA của `main` và `phase8.5.6-provider-compatibility-validation` trên GitHub trước khi ghi báo cáo. Working tree sạch. Commit implementation thêm `scripts/multisource/phase856_validation.py`, `scripts/multisource/phase856_reporting.py` và `tests/test_phase856_validation.py`. Diff từ implementation đến HEAD chỉ thêm hai báo cáo validation Markdown và JSON. Diff từ base qua HEAD không sửa file có sẵn, executable code, tests hoặc dependency manifests. Commit ghi nhận gate gồm hai báo cáo Final Merge Gate và dùng HEAD được đánh giá ở bảng trên làm mốc bằng chứng.

## Bằng chứng validation

JSON công khai khớp aggregate của run local tại commit đã test. Bảng Markdown khớp số liệu JSON cho cả home, away và overall theo từng provider. Gate đối chiếu mẫu số, các lý do loại và chặn, cùng số dòng ghép baseline. Sai số model được lấy từ kết quả đã ghi.

- **Overlap FBref–Understat.** 2.350/2.350 fixture khớp identity. Có 4.698/4.700 cặp xG hợp lệ. Hai quan sát còn lại bị gắn cờ unreliable và thiếu xG trong nguồn. Chênh lệch có dấu trung bình Understat − FBref là +0,0881191967, độ lệch tuyệt đối trung bình là 0,2136732354.
- **SH/SOT.** 140 cặp có coverage Understat đã review, 4.560 quan sát thiếu coverage cho mỗi trường. Sportmonks có 240 quan sát hợp lệ về cấu trúc, 0 cặp cùng fixture với FBref và thiếu metadata penalty để xác minh định nghĩa.

| Cohort | Catalogue | Trong phạm vi | Xác minh hoàn thành | Chưa xác minh hoàn thành | Thiếu xG | Blocked last-five | Trận chấm được | Quan sát đội–trận |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B1 · Understat | 380 | 310 | 310 | 0 | 1 | 10 | 299 | 598 |
| B2 · Sportmonks | 380 | 380 | 123 | 257 | 3 | 0 | 120 | 240 |

B1 có 70 trận catalogue trước hoặc tại mốc 30/09/2025. B2 giữ 257 trận chưa xác minh hoàn thành trong mẫu số. Bốn trận pending thiếu xG giữ nguyên trạng thái. Các baseline dưới đây dùng chính các dòng và nhãn đã chấm với LR.

| Cohort | Frozen LR MAE | Frozen LR RMSE | Baseline MAE | LR − baseline MAE |
|---|---:|---:|---:|---:|
| B1 · Understat | 0,6164018782711422 | 0,8037941943536051 | 0,6718967658862877 | −0,05549488761514543 |
| B2 · Sportmonks | 0,6175768052298535 | 0,7962040633813886 | 0,6809042543333333 | −0,06332744910347987 |

Nguồn kết quả và các metric theo vai trò nằm trong [Validation Markdown](PHASE_8_5_6_VALIDATION.md) và [Validation JSON](PHASE_8_5_6_VALIDATION.json).

## Kiểm tra hiện tại và kết quả test kế thừa

- **Kế thừa từ `3355580`.** Targeted suite 14/14 và full regression suite 340/340 pass. Cả hai có exit code 0, không có failure, error hoặc skip. Log gốc full suite ghi 340 tests trong 136,655 giây và chứa kết quả `ok` cho cả 14 test Phase 8.5.6.
- **Thực hiện tại gate.** Đối chiếu Git, báo cáo và log gốc. Kiểm tra lại hash, phiên bản runtime và đọc artifact qua trusted loader. So sánh manifest sidecar với metadata nhúng bằng kết nối SQLite chỉ đọc. Không chạy lại test suite hay tạo dự đoán mới. Bốn dependency manifests giữ nguyên. Phiên bản Python và sáu package ghi trong run khớp môi trường hiện tại.
- **Artifact protected.** Hai manifest lấy từ Git base khớp 77/77 và 107/107 mục, tương ứng 107 file duy nhất. Trong đó có 11 file Phase 7, frozen LR V1, metadata và Production History Store. Trusted loader kiểm tra đúng thứ tự 13 feature và fitted median.
- **Dữ liệu nghiên cứu.** Cả 13 input được attestation đều có tại chỗ và khớp SHA-256. Cả 8 file thuộc bốn cặp database/manifest nghiên cứu khớp baseline Phase 8.5.4. Composite History V3 khớp hash đã ghi, manifest sidecar khớp metadata nhúng và truy vấn chỉ đọc xác nhận 4 fixture `PENDING_UPDATE`. Kiểm tra SQLite integrity và foreign keys của V3 được kế thừa từ run trước.

| Artifact | SHA-256 vừa kiểm tra |
|---|---|
| Frozen LR V1 | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| Model metadata | `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c` |
| Production History Store | `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982` |
| Composite History V3 | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |

## Acceptance criteria

| AC | Trạng thái | Bằng chứng |
|---|---|---|
| AC-01 | PASS | Fixture overlap, provenance và 4.698 cặp xG khớp bằng chứng đã ghi. |
| AC-02 | PASS | Coverage SH/SOT và các giới hạn penalty được nêu rõ. Mapping giữ nguyên phạm vi đã review. |
| AC-03 | PASS | B1/B2 dùng cohort và mẫu số riêng. Các lý do loại, chặn khớp hồ sơ local. |
| AC-04 | PASS | Trusted frozen LR, cutoff strict-before và test thay nhãn mục tiêu được xác minh tại revision đã test. |
| AC-05 | PASS | Số trận, hai phía, lý do loại, metric và baseline ghép cặp đối chiếu nhất quán. |
| AC-06 | PASS | Diễn giải giữ nguyên giới hạn nhãn riêng theo provider và thiếu historical as-of-vintage. |
| AC-07 | PASS | Protected artifacts, snapshot và input khớp checksum. Replay và regression kế thừa được chạy offline. |
| AC-08 | PASS | Bằng chứng test tái sử dụng có căn cứ. Báo cáo công khai chỉ chứa tổng hợp và chỉ dẫn bàn giao backend. |

## Diễn giải khoa học và bàn giao backend

Frozen LR tương thích cấu trúc với 13 feature composite trên các trận đủ điều kiện. Hai cohort hồi cứu có MAE thấp hơn baseline ghép cặp. Nhãn xG FBref và Understat có chênh lệch đo được. Sportmonks thiếu đối chiếu trực tiếp cùng fixture với FBref. Tính tương đương chính xác giữa các provider vẫn `INCONCLUSIVE`.

Replay dùng dữ liệu trước ngày mục tiêu, nhưng snapshot thiếu bằng chứng dữ liệu thực sự có sẵn tại từng thời điểm lịch sử. Đánh giá này chưa xác minh dự báo triển vọng có timestamp và chưa thiết lập bảo đảm độ chính xác production.

FastAPI và website dùng kết quả ở chế độ research/demo. Hiển thị model, snapshot, nguồn nhãn và trạng thái thiếu lịch sử hoặc thống kê. Trình bày metric hồi cứu theo từng provider với mẫu số tương ứng. Chỉ công bố dữ liệu tổng hợp được phép, giữ chi tiết fixture trong vùng Git-ignored và giữ `production_approved=false`.

Bước tiếp theo là mở PR thủ công từ `phase8.5.6-provider-compatibility-validation` vào `main` và review phạm vi research-only cùng hai báo cáo gate.
