"""
Preprocessing dữ liệu La Liga: matches_laliga.csv  ->  laliga_processed.xlsx

Mỗi dòng trong CSV là một trận đấu nhìn từ góc độ của MỘT đội (mỗi trận xuất hiện 2 lần:
1 dòng cho đội nhà, 1 dòng cho đội khách).  Script này:
  1. Làm sạch dữ liệu (bỏ cột thừa, chuẩn hóa tên đội, ép kiểu)
  2. Tạo match_id (chung cho 2 dòng của cùng một trận) và is_home
  3. Tạo đặc trưng "phong độ" = trung bình 5 trận GẦN NHẤT TRƯỚC trận đang xét (không rò rỉ dữ liệu)
  4. Ghép đặc trưng của đối thủ vào cùng dòng
  5. Xuất ra file xlsx

Cách dùng:
    python preprocess_laliga.py                                  # dùng đường dẫn mặc định
    python preprocess_laliga.py matches_laliga.csv out.xlsx
"""
import sys
import unicodedata

import pandas as pd

INPUT_CSV = "matches_laliga.csv"
OUTPUT_XLSX = "laliga_processed.xlsx"

WINDOW = 5            # số trận gần nhất dùng để tính trung bình
SHORT_HISTORY_MIN = 5  # < 5 trận lịch sử => short_history = 1

# Giá trị mặc định (prior) cho trận đầu tiên của một đội, khi chưa có lịch sử.
# Đây là các hằng số được chọn thủ công (xấp xỉ trung bình giải đấu) – cần nêu rõ trong báo cáo.
DEFAULT_PRIOR = {
    "xg_avg5": 1.2,
    "xga_avg5": 1.24,
    "gf_avg5": 1.2,
    "ga_avg5": 1.2,
    "shot_avg5": 11.2,
    "sot_avg5": 3.6,
}

# Cột gốc -> cột trung bình 5 trận
ROLLING_MAP = {
    "xg": "xg_avg5",
    "xga": "xga_avg5",
    "gf": "gf_avg5",
    "ga": "ga_avg5",
    "sh": "shot_avg5",
    "sot": "sot_avg5",
}

# Các cột của CSV bị loại: chỉ số thừa, hằng số, toàn NaN hoặc không dùng để mô hình hóa
DROP_COLS = [
    "Unnamed: 0", "time", "comp", "day", "result", "poss", "attendance", "captain",
    "formation", "opp formation", "referee", "match report", "notes",
    "dist", "fk", "pk", "pkatt",
]

FINAL_COLS = [
    "match_id", "season", "team", "date", "round", "venue", "gf", "ga", "opponent",
    "xg", "xga", "sh", "sot", "is_home",
    "matches_seen", "short_history",
    "xg_avg5", "xga_avg5", "gf_avg5", "ga_avg5", "shot_avg5", "sot_avg5",
    "opponent_xg_avg5", "opponent_xga_avg5",
    "opponent_matches_seen", "opponent_short_history",
]


