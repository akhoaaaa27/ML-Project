# Phase 8.5.3 — Composite History Integration

Ngày: **22/11/2026 — Asia/Saigon**. Kết quả: **hoàn tất acceptance criteria ở mức nghiên cứu; chưa production-ready**.

## Git và phạm vi

Nhánh `phase8.5.3-composite-history-integration` tạo từ remote multisource mới nhất `2ae0f8920ca0435b8c32c1b4763bc30ec370ba5b`, sau fetch. Workspace sạch khi bắt đầu. Không merge/cherry-pick StrikerAPI, reset, discard hoặc force-push. Không dùng StrikerAPI, không tải lại datasets, không train/refit, không deployment.

## Thành phần bàn giao

Sáu module mới: `team_registry.py`, `match_registry.py`, `composite_history.py`, `composite_features.py`, `composite_inference.py`, `build_composite.py` dưới `scripts/multisource/`. Có research CLI, versioned SQLite local, per-team coverage, missing-history, source provenance, parity và reevaluation reports.

[Báo cáo kiến trúc chi tiết](../docs/COMPOSITE_HISTORY_INTEGRATION.md) giải thích Registry states, Option B, provenance, versioning và production boundaries. [Bản validation public](../docs/COMPOSITE_HISTORY_VALIDATION.json) chỉ chứa metadata/kết quả aggregate.

## Registry và Composite History thực tế

| Hạng mục | Số lượng |
|---|---:|
| Registry gồm completed và lịch khác | 3.040 fixture |
| VERIFIED_COMPLETED | 2.783 |
| COMPLETE_STATISTICS | 2.779 |
| PENDING_UPDATE | 4 |
| UNVERIFIED completion | 257 |
| Unresolved conflicts | 0 |

Giữ đủ 2.779 fixture hợp lệ từ Phase 8.5.2. Bốn trận pending giữ NULL ở thống kê chưa biết; không impute và không coi như chưa chơi. Một số raw records chỉ báo unplayed: không tự suy ra completed/LIVE từ ngày hoặc số lượng.

Version cuối nằm local ở `data/history/research/phase853_v3_20261122/laliga_composite.sqlite3`. V1/V2 thử trước được giữ nguyên. V3 có cùng business data với parent V2, revision delta 0/0/0; có validation/parity trước atomic publication và SQL authorizer chặn cả thao tác tạo database ngoài. Các unit tests kiểm tra refresh pending → complete bằng dữ liệu giả lập, không sửa xG thật đang thiếu.

Manifest chứa input hashes, code revision và working code hashes, source versions, counts, per-team coverage, schema/version, parent/revision tracking. Reader chỉ mở SQLite read-only và kiểm checksum. Thất bại build/parity không publish version mới hoặc làm thay đổi bản cũ.

## Option B và kết quả inference

`matches_seen` lấy từ toàn bộ verified completed trong continuous stint. Cửa sổ thực tế được chọn từ Registry trước, rồi mới kiểm đủ statistics. Rolling và assembly dùng lại code cũ; chỉ nguồn đếm count chuyển sang Registry. Không lấy trận complete thứ 6/7 thay missing trong last five.

| Experiment | Kết quả |
|---|---|
| Target 2026–27 | 123 fixture |
| Đúng 13 feature, frozen LR predict thành công | **123 fixture / 246 dự đoán** |
| 12 fixture từng bị chặn | **12/12 mở được** |
| Pending Villarreal trong stint | Vị trí 260, cách hiện tại 7–18 trận tại 12 cutoff |
| Last-five của 12 trường hợp | Đều đủ đúng 5/5 trận |
| Parity Phase 8.5.2 | **111/111**, max feature/prediction delta **0.0** |
| Kiểm tra actual historical window có pending | Trả `MISSING_ROLLING_STATISTICS` |

Các count Villarreal đúng lần lượt 266–277, không bị giảm một vì xG missing. Cả bốn pending vẫn tồn tại sau khi mở dự đoán. Research CLI đã chạy thành công cho Racing Santander–Villarreal ngày 16/08/2026.

Málaga CF, R. Racing Club và RC Deportivo đã được xác nhận bằng trang đội/roster chính thức La Liga; research alias/ID riêng không thay production team registry.

## Tests và bảo toàn

- **37/37 test mới pass**.
- **208/208 full-suite pass**, 0 failure/error/skip; mạng/DNS bị chặn và API key loại khỏi environment.
- Test parity trực tiếp với Phase 8 builder cho complete history; kiểm imputer fit 3.800 dòng, schema và artifact trusted loader.
- **139/139 file có sẵn byte-identical**, gồm model, imputer trong artifact, metadata, Final Test, production Feature Builder và SQLite history.
- Các nhánh StrikerAPI và multisource base giữ nguyên. `PRODUCTION_UPCOMING` bị cấm; predictor production cũ không nhận CompositeHistory.
- StrikerAPI calls/credits: **0/0**.

## File riêng, giới hạn và Phase 8.5.4

SQLite/version manifests nằm trong `data/history/research/` đã ignore. Detailed predictions, window provenance, coverage/missing/parity reports và log nằm trong `data/external/multisource/phase853/`, không đưa raw third-party data lên GitHub.

Chưa phê duyệt performance trên xG nguồn mới, penalty semantics, as-of-vintage hoặc production freshness/provider policy. Bốn pending và các cập nhật ngoài snapshot vẫn cần xử lý. Coverage là catalogue nghiên cứu đã review, không phải tuyên bố đã biết mọi trận đến hết ngày hiện tại.

Phase 8.5.4 nên xử lý verified refresh/revisions và pending, hoàn thiện review semantics/quyền sử dụng và operational gates, sau đó đánh giá predictive performance độc lập. Không scheduler, production migration, retrain hoặc website deployment trong Phase 8.5.3. Dừng sau safe GitHub publication.
