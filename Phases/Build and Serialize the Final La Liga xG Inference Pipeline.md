# Xây dựng và lưu pipeline suy luận xG La Liga

## 1. Mục tiêu và quyết định đóng băng

Hoàn tất Phase 8 bằng Linear Regression đã chỉ định production. Target là tổng team-match xG liên tục không âm, không phải xác suất ghi bàn của một cú sút. XGBoost chỉ là research benchmark. Giữ đúng 13 features, selected/fixed parameters Phase 5, imputer Development-only và clipping `maximum(0, raw_prediction)`. Không model selection, tuning, feature selection hoặc sửa kết quả Test. Dừng trước Phase 9 website.

## 2. Kiểm tra repository và bảo toàn nghiên cứu

Đã đọc Feature Engineering, raw CSV, normalized CSV, chuẩn hóa số, API median, training/tuning, Phase 6–7 evaluation, best parameters/protocol, prediction references, manifests, dependencies và tất cả tests hiện có.

Raw có 4.700 dòng/29 cột; normalized có 4.700 dòng/26 cột, 2.350 trận, 28 canonical teams, từ 2019-08-16 đến 2025-09-30. Development 2019–2023 có 3.800 dòng/1.900 trận; holdout 2024 có 760 dòng và 2025 có 140 dòng.

Trước thay đổi đã ghi SHA-256 của **77 file** vào [protected_files.json](../outputs/inference/protected_files.json). Đối chiếu sau triển khai và trong tests: toàn bộ giữ nguyên từng byte. Không chạy Phase 7 evaluation entry point, không ghi lại metrics/bootstrap/protocol/manifest cũ. Chỉ tạo các file Phase 8; không commit hoặc push.

## 3. Huấn luyện production LR và export

Đã chạy tường minh `python -m scripts.inference.export_final_pipeline` một lần. Đọc JSON cấu hình LR, kiểm tra dataset/best-params SHA với protocol, lọc đủ Development, sắp date/match_id/is_home như Phase 7, dùng `prepare_features()` và `build_pipeline()` hiện có. Fit đúng một pipeline mới trên 3.800 dòng, không dùng holdout. Không train trong inference, startup hoặc refresh.

Effective parameters:

```json
{
  "copy_X": true,
  "fit_intercept": true,
  "n_jobs": 1,
  "positive": false,
  "tol": 1e-06
}
```

Đã lưu toàn bộ preprocessing-plus-estimator bằng joblib. Clipping thực hiện tại API sau raw predict, được ghi rõ trong metadata. Tám median học độc lập từ Development và được đối chiếu; việc một số giá trị bằng prior cũ là kết quả median thực, không phải gán hằng số tùy ý. Các ô zero-history được khôi phục về NaN trước fit.

| Feature | Median Development |
|---|---:|
| xg_avg5 | 1.2 |
| xga_avg5 | 1.24 |
| gf_avg5 | 1.2 |
| ga_avg5 | 1.2 |
| shot_avg5 | 11.2 |
| sot_avg5 | 3.6 |
| opponent_xg_avg5 | 1.2 |
| opponent_xga_avg5 | 1.24 |

Artifact: [laliga_lr_pipeline.joblib](../models/laliga_lr_pipeline.joblib).

SHA-256 artifact: `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69`.

[model_metadata.json](../models/model_metadata.json) giữ timestamp export UTC thực tế, coefs/intercept, feature order, train lineage, môi trường và references Phase 5/7. Gọi export ở đích đã tồn tại trả `ARTIFACT_EXISTS` trước fit, không ghi đè.

Serialize hai lần cùng fitted object khớp byte; reload giữ dự báo và fitted state chính xác. Không cam kết byte-identical khi train lại trên Python/dependencies/OS/BLAS khác.

## 4. Feature builder target-free và parity

`build_fixture_features()` không gọi completed-match `prepare_features()` và không nhận target của fixture. Nó query lịch sử theo team, season và `date < cutoff`, bỏ canonical fixture key trước khi lấy outcomes. Chỉ dùng stint mùa liên tiếp; season gap >1 reset; count tất cả trận eligible và rolling tối đa năm. `short_history = count < 5`. `sh` và `sot` được ánh xạ riêng. Opponent features lấy từ lịch sử độc lập của đối thủ. Tạo đúng hai dòng: Home trước, Away sau, giữ 13 cột theo thứ tự.

Zero-history tạo NaN đúng sáu own-history features và hai opponent-history features tương ứng để imputer Development xử lý. Không đưa target giả vào validator, không thay bằng arbitrary zeros, không impute outcomes của history.

Thứ tự features:

```text
is_home, matches_seen, short_history, xg_avg5, xga_avg5, gf_avg5, ga_avg5, shot_avg5, sot_avg5, opponent_xg_avg5, opponent_xga_avg5, opponent_matches_seen, opponent_short_history
```

