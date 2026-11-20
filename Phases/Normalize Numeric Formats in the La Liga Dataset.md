# Báo cáo chuẩn hóa định dạng số trong bộ dữ liệu La Liga

## 1. Mục tiêu và phạm vi

Chuẩn hóa dấu thập phân trong dữ liệu đã qua Feature Engineering; bảo toàn giá trị, thứ tự và cấu trúc dữ liệu. Không tính lại features, chia Train/Test, thực hiện Cross-Validation hoặc huấn luyện mô hình.

## 2. Mã nguồn, thư viện và lệnh thực thi

- Mã nguồn: `scripts/normalize_laliga_numeric.py`.
- File nguồn: `D:\Documents\University\Năm 2\HK1\Machine Learning\all of thíngs r abt project\data\laliga_processed.csv`.
- File đầu ra: `D:\Documents\University\Năm 2\HK1\Machine Learning\all of thíngs r abt project\data\laliga_processed_normalized.csv`.
- Python `3.14.0`; Pandas `3.1.0`; NumPy `2.5.4`.
- Các thư viện csv, decimal, hashlib, pathlib, tempfile, os, argparse, platform, re, shlex, sys thuộc thư viện chuẩn Python.
- Lệnh gọi script của lần chạy này:

```powershell
python scripts/normalize_laliga_numeric.py
```

Đường dẫn dữ liệu mặc định được xác định từ vị trí script; có thể chạy từ thư mục khác. `--input` cho phép chỉ định file nguồn; đầu ra và báo cáo luôn nằm cạnh nguồn.

### Phương pháp

1. Đọc bằng Pandas mặc định để ghi nhận kiểu dữ liệu; đọc thêm bằng `dtype=str, keep_default_na=False, na_filter=False` để bảo toàn biểu diễn từng ô. Kiểm tra CSV, schema thực tế, giá trị thiếu, ô rỗng, bản ghi trùng và định dạng số.
2. Chỉ thay `,` thành `.` trong 10 cột yêu cầu bằng `.str.replace(..., regex=False)`. Kiểm tra cú pháp số, `pd.to_numeric(errors="raise")` và số hữu hạn; không dùng `errors="coerce"` hoặc điền giá trị tùy ý.
3. Ghi chuỗi đã chuẩn hóa qua `to_csv(index=False, sep=",", encoding="utf-8")` vào file tạm cùng thư mục. Không ghi thông qua float nên không làm tròn chữ số trong CSV.
4. Đọc lại file tạm bằng `pandas.read_csv()` mặc định và đối chiếu từng ô, kiểu dữ liệu, metadata, thứ tự bản ghi, features, target. Dùng Decimal so sánh số chính xác và kiểm tra riêng kết quả phân tích số của Pandas.
5. Chỉ khi tất cả validation thành công và nguồn không đổi mới dùng `os.replace` để cập nhật đầu ra. Khi chuyển đổi hoặc validation thất bại, giữ nguyên đầu ra cũ và ghi rõ lỗi vào chính báo cáo này. File tạm được dọn sau mỗi lần chạy.

## 3. Khảo sát dữ liệu gốc

- Kích thước: **4700 dòng × 26 cột**.
- Số đội: 28; số match_id: 2350.
- Khoảng ngày: `2019-08-16` đến `2025-09-30`.
- Giá trị thiếu: 0; ô rỗng: 0; bản ghi trùng: 0.

### Tên cột, thứ tự và kiểu dữ liệu

Kiểu `str` là kiểu chuỗi được Pandas suy luận trong môi trường thực thi này.

| Vị trí | Cột | Kiểu gốc | Kiểu sau chuẩn hóa |
|---|---|---|---|
| 1 | `match_id` | `int64` | `int64` |
| 2 | `season` | `int64` | `int64` |
| 3 | `team` | `str` | `str` |
| 4 | `date` | `str` | `str` |
| 5 | `round` | `str` | `str` |
| 6 | `venue` | `str` | `str` |
| 7 | `gf` | `int64` | `int64` |
| 8 | `ga` | `int64` | `int64` |
| 9 | `opponent` | `str` | `str` |
| 10 | `xg` | `str` | `float64` |
| 11 | `xga` | `str` | `float64` |
| 12 | `sh` | `int64` | `int64` |
| 13 | `sot` | `int64` | `int64` |
| 14 | `is_home` | `int64` | `int64` |
| 15 | `matches_seen` | `int64` | `int64` |
| 16 | `short_history` | `int64` | `int64` |
| 17 | `xg_avg5` | `str` | `float64` |
| 18 | `xga_avg5` | `str` | `float64` |
| 19 | `gf_avg5` | `str` | `float64` |
| 20 | `ga_avg5` | `str` | `float64` |
| 21 | `shot_avg5` | `str` | `float64` |
| 22 | `sot_avg5` | `str` | `float64` |
| 23 | `opponent_xg_avg5` | `str` | `float64` |
| 24 | `opponent_xga_avg5` | `str` | `float64` |
| 25 | `opponent_matches_seen` | `int64` | `int64` |
| 26 | `opponent_short_history` | `int64` | `int64` |

