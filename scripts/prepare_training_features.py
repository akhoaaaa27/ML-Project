"""Chuẩn bị features và kiểm chứng Median Imputation; không huấn luyện mô hình.

Chạy kiểm chứng: python scripts/prepare_training_features.py
Import: from scripts.prepare_training_features import prepare_features, make_preprocessor
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
import sklearn
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

if __package__:
    from .normalize_laliga_numeric import FEATURES, REQUIRED_COLUMNS, TEXT_COLUMNS
else:
    from normalize_laliga_numeric import FEATURES, REQUIRED_COLUMNS, TEXT_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data/laliga_processed_normalized.csv"
PREPROCESS_PATH = ROOT / "data/preprocess_laliga.py"
REPORT_PATH = ROOT / "data/Prepare Leakage-Safe Median Imputation for La Liga.md"
OWN_HISTORY = ("xg_avg5", "xga_avg5", "gf_avg5", "ga_avg5", "shot_avg5", "sot_avg5")
OPPONENT_HISTORY = ("opponent_xg_avg5", "opponent_xga_avg5")
HISTORY_FEATURES = (*OWN_HISTORY, *OPPONENT_HISTORY)
PASSTHROUGH_FEATURES = tuple(c for c in FEATURES if c not in HISTORY_FEATURES)
PROTECTED_PATHS = (
    ROOT / "data/matches_laliga.csv", ROOT / "data/laliga_processed.csv",
    ROOT / "data/laliga_processed.xlsx", INPUT_PATH, PREPROCESS_PATH,
    ROOT / "scripts/normalize_laliga_numeric.py",
)


@dataclass(frozen=True)
class HistoryConfig:
    priors: dict[str, float]
    short_history_min: int
    window: int


@dataclass(frozen=True)
class RestorationAudit:
    own_zero_rows: int
    opponent_zero_rows: int
    restored_cells: int
    cells_by_feature: dict[str, int]
    valid_prior_matches: dict[str, int]
    partial_history_rows: int


def read_history_config(path: Path = PREPROCESS_PATH) -> HistoryConfig:
    """Đọc hằng số bằng AST; không import hoặc chạy pipeline Feature Engineering."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    wanted = {"DEFAULT_PRIOR", "SHORT_HISTORY_MIN", "WINDOW", "ROLLING_MAP"}
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    constants[target.id] = ast.literal_eval(node.value)
    if set(constants) != wanted:
        raise ValueError("Mã nguồn thiếu hằng số lịch sử cần kiểm chứng.")
    priors = constants["DEFAULT_PRIOR"]
    if set(priors) != set(OWN_HISTORY) or set(constants["ROLLING_MAP"].values()) != set(OWN_HISTORY):
        raise ValueError("Danh sách Fixed Prior hoặc ROLLING_MAP khác sáu features đã xác minh.")
    if not all(isinstance(v, (int, float)) and np.isfinite(v) for v in priors.values()):
        raise ValueError("Fixed Prior phải là số hữu hạn.")
    function = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == "add_history_features"), None)
    code = ast.unparse(function) if function else ""
    for fragment in (".shift(1)", ".rolling(WINDOW, min_periods=1)",
                     ".fillna(DEFAULT_PRIOR[dst])", "grp.cumcount()"):
        if fragment not in code:
            raise ValueError(f"Logic add_history_features đã đổi; cần xem xét lại: thiếu {fragment}.")
    return HistoryConfig(dict(priors), constants["SHORT_HISTORY_MIN"], constants["WINDOW"])


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _require_values_equal(actual: pd.Series, expected: np.ndarray, label: str) -> None:
    same = actual.to_numpy() == expected
    if not same.all():
        pos = int(np.flatnonzero(~same)[0])
        raise ValueError(f"{label}: vị trí dòng {pos + 1}, index={actual.index[pos]!r}, "
                         f"giá trị {actual.iloc[pos]!r}, cần {expected[pos]!r}.")