Đối chiếu toàn bộ **4.700 dòng/2.350 fixtures**: NaN masks khớp; max absolute feature delta `3.33333360913457e-9`, atol `5.1e-9`, rtol=0. Dung sai dựa CSV gốc đã làm tròn, như `1,666666667` và `15,33333333`; không chỉnh dựa hiệu năng Test.

Đối chiếu **900 dự báo LR holdout**, gồm 760 Main và 140 Supplemental: max delta `8.119660499517067e-11` xG, dưới atol `1e-8`. Bound theo `sum(abs(coef))*feature_atol + 1e-12` là `6.0304090195821425e-9`. Chỉ đọc predicted_xg/source_row/model/test_split của reference, không dùng actual_xg để lựa chọn hoặc tính lại Test performance.

Bằng chứng: [verification_manifest.json](../outputs/inference/verification_manifest.json).

## 5. Historical Replay hoàn toàn offline

Đã chạy replay qua Python và CLI không cần API credentials. Fresh Python process load artifact và xác minh feature order, medians, coefficients, intercept và đúng cặp Home/Away. Test chặn socket.connect xác nhận đường suy luận hiện tại không cần network; CLI/child process chạy cùng code offline.

Kết quả thật fixture `legacy-local:1901`:

```json
{
  "status": "success",
  "mode": "replay",
  "home_team": "Athletic Club",
  "away_team": "Getafe",
  "home_xg": 1.3493648382441854,
  "away_xg": 1.2037992600673975,
  "history_cutoff": "2024-08-15",
  "model": "Linear Regression",
  "model_version": "1.0.0"
}
```

Kết quả đầy đủ có provenance từng rolling match và số trận mỗi đội. Normal prediction không đọc/hiển thị target fixture. Test thay outcomes trận hiện tại/tương lai trong bản sao store vẫn giữ nguyên dự báo.

Replay Development 2019–2023 chỉ là minh họa từ model đã học trên cùng Development, không được diễn giải thành đánh giá out-of-sample. Actual xG nếu cần hiển thị phải đi qua luồng hậu kiểm riêng.

## 6. Upcoming và các gate chất lượng

Đã triển khai mode upcoming, validation request, canonical aliases, per-team freshness, approved provider, verified schedule và coverage/stint/key-set checks.

Cutoff upcoming bắt buộc ngày UTC hiện tại, không sau fixture; cutoff cũ không thể dùng để vượt freshness. Mỗi đội cần trận gần nhất cách ngày fixture không quá 45 ngày. Đây là gate vận hành bảo thủ, không phải ngưỡng được tối ưu trên Test; có thể chặn cả kỳ nghỉ dài hợp lệ.

Schedule fetched_at và coverage reviewed_at phải có ngày UTC bằng cutoff hoặc ngày trước đó, không có timestamp tương lai. verified_through cũng phải trong khoảng ngày trước cutoff đến cutoff. Không dùng lịch/attestation cũ để tuyên bố đã biết các trận hoãn hoặc kết quả mới nhất.

Có trận trước target scheduled/postponed hoặc completed nhưng thiếu outcomes thì fail. Chưa có schedule thật không được dán nhãn officially scheduled. Dữ liệu thiếu trả lỗi, không fallback sang snapshot cũ. Đã kiểm thử success bằng provider/schedule/coverage **nhân tạo chỉ trong tests**, không gắn nhãn dữ liệu thật.

Lệnh minh họa Barcelona–Real Madrid ngày 2026-11-28, không xác nhận lịch thật, với snapshot hiện có trả:

```json
{
  "status": "error",
  "mode": "upcoming",
  "error": {
    "code": "STALE_DATA",
    "message": "Lịch sử đội quá cũ cho yêu cầu upcoming.",
    "details": {
      "team": "Barcelona",
      "last_match_date": "2025-09-28",
      "history_cutoff": "2026-11-21",
      "age_days": 426,
      "max_age_days": 45
    }
  }
}
```

Bằng chứng: [upcoming_snapshot_check.json](../outputs/inference/upcoming_snapshot_check.json).

Chưa có upcoming production thật khả dụng vì snapshot cũ và chưa có provider/schedule/coverage được phê duyệt. Việc triển khai gate không đồng nghĩa đã kết nối live data.

## 7. History store, CSV và refresh

Kho riêng `data/history/laliga_history.sqlite3` có 2.350 completed fixtures/4.700 team perspectives. Canonical key dùng competition/season/home/away. `legacy-local:<id>` không được coi là FBref provider match ID gốc.

Bootstrap provenance ghi nguồn nghiên cứu FBref/Opta-derived theo hồ sơ dự án, SHA normalized và thời điểm nhập snapshot, không giả timestamp fetch gốc. Nguồn training đóng băng, history store và schedule là ba khái niệm tách biệt.

