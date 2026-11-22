# XPECTA Phase 8.5.6 — Tương thích nguồn và kiểm chứng dự báo

Ngày 22/11/2026, Asia/Saigon. Branch `phase8.5.6-provider-compatibility-validation` từ `main` tại `6c1d0614558d6904185beb8346d6c0dfd31e516c`, sau khi Phase 8.5.5 được merge qua PR #3. Evaluator được chạy tại commit `3355580`. Các đối chiếu thiết kế dùng protocol và kết quả Phase 7, audit ngữ nghĩa và dữ liệu Phase 8.5.2, V3 Phase 8.5.3, hợp đồng refresh Phase 8.5.4 và báo cáo forecasting Phase 8.5.5.

**Implementation verdict: PASS. Scientific conclusion: SUPPORTED_WITH_LIMITATIONS.** Frozen LR xử lý được feature trên các fixture đủ điều kiện. MAE đo trên từng nguồn thấp hơn baseline ghép cặp trong snapshot này. Khả năng thay thế nhãn và cùng định nghĩa giữa các provider vẫn **INCONCLUSIVE**. `production_approved=false`.

## A. Đối chiếu FBref và Understat trên cùng fixture

Ghép bằng mùa, đội nhà, đội khách đã chuẩn hóa rồi kiểm tra ngày và tỷ số cho cả hai perspective. Không dùng ID provider để ghép hai nguồn. ID chỉ nối bảng cú sút và bảng fixture **trong cùng export Understat** sau khi xác minh namespace, scope và quan hệ khóa ngoại. Input là FBref normalized đã đóng băng và 7 archive La Liga 2019–2025 ghi trong manifest đã duyệt. Các checksum file thực tế khớp manifest V3 và acquisition đã khóa. Ngày và sân nhà/khách được kiểm trước khi dùng số liệu.

**2.350/2.350 fixture** khớp identity, không có date/score conflict. Có **4.698/4.700 cặp xG** hợp lệ. Hai quan sát còn lại thuộc một fixture overlap có xG trống và được provider gắn cờ unreliable. Đây là ca ở phần overlap, riêng với 4 pending target sau mốc tham chiếu.

| Đo trên 4.698 cặp xG | Kết quả |
|---|---:|
| FBref mean / SD mẫu | 1,2646 / 0,7764 |
| Understat mean / SD mẫu | 1,3528 / 0,8679 |
| Mean có dấu, Understat − FBref | **+0,0881** |
| Mean / median độ lệch tuyệt đối | **0,2137 / 0,1500** |
| P05 / P50 / P95 độ lệch có dấu | −0,2998 / +0,0379 / +0,6144 |
| Pearson r mô tả | 0,9445 |

| Mùa bắt đầu | Cặp xG | Mean Understat − FBref | Đội nhà | Đội khách |
|---|---:|---:|---:|---:|
| 2019 | 758 | +0,0252 | +0,0352 | +0,0151 |
| 2020 | 760 | +0,0284 | +0,0401 | +0,0167 |
| 2021 | 760 | +0,1019 | +0,1055 | +0,0983 |
| 2022 | 760 | +0,0853 | +0,1337 | +0,0368 |
| 2023 | 760 | +0,1351 | +0,1917 | +0,0785 |
| 2024 | 760 | +0,1384 | +0,1508 | +0,1261 |
| 2025, đến 30/09 | 140 | +0,1660 | +0,2365 | +0,0955 |

JSON chứa các thống kê nguồn, quantile 5/25/50/75/95%, missing và exclusion theo từng nhóm. Xu hướng trong bảng là mô tả mẫu ghép. Tương quan cao vẫn đi cùng độ lệch thực tế và khác biệt giữa mùa hoặc sân. xG của mỗi provider là phép đo theo định nghĩa của chính họ.

### SH/SOT

| Nguồn | Quan sát và giới hạn |
|---|---|
| FBref frozen | Giữ đúng SH/SOT đã đi vào huấn luyện. Các ca penalty trong snapshot hỗ trợ cách hiểu số đếm ngoài penalty. Tooltip lịch sử chưa được xác minh lại. |
| Understat shot events | Dùng mapping Phase 8.5.2, loại penalty và own goal. SOT là `Goal` + `SavedShot` theo mapping đã review. Trên 70 fixture overlap 2025 có **140 cặp** mỗi trường. Mean độ lệch có dấu bằng 0 cho cả hai. Mean độ lệch tuyệt đối **SH 0,0286**, **SOT 0,0000**. Còn **4.560** quan sát overlap mỗi trường thiếu coverage shot events đã review. |
| Sportmonks reported | **240/240** quan sát của 120 fixture full-time có SH/SOT nguyên không âm và SOT ≤ SH. Penalty fields đều trống. Có **0 cặp cùng fixture với FBref** trong snapshot này, nên không tính được paired delta. |

Đối chiếu số đếm Understat là mô tả trong phạm vi 70 trận, có bằng chứng gần nhau về giá trị. Phạm vi định nghĩa giữa các provider và xử lý penalty của Sportmonks vẫn chưa xác minh. Không dùng hệ số chuyển đổi hay coi ô trống là 0.

