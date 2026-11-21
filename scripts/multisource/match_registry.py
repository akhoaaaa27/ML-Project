"""Verified completion and statistical completeness are separate states."""

from datetime import datetime
import hashlib
import json

import pandas as pd

from scripts.inference.common import InferenceError
from .mapping import RAW_FIELDS, fixture_identity, number, validate_staging
from .team_registry import resolve

VERIFIED_COMPLETED = "VERIFIED_COMPLETED"
COMPLETE_STATISTICS = "COMPLETE_STATISTICS"
PENDING_UPDATE = "PENDING_UPDATE"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
UNVERIFIED = "UNVERIFIED"
GROUPS = ("fixture_source", "xg_source", "shots_source", "source_dataset_version", "fetched_at", "statistical_semantics")


def require(condition, code, message, **details):
    if not condition:
        raise InferenceError(code, message, **details)


def canonical_key(season, home, away):
    return f"research:laliga:{int(season)}:{resolve(home)}:{resolve(away)}"


def semantic_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        require(result.tzinfo is not None, "INVALID_PROVENANCE", "Timestamp requires timezone")
    except (TypeError, ValueError):
        raise InferenceError("INVALID_PROVENANCE", "Invalid timezone-aware timestamp") from None
    return value


class MatchRegistry:
    def __init__(self):
        self.fixtures = {}
        self.evidence = []
        self.conflicts = []
        self.statistics = {}
        self._observations = set()

    def observe(self, *, season, match_date, home_team, away_team, observed_status,
                verification_source, source_version, verified_at, home_goals=None, away_goals=None,
                evidence_verified=False, provider_fixture_id=None):
        season, day, home, away = fixture_identity(season, match_date, resolve(home_team), resolve(away_team))
        require(bool(verification_source) and bool(source_version), "INVALID_PROVENANCE", "Missing completion provenance")
        timestamp(verified_at)
        status = str(observed_status).lower()
        require(status in {"completed", "scheduled", "live", "postponed", "cancelled", "unverified"},
                "INVALID_REGISTRY", "Unknown observed status")
        completed = status == "completed" and evidence_verified is True
        h = number(home_goals, "home_goals", integer=True) if completed else None
        a = number(away_goals, "away_goals", integer=True) if completed else None
        key = canonical_key(season, home, away)
        item = dict(canonical_fixture_key=key, season=season, match_date=day, home_team=home, away_team=away,
                    observed_status=status, home_goals=h, away_goals=a, verification_source=verification_source,
                    source_version=source_version, verified_at=verified_at, evidence_verified=completed,
                    provider_fixture_id=None if provider_fixture_id is None else str(provider_fixture_id))
        observation = (key, verification_source, source_version)
        require(observation not in self._observations, "DUPLICATE_FIXTURE", "Duplicate observation in one source version")
        self._observations.add(observation)
        self.evidence.append(item)
        old = self.fixtures.get(key)
        if old is None:
            self.fixtures[key] = dict(item, match_status=VERIFIED_COMPLETED if completed else UNVERIFIED,
                                      statistics_status=PENDING_UPDATE if completed else UNVERIFIED)
        else:
            conflict = old["match_date"] != day or (completed and old["match_status"] == VERIFIED_COMPLETED
                                                       and (old["home_goals"], old["away_goals"]) != (h, a))
            if conflict:
                old["match_status"] = old["statistics_status"] = SOURCE_CONFLICT
                self.conflicts.append(dict(canonical_fixture_key=key, kind="identity_or_score", evidence=item))
            elif old["match_status"] != SOURCE_CONFLICT and completed:
                self.fixtures[key] = dict(item, match_status=VERIFIED_COMPLETED,
                                          statistics_status=old["statistics_status"] if old["match_status"] == VERIFIED_COMPLETED else PENDING_UPDATE)
        return key

    def attach_statistics(self, rows):
        """Store partial pairs as NULLs; never impute their missing statistics."""
        require(set(RAW_FIELDS + ("canonical_key",) + GROUPS).issubset(rows.columns),
                "INVALID_STATISTICS", "Missing statistics or provenance fields")
        attached = dict(self.statistics)
        for key, pair in rows.groupby("canonical_key", sort=True):
            require(key in self.fixtures, "UNREGISTERED_STATISTICS", "Statistics have no registry fixture")
            fixture = self.fixtures[key]
            require(fixture["match_status"] == VERIFIED_COMPLETED, "UNVERIFIED_COMPLETION", "Statistics require verified completion")
            require(fixture["statistics_status"] != SOURCE_CONFLICT, "SOURCE_CONFLICT", "Unresolved statistics conflict")
            require(len(pair) == 2 and set(pair.is_home) == {0, 1}, "INVALID_STATISTICS", "Exactly two perspectives required")
            h = pair.loc[pair.is_home.eq(1)].iloc[0]
            a = pair.loc[pair.is_home.eq(0)].iloc[0]
            require(h.date == fixture["match_date"] and h.team == fixture["home_team"] and h.opponent == fixture["away_team"],
                    "SOURCE_CONFLICT", "Statistics identity differs from registry")
            require(a.team == h.opponent and a.opponent == h.team and a.date == h.date and a.season == h.season,
                    "INVALID_STATISTICS", "Perspective identity mismatch")
            for column in ("gf", "ga", "xg", "xga", "sh", "sot"):
                for value in pair[column].dropna():
                    number(value, column, integer=column not in {"xg", "xga"})
            for left, right in [("gf", "ga"), ("ga", "gf"), ("xg", "xga"), ("xga", "xg")]:
                require((pd.isna(h[left]) and pd.isna(a[right])) or h[left] == a[right],
                        "INVALID_STATISTICS", "Contradictory opponent outcomes")
            require(all(pd.isna(r.sh) or pd.isna(r.sot) or r.sot <= r.sh for r in pair.itertuples()),
                    "INVALID_STATISTICS", "SOT exceeds shots")
            score_conflict = (int(h.gf), int(h.ga)) != (fixture["home_goals"], fixture["away_goals"])
            if score_conflict:
                fixture["match_status"] = fixture["statistics_status"] = SOURCE_CONFLICT
                self.conflicts.append(dict(canonical_fixture_key=key, kind="statistics_score"))
                continue
            records = [{k: None if pd.isna(v) else v for k, v in record.items()} for record in pair.to_dict("records")]
            for record in records:
                require(all(isinstance(record.get(k), str) and bool(record[k].strip()) for k in GROUPS),
                        "INVALID_PROVENANCE", "Missing field-group provenance")
            if key in attached:
                numeric = lambda pair: [{k:r[k] for k in ("team","gf","ga","xg","xga","sh","sot")} for r in sorted(pair,key=lambda r:r["team"])]
                self.evidence.append(dict(canonical_fixture_key=key,kind="statistical_candidate",candidate=records))
                if numeric(attached[key]) != numeric(records):
                    self.conflicting_statistics(key,dict(candidate=records,reason="multiple_statistical_values_require_review"))
                continue  # Preserve the selected source, never choose by arrival order.
            attached[key] = records
            complete = not pair[["gf", "ga", "xg", "xga", "sh", "sot"]].isna().any().any()
            if complete:
                validate_staging(pair)
            fixture["statistics_status"] = COMPLETE_STATISTICS if complete else PENDING_UPDATE
        self.statistics = attached
        return attached

    def conflicting_statistics(self, key, evidence):
        require(key in self.fixtures, "INVALID_FIXTURE", "Unknown conflict fixture")
        self.fixtures[key]["statistics_status"] = SOURCE_CONFLICT
        self.conflicts.append(dict(canonical_fixture_key=key, kind="statistics", evidence=evidence))


