"""Explicit, offline mappings for research; field names never establish semantics."""

from datetime import date
import math
import re
import unicodedata

import pandas as pd

from scripts.inference.common import CANONICAL_TEAMS

DIRECT_MAPPING = "DIRECT_MAPPING"
DERIVED_MAPPING = "DERIVED_MAPPING"
SEMANTIC_DIFFERENCE = "SEMANTIC_DIFFERENCE"
MISSING_OR_UNVERIFIED = "MISSING_OR_UNVERIFIED"
RAW_FIELDS = ("season", "date", "team", "opponent", "is_home", "gf", "ga", "xg", "xga", "sh", "sot")
OUTCOMES = {"Goal", "SavedShot", "MissedShots", "BlockedShot", "ShotOnPost", "OwnGoal"}


def folded(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing team identity")
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value)
                            if not unicodedata.combining(c)).casefold().split())


TEAMS = (*CANONICAL_TEAMS, "Malaga", "Racing Santander", "Deportivo La Coruna")
ALIASES = {folded(team): team for team in TEAMS}
ALIASES.update({"fc barcelona": "Barcelona", "atletico de madrid": "Atletico Madrid",
                "deportivo alaves": "Alaves", "celta de vigo": "Celta Vigo", "betis": "Real Betis",
                "real oviedo": "Oviedo", "deportivo a coruna": "Deportivo La Coruna",
                "real valladolid": "Valladolid", "sd huesca": "Huesca"})


def team_name(value):
    key = folded(value)
    if key not in ALIASES:
        raise ValueError("Unknown team alias; explicit review required")
    return ALIASES[key]


def fixture_identity(season, day, home, away):
    if isinstance(season, bool) or int(season) != season:
        raise ValueError("Invalid season")
    season = int(season)
    parsed = date.fromisoformat(str(day))
    home, away = team_name(home), team_name(away)
    if parsed.year not in (season, season + 1) or home == away:
        raise ValueError("Invalid fixture date, season or teams")
    return season, parsed.isoformat(), home, away


def number(value, field, *, integer=False):
    if isinstance(value, bool):
        raise ValueError("Invalid numeric " + field)
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("Missing numeric " + field) from None
    if not math.isfinite(result) or result < 0 or (integer and result % 1):
        raise ValueError("Invalid numeric " + field)
    return int(result) if integer else result


def mapped_fixture(record, fields, *, season, provenance):
    """A reviewed field map, including Home/Away roles, is supplied explicitly.

    This function does not infer definitions from column names. Provenance must
    describe the selected field groups and unresolved statistical differences.
    """
    required = {"date", "home", "away", "home_gf", "away_gf", "home_xg", "away_xg",
                "home_sh", "away_sh", "home_sot", "away_sot"}
    if not required.issubset(fields) or not set(fields.values()).issubset(record):
        raise ValueError("Missing mapped fields")
    if not all(provenance.get(k) for k in ("fixture_source", "xg_source", "shots_source",
                                           "source_dataset_version", "fetched_at", "statistical_semantics")):
        raise ValueError("Missing provenance")
    v = {k: record[source] for k, source in fields.items()}
    season, day, home, away = fixture_identity(season, v["date"], v["home"], v["away"])
    key = f"research:laliga:{season}:{home}:{away}"
    for side in ("home", "away"):
        for field in ("gf", "xg", "sh", "sot"):
            v[side + "_" + field] = number(v[side + "_" + field], field, integer=field != "xg")
        if v[side + "_sot"] > v[side + "_sh"]:
            raise ValueError("SOT exceeds shots")
    return [dict(season=season, date=day, team=team, opponent=opponent, is_home=is_home,
                 gf=v[side+"_gf"], ga=v[other+"_gf"], xg=v[side+"_xg"], xga=v[other+"_xg"],
                 sh=v[side+"_sh"], sot=v[side+"_sot"], canonical_key=key, **provenance)
            for team, opponent, side, other, is_home in
            [(home, away, "home", "away", 1), (away, home, "away", "home", 0)]]