def validate_source_frame(frame: pd.DataFrame, config: HistoryConfig) -> None:
    """Kiểm tra dữ liệu nguồn chưa khôi phục NaN; cần đủ hai phía của mỗi trận."""
    _require(isinstance(frame, pd.DataFrame), "Đầu vào phải là pandas.DataFrame.")
    _require(frame.columns.is_unique and frame.index.is_unique, "Tên cột và index phải duy nhất.")
    missing = [c for c in REQUIRED_COLUMNS if c not in frame]
    _require(not missing, f"Thiếu cột bắt buộc: {missing}.")
    _require(not frame.empty, "DataFrame không có bản ghi.")
    for c in REQUIRED_COLUMNS:
        _require(not frame[c].isna().any(), f"Cột {c} có giá trị thiếu sẵn; chưa được xác minh là Fixed Prior.")
        if c not in TEXT_COLUMNS:
            _require(is_numeric_dtype(frame[c]), f"Cột {c} không có kiểu số.")
            bad = ~np.isfinite(frame[c].to_numpy(dtype=float))
            if bad.any():
                i = int(np.flatnonzero(bad)[0])
                raise ValueError(f"Cột {c}, vị trí dòng {i + 1}: giá trị không hữu hạn.")
    pd.to_datetime(frame["date"], errors="raise")
    for c in ("match_id", "season", "matches_seen", "opponent_matches_seen"):
        _require(frame[c].ge(0).all() and frame[c].mod(1).eq(0).all(), f"Cột {c} phải là số nguyên không âm.")
    for c in ("is_home", "short_history", "opponent_short_history"):
        _require(frame[c].isin([0, 1]).all(), f"Cột {c} phải thuộc {{0, 1}}.")
    for count, flag in (("matches_seen", "short_history"), ("opponent_matches_seen", "opponent_short_history")):
        _require_values_equal(frame[flag], frame[count].lt(config.short_history_min).astype(int).to_numpy(), flag)
    _require(frame.groupby("match_id").size().eq(2).all(), "Mỗi match_id phải có đủ hai bản ghi; không chia tách một trận.")
    _require(not frame.duplicated(["match_id", "team"]).any(), "Trùng khóa (match_id, team).")
    lookup = frame.set_index(["match_id", "team"], drop=False)
    keys = pd.MultiIndex.from_arrays([frame["match_id"], frame["opponent"]], names=["match_id", "team"])
    _require(keys.isin(lookup.index).all(), "Thiếu dòng tương ứng của đối thủ trong cùng match_id.")
    other = lookup.reindex(keys)
    for own, opponent in (("opponent", "team"), ("season", "season"), ("date", "date"),
                          ("gf", "ga"), ("ga", "gf"), ("xg", "xga"), ("xga", "xg"),
                          ("opponent_matches_seen", "matches_seen"),
                          ("opponent_short_history", "short_history"),
                          ("opponent_xg_avg5", "xg_avg5"), ("opponent_xga_avg5", "xga_avg5")):
        _require_values_equal(frame[own], other[opponent].to_numpy(), f"Đối chiếu đối thủ: {own}")
    _require_values_equal(frame["is_home"], 1 - other["is_home"].to_numpy(), "is_home giữa hai đội")


def load_dataset(path: Path = INPUT_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path)
    validate_source_frame(frame, read_history_config())
    return frame


def audit_history_counts(frame: pd.DataFrame) -> int:
    """Đối chiếu số trận lịch sử theo team/stint, không tính lại rolling averages."""
    ordered = frame.sort_values(["team", "date"])
    gaps = ordered.groupby("team")["season"].diff().fillna(1)
    stint = gaps.gt(1).groupby(ordered["team"]).cumsum()
    expected = ordered.groupby([ordered["team"], stint]).cumcount()
    _require_values_equal(ordered["matches_seen"], expected.to_numpy(), "matches_seen theo lịch sử đầy đủ")
    return int(expected.eq(0).sum())


def restore_fixed_priors(frame: pd.DataFrame, config: HistoryConfig | None = None
                         ) -> tuple[pd.DataFrame, RestorationAudit]:
    """Chỉ khôi phục prior đã xác minh khi số trận lịch sử bằng 0; không sửa đầu vào."""
    config = config if config is not None else read_history_config()
    validate_source_frame(frame, config)
    own_zero = frame["matches_seen"].eq(0)
    opponent_zero = frame["opponent_matches_seen"].eq(0)
    result = frame.copy(deep=True)
    counts, valid_matches = {}, {}
    for c in HISTORY_FEATURES:
        mask = opponent_zero if c in OPPONENT_HISTORY else own_zero
        base = c.removeprefix("opponent_")
        prior = config.priors[base]
        wrong = mask & frame[c].ne(prior)
        if wrong.any():
            i = int(np.flatnonzero(wrong.to_numpy())[0])
            raise ValueError(f"Fixed Prior không khớp: cột {c}, vị trí dòng {i + 1}, "
                             f"index={frame.index[i]!r}, nhận {frame[c].iloc[i]!r}, cần {prior!r}.")
        counts[c] = int(mask.sum())
        valid_matches[c] = int((~mask & frame[c].eq(prior)).sum())
        result[c] = frame[c].mask(mask, np.nan)
    audit = RestorationAudit(int(own_zero.sum()), int(opponent_zero.sum()), sum(counts.values()),
                             counts, valid_matches,
                             int((frame["short_history"].eq(1) & ~own_zero).sum()))
    _require(int(result.isna().sum().sum()) == audit.restored_cells, "Số ô NaN không khớp các ô đã xác minh.")
    return result, audit


