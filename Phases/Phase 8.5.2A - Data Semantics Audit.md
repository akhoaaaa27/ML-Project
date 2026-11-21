# Phase 8.5.2A — Data Semantics Audit

Ngày: **21/11/2026**. Repository: `akhoaaaa27/ML-Project`.
Nhánh làm việc: `phase8.5.2-semantic-audit`.
Base: `ee83689d117620b5085c389ce3266ed2a92cca77` trên `phase8.5.1-strikerapi-live-audit`, đã xác minh remote. Workspace sạch lúc bắt đầu; không ghi đè thay đổi người dùng.

## Kết quả review

**Hoàn tất nghiên cứu offline; chưa phê duyệt tương thích production.**

Dataset gốc có 4.700 dòng / 2.350 trận trong các mùa bắt đầu 2019–2025; mùa 2025 mới có 70 trận. Có 794 penalty thực hiện, 613 ghi bàn và 181 không thành bàn. Ở cấp trận duy nhất, 1.707 trận không có penalty, 518 có penalty thành công, 173 có penalty không thành bàn; hai nhóm sau chồng nhau 48 trận.

Có 1 dòng `sh=0` dù có penalty, 36 dòng `sot=0` dù có penalty, trong đó 29 có penalty ghi bàn. Số liệu hỗ trợ mạnh cách hiểu SH/SOT training loại penalty. Preprocessing và Feature Builder giữ nguyên số đếm gốc; không trừ penalty khỏi CSV training một lần nữa.

Tooltip FBref lịch sử chưa xác minh lại được do nguồn trả 403. Báo cáo kỹ thuật ghi rõ định nghĩa nào là quan sát cục bộ, suy luận có điều kiện hoặc còn chưa xác nhận. Không tuyên bố đã đọc tài liệu bị chặn.

Cache `get_game` có aggregate penalty attempts/goals, thiếu penalty SOT và breakdown đầy đủ cho penalty không thành bàn. Mẫu hiện tại chỉ bao phủ trường hợp mọi penalty đều thành công. Phép trừ có điều kiện khớp ở mẫu này không chứng minh trường hợp bị cứu/ra ngoài hoặc toàn bộ seasons.

## Quyết định ngữ nghĩa

```text
non_penalty_shots = total_shots - penalty_attempts
non_penalty_sot   = total_sot   - penalty_shots_on_target
```

Hai công thức dùng được khi định nghĩa nguồn/đích, phạm vi, coverage và các số đếm đã được xác nhận. Penalty bị cứu có thể trúng đích nhưng không ghi bàn; penalty ra ngoài không trúng đích. Không thay penalty SOT bằng tất cả attempts hoặc chỉ goals.

`get_game` một mình **chưa đủ cho trường hợp tổng quát**. Cần penalty SOT hoặc đầy đủ shot events có phân loại đã xác minh. Chỉ đọc tài liệu chính thức của `get_events` và `get_shot_map`; không thực thi. Schema có penalty/outcome nhưng chưa bảo đảm mapping SOT và coverage cho La Liga. Các trường hợp aggregate tự xác định được P vẫn cần hợp đồng thống kê trước khi chấp nhận.

## File bàn giao

- [Báo cáo kỹ thuật, bảng theo mùa và nguồn tham chiếu](../docs/STRIKERAPI_SEMANTIC_AUDIT.md).
- [Helper phép trừ có kiểm tra điều kiện](../scripts/data_provider/penalty_semantics.py).
- [Auditor aggregate read-only cho CSV gốc](../scripts/data_provider/audit_fbref_penalties.py).
- [Unit tests offline và kiểm tra frozen artifacts](../tests/test_penalty_semantics.py).

Không tích hợp helper vào adapter hoặc inference. `quality_status=verified` của PoC cũ là kiểm tra cấu trúc, không phải chứng nhận ngữ nghĩa SH/SOT. Production History Store không được cập nhật từ kết quả nghiên cứu.

## Kiểm thử và integrity

| Kiểm tra đã chạy | Kết quả |
|---|---|
| `python -m unittest discover -s tests -p test_penalty_semantics.py -v` | **16/16 pass** |
| Toàn bộ `unittest discover -s tests`, runner chặn socket/DNS và bỏ API key khỏi environment | **176/176 pass**, 0 failures, 0 errors, 0 skipped; 58.948 giây |
| Pin manifest và SHA-256 107 file frozen | Khớp toàn bộ |
| Baseline trước phase của 133 file tracked | Không file nào thay đổi |
| Artifact LR, fitted imputer và 13 feature | Khớp metadata và checksum frozen |
| `.env` và credit ledger riêng | Byte-identical; vẫn ignored/untracked |

Runner/log/JSON kết quả đầy đủ giữ trong thư mục ignored `outputs/provider_poc/raw/semantic_audit_20261121/`. Không cần key thật hoặc kết nối mạng để chạy test. Các test client cũ dùng session và credential giả lập.

Các test mới bao phủ không penalty, thành công, thủ môn cứu, ra ngoài/trúng khung, nhiều penalty, thiếu metadata, số âm sau tái tạo, tập con bất khả thi, contract chưa xác minh và kiểu dữ liệu không hợp lệ. Phản ví dụ tổng hợp kiểm chứng rằng attempts/goals giống nhau vẫn có thể cho SOT khác nhau. Auditor tái lập thống kê và từ chối thiếu góc nhìn/non-integer.

Artifact test pin manifest SHA-256 và kiểm tra 107 file gốc bao gồm model, metadata, preprocessing, Phase 7, Feature Builder, production history; kiểm tra thêm đúng 13 feature, LR và fitted imputer. Kiểm tra baseline cuối phase bảo toàn cả 133 file tracked có sẵn.

## API, dữ liệu riêng và GitHub

Phase này thực hiện **0 billable API calls**. Không chạy expanded sample, historical backfill, retraining, scheduler hoặc production migration. Ledger cũ không được sửa; không suy ra số credit tính phí thực tế từ số đã reserve.

Chỉ public báo cáo, helper và tests. Raw cache, số liệu so sánh provider, `.env` và log giữ local trong vùng ignored. Đã rà soát diff của đúng 5 file mới và kiểm tra credential thật không xuất hiện trong nội dung công bố; không stage thay đổi ngoài allowlist. Bàn giao bằng push nhánh riêng, không merge.

## Đề nghị Phase 8.5.2B

Ưu tiên lấy xác nhận định nghĩa FBref lịch sử và StrikerAPI, sau đó mới đề nghị pilot nhỏ có hạn mức và scope riêng. `get_events(kind=shots)` là ứng viên đầu tiên để kiểm tra penalty chưa thành bàn; cần đủ trang, định danh đúng đội/trận, loại shootout/retake và mapping outcome chính thức. Chỉ xét `get_shot_map` nếu cần bổ sung coverage hoặc aggregate penalty SOT đã được xác nhận. Không bảo đảm endpoint bổ sung tự giải quyết được mọi thiếu hụt.

Điều kiện tiến tiếp: đủ metadata và đối soát chính xác từng loại penalty; không đoán outcome hoặc impute. XG khác nguồn và as-of vẫn là cổng độc lập. Dừng ở review Phase 8.5.2A; pilot 8.5.2B chưa được thực hiện.