def strip_accents(s: str) -> str:
    """'Atlético' -> 'Atletico', 'Alavés' -> 'Alaves'."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # Chuẩn hóa tên đội (cột `team` đã bỏ dấu, cột `opponent` thì chưa, và 'Betis' != 'Real Betis')
    for col in ("team", "opponent"):
        df[col] = df[col].map(strip_accents).str.strip()
    df["opponent"] = df["opponent"].replace({"Betis": "Real Betis"})

    # Ép kiểu số nguyên cho các cột đếm
    for col in ("gf", "ga", "sh", "sot"):
        df[col] = df[col].astype(int)

    df["is_home"] = (df["venue"] == "Home").astype(int)
    return df.drop(columns=[c for c in DROP_COLS if c in df.columns])


def add_match_id(df: pd.DataFrame) -> pd.DataFrame:
    """Gán cùng một match_id cho 2 dòng (đội nhà + đội khách) của cùng một trận."""
    df = df.copy()
    df["home_team"] = df["team"].where(df["is_home"] == 1, df["opponent"])
    df["away_team"] = df["opponent"].where(df["is_home"] == 1, df["team"])
    # Trận được xác định duy nhất bởi (mùa, đội nhà, đội khách)
    key = ["season", "home_team", "away_team"]
    # Đánh số theo thứ tự: ngày thi đấu -> vòng đấu (sắp theo chuỗi ký tự, vd "Matchweek 21" < "Matchweek 9")
    # -> tên đội đứng đầu theo bảng chữ cái trong cặp đấu
    matches = df.groupby(key, as_index=False).agg(date=("date", "min"), round=("round", "first"))
    matches["first_team"] = matches[["home_team", "away_team"]].min(axis=1)
    matches = matches.sort_values(["date", "round", "first_team"]).reset_index(drop=True)
    matches["match_id"] = matches.index + 1
    df = df.merge(matches[key + ["match_id"]], on=key, how="left")
    return df.drop(columns=["home_team", "away_team"])


def add_history_features(df: pd.DataFrame) -> pd.DataFrame:
    """matches_seen, short_history và trung bình 5 trận gần nhất (shift(1) => không dùng trận hiện tại)."""
    df = df.sort_values(["team", "date"]).reset_index()  # giữ 'index' để khôi phục thứ tự gốc

    # Một "giai đoạn" (stint) = chuỗi mùa liên tiếp của một đội trong La Liga.
    # Nếu đội xuống hạng rồi lên lại (mùa cách nhau > 1) thì lịch sử được tính lại từ đầu.
    season_gap = df.groupby("team")["season"].diff().fillna(1)
    df["stint"] = (season_gap > 1).groupby(df["team"]).cumsum()
    grp = df.groupby(["team", "stint"])

    df["matches_seen"] = grp.cumcount()
    df["short_history"] = (df["matches_seen"] < SHORT_HISTORY_MIN).astype(int)

    for src, dst in ROLLING_MAP.items():
        df[dst] = (
            grp[src]
            .transform(lambda s: s.shift(1).rolling(WINDOW, min_periods=1).mean())
            .fillna(DEFAULT_PRIOR[dst])
        )
    return df.drop(columns="stint").sort_values("index").drop(columns="index")


def add_opponent_features(df: pd.DataFrame) -> pd.DataFrame:
    """Lấy đặc trưng của đối thủ = đặc trưng của dòng còn lại có cùng match_id."""
    cols = ["xg_avg5", "xga_avg5", "matches_seen", "short_history"]
    opp = df[["match_id", "team"] + cols].rename(
        columns={"team": "opponent", **{c: f"opponent_{c}" for c in cols}}
    )
    return df.merge(opp, on=["match_id", "opponent"], how="left")


def validate(df: pd.DataFrame) -> None:
    assert df["match_id"].value_counts().eq(2).all(), "Mỗi match_id phải có đúng 2 dòng"
    assert df[FINAL_COLS].notna().all().all(), "Còn giá trị thiếu sau preprocessing"
    # Bàn thắng của đội này phải bằng bàn thua của đối thủ trong cùng trận
    g = df.groupby("match_id")
    assert (g["gf"].sum() == g["ga"].sum()).all(), "gf/ga của 2 đội trong một trận không khớp"
    assert df.groupby("match_id")["is_home"].sum().eq(1).all(), "Mỗi trận phải có đúng 1 đội nhà"


def export_xlsx(df: pd.DataFrame, path: str) -> None:
    with pd.ExcelWriter(path, engine="openpyxl", datetime_format="yyyy-mm-dd") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
        ws = writer.sheets["Sheet1"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, col in enumerate(df.columns, start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(12, len(col) + 2)


def main(src: str = INPUT_CSV, dst: str = OUTPUT_XLSX) -> pd.DataFrame:
    raw = pd.read_csv(src)
    print(f"Đọc {src}: {raw.shape[0]} dòng, {raw.shape[1]} cột")

    df = clean(raw)
    df = add_match_id(df)
    df = add_history_features(df)
    df = add_opponent_features(df)
    df = df[FINAL_COLS]

    validate(df)
    export_xlsx(df, dst)
    print(f"Đã ghi {dst}: {df.shape[0]} dòng, {df.shape[1]} cột")
    return df


if __name__ == "__main__":
    args = sys.argv[1:]
    main(*args[:2])
