"""Research-only adapter, with production rolling/stint rules and no DB writes.

Supports explicitly reviewed new club aliases without changing the production
registry. Parity with the unchanged production Feature Builder is unit-tested.
"""

import numpy as np
import pandas as pd

from scripts.inference.build_fixture_features import ROLLING_SOURCES, stint_history
from scripts.prepare_training_features import FEATURES, read_history_config
from .mapping import fixture_identity


def build_features(history, home, away, day, season, *, expected=None):
    season, day, home, away = fixture_identity(season, day, home, away)
    config = read_history_config()
    own, audit = [], {}
    key = f"research:laliga:{season}:{home}:{away}"
    for team, is_home in [(home, 1), (away, 0)]:
        prior = history.loc[history.team.eq(team) & history.season.le(season)
                            & history.date.lt(day) & history.canonical_key.ne(key)]
        records = stint_history(prior, season)
        if expected is not None:
            required = expected.loc[expected.team.eq(team) & expected.season.le(season)
                                    & expected.date.lt(day) & expected.canonical_key.ne(key)]
            required = stint_history(required, season)
            if set(required.canonical_key) != set(records.canonical_key):
                raise ValueError("Incomplete team history: " + team)
        count = len(records)
        values = records[["xg", "xga", "gf", "ga", "sh", "sot"]].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("Invalid prior statistics")
        row = dict(is_home=is_home, matches_seen=count, short_history=int(count < config.short_history_min))
        for name, source in ROLLING_SOURCES.items():
            row[name] = float(records.tail(config.window)[source].mean()) if count else np.nan
        own.append(row)
        audit[team] = dict(matches_seen=count, short_history=int(count < config.short_history_min),
                           eligible_match_keys=records.canonical_key.tolist(),
                           rolling_match_keys=records.tail(config.window).canonical_key.tolist(),
                           last_date=None if not count else records.date.iloc[-1])
    rows = []
    for i, row in enumerate(own):
        other = own[1-i]
        rows.append(dict(row, opponent_xg_avg5=other["xg_avg5"], opponent_xga_avg5=other["xga_avg5"],
                         opponent_matches_seen=other["matches_seen"], opponent_short_history=other["short_history"]))
    X = pd.DataFrame(rows, columns=list(FEATURES), dtype=float)
    if X.shape != (2, 13) or np.isinf(X.to_numpy()).any():
        raise ValueError("Feature schema mismatch")
    return X, audit