def prepare_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, RestorationAudit]:
    restored, audit = restore_fixed_priors(frame)
    return restored.loc[:, list(FEATURES)].copy(), restored["xg"].copy(), audit


class HistoryMedianImputer(TransformerMixin, BaseEstimator):
    """Impute tám cột, giữ nguyên năm cột khác và thứ tự DataFrame.

    Mỗi fold phải tạo instance mới và chỉ fit trên X_train đã khôi phục prior.
    X_validation chỉ được transform; estimator không tự chọn ranh giới thời gian.
    """

    def _validate_X(self, X: pd.DataFrame) -> None:
        _require(isinstance(X, pd.DataFrame), "X phải là DataFrame có tên và thứ tự 13 features.")
        _require(list(X.columns) == list(FEATURES), "X phải có đúng 13 features theo thứ tự quy định; không chứa target hoặc metadata.")
        _require(not X.empty, "X không có bản ghi.")
        for c in FEATURES:
            _require(is_numeric_dtype(X[c]), f"Feature {c} phải có kiểu số.")
            _require(not np.isinf(X[c].to_numpy(dtype=float)).any(), f"Feature {c} chứa giá trị vô hạn.")
            if c in PASSTHROUGH_FEATURES:
                _require(not X[c].isna().any(), f"Feature {c} không thuộc nhóm được phép impute.")

    def fit(self, X: pd.DataFrame, y=None):
        self._validate_X(X)
        empty = [c for c in HISTORY_FEATURES if X[c].isna().all()]
        _require(not empty, f"Train thiếu toàn bộ dữ liệu ở các cột {empty}; không có median để học, không tự điền hoặc bỏ cột.")
        fitted = SimpleImputer(strategy="median").fit(X.loc[:, list(HISTORY_FEATURES)])
        _require(np.isfinite(fitted.statistics_).all(), "Median từ Train không hữu hạn.")
        self.imputer_ = fitted
        self.feature_names_in_ = np.asarray(FEATURES, dtype=object)
        self.n_features_in_ = len(FEATURES)
        self.n_samples_fit_ = len(X)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(self, "imputer_")
        self._validate_X(X)
        result = X.copy(deep=True)
        result.loc[:, list(HISTORY_FEATURES)] = self.imputer_.transform(X.loc[:, list(HISTORY_FEATURES)])
        _require(np.isfinite(result.to_numpy(dtype=float)).all(), "Features sau imputation chưa phải toàn bộ số hữu hạn.")
        return result

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        check_is_fitted(self, "feature_names_in_")
        if input_features is not None:
            _require(list(input_features) == list(FEATURES), "input_features không khớp thứ tự 13 features.")
        return self.feature_names_in_.copy()


