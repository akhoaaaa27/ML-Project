# XPECTA Phase 8.5.5 — Final Integration Gate

**PASS — Phase 8.5.5 Final Integration Gate**

Lượt kiểm chứng ngày 22/11/2026 đánh giá branch `phase8.5.5-rolling-prematch-forecast` từ base `c1138551121edab1d0c37e0a25f5ed09493f75a3`. Commit được chạy là `58534c0a12f7a9c7260bcbd61245d440a4377ab0`, sau commit eligibility và generation `a3e9235`. Các thay đổi ở hai commit này chỉ thêm module, test và tài liệu forecast.

Full regression offline thực thi **326 test trong 140,465 giây**, gồm 299 test sẵn có và 27 test forecast. Tất cả pass, zero failures/errors/skips, exit 0. Dùng Python 3.14.0 và pinned environment. Existing runner chặn socket connect và không cần API credentials. Các đường dẫn kết quả chi tiết đều được Git-ignore.

```powershell
.venv/Scripts/python.exe -m scripts.multisource.validate_refresh --workspace data/external/multisource/forecasts/gate-855-58534c0/regression --output data/external/multisource/forecasts/gate-855-58534c0/regression-report.json
.venv/Scripts/python.exe -m scripts.multisource.forecast_demo --name final-855-58534c0
```

| AC | Trạng thái | Bằng chứng |
|---|---|---|
| AC-01 | PASS | Test đủ READY, EARLY_READY, WAITING_DATA, UNAVAILABLE với kickoff, trạng thái và freshness |
| AC-02 | PASS | Test một và nhiều trận trung gian; demo A publish INITIAL/EARLY_READY |
| AC-03 | PASS | Coverage chưa đủ và actual last-five thiếu thống kê bị chặn; pending ngoài cửa sổ vẫn suy luận |
| AC-04 | PASS | Strict-before theo UTC date, kết quả cùng ngày/tương lai không đổi feature; fixture tới kickoff bị chặn; real clock do hệ thống cấp |
| AC-05 | PASS | Demo B publish bằng verified successor từ workflow Phase 8.5.4; V1 và hash vẫn nguyên, V2 giữ binding riêng |
| AC-06 | PASS | Output khớp trực tiếp Frozen LR; Demo C cùng features trả NO_CHANGE; model parity guard kiểm cả raw và clipped |
| AC-07 | PASS | Kiểm checksum, lineage, hai writer, stale writer, lỗi ghi tạm và reschedule; hai record bất biến; DB hash nguyên |
| AC-08 | PASS | Demo và giao diện Python tái lập được; namespace tách biệt, snapshot bảo toàn và production approval tắt |

## Demo và dữ liệu thật

| Demo | Quan sát |
|---|---|
| A | Revision 1, INITIAL/EARLY_READY, cutoff 19/11 UTC; xG tổng hợp 1.4364 / 1.1047 |
| B | Một completion tổng hợp được publish qua Phase 8.5.4; revision 2, UPDATED/EARLY_READY, cutoff 21/11 UTC; xG 1.4233 / 1.0971; 6 feature thay đổi |
| C | Snapshot khác, cùng 13 feature; NO_CHANGE giữ ID V2, tổng số revision vẫn bằng hai |
| D | WAITING_DATA với MISSING_ROLLING_STATISTICS |
| E | UNAVAILABLE cho key không hợp lệ; hồi quy cũng kiểm thời điểm kickoff |
| F | Replay V3 thành công 123/123 fixture, 246 team predictions; parity 111/111, feature và raw prediction delta bằng 0 |

Kiểm tra eligibility thật, chỉ đọc, tại **22/11/2026 15:25:43 giờ Việt Nam** trên V3 quét 380 fixture. Có 5 READY, 85 EARLY_READY, 166 WAITING_DATA và 124 UNAVAILABLE. Trong nhóm chờ có 125 trường hợp thiếu thống kê trong cửa sổ và 41 trường hợp thiếu coverage. Những số này gắn với lần quét và đồng hồ cụ thể; trạng thái sẽ đổi theo lịch và freshness. Lượt gate không ghi forecast thật. Demo A–E dùng clock mô phỏng và F dùng historical replay.

## Toàn vẹn và giới hạn

Đã so SHA với protected manifest từ Git base. **107/107 và 77/77** mục khớp, hai tập có phần giao. **8 file DB/manifest** nghiên cứu đối chiếu với baseline Phase 8.5.4 vẫn nguyên vẹn. Composite History V3 qua SQLite integrity/FK, fingerprints khớp. Model artifact SHA-256 `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69`. Production History Store SHA-256 `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982`. V3 SHA-256 `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e`. 13 feature, preprocessing và Phase 7 giữ nguyên. Runner và demo dùng input local, không tải dataset hay gọi paid API.

Schedule freshness v1.0 là 48 giờ kể từ observation đã xác minh. Lịch sử đội có ngưỡng 45 ngày và có xử lý riêng cho zero-history được xác nhận. Cutoff theo ngày và eligibility phụ thuộc bằng chứng snapshot. Không có chứng minh intraday hay statistical equivalence giữa các provider. Forecast là xG tổng mỗi đội và không hàm ý xác suất thắng hay accuracy mới. Ledger phục vụ local research, cần hard link trên cùng volume và xử lý thủ công nếu writer chết để lại lock.

Bằng chứng định lượng nằm trong [report JSON](PHASE_8_5_5_FINAL_INTEGRATION.json). Hướng dẫn chạy và giao diện đọc nằm trong [demo guide](FORECAST_DEMO_GUIDE.md) và [data contract](FORECAST_DATA_CONTRACT.md).
