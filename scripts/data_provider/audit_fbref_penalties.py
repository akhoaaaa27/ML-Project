"""Read-only, offline aggregate audit of the original FBref-derived CSV.

No provider imports, requests, credentials, imputation or dataset writes.
Run: python -m scripts.data_provider.audit_fbref_penalties
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.inference.common import resolve_team


DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "data/matches_laliga.csv"
NUMERIC = ("sh", "sot", "pk", "pkatt", "xg", "xga")


def audit_dataset(path=DEFAULT_SOURCE):
    rows = pd.read_csv(path)
    for field in NUMERIC:
        rows[field] = pd.to_numeric(rows[field], errors="raise")
        if not np.isfinite(rows[field]).all() or rows[field].lt(0).any():
            raise ValueError(f"Missing, non-finite or negative {field}")
    for field in ("sh", "sot", "pk", "pkatt"):
        if rows[field].mod(1).ne(0).any():
            raise ValueError(f"Non-integer {field}")
        rows[field] = rows[field].astype(int)
    if rows.pk.gt(rows.pkatt).any() or rows.sot.gt(rows.sh).any():
        raise ValueError("Invalid subset counts")
    if not rows.venue.isin(["Home", "Away"]).all():
        raise ValueError("Unknown venue")
    rows["team"] = rows.team.map(resolve_team)
    rows["opponent"] = rows.opponent.map(resolve_team)
    rows["home"] = rows.team.where(rows.venue.eq("Home"), rows.opponent)
    rows["away"] = rows.opponent.where(rows.venue.eq("Home"), rows.team)
    keys = ["season", "date", "home", "away"]
    if (rows[keys].isna().any().any() or rows.home.eq(rows.away).any()
            or rows.duplicated(keys + ["venue"]).any()
            or not rows.groupby(keys).size().eq(2).all()):
        raise ValueError("Missing, duplicate or inconsistent fixture perspectives")
    rows["no_penalties"] = rows.pkatt.eq(0)
    rows["successful_penalty"] = rows.pk.gt(0)
    rows["unconverted_penalty"] = rows.pkatt.gt(rows.pk)
    rows["attempts"] = rows.pkatt
    rows["penalty_goals"] = rows.pk
    rows["unconverted_attempts"] = rows.pkatt - rows.pk
    rows["zero_sh_with_penalty"] = rows.sh.eq(0) & rows.pkatt.gt(0)
    rows["zero_sot_with_penalty"] = rows.sot.eq(0) & rows.pkatt.gt(0)
    rows["zero_sot_with_penalty_goal"] = rows.sot.eq(0) & rows.pk.gt(0)
    rows["team_rows"] = 1
    flags = ["team_rows", "no_penalties", "successful_penalty", "unconverted_penalty",
             "attempts", "penalty_goals", "unconverted_attempts", "zero_sh_with_penalty",
             "zero_sot_with_penalty", "zero_sot_with_penalty_goal"]
    fixtures = rows.groupby(keys).agg(pk=("pk", "sum"), pkatt=("pkatt", "sum"))
    fixtures["matches"] = 1
    fixtures["no_penalties"] = fixtures.pkatt.eq(0)
    fixtures["successful_penalty"] = fixtures.pk.gt(0)
    fixtures["unconverted_penalty"] = fixtures.pkatt.gt(fixtures.pk)
    match_flags = ["matches", "no_penalties", "successful_penalty", "unconverted_penalty"]
    paired = rows.loc[rows.venue.eq("Home"), keys + ["xg", "xga"]].merge(
        rows.loc[rows.venue.eq("Away"), keys + ["xg", "xga"]],
        on=keys, validate="one_to_one", suffixes=("_home", "_away"))
    return dict(
        team_rows=len(rows), matches=len(fixtures),
        team_rows_by_season=json.loads(rows.groupby("season")[flags].sum().to_json(orient="index")),
        matches_by_season=json.loads(fixtures.groupby("season")[match_flags].sum().to_json(orient="index")),
        team_row_totals={field: int(rows[field].sum()) for field in flags},
        match_totals={field: int(fixtures[field].sum()) for field in match_flags},
        exclusive_team_row_categories=dict(
            no_penalties=int(rows.no_penalties.sum()),
            all_scored=int((rows.pkatt.gt(0) & rows.pkatt.eq(rows.pk)).sum()),
            all_unconverted=int((rows.pkatt.gt(0) & rows.pk.eq(0)).sum()),
            mixed=int((rows.pk.gt(0) & rows.pkatt.gt(rows.pk)).sum())),
        numeric_summary={field: dict(missing=int(rows[field].isna().sum()),
                                    minimum=float(rows[field].min()), maximum=float(rows[field].max()))
                         for field in NUMERIC},
        paired_xg_xga_exact=bool(paired.xg_home.eq(paired.xga_away).all()
                                and paired.xga_home.eq(paired.xg_away).all()),
        zero_xg_with_penalty=int((rows.xg.eq(0) & rows.pkatt.gt(0)).sum()),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    print(json.dumps(audit_dataset(parser.parse_args().source), indent=2, allow_nan=False))