CSVProvider và FrozenSnapshotProvider thực hiện interface CompletedMatchProvider. Import CSV bắt buộc đủ hai phía và xg/xga/gf/ga/sh/sot; đối chiếu xG atol=1e-9, goals chính xác, số hữu hạn, canonical mapping và final status. Không tự trộn xG của hai provider. Provider mới vào staging store riêng và cần compatibility review trước production.

Writer lấy `BEGIN IMMEDIATE`; batch fixtures/team rows/schedule/coverage commit cùng nhau hoặc rollback. Reimport giống nội dung không đổi record và không nhân đôi trận. Fetch timestamp mới chỉ thêm log. Completed outcome/version/date thay đổi cần `CORRECTION_REQUIRES_REVIEW`: review correction và tạo store version mới, không tự ghi đè.

Đã thực thi bootstrap lần hai trên store thật: **inserted_matches=0, unchanged_matches=2350**. Tests CSV xác minh import hợp lệ, thiếu xG, invalid schema/numeric, trùng, cặp sai, provider conflict và partial-insert rollback. Mỗi refresh có audit SQLite và CLI manifest riêng trong `outputs/inference/refresh_runs/`. Không retrain model.

Chưa có provider API connector thật, credentials, quyền truy cập/tài liệu nguồn được duyệt, kiểm chứng metric compatibility hoặc scheduler tự động. Interface và command sẵn sàng để tích hợp sau review. Không scrape, không bịa endpoint/dữ liệu live, không ghi secrets. Scheduling opt-in được mô tả và disabled mặc định.

## 8. Bảo mật artifact và môi trường

Joblib có thể thực thi mã khi deserialize. Chỉ load từ trusted directory do backend cấu hình, không nhận upload/path/metadata/hash từ frontend. Kiểm tra hash trước load, dùng chính bytes đã hash, schema/version/fitted state, path không thoát trusted directory và môi trường pin.

Checksum không thay thế trust nếu kẻ tấn công có quyền ghi cả artifact và metadata. Production phải bảo vệ/mount chỉ đọc; đây chưa phải môi trường production đã harden.

Custom HistoryMedianImputer giữ nguyên import path `scripts.prepare_training_features`. Loader yêu cầu Python và relevant dependencies khớp, không thử tải mù artifact khác môi trường. Runtime không cần XGBoost/matplotlib. Export dùng research helper nên môi trường tái tạo còn cần training requirements.

| Thành phần | Phiên bản thực tế |
|---|---|
| Python | 3.14.0 |
| numpy | 2.5.4 |
| pandas | 3.1.0 |
| scipy | 1.18.1 |
| scikit-learn | 1.9.1 |
| joblib | 1.6.0 |
| threadpoolctl | 3.8.0 |

Artifact/metadata/history store trên Windows đều có `AreAccessRulesProtected=False`, kế thừa quyền đọc workspace. File mới được tạo tại thư mục đích, không chuyển từ private temp folder. SQLite connection được đóng tường minh.

## 9. Kiểm thử đã thực thi

Kết quả cuối: **109 tests**, failures=0, errors=0, skipped=0; thời gian khoảng **57,818 giây**. Gồm 62 tests Phase 4–7 và 47 tests Phase 8.

| Module | Số tests |
|---|---:|
| test_evaluation.py | 13 |
| test_final_test.py | 18 |
| test_history_store.py | 14 |
| test_inference.py | 23 |
| test_model_export.py | 10 |
| test_training.py | 19 |
| test_tuning.py | 12 |

Đã chạy riêng các lệnh unittest discovery cho test_history_store.py, test_model_export.py và test_inference.py. Sau các sửa cuối, chạy lại toàn bộ bằng Python runner gọi unittest discovery/TextTestRunner, cùng suite với lệnh CLI ở mục 10. Lưu đầy đủ log và thông số thực thi trong [test_results.json](../outputs/inference/test_results.json).

```python
suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
```

Không train production lần hai trong tests: fit-routing dùng spy thay fit; artifact đã xuất được dùng cho reload/parity. Các fits nhỏ trong regression tests cũ là fixtures kiểm thử, không phải Phase 5 search hoặc Phase 7 thực nghiệm.

Phạm vi đã kiểm tra: Dev-only routing/medians/schema/params; serialization/reload/fresh process; no-fit inference; strict cutoff/current/future/same-day exclusion; gap reset/count/window/short history; symmetry/opponent alignment; zero-history; clip/Home-Away; CLI/Python parity; requests/stale/cutoff/provider/schedule/coverage; CSV/dedup/rollback/provenance; không đổi file protected.

