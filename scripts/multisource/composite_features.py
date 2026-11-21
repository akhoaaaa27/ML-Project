"""Option B: registry counts, actual rolling window, unchanged frozen features."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scripts.inference.build_fixture_features import stint_history
from scripts.inference.common import parse_date
from scripts.inference.common import InferenceError
from scripts.prepare_training_features import FEATURES, OWN_HISTORY, read_history_config
from .features import build_features
from .mapping import fixture_identity
from .match_registry import COMPLETE_STATISTICS, GROUPS, canonical_key, require
from .team_registry import resolve


@dataclass
class CompositeFeatures:
    X: pd.DataFrame
    history: dict
    provenance: list
    cutoff: str
    fixture: dict


def build_composite_features(home_team, away_team, match_date, season, history, *, prediction_cutoff=None):
    try:
        season, day, home, away = fixture_identity(season, match_date, resolve(home_team), resolve(away_team))
    except (TypeError,ValueError):
        raise InferenceError("INVALID_FIXTURE","Invalid research fixture identity") from None
    cutoff = day if prediction_cutoff is None else parse_date(prediction_cutoff).isoformat()
    require(cutoff <= day, "INVALID_CUTOFF", "Prediction cutoff cannot follow fixture date")
    identity = history.fixture(home,away,day,season)
    key = canonical_key(season,home,away)
    config = read_history_config()
    selected, audit, provenance = [], {}, []
    for team in (home,away):
        coverage = history.assert_coverage(team,season,cutoff)
        registry = stint_history(history.prior_registry(team,season,cutoff,key),season)
        require(registry.empty or registry.date.lt(cutoff).all(), "INVALID_HISTORY", "Current/future match in history")
        require(registry.empty or int(registry.season.min()) == coverage["stint_start_season"],
                "REGISTRY_COVERAGE_UNVERIFIED", "Registry stint differs from verified membership")
        window = registry.tail(config.window)
        pending = window.loc[window.statistics_status.ne(COMPLETE_STATISTICS)]
        require(pending.empty, "MISSING_ROLLING_STATISTICS", "Actual rolling window contains unavailable/conflicting statistics",
                team=team, fixture_keys=pending.canonical_key.tolist())
        for row in window.itertuples():
            record = history.statistics_for(row.canonical_key,team)
            require(record is not None and all(record.get(k) for k in GROUPS),
                    "INVALID_PROVENANCE", "Rolling record lacks source provenance")
            values = [record.get(k) for k in ("gf","ga","xg","xga","sh","sot")]
            require(all(v is not None for v in values) and np.isfinite(np.asarray(values,dtype=float)).all(),
                    "MISSING_ROLLING_STATISTICS", "Rolling raw outcomes are incomplete")
            require(record["date"] < cutoff and record["canonical_key"] != key,
                    "INVALID_HISTORY", "Target/future statistics selected")
            selected.append(record)
            provenance.append(dict(canonical_fixture_key=row.canonical_key, team=team,
                                   **{k:record[k] for k in GROUPS}))
        count = len(registry)
        audit[team] = dict(matches_seen=count,short_history=int(count<config.short_history_min),
                           stint_start_season=coverage["stint_start_season"],
                           eligible_match_keys=registry.canonical_key.tolist(),
                           rolling_match_keys=window.canonical_key.tolist(),
                           pending_outside_window=registry.iloc[:-len(window) if len(window) else None].loc[
                               lambda d:d.statistics_status.ne(COMPLETE_STATISTICS),"canonical_key"].tolist(),
                           last_date=None if registry.empty else registry.date.iloc[-1], coverage=coverage)
    columns = ["team","season","date","canonical_key","gf","ga","xg","xga","sh","sot"]
    rolling_only = pd.DataFrame(selected) if selected else pd.DataFrame(columns=columns)
    # Reuse the tested Phase 8.5.2 rolling/assembly implementation. Only count
    # features are restored from the full registry rather than the window rows.
    X, _ = build_features(rolling_only,home,away,day,season)
    for i, team in enumerate((home,away)):
        opponent = (away,home)[i]
        X.loc[i,"matches_seen"] = audit[team]["matches_seen"]
        X.loc[i,"short_history"] = audit[team]["short_history"]
        X.loc[i,"opponent_matches_seen"] = audit[opponent]["matches_seen"]
        X.loc[i,"opponent_short_history"] = audit[opponent]["short_history"]
        allowed = set(OWN_HISTORY) if audit[team]["matches_seen"] == 0 else set()
        if audit[opponent]["matches_seen"] == 0:
            allowed |= {"opponent_xg_avg5","opponent_xga_avg5"}
        require(set(X.columns[X.iloc[i].isna()]) == allowed, "INVALID_NUMERIC", "Only verified zero-history may contain NaN")
    require(X.shape == (2,13) and tuple(X.columns) == FEATURES and not np.isinf(X.to_numpy()).any(),
            "FEATURE_SCHEMA_MISMATCH", "Frozen feature schema differs")
    return CompositeFeatures(X,audit,provenance,cutoff,identity)