def make_preprocessor() -> Pipeline:
    """Tạo Pipeline chưa fit; không dùng chung median giữa các fold."""
    return Pipeline([("median", HistoryMedianImputer())])


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_workflow(state: dict) -> None:
    """Chạy các kiểm chứng xử lý dữ liệu; không gọi model.fit hoặc chấm điểm."""
    checks = state["checks"]

    def record(name: str, condition: bool, detail: str):
        checks.append((name, bool(condition), detail))
        _require(bool(condition), f"{name}: {detail}")

    config = read_history_config()
    data = load_dataset()
    original = data.copy(deep=True)
    state.update(config=config, shape=data.shape,
                 seasons=data.groupby("season")["date"].agg(["size", "min", "max"]),
                 dtypes=data.dtypes.astype(str).to_dict())
    state["stints"] = audit_history_counts(data)
    record("Lịch sử và đối thủ", True, "Đã đối chiếu counters theo team/stint, flags và hai bản ghi cùng match_id; không tính lại rolling averages.")
    restored, audit = restore_fixed_priors(data, config)
    state["audit"] = asdict(audit)
    mask = pd.DataFrame(False, index=data.index, columns=data.columns)
    mask.loc[data.matches_seen.eq(0), list(OWN_HISTORY)] = True
    mask.loc[data.opponent_matches_seen.eq(0), list(OPPONENT_HISTORY)] = True
    record("Khôi phục đúng ô", restored.isna().equals(mask), f"{audit.restored_cells} ô; xác định bằng lịch sử và đối chiếu Fixed Prior.")
    record("Bảo toàn ô hợp lệ", restored.where(~mask).equals(data.where(~mask)), "Mọi ô ngoài mask giữ nguyên giá trị.")
    record("Không sửa DataFrame đầu vào", data.equals(original), "DataFrame nguồn không bị sửa tại chỗ.")
    untouched = [c for c in data if c not in HISTORY_FEATURES]
    record("Metadata, target và thứ tự", data[untouched].equals(restored[untouched]) and data.index.equals(restored.index), "Metadata, xg, năm features giữ nguyên, không đổi dòng/index.")
    record("Short history không đồng nghĩa missing", restored.loc[data.matches_seen.gt(0), list(OWN_HISTORY)].notna().all().all(), f"Giữ nguyên {audit.partial_history_rows} dòng 0 < matches_seen < {config.short_history_min}.")
    record("Không thay mọi giá trị trùng prior", sum(audit.valid_prior_matches.values()) > 0,
           f"{sum(audit.valid_prior_matches.values())} ô có lịch sử hợp lệ trùng Fixed Prior đã được giữ lại.")
    state["folds"] = []
    for number, validation_season in enumerate((2021, 2022, 2023), 1):
        train = data.loc[data.season.between(2019, validation_season - 1)].copy()
        validation = data.loc[data.season.eq(validation_season)].copy()
        record(f"Fold {number}: ranh giới thời gian", not train.empty and not validation.empty
               and train.date.max() < validation.date.min()
               and set(train.match_id).isdisjoint(set(validation.match_id)),
               f"Train {train.date.min()} → {train.date.max()}; Validation {validation.date.min()} → {validation.date.max()}; không chung trận.")
        X_train, y_train, train_audit = prepare_features(train)
        X_val, y_val, val_audit = prepare_features(validation)
        train_snapshot, val_snapshot = X_train.copy(deep=True), X_val.copy(deep=True)
        pipeline = make_preprocessor()
        pipeline.fit(X_train)
        estimator = pipeline.named_steps["median"]
        statistics = estimator.imputer_.statistics_.copy()
        expected_medians = X_train.loc[:, list(HISTORY_FEATURES)].median().to_numpy()
        record(f"Fold {number}: median chỉ từ Train", np.array_equal(statistics, expected_medians)
               and estimator.n_samples_fit_ == len(train)
               and list(estimator.imputer_.feature_names_in_) == list(HISTORY_FEATURES),
               "8 median khớp phép tính độc lập trên Train sau khôi phục; SimpleImputer chỉ nhận 8 cột.")
        processed_train, processed_val = pipeline.transform(X_train), pipeline.transform(X_val)
        state["feature_dtypes"] = processed_val.dtypes.astype(str).to_dict()
        for label, before, after in (("Train", X_train, processed_train), ("Validation", X_val, processed_val)):
            record(f"Fold {number}: toàn vẹn {label}", before.shape == after.shape and before.index.equals(after.index)
                   and list(after.columns) == list(FEATURES) and np.isfinite(after.to_numpy(dtype=float)).all()
                   and after.where(before.notna()).equals(before.where(before.notna()))
                   and before.loc[:, list(PASSTHROUGH_FEATURES)].equals(after.loc[:, list(PASSTHROUGH_FEATURES)]),
                   f"{len(after)} dòng × 13 features; hữu hạn, không missing, giữ nguyên ô hợp lệ và năm features còn lại.")
            for c, median in zip(HISTORY_FEATURES, statistics):
                record(f"Fold {number}: điền {label}/{c}", after.loc[before[c].isna(), c].eq(median).all(), "Ô thiếu được điền đúng median Train của cột.")
        changed_validation = X_val.copy(deep=True)
        changed_validation.loc[:, list(HISTORY_FEATURES)] = changed_validation.loc[:, list(HISTORY_FEATURES)] + 1_000_000
        altered = pipeline.transform(changed_validation)
        record(f"Fold {number}: Validation không cập nhật median", np.array_equal(statistics, estimator.imputer_.statistics_)
               and all(altered.loc[X_val[c].isna(), c].eq(m).all() for c, m in zip(HISTORY_FEATURES, statistics)),
               "Dịch phân phối Validation thêm 1.000.000; statistics_ và giá trị điền ô thiếu không đổi.")
        record(f"Fold {number}: input và target", X_train.equals(train_snapshot) and X_val.equals(val_snapshot)
               and y_train.equals(train.xg) and y_val.equals(validation.xg), "X nguồn và y giữ nguyên sau fit/transform.")
        fresh = clone(pipeline)
        record(f"Fold {number}: Pipeline có thể clone", not hasattr(fresh.named_steps["median"], "imputer_")
               and list(pipeline.get_feature_names_out()) == list(FEATURES), "Clone tạo bộ xử lý chưa fit, không mang median cũ.")
        state["folds"].append(dict(number=number, train_seasons=sorted(train.season.unique().tolist()),
            validation_season=validation_season, train_rows=len(train), validation_rows=len(validation),
            train_missing=train_audit.restored_cells, validation_missing=val_audit.restored_cells,
            medians=dict(zip(HISTORY_FEATURES, statistics.tolist()))))

    def expect_error(name, callback):
        try:
            callback()
        except ValueError as exc:
            record(name, True, f"Đã chặn đúng yêu cầu: {exc}")
        else:
            record(name, False, "Dữ liệu không hợp lệ bị chấp nhận.")

    bad_prior = data.copy(deep=True)
    index = data.index[data.matches_seen.eq(0)][0]
    match_id, team = data.loc[index, ["match_id", "team"]]
    bad_prior.loc[index, "xg_avg5"] += 0.125
    bad_prior.loc[bad_prior.match_id.eq(match_id) & bad_prior.opponent.eq(team), "opponent_xg_avg5"] += 0.125
    expect_error("Từ chối Fixed Prior không khớp", lambda: restore_fixed_priors(bad_prior))
    bad_opponent = data.copy(deep=True)
    bad_opponent.loc[bad_opponent.index[0], "opponent_xg_avg5"] += 1
    expect_error("Từ chối đối thủ không nhất quán", lambda: restore_fixed_priors(bad_opponent))
    expect_error("Từ chối thiếu cột nguồn", lambda: restore_fixed_priors(data.drop(columns="matches_seen")))
    bad_infinite = data.copy(deep=True)
    bad_infinite.loc[bad_infinite.index[0], "xg_avg5"] = np.inf
    expect_error("Từ chối dữ liệu vô hạn", lambda: restore_fixed_priors(bad_infinite))
    expect_error("Từ chối thứ tự features sai", lambda: make_preprocessor().fit(X_train.iloc[:, ::-1]))
    empty_feature = X_train.copy(deep=True)
    empty_feature[HISTORY_FEATURES[0]] = np.nan
    expect_error("Từ chối Train không có median", lambda: make_preprocessor().fit(empty_feature))
    missing_passthrough = X_val.copy(deep=True)
    missing_passthrough["is_home"] = np.nan
    expect_error("Không impute ngoài tám cột", lambda: pipeline.transform(missing_passthrough))

    # Kiểm chứng nhân tạo độc lập: không có metadata hoặc target trong phép fit.
    toy_train = pd.DataFrame(0.0, index=range(3), columns=list(FEATURES))
    toy_val = pd.DataFrame(0.0, index=range(3, 5), columns=list(FEATURES))
    for offset, c in enumerate(HISTORY_FEATURES):
        toy_train[c] = [offset + 1.0, offset + 9.0, np.nan]
        toy_val[c] = [np.nan, offset + 1_000_000.0]
    toy_pipeline = make_preprocessor().fit(toy_train)
    toy_stats = toy_pipeline.named_steps["median"].imputer_.statistics_.copy()
    toy_result = toy_pipeline.transform(toy_val)
    record("Median nhân tạo Train-only", np.array_equal(toy_stats, np.arange(8) + 5.0)
           and np.array_equal(toy_result.loc[3, list(HISTORY_FEATURES)].to_numpy(), toy_stats),
           "Train có median 5, 6, ..., 12; Validation cực lớn không tham gia fit và các ô thiếu nhận đúng median Train.")
    record("Không sửa dataset hoặc script được bảo vệ", all(_hash(p) == h for p, h in state["hashes"].items()),
           "SHA-256 của sáu file được bảo vệ giống trước khi thực thi.")


