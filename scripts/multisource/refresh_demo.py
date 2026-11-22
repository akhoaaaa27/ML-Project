"""Reproducible A/B/C demonstrations using generated fixtures only, offline."""

import argparse
from datetime import date, timedelta
from itertools import permutations
import json
from pathlib import Path

import pandas as pd

from scripts.inference.common import sha256
from .acquire import LOCAL
from .composite_history import RESEARCH_ROOT, publish_version
from .match_registry import MatchRegistry, canonical_key, require, validate_catalogue
from .refresh_composite import prepare, publish, review
from .refresh_validation import read_json

STAMP = "2026-11-22T00:00:00+00:00"
CLUBS = ["Barcelona","Real Madrid","Sevilla","Valencia"]


def save_source(directory, records, *, evidence=True):
    directory = Path(directory)
    (directory/"raw").mkdir(parents=True,exist_ok=True)
    path = directory/"raw/synthetic_snapshot.json"
    path.write_text(json.dumps(records,sort_keys=True,allow_nan=False),encoding="utf-8")
    (directory/"acquisition_manifest.json").write_text(json.dumps([dict(file=path.name,status=200,bytes=path.stat().st_size,
        sha256=sha256(path),url="synthetic://fixtures/current",retrieved_at=STAMP)]),encoding="utf-8")
    completed = [dict(season=2026,date=r["date"],home=r["home"],away=r["away"],home_gf=r["home_goals"],away_gf=r["away_goals"])
                 for r in records if r["status"] == "full_time"] if evidence else []
    (directory/"independent_completed.json").write_text(json.dumps(dict(source_url="synthetic://independent/results",
        reviewed_at=STAMP,matches=completed)),encoding="utf-8")


def synthetic_parent(root, *, clubs=CLUBS, prior=True, current_completed=3, missing=None, unreliable=False):
    """Small roster by default; twenty clubs can exercise the full 380 universe."""
    registry = MatchRegistry(); statistics = []; records = []; catalogues = {}
    for season in ([2025,2026] if prior else [2026]):
        for i,(home,away) in enumerate(permutations(clubs,2)):
            completed = season == 2025 or i < current_completed
            day = (date(season,7,1)+timedelta(days=i)).isoformat()
            key = registry.observe(season=season,match_date=day,home_team=home,away_team=away,
                                   observed_status="completed" if completed else "scheduled",evidence_verified=completed,
                                   verification_source="synthetic://results",source_version="synthetic-seed-v1",verified_at=STAMP,
                                   provider_fixture_id=str(1000+i),home_goals=2 if completed else None,away_goals=1 if completed else None)
            if completed:
                for team,opponent,is_home in [(home,away,1),(away,home,0)]:
                    statistics.append(dict(canonical_key=key,season=season,date=day,team=team,opponent=opponent,is_home=is_home,
                        gf=2 if is_home else 1,ga=1 if is_home else 2,xg=None if missing==(season,i) else float(i+1),
                        xga=None if missing==(season,i) else float(i+1),sh=10,sot=4,fixture_source="synthetic",
                        xg_source="synthetic_unreliable" if missing==(season,i) and unreliable else "synthetic",
                        shots_source="synthetic",source_dataset_version="synthetic-seed-v1",fetched_at=STAMP,
                        statistical_semantics="synthetic_test_data"))
            if season == 2026:
                records.append(dict(fixture_id=1000+i,date=day,kickoff_utc=None,home=home,away=away,source="synthetic",
                    status="full_time" if completed else "unplayed",home_goals=2 if completed else None,away_goals=1 if completed else None,
                    home_xg=(None if missing==(season,i) else float(i+1)) if completed else None,
                    away_xg=(None if missing==(season,i) else float(i+1)) if completed else None,
                    home_shots=10 if completed else None,away_shots=10 if completed else None,
                    home_shots_on_target=4 if completed else None,away_shots_on_target=4 if completed else None))
        catalogues[season] = validate_catalogue(registry,season,clubs,"synthetic://calendar","a"*64,STAMP)
    stats = {} if not statistics else registry.attach_statistics(pd.DataFrame(statistics))
    store = publish_version(registry,stats,catalogues,version_id="synthetic_parent",input_hashes={"synthetic":"a"*64},
                            identity_review={"dataset_kind":"synthetic"},root=Path(root))
    return store, records


def complete(record, *, value=4.0):
    record.update(status="full_time",home_goals=2,away_goals=1,home_xg=value,away_xg=value,
                  home_shots=10,away_shots=10,home_shots_on_target=4,away_shots_on_target=4)


def run_demos(directory):
    directory = Path(directory).resolve()
    require(not directory.is_relative_to(RESEARCH_ROOT.resolve()),"INVALID_SCOPE","Demos must be outside real history namespace")
    directory.mkdir(parents=True,exist_ok=False)
    parent, records = synthetic_parent(directory/"versions")
    parent_hash = sha256(parent.path)
    source = directory/"source_a"; complete(records[3]); save_source(source,records)
    a = prepare(parent,candidate_id="demo_a",candidate_version="demo_a",source_directory=source,workspace=directory/"candidates",
                as_of="2026-11-22",dataset_kind="synthetic")
    a = publish(directory/"candidates/demo_a",root=directory/"versions")
    from .composite_history import CompositeHistory
    successor = CompositeHistory(directory/"versions/demo_a/laliga_composite.sqlite3",research_root=directory/"versions")
    source_b = directory/"source_b"; records[0]["home_xg"] += 0.5; save_source(source_b,records)
    b = prepare(successor,candidate_id="demo_b",candidate_version="demo_b",source_directory=source_b,workspace=directory/"candidates",
                as_of="2026-11-22",dataset_kind="synthetic")
    bundle = read_json(directory/"candidates/demo_b/candidate.json")
    for change in bundle["changes"]:
        if change["decision"] == "MANUAL_REVIEW":
            review(directory/"candidates/demo_b",change["change_id"],"APPROVE","Synthetic demonstration only",
                   "synthetic://correction-evidence",reviewed_at=STAMP)
    b = dict(before_review=b,after_review=publish(directory/"candidates/demo_b",root=directory/"versions"))
    source_c = directory/"source_c"; save_source(source_c,records)
    with (source_c/"raw/synthetic_snapshot.json").open("a",encoding="utf-8") as stream:
        stream.write(" ")
    c = prepare(parent,candidate_id="demo_c",candidate_version="demo_c",source_directory=source_c,workspace=directory/"candidates",
                as_of="2026-11-22",dataset_kind="synthetic")
    result = dict(dataset_kind="synthetic",A=a,B=b,C=c,parent_preserved=sha256(parent.path)==parent_hash,
                  production_approved=False)
    (directory/"demo-results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True)
    print(json.dumps(run_demos(parser.parse_args().directory),indent=2))
