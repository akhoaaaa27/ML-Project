"""Expanding Window theo mùa, trả về vị trí iloc để tái sử dụng trong sklearn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np
import pandas as pd
from sklearn.model_selection import BaseCrossValidator


RESERVED_SEASONS = frozenset({2024, 2025})


@dataclass(frozen=True)
class FoldSpec:
    train_seasons: tuple[int, ...]
    validation_season: int


DEFAULT_FOLDS = (
    FoldSpec((2019, 2020), 2021),
    FoldSpec((2019, 2020, 2021), 2022),
    FoldSpec((2019, 2020, 2021, 2022), 2023),
)


@dataclass(frozen=True)
class SeasonFold:
    fold: int
    spec: FoldSpec
    train_indices: np.ndarray
    validation_indices: np.ndarray
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_specs(specs: tuple[FoldSpec, ...]) -> None:
    _require(bool(specs), "Cần ít nhất một fold.")
    previous = None
    for spec in specs:
        seasons = spec.train_seasons
        _require(bool(seasons) and tuple(sorted(set(seasons))) == seasons,
                 "Mùa Train phải tăng dần, duy nhất và không rỗng.")
        _require(max(seasons) < spec.validation_season, "Mùa Train phải trước mùa Validation.")
        _require(not (set(seasons) | {spec.validation_season}) & RESERVED_SEASONS,
                 "Không được đưa mùa Final Test 2024 hoặc 2025 vào fold.")
        if previous is not None:
            _require(set(previous.train_seasons) | {previous.validation_season} <= set(seasons)
                     and previous.validation_season < spec.validation_season,
                     "Các fold phải mở rộng Train và tăng mùa Validation.")
        previous = spec


def make_season_folds(frame: pd.DataFrame, specs: tuple[FoldSpec, ...] = DEFAULT_FOLDS
                      ) -> tuple[SeasonFold, ...]:
    """Chia theo season, giữ đủ cặp trận; chỉ sắp xếp vị trí trong bộ nhớ.

    Các indices là vị trí iloc, không phải nhãn index. Khi tái sử dụng với X/y,
    phải giữ cùng thứ tự dòng giữa frame metadata và X/y.
    """
    specs = tuple(specs)
    _validate_specs(specs)
    required = ("match_id", "season", "date", "is_home")
    _require(isinstance(frame, pd.DataFrame) and frame.columns.is_unique,
             "Đầu vào cần là DataFrame với tên cột duy nhất.")
    _require(all(c in frame for c in required), f"Thiếu metadata chia fold: {required}.")
    _require(not frame.empty and frame.index.is_unique, "Dữ liệu cần có bản ghi và index duy nhất.")
    _require(not frame.loc[:, list(required)].isna().any().any(), "Metadata có giá trị thiếu.")
    for c in ("season", "match_id"):
        _require(pd.api.types.is_numeric_dtype(frame[c]), f"{c} phải có kiểu số nguyên.")
        _require(np.isfinite(frame[c]).all() and frame[c].mod(1).eq(0).all(), f"{c} không hợp lệ.")
    _require(frame.is_home.isin([0, 1]).all(), "is_home phải là 0 hoặc 1.")
    dates = pd.to_datetime(frame.date, errors="raise")
    matches = frame.groupby("match_id")
    _require(matches.size().eq(2).all(), "Mỗi match_id phải có đúng hai bản ghi.")
    _require(matches.season.nunique().eq(1).all(), "Hai phía của một match_id thuộc các mùa khác nhau.")
    _require(dates.groupby(frame.match_id).nunique().eq(1).all(), "Hai phía của một match_id có ngày khác nhau.")
    _require(matches.is_home.sum().eq(1).all(), "Mỗi trận cần đúng một đội nhà và một đội khách.")

    def positions(mask: pd.Series) -> np.ndarray:
        indices = np.flatnonzero(mask.to_numpy())
        # Không phụ thuộc cách các đội được sắp trong CSV.
        order = np.lexsort((frame.is_home.iloc[indices].to_numpy(),
                            frame.match_id.iloc[indices].to_numpy(),
                            dates.iloc[indices].to_numpy()))
        result = indices[order]
        result.setflags(write=False)
        return result

    result = []
    for number, spec in enumerate(specs, 1):
        train_indices = positions(frame.season.isin(spec.train_seasons))
        validation_indices = positions(frame.season.eq(spec.validation_season))
        _require(len(train_indices) > 0 and len(validation_indices) > 0, f"Fold {number}: tập rỗng.")
        train, validation = frame.iloc[train_indices], frame.iloc[validation_indices]
        _require(set(train.season) == set(spec.train_seasons), f"Fold {number}: thiếu mùa Train.")
        _require(set(validation.season) == {spec.validation_season}, f"Fold {number}: sai mùa Validation.")
        _require(not np.intersect1d(train_indices, validation_indices).size, f"Fold {number}: trùng bản ghi.")
        _require(set(train.match_id).isdisjoint(validation.match_id), f"Fold {number}: trùng trận giữa hai tập.")
        _require(train.groupby("match_id").size().eq(2).all()
                 and validation.groupby("match_id").size().eq(2).all(), f"Fold {number}: cặp trận bị tách.")
        train_dates, val_dates = dates.iloc[train_indices], dates.iloc[validation_indices]
        _require(train_dates.max() < val_dates.min(), f"Fold {number}: ngày Train không trước Validation.")
        result.append(SeasonFold(number, spec, train_indices, validation_indices,
                                 train_dates.min().date().isoformat(), train_dates.max().date().isoformat(),
                                 val_dates.min().date().isoformat(), val_dates.max().date().isoformat()))
    return tuple(result)


class SeasonExpandingWindowCV(BaseCrossValidator):
    """Splitter dùng metadata; có thể truyền list(cv.split(metadata)) vào search sau này."""

    def __init__(self, specs: tuple[FoldSpec, ...] = DEFAULT_FOLDS):
        self.specs = tuple(specs)

    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        return len(self.specs)

    def split(self, X: pd.DataFrame, y=None, groups=None) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        if groups is not None:
            _require(np.array_equal(np.asarray(groups), X.match_id.to_numpy()), "groups phải khớp match_id theo thứ tự dòng.")
        for fold in make_season_folds(X, self.specs):
            yield fold.train_indices.copy(), fold.validation_indices.copy()