def build_report(state: dict, error: str | None = None) -> str:
    lines = ["# Chuẩn bị Median Imputation an toàn trước Data Leakage cho La Liga", "",
        "## 1. Mục tiêu và phạm vi", "",
        "Chuẩn bị cơ chế khôi phục Fixed Prior về NaN và Median Imputation chỉ học từ Train của từng fold. Chỉ kiểm chứng bộ xử lý; không huấn luyện, tối ưu hoặc đánh giá mô hình; không chạy Cross-Validation chính thức và không đánh giá Final Test.", "",
        "## 2. Repository và Preprocessing", "",
        "Đã đọc `data/preprocess_laliga.py`, `scripts/normalize_laliga_numeric.py` và CSV chuẩn hóa. Repository có Git trên nhánh main; không có module chuẩn bị features tương đương khi bắt đầu. Module mới tái sử dụng FEATURES, REQUIRED_COLUMNS và TEXT_COLUMNS từ script chuẩn hóa, không sửa script đó.", "",
        "`add_history_features()` nhóm theo team/stint; stint được tính lại khi có khoảng trống mùa > 1. Rolling sử dụng shift(1), window 5, min_periods=1. matches_seen là cumcount; short_history đánh dấu số trận < 5. `.fillna(DEFAULT_PRIOR[dst])` điền các hằng số khi chưa có lịch sử. Đã đối chiếu riêng counters theo team/stint và các cột đối thủ, không tính lại rolling averages.", "",
        "**Fixed Prior** được khai báo sẵn trong mã nguồn, không phải median học tự động hoặc trung vị từ tương lai. **Median Imputation** ở module mới học từ những giá trị lịch sử hợp lệ của Train sau khi khôi phục prior. Kiểm tra trùng giá trị prior chỉ dùng xác minh các ô có counter bằng 0, không dùng để chọn mọi ô thiếu.", "",
        "## 3. Dữ liệu và những ô được khôi phục", ""]
    if "audit" in state:
        audit, config = state["audit"], state["config"]
        lines += [f"- Dữ liệu: {state['shape'][0]} dòng × {state['shape'][1]} cột; không có missing ban đầu.",
                  f"- matches_seen == 0: {audit['own_zero_rows']} dòng; opponent_matches_seen == 0: {audit['opponent_zero_rows']} dòng.",
                  f"- Khôi phục tổng cộng **{audit['restored_cells']} ô**; số stint kiểm chứng được: {state['stints']}.",
                  f"- Giữ nguyên {audit['partial_history_rows']} dòng có 0 < matches_seen < {config.short_history_min}.", "",
                  "| Feature | Fixed Prior từ mã nguồn | Ô khôi phục | Ô có lịch sử hợp lệ trùng prior được giữ nguyên |",
                  "|---|---:|---:|---:|"]
        for c in HISTORY_FEATURES:
            lines.append(f"| `{c}` | {config.priors[c.removeprefix('opponent_')]} | {audit['cells_by_feature'][c]} | {audit['valid_prior_matches'][c]} |")
        lines += ["", "### Mã mùa thực tế trong dữ liệu", "", "| season | Số dòng | Ngày đầu | Ngày cuối |", "|---|---:|---|---|"]
        for season, row in state["seasons"].iterrows():
            lines.append(f"| {season} | {row['size']} | {row['min']} | {row['max']} |")
    if "feature_dtypes" in state:
        lines += ["", "### Danh sách và thứ tự 13 input features", "",
                  "| Thứ tự | Feature | Kiểu sau transform | Cách xử lý |", "|---|---|---|---|"]
        for position, c in enumerate(FEATURES, 1):
            role = "Median chỉ học từ Train" if c in HISTORY_FEATURES else "Giữ nguyên"
            lines.append(f"| {position} | `{c}` | `{state['feature_dtypes'][c]}` | {role} |")
        lines += ["", "Target `xg` có kiểu float64 trong dữ liệu hiện tại, được giữ riêng trong y và không tham gia imputer."]
    lines += ["", "## 4. Thiết kế module và cách tái sử dụng", "",
        "- `read_history_config()` đọc hằng số bằng AST và kiểm tra những thành phần chính của logic lịch sử; không chạy Feature Engineering.",
        "- `load_dataset()` và `validate_source_frame()` kiểm tra tên cột, kiểu số, số hữu hạn, flags và hai phía của trận đấu. Nguồn cần còn nguyên Fixed Prior và đủ hai bản ghi mỗi trận; dữ liệu có missing sẵn chưa xác minh sẽ bị từ chối.",
        "- `restore_fixed_priors()` trả về bản sao đầy đủ và RestorationAudit; không sửa metadata, target, counters, flags hoặc dữ liệu đầu vào.",
        "- `prepare_features()` trả về X đúng 13 cột, y=xg và audit. Thứ tự 13 features được lấy từ mã chuẩn hóa hiện có.",
        "- `HistoryMedianImputer` dùng SimpleImputer(strategy=\"median\") trên đúng tám cột lịch sử; năm cột còn lại đi qua nguyên vẹn. Kết quả là DataFrame giữ index, thứ tự dòng và thứ tự features. Không có StandardScaler.",
        "- `make_preprocessor()` trả về sklearn.pipeline.Pipeline chưa fit. Có thể clone và ghép vào pipeline huấn luyện sau này. Nếu một cột lịch sử của Train toàn NaN, module báo lỗi, không dùng zero hoặc làm mất cột.",
        "- Khôi phục prior là phép biến đổi xác định theo dữ liệu của trận; không học thống kê. Lịch sử tích lũy hợp lệ từ các trận Validation đã diễn ra trước trận đang xét vẫn được giữ nguyên, phù hợp dự báo tuần tự trước từng trận; không phải dự báo đồng thời cả mùa từ ngày đầu mùa.", "",
        "```python", "from scripts.prepare_training_features import load_dataset, prepare_features, make_preprocessor", "",
        "df = load_dataset()",
        "train = df.loc[df['season'].isin([2019, 2020])]",
        "validation = df.loc[df['season'].eq(2021)]",
        "X_train, y_train, train_audit = prepare_features(train)",
        "X_validation, y_validation, validation_audit = prepare_features(validation)",
        "preprocessor = make_preprocessor()  # Tạo mới cho từng fold",
        "preprocessor.fit(X_train)  # Chỉ Train",
        "X_train_ready = preprocessor.transform(X_train)",
        "X_validation_ready = preprocessor.transform(X_validation)", "```", "",
        "Không fit imputer trên toàn bộ dataset, Validation hoặc Final Test; không lưu một bộ median chung. API không tự xác định dữ liệu nào là Train: người gọi phải giữ quy tắc fit/transform nêu trên.", "",
        "### Thư viện và thực thi", "",
        f"Python `{platform.python_version()}`; Pandas `{pd.__version__}`; NumPy `{np.__version__}`; scikit-learn `{sklearn.__version__}`. Các thư viện ast, dataclasses, hashlib, pathlib, platform và sys thuộc Python chuẩn; không cài thêm dependency.", "",
        "Lệnh đã thực thi:", "", "```powershell", "python scripts/prepare_training_features.py", "```", "",
        "Chạy lại lệnh sẽ kiểm chứng và cập nhật chính báo cáo này; không xuất CSV hoặc lưu imputer đã fit.", "",
        "## 5. Kết quả ba fold kiểm chứng", "",
        "season biểu thị năm bắt đầu mùa: 2019 tương ứng 2019–2020. Mỗi fold dùng Train mở rộng và Validation mùa kế tiếp. Chỉ các mùa 2019–2023 tham gia kiểm chứng fit/transform; các mùa 2024–2025 và 2025–2026 chỉ được đọc trong kiểm tra toàn vẹn nguồn, không được dùng để fit hoặc đánh giá.", "",
        "| Fold | season Train | season Validation | Dòng Train | Dòng Validation | Ô NaN khôi phục Train | Ô NaN khôi phục Validation |",
        "|---|---|---|---:|---:|---:|---:|"]
    for fold in state.get("folds", []):
        lines.append(f"| {fold['number']} | {', '.join(map(str, fold['train_seasons']))} | {fold['validation_season']} | {fold['train_rows']} | {fold['validation_rows']} | {fold['train_missing']} | {fold['validation_missing']} |")
    lines += ["", "### Median thực tế học từ Train sau khi khôi phục prior", "",
              "| Feature | Fold 1 | Fold 2 | Fold 3 |", "|---|---:|---:|---:|"]
    for c in HISTORY_FEATURES:
        values = [str(f['medians'][c]) for f in state.get("folds", [])]
        lines.append(f"| `{c}` | " + " | ".join(values + ["chưa xác nhận"] * (3 - len(values))) + " |")
    lines += ["", "## 6. Các kiểm chứng đã thực thi", "", "| Kiểm chứng | Kết quả | Bằng chứng |", "|---|---|---|"]
    for name, passed, detail in state["checks"]:
        lines.append(f"| {name} | {'Đạt' if passed else 'Không đạt'} | {detail.replace('|', '/')} |")
    lines += ["", "### Bằng chứng Train-only", "",
        "Mỗi fold tạo Pipeline mới, chỉ gọi fit(X_train). Tám statistics_ được đối chiếu phép tính median độc lập trên chính Train sau khôi phục; số dòng fit bằng số dòng Train. Sau transform Validation và sau khi dịch phân phối Validation thêm 1.000.000, statistics_ không thay đổi. Kiểm chứng nhân tạo có median Train biết trước 5–12 và Validation rất lớn xác nhận các ô thiếu vẫn nhận đúng median Train. Không đưa y hoặc metadata vào SimpleImputer.", "",
        "## 7. Bảo toàn file và thay đổi repository", "",
        "- Tạo `scripts/prepare_training_features.py`.",
        f"- Tạo/cập nhật duy nhất báo cáo `{REPORT_PATH.name}`; giữ nguyên báo cáo chuẩn hóa trước đó.",
        "- Không tạo dataset đã impute toàn cục, không lưu model hoặc medians dùng chung.",
        "- Không commit, push hoặc tái cấu trúc repository. File Excel tạm `data/~$laliga_processed.xlsx` có sẵn ở trạng thái untracked khi bắt đầu; không chỉnh sửa hoặc xóa file này.", "",
        "| File được bảo vệ | SHA-256 trước thực thi | Đối chiếu sau thực thi |", "|---|---|---|"]
    for path, digest in state["hashes"].items():
        unchanged = path.exists() and _hash(path) == digest
        lines.append(f"| `{path.relative_to(ROOT).as_posix()}` | `{digest}` | {'Giống hoàn toàn' if unchanged else 'Không khớp hoặc thiếu file'} |")
    lines += ["", "## 8. Cảnh báo, vấn đề và giới hạn", ""]
    if error:
        lines += ["**Chưa hoàn tất.**", "", "```text", error, "```", "",
                  "Chỉ các kiểm chứng ghi Đạt đã thực thi thành công; các kết quả còn thiếu chưa được xác nhận. Không tự bỏ qua hoặc sửa dữ liệu bất nhất."]
    else:
        lines += ["Không phát hiện bất nhất giữa Fixed Prior và các ô không có lịch sử; các tình huống lỗi nhân tạo trong bảng là kiểm chứng có chủ đích và đã bị chặn. Không có lỗi chưa giải quyết trong phạm vi nhiệm vụ.", "",
                  "Giới hạn: AST chỉ kiểm tra các thành phần chính của logic lịch sử; khi thay đổi công thức Feature Engineering cần xem xét lại module. Việc đối chiếu counters giả định đầu vào audit là toàn bộ lịch sử hiện có, bắt đầu từ mùa 2019. Module khôi phục yêu cầu mỗi trận còn đủ hai phía và nguồn chưa được khôi phục NaN trước đó.", "",
                  "Tính an toàn được xác nhận cho bước học median trong ba fold đã kiểm chứng; không thay thế một cuộc kiểm toán Data Leakage toàn bộ hệ thống hoặc đánh giá chất lượng mô hình."]
    lines += ["", "## 9. Tài liệu đối chiếu", "",
        "SimpleImputer học giá trị thay thế theo từng cột; module cấu hình strategy=median. Tham khảo [tài liệu SimpleImputer của scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.impute.SimpleImputer.html).", "",
        "Nguyên tắc fit trên Train và chỉ transform dữ liệu kiểm chứng tuân theo [hướng dẫn tránh Data Leakage của scikit-learn](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).", "",
        "## 10. Kết luận", "",
        ("Tác vụ chưa hoàn tất; cần xử lý lỗi nêu trên trước khi tái sử dụng." if error else
         f"Đã hoàn tất chuẩn bị và kiểm chứng với {len(state['checks'])} kiểm tra đạt. Khôi phục đúng {state['audit']['restored_cells']} ô prior trong bộ nhớ, giữ nguyên các ô lịch sử hợp lệ và học median riêng từ Train của ba fold. Sau transform, mỗi tập giữ nguyên số bản ghi, đúng 13 features số hữu hạn và target không đổi."), "",
        "Dừng tại chuẩn bị và kiểm chứng Median Imputation. Chưa huấn luyện mô hình, chưa chạy Cross-Validation chính thức, chưa đánh giá Final Test; các bước tiếp theo cần yêu cầu rõ ràng của người dùng."]
    return "\n".join(lines) + "\n"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    state = {"hashes": {p: _hash(p) for p in PROTECTED_PATHS}, "checks": []}
    try:
        verify_workflow(state)
    except Exception as exc:
        REPORT_PATH.write_text(build_report(state, f"{type(exc).__name__}: {exc}"), encoding="utf-8")
        print(f"Chưa hoàn tất: {exc}", file=sys.stderr)
        return 1
    REPORT_PATH.write_text(build_report(state), encoding="utf-8")
    print(f"Hoàn tất: {len(state['checks'])} kiểm tra đạt; khôi phục {state['audit']['restored_cells']} ô trong bộ nhớ.")
    for fold in state["folds"]:
        print(f"Fold {fold['number']}: Train {fold['train_rows']} dòng, Validation {fold['validation_rows']} dòng; median Train: {fold['medians']}")
    print(f"Báo cáo: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