## B. Retrospective date-cutoff replay

B1 chọn mùa 2025–26 sau **30/09/2025** từ roster đầy đủ. B2 dùng toàn bộ catalogue 2026–27 tại snapshot V3. Trạng thái hoàn thành phải được registry xác minh. Feature Builder dùng đúng cutoff **nhỏ hơn ngày trận**, loại mục tiêu và tương lai, giữ continuous stint và actual last-five. Evaluator lấy nhãn mục tiêu riêng sau inference đối với các trận complete. Test đổi riêng nhãn xG mục tiêu và xGA đối ứng giữ nguyên feature, dự đoán và baseline của chính trận đó.

| Mẫu số | B1 Understat | B2 Sportmonks |
|---|---:|---:|
| Fixture trong catalogue | 380 | 380 |
| Trước hoặc tại mốc tham chiếu | 70 | 0 |
| Fixture trong phạm vi | 310 | 380 |
| Verified completed | 310 | 123 |
| Ngoài verified completed | 0 | 257 |
| Verified completed nhưng thiếu xG mục tiêu | 1 | 3 |
| Đủ nhãn nhưng bị chặn bởi actual last-five | 10 | 0 |
| Dự đoán thành công và chấm được | **299** | **120** |
| Số quan sát đội–trận được chấm | **598** | **240** |

Giữ bốn pending target ở trạng thái thiếu. Cả 10 blocked fixture ở B1 có lỗi `MISSING_ROLLING_STATISTICS`. 257 fixture B2 không có trạng thái verified completed được giữ trong mẫu số catalogue. Chúng không bị quy thành lỗi dự đoán và không được chấm.

### Sai số theo provider

Residual bằng **xG dự đoán đã clip − xG provider báo cáo**. Giữ `max(0, raw_prediction)`. Baseline dùng `xg_avg5` sau `preprocessing.transform` của chính pipeline frozen, cùng các nhãn và dòng chấm. Tái sử dụng median đã fit cho zero-history hợp lệ. Phase 7 được đọc làm tham chiếu lịch sử, với nhãn FBref và giai đoạn khác.

| Cohort | Phía | N | LR MAE | LR RMSE | Mean residual | Median AE | Baseline MAE | LR − baseline MAE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Understat | Gộp hai phía trong B1 | 598 | 0,6164 | 0,8038 | −0,1649 | 0,5205 | 0,6719 | **−0,0555** |
| Understat | Nhà | 299 | 0,6472 | 0,8378 | −0,2502 | 0,5154 | 0,6982 | −0,0510 |
| Understat | Khách | 299 | 0,5856 | 0,7683 | −0,0797 | 0,5402 | 0,6456 | −0,0600 |
| Sportmonks | Gộp hai phía trong B2 | 240 | 0,6176 | 0,7962 | −0,0950 | 0,5135 | 0,6809 | **−0,0633** |
| Sportmonks | Nhà | 120 | 0,6176 | 0,8060 | −0,0282 | 0,5181 | 0,6697 | −0,0521 |
| Sportmonks | Khách | 120 | 0,6175 | 0,7862 | −0,1619 | 0,4746 | 0,6921 | −0,0746 |

Bootstrap ghép cặp dùng 2.000 lần lấy mẫu lại fixture có hoàn lại, giữ cả hai phía, seed 856 và percentile 95%. Khoảng mô tả ΔMAE là **[−0,0864; −0,0223]** ở B1 và **[−0,1157; −0,0098]** ở B2. Fixture có đội lặp lại và phụ thuộc theo thời gian, nên khoảng này không đại diện đầy đủ cho bất định khi khái quát ra ngoài snapshot. Không tạo điểm pooled B1/B2 hoặc ngưỡng accuracy PASS.

### Lịch sử và phân phối feature

| Cohort | Zero-history | Short-history, gồm zero | Số cửa sổ đội hỗn hợp | Lượt dòng lịch sử theo nguồn xG |
|---|---:|---:|---:|---|
| B1 | 0 | 0 | 80 | FBref 300, Understat 2.690 |
| B2 | 3 | 15 | 68 | Understat 255, Sportmonks 900 |

Mỗi mùa có 80 và 68 lần đổi nguồn giữa hai trận liền kề trong cửa sổ tương ứng. Số lượt lịch sử là tổng dòng dùng trên các cửa sổ, một trận có thể góp vào nhiều cửa sổ. JSON phân tách provenance theo nguồn fixture, xG và shots. B2 có 7 short-history phía nhà và 8 phía khách, gồm 2 và 1 zero-history. Với các feature chưa impute có quan sát, mean `xg_avg5` nhà/khách là 1,4802/1,5238 ở B1 và 1,4402/1,4522 ở B2. Mean `shot_avg5` tương ứng 12,2542/12,4943 và 12,9781/13,0780. B1 có 299 quan sát mỗi phía, B2 có 118 nhà và 119 khách do các cửa sổ trống. Đây là mô tả theo cùng schema với khác biệt về thời đoạn, roster, nguồn và selection. Không quy chênh lệch feature cho một provider riêng.