def validate_staging(frame):
    if frame.empty or not set(RAW_FIELDS + ("canonical_key",)).issubset(frame):
        raise ValueError("Missing staging fields")
    for key, pair in frame.groupby("canonical_key"):
        if len(pair) != 2 or set(pair.is_home) != {0, 1}:
            raise ValueError("Duplicate or incomplete fixture")
        h, a = pair.loc[pair.is_home.eq(1)].iloc[0], pair.loc[pair.is_home.eq(0)].iloc[0]
        fixture_identity(h.season, h.date, h.team, a.team)
        if (h.date != a.date or h.season != a.season or h.opponent != a.team or a.opponent != h.team
                or h.gf != a.ga or h.ga != a.gf or h.xg != a.xga or h.xga != a.xg):
            raise ValueError("Conflicting fixture perspectives")
    if frame.duplicated(["season", "team", "opponent", "is_home"]).any():
        raise ValueError("Conflicting identity/date across sources")
    for field in ("gf", "ga", "xg", "xga", "sh", "sot"):
        for value in frame[field]:
            number(value, field, integer=field not in {"xg", "xga"})
    if frame.sot.gt(frame.sh).any():
        raise ValueError("SOT exceeds shots")
    return frame


def understat_shots(shots):
    """Count exported non-penalty, non-own-goal shots; no missing-side zero fill.

    Goal/SavedShot are the reviewed research on-target classes. OwnGoal is not
    a shot by the credited attacking side. This is not proof of identical Opta
    classification. Unrecognized outcomes or duplicate shots block conversion.
    """
    needed = {"fixture_id", "shot_id", "side", "result", "situation"}
    if not needed.issubset(shots) or shots[list(needed)].isna().any().any():
        raise ValueError("Missing shot metadata")
    if shots.shot_id.duplicated().any() or not shots.side.isin(["h", "a"]).all():
        raise ValueError("Duplicate shot or invalid side")
    if not set(shots.result).issubset(OUTCOMES):
        raise ValueError("Unknown shot outcome")
    rows = []
    for fixture, group in shots.groupby("fixture_id"):
        if set(group.side) != {"h", "a"}:
            raise ValueError("Missing shot perspective; cannot assume zero")
        row = {"fixture_id": fixture}
        for side, name in [("h", "home"), ("a", "away")]:
            events = group.loc[group.side.eq(side) & group.situation.ne("Penalty") & group.result.ne("OwnGoal")]
            row[name + "_sh"] = len(events)
            row[name + "_sot"] = int(events.result.isin(["Goal", "SavedShot"]).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def checked_supplement(primary, supplement):
    """Join by season/date/canonical teams, never unrelated provider IDs.

    Scores must agree. A same-season/team pairing on a different date is an
    unresolved conflict. Conflicting nonmissing statistics are not selected.
    """
    keys = ["season", "date", "home", "away"]
    for frame in (primary, supplement):
        if frame.duplicated(keys).any():
            raise ValueError("Duplicate supplement identity")
    pairing = ["season", "home", "away"]
    dates = primary[keys].merge(supplement[keys], on=pairing, suffixes=("_p", "_s"))
    if dates.date_p.ne(dates.date_s).any():
        raise ValueError("Date discrepancy requires timestamp evidence")
    joined = primary.merge(supplement, on=keys, how="left", suffixes=("", "_supplement"), validate="one_to_one")
    statistics = {"home_gf", "away_gf", "home_xg", "away_xg", "home_sh", "away_sh", "home_sot", "away_sot"}
    for field in set(primary).intersection(supplement).intersection(statistics):
        right = field + "_supplement"
        conflict = joined[field].notna() & joined[right].notna() & joined[field].ne(joined[right])
        if conflict.any():
            raise ValueError("Unresolved source conflict: " + field)
    return joined


def reconcile_completion(current, evidence, *, season):
    """Independent completion evidence cannot invent missing box-score fields.

    Evidence is a reviewed local list of final results, not an automated
    declaration that an old scheduled date means the match finished.
    """
    result = current.copy()
    result["independently_completed"] = False
    seen = set()
    for item in evidence:
        identity = fixture_identity(item["season"], item["date"], item["home"], item["away"])
        if identity in seen or identity[0] != season:
            raise ValueError("Duplicate or wrong-season completion evidence")
        seen.add(identity)
        mask = (result.date.eq(identity[1]) & result.home.map(team_name).eq(identity[2])
                & result.away.map(team_name).eq(identity[3]))
        if mask.sum() != 1:
            raise ValueError("Unmatched completion identity; date evidence required")
        idx = result.index[mask][0]
        h, a = number(item["home_gf"], "home_gf", integer=True), number(item["away_gf"], "away_gf", integer=True)
        if result.loc[idx, "status"] == "full_time":
            if result.loc[idx,"home_goals"] != h or result.loc[idx,"away_goals"] != a:
                raise ValueError("Conflicting completed score")
        else:
            result.loc[idx,"independently_completed"] = True
            # Deliberately leave xG and shots missing. Scores are evidence only.
    return result