## 4. Các cột chuẩn hóa

| Cột | Số ô có dấu phẩy thập phân trong nguồn |
|---|---:|
| `xg` | 4275 |
| `xga` | 4275 |
| `xg_avg5` | 4599 |
| `xga_avg5` | 4588 |
| `gf_avg5` | 3694 |
| `ga_avg5` | 3714 |
| `shot_avg5` | 3730 |
| `sot_avg5` | 3731 |
| `opponent_xg_avg5` | 4599 |
| `opponent_xga_avg5` | 4588 |

Tổng số ô cần thay dấu thập phân: **41793**. Các ô còn lại giữ nguyên biểu diễn.

## 5. Kết quả validation đã thực thi

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Kích thước | Đạt | Trước và sau: 4700 dòng × 26 cột. |
| Tên và thứ tự cột | Đạt | Toàn bộ tên cột và vị trí cột được bảo toàn. |
| Thứ tự và số lượng bản ghi | Đạt | Không có sai khác. |
| Giá trị thiếu | Đạt | Trước: 0; sau: 0. |
| Ô rỗng | Đạt | Không có ô rỗng hoặc chỉ chứa khoảng trắng. |
| Cột ngoài phạm vi chuyển đổi | Đạt | 16 cột đối chiếu từng ô. Không có sai khác. |
| Định danh và metadata | Đạt | match_id, season, team, date, round, venue, opponent giữ nguyên từng dòng. |
| Kiểu dữ liệu số | Đạt | 21 cột là kiểu số khi đọc bằng pandas.read_csv() mặc định. |
| Tương đương số chính xác | Đạt | 98700 ô số so sánh bằng Decimal; 0 sai khác. |
| Giá trị Pandas sau khi đọc mặc định | Đạt | Toàn bộ cột số có giá trị giống dữ liệu nguồn được phân tích đúng dấu thập phân. |
| Chữ số và độ chính xác | Đạt | 47000 ô giữ nguyên chữ số; chỉ thay dấu thập phân, không làm tròn. |
| Dấu thập phân | Đạt | Không còn dấu phẩy thập phân trong 10 cột chuẩn hóa. |
| Bản ghi trùng | Đạt | Trước: 0; sau: 0; không tự loại bản ghi. |
| 13 input features | Đạt | 13/13 features có kiểu số. |
| Target xg | Đạt | xg có kiểu float64. |
| Bảo toàn Feature Engineering | Đạt | 61100 ô thuộc 13 features đã nằm trong phép đối chiếu Decimal chính xác; không tính lại. |
| Delimiter và cấu trúc CSV | Đạt | Delimiter dấu phẩy; mỗi bản ghi có đúng số trường; không thêm index. |
| Đọc nhất quán | Đạt | Hai lần đọc mặc định cho cùng dữ liệu và kiểu dữ liệu. |
| File gốc và file hiện có | Đạt | SHA-256 của 4 file được bảo toàn, gồm nguồn và các file dữ liệu hiện có. |

### 13 input features và target

| Cột | Kiểu dữ liệu | Giá trị thiếu |
|---|---|---:|
| `is_home` | `int64` | 0 |
| `matches_seen` | `int64` | 0 |
| `short_history` | `int64` | 0 |
| `xg_avg5` | `float64` | 0 |
| `xga_avg5` | `float64` | 0 |
| `gf_avg5` | `float64` | 0 |
| `ga_avg5` | `float64` | 0 |
| `shot_avg5` | `float64` | 0 |
| `sot_avg5` | `float64` | 0 |
| `opponent_xg_avg5` | `float64` | 0 |
| `opponent_xga_avg5` | `float64` | 0 |
| `opponent_matches_seen` | `int64` | 0 |
| `opponent_short_history` | `int64` | 0 |
| `xg` | `float64` | 0 |

### Dấu kiểm tra và khả năng tái lập

- SHA-256 nguồn trước xử lý: `666661b49f4055104bd73b8ceb53f50407bf6e90cae6551dbbee820fe9fd6a3a`.
- SHA-256 đầu ra đã validation: `90000ce22f42abe5eb5b5bfa38ad1ed5ef7b1c1c75cd4d39e749e7b324e0e5ca`.
- So sánh với đầu ra có trước lần chạy: SHA-256 giống hoàn toàn; đầu ra tái lập từng byte so với lần chạy trước.

## 6. Tóm tắt thay đổi file