## C. Phạm vi kết luận và bàn giao

| Lớp đánh giá | Kết luận |
|---|---|
| Structural compatibility | Pipeline V1 đọc đúng 13 feature trên 419 fixture được chấm theo hai cohort riêng. Coverage và last-five chặn các trường hợp thiếu. |
| Statistical compatibility | Có label-definition shift quan sát được ở overlap. Shot mapping có bằng chứng hẹp theo 70 fixture và Sportmonks thiếu overlap cùng fixture. Tính tương đương chưa đủ bằng chứng. |
| Predictive evidence | Đo sai số hồi cứu với từng bộ nhãn trong snapshot đủ điều kiện. Cả hai cohort cho MAE LR thấp hơn baseline trên dòng chấm ghép cặp, đồng thời residual trung bình âm. Result phụ thuộc cụ thể vào mẫu và nhãn. |
| Deployment approval | Research-only. Snapshot có thể chứa correction đến sau ngày replay. Cutoff theo ngày ngăn target/future outcome đi vào feature nhưng không chứng minh availability lịch sử as-of-vintage. |

Phase 8.5.7 nên truyền các lý do thiếu lịch sử và provenance theo cặp snapshot/model hiện có. Giao diện website có thể trình bày đây là xG kỳ vọng của đội và hai bảng replay theo nguồn nhãn. Không dùng lỗi hồi cứu như một cam kết hiệu năng dự báo trực tiếp. API chỉ công bố tổng hợp được phép, đưa trạng thái chờ ra rõ ràng và giữ `production_approved=false`. Dữ liệu dòng, nhãn, prediction chi tiết và lịch sử theo fixture nằm trong kho ignored vì quyền tái phân phối nguồn thứ ba chưa xác minh.

## Artifact, tái lập và acceptance criteria

| Artifact | SHA-256 |
|---|---|
| Frozen LR V1 | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| V3 nghiên cứu | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| FBref normalized | `90000ce22f42abe5eb5b5bfa38ad1ed5ef7b1c1c75cd4d39e749e7b324e0e5ca` |
| Understat archive 2025 | `cf00d4a4298c756303d3f916fd16fa9eded16bd2dd49e24577a8c1141f4805e8` |
| Understat shot events 2025 | `84ffc98f9400191f6ae313d8f7cdeb975aa1ab2477a5e952f50aaf71d1be3192` |
| Sportmonks export 2026 | `dbbd9d99526717a03af3548375340aaa7364c4699a0689bf9e0d1a6421cd3c0e` |
| Production History Store | `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982` |

V3 qua SQLite integrity và foreign key checks. Hai protected manifest từ Git base khớp **77/77**, **107/107** mục, gồm Phase 7, model/imputer và preprocessing. Cả **8/8** file snapshot khớp SHA-256 trước và sau replay, đồng thời khớp baseline ghi trong final gate Phase 8.5.4. Detailed overlap, scores và test log local dưới `data/external/multisource/phase856/phase856-3355580/`. Kết quả tổng hợp, checksum từng input, theo-side metrics, quantiles và feature distribution nằm trong [JSON](PHASE_8_5_6_VALIDATION.json).

Targeted suite pass **14/14**, exit code `0`. Full regression suite chạy offline một lần sau khi code ổn định, pass **340/340** trong 136,655 giây, exit code `0`. Cả hai không có failure, error hay skip.

```powershell
.venv/Scripts/python.exe -m unittest tests.test_phase856_validation -q
.venv/Scripts/python.exe -m scripts.multisource.phase856_reporting --run-id phase856-recheck --full-suite
```

Chọn run ID mới. Thiếu hoặc sai SHA input riêng tư ghi `BLOCKED` kèm danh sách file và SHA kỳ vọng. SQLite sidecar được xác thực bằng manifest nhúng trong V3. Runner không tải thay thế. Các test synthetic xác minh hành vi evaluator. Metric ở báo cáo đến từ dữ liệu thật đã hash.

| AC | Trạng thái | Bằng chứng |
|---|---|---|
| AC-01 | PASS | 2.350 identity và 4.698 cặp xG có provenance, 2 exclusions có lý do |
| AC-02 | PASS | Chỉ 140 cặp SH/SOT đủ coverage, Sportmonks kiểm cấu trúc, không normalization suy đoán |
| AC-03 | PASS | B1/B2 độc lập, xác định trước cửa sổ và mẫu số |
| AC-04 | PASS | Frozen LR strict-before, regression đổi nhãn mục tiêu |
| AC-05 | PASS | Paired baseline, residual/RMSE/MAE, subgroup và toàn bộ lý do loại/chặn |
| AC-06 | PASS | Nhãn theo provider, replay và as-of-vintage được phân biệt |
| AC-07 | PASS | Protected hashes và snapshot nguyên vẹn, evaluator offline, không fit |
| AC-08 | PASS | Regression, báo cáo tổng hợp và hướng bàn giao API |
