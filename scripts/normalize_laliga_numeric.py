"""Chuẩn hóa dấu thập phân và kiểm tra dữ liệu La Liga, không tính lại features.

Chạy từ workspace: python scripts/normalize_laliga_numeric.py
Đường dẫn mặc định được xác định theo vị trí script, độc lập thư mục chạy.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
import platform
import re
import shlex
import sys
import tempfile
from decimal import Decimal

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "laliga_processed.csv"
REPORT_NAME = "Normalize Numeric Formats in the La Liga Dataset.md"
CONVERT_COLUMNS = (
    "xg", "xga", "xg_avg5", "xga_avg5", "gf_avg5", "ga_avg5",
    "shot_avg5", "sot_avg5", "opponent_xg_avg5", "opponent_xga_avg5",
)
FEATURES = (
    "is_home", "matches_seen", "short_history", "xg_avg5", "xga_avg5",
    "gf_avg5", "ga_avg5", "shot_avg5", "sot_avg5", "opponent_xg_avg5",
    "opponent_xga_avg5", "opponent_matches_seen", "opponent_short_history",
)
TEXT_COLUMNS = ("team", "date", "round", "venue", "opponent")
METADATA = ("match_id", "season", *TEXT_COLUMNS)
REQUIRED_COLUMNS = (
    "match_id", "season", "team", "date", "round", "venue", "gf", "ga",
    "opponent", "xg", "xga", "sh", "sot", *FEATURES,
)
NUMBER_PATTERN = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text_frame(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)


def count_text(frame: pd.DataFrame, token: str) -> dict[str, int]:
    return {c: int(frame[c].str.contains(token, regex=False).sum()) for c in frame}


def describe_difference(left: pd.DataFrame, right: pd.DataFrame) -> str:
    if left.shape != right.shape or list(left.columns) != list(right.columns):
        return "Cấu trúc bảng không khớp."
    for c in left:
        different = ~left[c].eq(right[c])
        if different.any():
            i = different[different].index[0]
            return f"Cột {c}, bản ghi {i + 1}: {left.at[i, c]!r} → {right.at[i, c]!r}."
    return "Không có sai khác."


def check(checks: list, name: str, condition: bool, evidence: str) -> None:
    passed = bool(condition)
    checks.append((name, passed, evidence))
    if not passed:
        raise ValueError(f"{name}: {evidence}")


def inspect(source: Path, state: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader)
        if len(header) != len(set(header)):
            raise ValueError("Tiêu đề CSV có tên cột trùng; chưa chuyển đổi dữ liệu.")
        for record, row in enumerate(reader, 1):
            if len(row) != len(header):
                raise ValueError(f"Bản ghi {record}: {len(row)} trường, cần {len(header)} trường.")
    raw = read_text_frame(source)
    before = pd.read_csv(source)
    state.update(raw=raw, before=before)
    if list(raw.columns) != list(REQUIRED_COLUMNS):
        raise ValueError(f"Cấu trúc cột khác cấu trúc La Liga đã xác minh: {list(raw.columns)!r}.")
    if raw.empty:
        raise ValueError("Dataset không có bản ghi.")
    missing = int(before.isna().sum().sum())
    blank_mask = raw.apply(lambda s: s.str.strip().eq(""))
    state.update(missing=missing, blanks=int(blank_mask.sum().sum()),
                 duplicates=int(raw.duplicated().sum()), commas=count_text(raw, ","))
    for c in raw:
        invalid = blank_mask[c] | before[c].isna()
        if invalid.any():
            i = invalid[invalid].index[0]
            raise ValueError(f"Cột {c}, bản ghi {i + 1}: giá trị thiếu hoặc rỗng {raw.at[i, c]!r}; không tự điền.")
    return raw, before


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    result = raw.copy()
    for c in raw:
        if c in TEXT_COLUMNS:
            continue
        text = raw[c].str.replace(",", ".", regex=False) if c in CONVERT_COLUMNS else raw[c]
        valid = text.str.fullmatch(NUMBER_PATTERN)
        if not valid.all():
            i = valid[~valid].index[0]
            raise ValueError(f"Cột {c}, bản ghi {i + 1}: định dạng số không hợp lệ {raw.at[i, c]!r}; không tự sửa.")
        try:
            numeric = pd.to_numeric(text, errors="raise")
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"Không chuyển được cột {c} sang kiểu số: {exc}") from exc
        finite = np.isfinite(numeric.to_numpy())
        if not finite.all():
            i = int(np.flatnonzero(~finite)[0])
            raise ValueError(f"Cột {c}, bản ghi {i + 1}: số không hữu hạn {raw.at[i, c]!r}.")
        if c in CONVERT_COLUMNS:
            result[c] = text
    return result


def validate(raw: pd.DataFrame, before: pd.DataFrame, expected: pd.DataFrame,
             staged: Path, state: dict) -> pd.DataFrame:
    after = pd.read_csv(staged)
    actual = read_text_frame(staged)
    checks = state["checks"]
    check(checks, "Kích thước", after.shape == before.shape,
          f"Trước và sau: {len(raw)} dòng × {len(raw.columns)} cột.")
    check(checks, "Tên và thứ tự cột", list(actual.columns) == list(raw.columns),
          "Toàn bộ tên cột và vị trí cột được bảo toàn.")
    check(checks, "Thứ tự và số lượng bản ghi", expected.equals(actual),
          describe_difference(expected, actual))
    check(checks, "Giá trị thiếu", before.isna().equals(after.isna()),
          f"Trước: {int(before.isna().sum().sum())}; sau: {int(after.isna().sum().sum())}.")
    check(checks, "Ô rỗng", not actual.apply(lambda s: s.str.strip().eq("").any()).any(),
          "Không có ô rỗng hoặc chỉ chứa khoảng trắng.")
    unchanged = [c for c in raw if c not in CONVERT_COLUMNS]
    check(checks, "Cột ngoài phạm vi chuyển đổi", raw[unchanged].equals(actual[unchanged]),
          f"{len(unchanged)} cột đối chiếu từng ô. " + describe_difference(raw[unchanged], actual[unchanged]))
    check(checks, "Định danh và metadata", raw[list(METADATA)].equals(actual[list(METADATA)]),
          "match_id, season, team, date, round, venue, opponent giữ nguyên từng dòng.")
    numeric_columns = [c for c in raw if c not in TEXT_COLUMNS]
    check(checks, "Kiểu dữ liệu số", all(is_numeric_dtype(after[c]) for c in numeric_columns),
          f"{len(numeric_columns)} cột là kiểu số khi đọc bằng pandas.read_csv() mặc định.")
    for c in numeric_columns:
        for i, (a, b) in enumerate(zip(raw[c], actual[c]), 1):
            if Decimal(a.replace(",", ".")) != Decimal(b):
                check(checks, "Tương đương số chính xác", False,
                      f"Cột {c}, bản ghi {i}: {a!r} → {b!r}.")
    state["numeric_cells"] = len(raw) * len(numeric_columns)
    check(checks, "Tương đương số chính xác", True,
          f"{state['numeric_cells']} ô số so sánh bằng Decimal; 0 sai khác.")
    for c in numeric_columns:
        original = pd.to_numeric(raw[c].str.replace(",", ".", regex=False), errors="raise")
        same = original.eq(after[c])
        if not same.all():
            i = same[~same].index[0]
            check(checks, "Giá trị Pandas sau khi đọc mặc định", False,
                  f"Cột {c}, bản ghi {i + 1}: {original.iat[i]!r} → {after.at[i, c]!r}; có thể do suy luận hoặc làm tròn khi phân tích CSV.")
    check(checks, "Giá trị Pandas sau khi đọc mặc định", True,
          "Toàn bộ cột số có giá trị giống dữ liệu nguồn được phân tích đúng dấu thập phân.")
    check(checks, "Chữ số và độ chính xác", all(
        actual[c].equals(raw[c].str.replace(",", ".", regex=False)) for c in CONVERT_COLUMNS),
        f"{len(raw) * len(CONVERT_COLUMNS)} ô giữ nguyên chữ số; chỉ thay dấu thập phân, không làm tròn.")
    check(checks, "Dấu thập phân", all(count_text(actual, ",")[c] == 0 for c in CONVERT_COLUMNS),
          "Không còn dấu phẩy thập phân trong 10 cột chuẩn hóa.")
    check(checks, "Bản ghi trùng", int(raw.duplicated().sum()) == int(actual.duplicated().sum()),
          f"Trước: {int(raw.duplicated().sum())}; sau: {int(actual.duplicated().sum())}; không tự loại bản ghi.")
    feature_slice = list(after.loc[:, "is_home":"opponent_short_history"].columns)
    check(checks, "13 input features", feature_slice == list(FEATURES) and all(
        is_numeric_dtype(after[c]) for c in FEATURES), "13/13 features có kiểu số.")
    check(checks, "Target xg", is_numeric_dtype(after["xg"]), f"xg có kiểu {after['xg'].dtype}.")
    check(checks, "Bảo toàn Feature Engineering", True,
          f"{len(raw) * len(FEATURES)} ô thuộc 13 features đã nằm trong phép đối chiếu Decimal chính xác; không tính lại.")
    with staged.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream, strict=True))
    check(checks, "Delimiter và cấu trúc CSV", len(rows) == len(raw) + 1 and all(
        len(r) == len(raw.columns) for r in rows), "Delimiter dấu phẩy; mỗi bản ghi có đúng số trường; không thêm index.")
    check(checks, "Đọc nhất quán", after.equals(pd.read_csv(staged)),
          "Hai lần đọc mặc định cho cùng dữ liệu và kiểu dữ liệu.")
    state["after"] = after
    return after


def build_report(state: dict, error: str | None = None) -> str:
    lines = ["# Báo cáo chuẩn hóa định dạng số trong bộ dữ liệu La Liga", "",
             "## 1. Mục tiêu và phạm vi", "",
             "Chuẩn hóa dấu thập phân trong dữ liệu đã qua Feature Engineering; bảo toàn giá trị, thứ tự và cấu trúc dữ liệu. Không tính lại features, chia Train/Test, thực hiện Cross-Validation hoặc huấn luyện mô hình.", "",
             "## 2. Mã nguồn, thư viện và lệnh thực thi", "",
             "- Mã nguồn: `scripts/normalize_laliga_numeric.py`.",
             f"- File nguồn: `{state['source']}`.",
             f"- File đầu ra: `{state['output']}`.",
             f"- Python `{platform.python_version()}`; Pandas `{pd.__version__}`; NumPy `{np.__version__}`.",
             "- Các thư viện csv, decimal, hashlib, pathlib, tempfile, os, argparse, platform, re, shlex, sys thuộc thư viện chuẩn Python.",
             "- Lệnh gọi script của lần chạy này:", "", "```powershell", state["command"], "```", "",
             "Đường dẫn dữ liệu mặc định được xác định từ vị trí script; có thể chạy từ thư mục khác. `--input` cho phép chỉ định file nguồn; đầu ra và báo cáo luôn nằm cạnh nguồn.", "",
             "### Phương pháp", "",
             "1. Đọc bằng Pandas mặc định để ghi nhận kiểu dữ liệu; đọc thêm bằng `dtype=str, keep_default_na=False, na_filter=False` để bảo toàn biểu diễn từng ô. Kiểm tra CSV, schema thực tế, giá trị thiếu, ô rỗng, bản ghi trùng và định dạng số.",
             "2. Chỉ thay `,` thành `.` trong 10 cột yêu cầu bằng `.str.replace(..., regex=False)`. Kiểm tra cú pháp số, `pd.to_numeric(errors=\"raise\")` và số hữu hạn; không dùng `errors=\"coerce\"` hoặc điền giá trị tùy ý.",
             "3. Ghi chuỗi đã chuẩn hóa qua `to_csv(index=False, sep=\",\", encoding=\"utf-8\")` vào file tạm cùng thư mục. Không ghi thông qua float nên không làm tròn chữ số trong CSV.",
             "4. Đọc lại file tạm bằng `pandas.read_csv()` mặc định và đối chiếu từng ô, kiểu dữ liệu, metadata, thứ tự bản ghi, features, target. Dùng Decimal so sánh số chính xác và kiểm tra riêng kết quả phân tích số của Pandas.",
             "5. Chỉ khi tất cả validation thành công và nguồn không đổi mới dùng `os.replace` để cập nhật đầu ra. Khi chuyển đổi hoặc validation thất bại, giữ nguyên đầu ra cũ và ghi rõ lỗi vào chính báo cáo này. File tạm được dọn sau mỗi lần chạy.", ""]
    if "raw" in state:
        raw, before = state["raw"], state["before"]
        lines += ["## 3. Khảo sát dữ liệu gốc", "",
                  f"- Kích thước: **{len(raw)} dòng × {len(raw.columns)} cột**.",
                  f"- Số đội: {raw['team'].nunique() if 'team' in raw else 'thiếu cột team'}; số match_id: {raw['match_id'].nunique() if 'match_id' in raw else 'thiếu cột match_id'}.",
                  (f"- Khoảng ngày: `{raw['date'].min()}` đến `{raw['date'].max()}`." if 'date' in raw else "- Thiếu cột date; không xác định khoảng ngày."),
                  f"- Giá trị thiếu: {state.get('missing', 'chưa kiểm tra')}; ô rỗng: {state.get('blanks', 'chưa kiểm tra')}; bản ghi trùng: {state.get('duplicates', 'chưa kiểm tra')}.", "",
                  "### Tên cột, thứ tự và kiểu dữ liệu", "",
                  "Kiểu `str` là kiểu chuỗi được Pandas suy luận trong môi trường thực thi này.", "",
                  "| Vị trí | Cột | Kiểu gốc | Kiểu sau chuẩn hóa |", "|---|---|---|---|"]
        for i, c in enumerate(raw, 1):
            dtype = str(state["after"][c].dtype) if "after" in state else "chưa xác nhận"
            lines.append(f"| {i} | `{c}` | `{before[c].dtype}` | `{dtype}` |")
        lines += ["", "## 4. Các cột chuẩn hóa", "",
                  "| Cột | Số ô có dấu phẩy thập phân trong nguồn |", "|---|---:|"]
        for c in CONVERT_COLUMNS:
            lines.append(f"| `{c}` | {state.get('commas', {}).get(c, 'chưa kiểm tra')} |")
        if "commas" in state:
            lines += ["", f"Tổng số ô cần thay dấu thập phân: **{sum(state['commas'].get(c, 0) for c in CONVERT_COLUMNS)}**. Các ô còn lại giữ nguyên biểu diễn."]
    lines += ["", "## 5. Kết quả validation đã thực thi", "",
              "| Kiểm tra | Kết quả | Bằng chứng |", "|---|---|---|"]
    for name, passed, evidence in state["checks"]:
        lines.append(f"| {name} | {'Đạt' if passed else 'Không đạt'} | {evidence.replace('|', '/')} |")
    if "after" in state:
        lines += ["", "### 13 input features và target", "",
                  "| Cột | Kiểu dữ liệu | Giá trị thiếu |", "|---|---|---:|"]
        for c in (*FEATURES, "xg"):
            lines.append(f"| `{c}` | `{state['after'][c].dtype}` | {int(state['after'][c].isna().sum())} |")
    lines += ["", "### Dấu kiểm tra và khả năng tái lập", "",
              f"- SHA-256 nguồn trước xử lý: `{state.get('source_hash', 'chưa xác nhận')}`.",
              f"- SHA-256 đầu ra đã validation: `{state.get('output_hash', 'chưa xác nhận')}`.",
              "- So sánh với đầu ra có trước lần chạy: " + state.get("repeat", "chưa thực hiện") + ".", "",
              "## 6. Tóm tắt thay đổi file", "",
              "- Bổ sung mã nguồn `scripts/normalize_laliga_numeric.py`; không có script tương đương khi khảo sát workspace.",
              "- " + ("Đã tạo/cập nhật CSV chuẩn hóa bằng chính script sau khi validation thành công." if not error else "Lần chạy thất bại; CSV đầu ra cũ không bị thay thế bởi dữ liệu chưa hợp lệ."),
              f"- Tạo/cập nhật duy nhất báo cáo `{REPORT_NAME}`; không tạo các bản sao mang hậu tố phiên bản.",
              "- Giữ nguyên CSV gốc, dữ liệu thô, Excel và `preprocess_laliga.py`; không gọi script Feature Engineering.",
              "- Workspace khảo sát chưa phải Git repository; không khởi tạo repository, commit, push hoặc thực hiện thao tác Git khác.", "",
              "## 7. Cảnh báo và vấn đề", ""]
    if error:
        lines += ["**Tác vụ chưa hoàn tất.**", "", "```text", error, "```", "",
                  "Lỗi ở trên ngăn việc xác nhận dữ liệu mới đủ điều kiện dùng cho Machine Learning. Không tự sửa giá trị ngoài phạm vi; cần giải quyết nguyên nhân và chạy lại script. Các kiểm tra chưa có trong bảng chưa được xác nhận thành công."]
    else:
        lines += ["Không phát hiện lỗi chuyển đổi, giá trị số không hợp lệ hoặc sai khác giá trị trong phạm vi các kiểm tra đã thực thi. Không có validation thất bại hoặc công việc chưa hoàn tất trong phạm vi tác vụ.", "",
                  "CSV không lưu dtype như một schema; kiểu số được xác nhận qua việc đọc mặc định bằng Pandas. Decimal và đối chiếu chuỗi xác nhận độ chính xác của CSV; float64 trong bộ nhớ vẫn tuân theo biểu diễn số thực dấu phẩy động thông thường.", "",
                  "Không thực hiện kiểm toán Data Leakage hoặc đánh giá chất lượng mô hình."]
    lines += ["", "## 8. Kết luận", "",
              ("Chưa thể xác nhận hoàn tất chuẩn hóa; xem lỗi và các kiểm tra còn thiếu ở trên." if error else
               f"Đã hoàn tất chuẩn hóa với {len(state['checks'])} kiểm tra đạt. Bộ dữ liệu sẵn sàng cho bước Machine Learning tiếp theo xét theo định dạng số và tính toàn vẹn được yêu cầu; 13 input features và target xg đều là kiểu số. Giá trị Feature Engineering, cấu trúc, metadata và thứ tự dữ liệu được bảo toàn."), "",
              "Dừng tại chuẩn hóa, validation và báo cáo; chỉ thực hiện các bước tiếp theo khi có yêu cầu rõ ràng của người dùng."]
    return "\n".join(lines) + "\n"


def run(source: Path, command: str) -> dict:
    source = source.resolve()
    output = source.with_name("laliga_processed_normalized.csv")
    report = source.with_name(REPORT_NAME)
    if source in (output, report):
        raise ValueError("File nguồn phải khác file đầu ra và báo cáo.")
    state = dict(source=source, output=output, command=command, checks=[])
    temporary: list[Path] = []
    try:
        state["source_hash"] = sha256(source)
        preserved = {p: sha256(p) for p in source.parent.iterdir()
                     if p.is_file() and p not in (output, report)}
        previous_hash = sha256(output) if output.exists() else None
        raw, before = inspect(source, state)
        normalized = normalize(raw)
        with tempfile.NamedTemporaryFile(dir=source.parent, prefix=".laliga-", suffix=".tmp", delete=False) as handle:
            staged = Path(handle.name)
        temporary.append(staged)
        normalized.to_csv(staged, index=False, sep=",", encoding="utf-8", lineterminator="\n")
        validate(raw, before, normalized, staged, state)
        check(state["checks"], "File gốc và file hiện có", all(sha256(p) == h for p, h in preserved.items()),
              f"SHA-256 của {len(preserved)} file được bảo toàn, gồm nguồn và các file dữ liệu hiện có.")
        state["output_hash"] = sha256(staged)
        if previous_hash is None:
            state["repeat"] = "không có đầu ra trước lần chạy này; cần chạy lại để kiểm chứng giữa hai lần thực thi"
        elif previous_hash == state["output_hash"]:
            state["repeat"] = "SHA-256 giống hoàn toàn; đầu ra tái lập từng byte so với lần chạy trước"
        else:
            state["repeat"] = "SHA-256 khác; không xác nhận tái lập so với đầu ra cũ, có thể nguồn hoặc phiên bản xử lý đã đổi; đầu ra mới vẫn đã vượt qua validation so với nguồn hiện tại"
        with tempfile.NamedTemporaryFile(dir=source.parent, prefix=".laliga-report-", suffix=".tmp", delete=False) as handle:
            staged_report = Path(handle.name)
        temporary.append(staged_report)
        staged_report.write_text(build_report(state), encoding="utf-8")
        os.replace(staged, output)
        os.replace(staged_report, report)
        return state
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        report.write_text(build_report(state, error), encoding="utf-8")
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chuẩn hóa định dạng số La Liga và kiểm tra tính toàn vẹn.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="File CSV gốc; mặc định data/laliga_processed.csv theo vị trí script.")
    args = parser.parse_args()
    command = shlex.join(["python", *sys.argv])
    try:
        state = run(args.input, command)
    except Exception as exc:
        print(f"Chưa hoàn tất: {exc}", file=sys.stderr)
        return 1
    print(f"Hoàn tất: {len(state['checks'])} kiểm tra đạt; {len(state['raw'])} dòng × {len(state['raw'].columns)} cột.")
    print(f"Đã đối chiếu chính xác {state['numeric_cells']} ô số.")
    print(f"Dữ liệu: {state['output']}")
    print(f"Báo cáo: {state['source'].with_name(REPORT_NAME)}")
    print(f"Tái lập: {state['repeat']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