- Bổ sung mã nguồn `scripts/normalize_laliga_numeric.py`; không có script tương đương khi khảo sát workspace.
- Đã tạo/cập nhật CSV chuẩn hóa bằng chính script sau khi validation thành công.
- Tạo/cập nhật duy nhất báo cáo `Normalize Numeric Formats in the La Liga Dataset.md`; không tạo các bản sao mang hậu tố phiên bản.
- Giữ nguyên CSV gốc, dữ liệu thô, Excel và `preprocess_laliga.py`; không gọi script Feature Engineering.
- Workspace khảo sát chưa phải Git repository; không khởi tạo repository, commit, push hoặc thực hiện thao tác Git khác.

## 7. Cảnh báo và vấn đề

Không phát hiện lỗi chuyển đổi, giá trị số không hợp lệ hoặc sai khác giá trị trong phạm vi các kiểm tra đã thực thi. Không có validation thất bại hoặc công việc chưa hoàn tất trong phạm vi tác vụ.

CSV không lưu dtype như một schema; kiểu số được xác nhận qua việc đọc mặc định bằng Pandas. Decimal và đối chiếu chuỗi xác nhận độ chính xác của CSV; float64 trong bộ nhớ vẫn tuân theo biểu diễn số thực dấu phẩy động thông thường.

Không thực hiện kiểm toán Data Leakage hoặc đánh giá chất lượng mô hình.

## 8. Kiểm chứng bổ sung và vấn đề đã xử lý

Các tình huống dưới đây đã được thực thi trên bản sao trong thư mục tạm hệ thống, không trên dữ liệu dự án. Chúng được thiết kế để thất bại; kết quả đúng yêu cầu là báo lỗi, ghi báo cáo chưa hoàn tất và giữ nguyên CSV đầu ra cũ. Dữ liệu và báo cáo kiểm chứng tạm đã được dọn sạch.

| Tình huống mô phỏng | Kết quả thực tế | Bảo toàn đầu ra cũ |
|---|---|---|
| Số không hợp lệ tại xg, bản ghi 1: `2,1,3` | Phát hiện lỗi đúng yêu cầu; ghi báo cáo chưa hoàn tất | SHA-256 không đổi |
| File tạm bị thay xg bản ghi 1 từ `2.1` thành `999.0` | Phát hiện lỗi đúng yêu cầu; ghi báo cáo chưa hoàn tất | SHA-256 không đổi |
| Nguồn kiểm chứng thiếu cột xg | Phát hiện lỗi đúng yêu cầu; ghi báo cáo chưa hoàn tất | SHA-256 không đổi |

- Với số không hợp lệ, script chỉ rõ cột `xg`, bản ghi 1 và giá trị `2,1,3`; không tự chuyển thành NaN.
- Với file tạm bị sai giá trị, validation chỉ rõ cột `xg`, bản ghi 1 và sai khác `2.1` → `999.0`; không cập nhật đầu ra.
- Với nguồn thiếu cột, script báo cấu trúc không khớp và vẫn ghi được báo cáo thất bại.
- SHA-256 của nguồn kiểm chứng và CSV cũ giữ nguyên trong cả ba tình huống; không còn file tạm.
- Script đã được chạy thành công hai lần liên tiếp bằng đúng lệnh `python scripts/normalize_laliga_numeric.py`, cả hai trả mã thoát 0 và 19 validation đạt. SHA-256 của CSV giống hoàn toàn giữa các lần chạy.
- Lần gọi đầu trước khi sửa xử lý terminal trả mã thoát 1 do `UnicodeEncodeError`: terminal Windows dùng cp1252 không in được thông báo tiếng Việt, sau khi CSV đã vượt qua validation và được ghi. Đã sửa mã nguồn để cấu hình stdout/stderr UTF-8; hai lần chạy sau hoàn tất thành công. Đây là lỗi hiển thị đã giải quyết, không phải lỗi giá trị dữ liệu.
- Sau các lần chạy và kiểm chứng, CSV nguồn và CSV chuẩn hóa tiếp tục khớp các SHA-256 đã ghi. 10 cột yêu cầu có 0 định dạng số không hợp lệ và 0 giá trị không hữu hạn trên dữ liệu dự án.
- Các tình huống lỗi mô phỏng không phải bất thường tồn tại trong bộ dữ liệu thực tế. Không còn lỗi chưa giải quyết trong phạm vi tác vụ.

## 9. Kết luận

Đã hoàn tất chuẩn hóa với 19 kiểm tra đạt. Bộ dữ liệu sẵn sàng cho bước Machine Learning tiếp theo xét theo định dạng số và tính toàn vẹn được yêu cầu; 13 input features và target xg đều là kiểu số. Giá trị Feature Engineering, cấu trúc, metadata và thứ tự dữ liệu được bảo toàn.

Dừng tại chuẩn hóa, validation và báo cáo; chỉ thực hiện các bước tiếp theo khi có yêu cầu rõ ràng của người dùng.
