"""Isolated generated data for forecast tests and reproducing the demo."""

from datetime import date, timedelta
from itertools import permutations

import pandas as pd

from .composite_history import RESEARCH_ROOT, publish_version
from .match_registry import MatchRegistry, require, semantic_hash, validate_catalogue
from .refresh_demo import CLUBS

FIRST = "2026-11-19T09:00:00Z"
UPDATE = "2026-11-21T09:00:00Z"
TARGET = "research:laliga:2026:Valencia:Real Madrid"


def synthetic_snapshot(root, version, *, completed=range(6), pending=(), now=FIRST, parent=None,
                       status_changes=None, kickoff_changes=None, shifted=False):
    """All pairings use generated scores, statistics and verification timestamps."""
    root = root.resolve()
    require(not root.is_relative_to(RESEARCH_ROOT.resolve())
            and not RESEARCH_ROOT.resolve().is_relative_to(root),
            "INVALID_SCOPE", "Synthetic history must be separate from real history")
    registry = MatchRegistry()
    schedule = {}
    records = []
    catalogues = {}
    for season in (2025, 2026):
        for index, (home, away) in enumerate(permutations(CLUBS, 2)):
            start = date(2026, 5, 1) if season == 2025 else date(2026, 11, 13)
            day = (start + timedelta(days=index - int(shifted) * 50)).isoformat()
            is_complete = season == 2025 or index in completed
            status = "completed" if is_complete else "scheduled"
            if season == 2026:
                status = (status_changes or {}).get(index, status)
            key = registry.observe(season=season, match_date=day, home_team=home, away_team=away,
                                   observed_status=status, evidence_verified=status == "completed",
                                   verification_source="synthetic://forecast-fixtures", source_version=version,
                                   verified_at=now, provider_fixture_id=f"{season}{index:02d}", home_goals=2, away_goals=1)
            kickoff = (kickoff_changes or {}).get(index, day + "T19:30:00Z") if season == 2026 else day + "T19:30:00Z"
            schedule[key] = dict(kickoff_utc=kickoff, source_provider="synthetic://forecast-fixtures", source_version=version)
            if status == "completed":
                xg = None if (season,index) in pending else 0.7 + index / 10
                for team, opponent, is_home in [(home,away,1), (away,home,0)]:
                    records.append(dict(canonical_key=key, season=season, date=day, team=team, opponent=opponent,
                                        is_home=is_home, gf=2 if is_home else 1, ga=1 if is_home else 2,
                                        xg=xg, xga=xg, sh=10, sot=4, fixture_source="synthetic", xg_source="synthetic",
                                        shots_source="synthetic", source_dataset_version=version, fetched_at=now,
                                        statistical_semantics="synthetic_test_data"))
        catalogues[season] = validate_catalogue(registry,season,CLUBS,"synthetic://calendar",version,now)
    stats = registry.attach_statistics(pd.DataFrame(records))
    metadata = dict(dataset_kind="synthetic",schedule=schedule,
                    candidate_content_sha256=semantic_hash(version),effect_sha256=semantic_hash(version))
    return publish_version(registry,stats,catalogues,version_id=version,input_hashes={"synthetic":semantic_hash(version)},
                           root=root,parent=parent,identity_review={"dataset_kind":"synthetic"},refresh_metadata=metadata)