Trong phát triển đã sửa connection cleanup Windows và fixture symmetry bị trùng identity của trận cũ. Suite cuối qua đầy đủ, không bỏ qua test lỗi. Không kiểm chứng live API, lịch thật cuối 2026, website/HTTP, mọi OS hoặc byte-identical refit khác môi trường; không tuyên bố các chức năng đó đã hoàn tất.

## 10. Lệnh sử dụng và tái tạo

Chạy tại repository root. Export đã thực hiện; lệnh đầu sẽ từ chối ghi đè ở trạng thái bàn giao, đúng thiết kế. Chỉ dùng đích version mới khi chủ động thực hiện export riêng.

```powershell
.\.venv\Scripts\python.exe -m scripts.inference.export_final_pipeline
.\.venv\Scripts\python.exe -m scripts.inference.data_refresh bootstrap-snapshot
.\.venv\Scripts\python.exe -m scripts.inference.predict_fixture replay --match-id 1901
.\.venv\Scripts\python.exe -m scripts.inference.predict_fixture upcoming --home "Barcelona" --away "Real Madrid" --date 2026-11-28 --season 2026
.\.venv\Scripts\python.exe -m scripts.inference.data_refresh import-csv --csv "C:\approved-data\completed_matches.csv" --store "data/history/provider_staging.sqlite3"
.\.venv\Scripts\python.exe -m scripts.inference.verify_inference
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

CSV path là placeholder cho file đã review, không phải file live có sẵn. Upcoming minh họa sẽ trả exit code 2/STALE_DATA. Replay/export/refresh thành công trả 0; export tồn tại trả 2, không train ngầm.

Hướng dẫn installation, trusted load và fresh process tại DEPLOYMENT_GUIDE.md.

## 11. File bàn giao và giới hạn còn lại

Chỉ thêm các nhóm file mới:

- `scripts/inference/`: common, model_artifact, export_final_pipeline, build_fixture_features, history_store, predict_fixture, data_refresh, verify_inference, requirements và package init.
- `models/`: pipeline joblib và model_metadata.json.
- `data/history/`: history SQLite riêng, không sửa frozen CSV.
- `tests/`: test_inference.py, test_history_store.py, test_model_export.py, inference_fixtures.py.
- `outputs/inference/`: protected hashes, parity/fresh-process verification, full test log, stale-data demonstration, refresh manifests và phase8_manifest.json.
- `docs/`: năm tài liệu API/schema/refresh/website handoff/environment.
- Đúng một báo cáo Phase 8 là file này. Không sửa bất kỳ 77 file cũ.

Giới hạn: độ phân giải ngày; kickoff timestamp mới chỉ lưu và chưa bật policy khác; provider/date compatibility cần review; mapping chỉ 28 đội snapshot; gate 45 ngày có thể chặn nghỉ dài; upcoming chưa dùng được với nguồn thật hiện tại; correction cần store version mới; chưa có HTTP/auth/UI/scheduler/deployment. Coverage attestation cần review thực, không được tự tạo từ số dòng hiện có rồi tuyên bố đầy đủ.

Bản báo cáo đã được ghi lại đúng UTF-8 sau khi phát hiện PowerShell pipe làm mất dấu trong bản tạo tài liệu ban đầu. Việc sửa encoding chỉ tác động tài liệu Phase 8, không thay code đã kiểm thử, artifact, dự báo hoặc research outputs.

## 12. Bàn giao cho đội website và trạng thái hoàn thành

Backend dùng HistoryStore + FixturePredictor, load model một lần và gọi predictor.predict. Frontend chỉ nhập đội/ngày/mùa/mode, không load joblib hoặc tự tính features.

Routes GET /api/teams, GET /api/fixtures, GET /api/data-status, POST /api/predict mới là hợp đồng đề xuất để Phase 9 thực hiện. status=error nghĩa là không có dự báo; không thay bằng 0 hoặc cached stale form. Panel actual xG sau trận phải tách khỏi inference.

- [INFERENCE_API.md](../docs/INFERENCE_API.md): signature, schema success/error, aliases, date/cutoff và CLI.
- [HISTORY_DATA_SCHEMA.md](../docs/HISTORY_DATA_SCHEMA.md): CSV, canonical identity, schedule/coverage và provenance.
- [DATA_REFRESH_GUIDE.md](../docs/DATA_REFRESH_GUIDE.md): nhập CSV, interface provider, review và scheduler opt-in.
- [WEBSITE_INTEGRATION_GUIDE.md](../docs/WEBSITE_INTEGRATION_GUIDE.md): adapter Python, routes đề xuất, UX và readiness.
- [DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md): môi trường, export, trusted load và kiểm toán offline.

Hoàn thành các thành phần độc lập/offline và nền tảng Phase 8 đã yêu cầu. Các phụ thuộc live provider/production coverage còn thiếu được ghi rõ; không báo auto-refresh/live forecasting đang hoạt động. Không chuyển sang Phase 9 hoặc đổi model selection.
