# Thiết lập môi trường và sử dụng artifact LR

Tên tài liệu mô tả cách chuẩn bị backend tương lai; Phase 8 không triển khai website hoặc cloud service.

## Môi trường tham chiếu

Python 3.14.0; numpy 2.5.4, pandas 3.1.0, scipy 1.18.1, scikit-learn 1.9.1, joblib 1.6.0, threadpoolctl 3.8.0. Đây là phiên bản đã đọc từ môi trường thực, không suy đoán tương thích với bản khác.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts/inference/requirements.txt
```

Repository hiện tại đã có môi trường phù hợp, không cần cài lại. Runtime suy luận không cần XGBoost hoặc matplotlib. Export dùng `build_pipeline` nghiên cứu, nên máy cần tái tạo artifact còn cần `scripts/training/requirements.txt`; kiểm thử toàn bộ research cần thêm `scripts/evaluation/requirements.txt`. Không chạy lại Phase 5 search hoặc Phase 7 evaluation.

## Export tường minh

```powershell
.\.venv\Scripts\python.exe -m scripts.inference.export_final_pipeline
```

Lệnh chỉ được dùng khi artifact đích chưa tồn tại. Nó fit một LR pipeline trên 3.800 Development rows, dùng đúng selected/fixed parameters từ Phase 5 và đối chiếu Phase 7 protocol, rồi xuất:

```text
models/laliga_lr_pipeline.joblib
models/model_metadata.json
```

Artifact này đã được tạo trong Phase 8. Gọi lại ở đích mặc định sẽ trả `ARTIFACT_EXISTS` **trước fit**. Để tái tạo có chủ đích trong thư mục version mới, quản trị có thể dùng `--output-dir models/reproduction-<version>`; việc đó là một production export riêng, không phải inference/startup. Không có `--force`, không xóa artifact gốc để thử lại. Export dở thiếu metadata khiến loader từ chối; cần quản trị kiểm tra và chọn đích sạch mới, không tự fit ngầm.

Metadata giữ model/version, mùa và số dòng train, 13 features, LR params/coefs/intercept, tám median, clipping, source/best-params/artifact hashes, references Phase 5/7, dependencies và timestamp export UTC. `HistoryMedianImputer` phải còn import được tại `scripts.prepare_training_features`; đóng gói repository/package Python cùng artifact. Không đổi file này vì cần cho unpickle.

Serialize hai lần cùng fitted object đã khớp byte trong môi trường này; reload giữ nguyên dự báo. Điều đó không cam kết byte-identical nếu fit lại trên OS/BLAS/Python/dependencies khác. Loader hiện yêu cầu toàn bộ phiên bản tham chiếu khớp chính xác; upgrade cần môi trường tái tạo và kiểm toán riêng.

## Trusted loading

`joblib` dùng pickle và có khả năng thực thi mã. Chỉ load artifact do quy trình export tin cậy tạo, từ thư mục backend được quản trị cấu hình. Không nhận `.joblib`, metadata hoặc checksum từ upload/frontend. Metadata và artifact cùng nằm trong trust boundary; checksum phát hiện hỏng/thay đổi ngoài ý muốn, **không xác thực một cặp file đều đã bị kẻ tấn công thay thế**. Production phải bảo vệ thư mục/metadata bằng quyền ghi của quản trị, mount read-only cho request workers và pin checksum từ kênh triển khai tin cậy.

Loader kiểm tra path/symlink không thoát thư mục, hash trước deserialize, schema, môi trường, đúng Pipeline+LinearRegression+HistoryMedianImputer, feature order và fitted params/medians. Load bytes từ buffer đã hash để tránh đọc lại file sau kiểm tra. Không bảo đảm an toàn nếu chính trust boundary bị chiếm quyền.

Không export/train trong startup hoặc prediction. `FixturePredictor` load một lần; model chỉ predict/transform. Artifact không bao gồm XGBoost.

## Offline smoke test và kiểm toán

```powershell
.\.venv\Scripts\python.exe -m scripts.inference.data_refresh bootstrap-snapshot
.\.venv\Scripts\python.exe -m scripts.inference.predict_fixture replay --match-id 1901
.\.venv\Scripts\python.exe -m scripts.inference.verify_inference
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Parity verifier không train và không chạy lại Phase 7 entry point. Nó dựng lại 4.700 feature rows, đối chiếu 900 dự báo LR holdout đã lưu (không đọc actual_xg trong file dự báo), kiểm tra load trong tiến trình mới và hash 77 file đóng băng. `outputs/inference/verification_manifest.json` là bằng chứng riêng Phase 8.

Feature atol=5.1e-9 theo độ làm tròn CSV nguồn; prediction atol=1e-8, rtol=0, lớn hơn bound `sum(abs(LR coefficients))*feature_atol + 1e-12`. Không điều chỉnh ngưỡng để làm đẹp Test performance. Chỉ đối chiếu hành vi inference, không tính lại MAE/RMSE Test.

CSV staging/JSON được tạo ngay trong thư mục đích để kế thừa ACL Windows; joblib tạo bằng chế độ `xb`. Không di chuyển file từ thư mục tạm private vào workspace. SQLite connection được đóng tường minh để tránh giữ file khi kiểm thử trên Windows.

Để chạy lệnh từ working directory khác, backend cần cài package đúng cách hoặc thêm repository root vào PYTHONPATH; ví dụ đã được kiểm thử đều chạy tại root. Không cung cấp Docker/cloud deploy hoặc scheduler bật sẵn trong Phase 8.