def validate_catalogue(registry, season, clubs, source, source_version, verified_at):
    """Validate an explicitly reviewed season universe, not a downloaded row count.

    The source and version establish the scope of the season roster/calendar.
    All directed team pairings, identities, dates and completion states are
    inspected. Unresolved statuses restrict coverage at their earliest date.
    """
    clubs = sorted(resolve(team) for team in clubs)
    require(len(clubs) >= 2 and len(set(clubs)) == len(clubs), "REGISTRY_COVERAGE_UNVERIFIED", "Invalid season membership")
    require(bool(source) and bool(source_version), "INVALID_PROVENANCE", "Missing calendar evidence")
    timestamp(verified_at)
    season_rows = [row for row in registry.fixtures.values() if row["season"] == season]
    pairs = {(row["home_team"], row["away_team"]) for row in season_rows}
    expected = {(home, away) for home in clubs for away in clubs if home != away}
    require(pairs == expected and len(season_rows) == len(expected), "REGISTRY_COVERAGE_UNVERIFIED", "Incomplete reviewed fixture universe")
    # Never infer completion from a past date. Unknown/conflicting records cap
    # the strict-before date cutoff; the day itself can still be a valid cutoff.
    uncertain = [r["match_date"] for r in season_rows if r["match_status"] != VERIFIED_COMPLETED]
    verified_before = min(uncertain) if uncertain else f"{season+1}-07-01"
    by_team = {team: min((r["match_date"] for r in season_rows if team in (r["home_team"], r["away_team"])
                          and r["match_status"] != VERIFIED_COMPLETED), default=f"{season+1}-07-01") for team in clubs}
    return dict(season=season, clubs=clubs, verification_source=source, source_version=source_version,
                verified_at=verified_at, verified_before=verified_before,
                verified_before_by_team=by_team,
                basis="reviewed_season_roster_and_exact_directed_fixture_universe_with_completion_evidence",
                scope="research_export_snapshot_not_production_as_of_vintage", calendar_verified=True)
