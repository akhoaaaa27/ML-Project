"""Build/evaluate a version from the existing Phase 8.5.2 snapshot, offline."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.inference.common import ROOT, sha256
from scripts.prepare_training_features import FEATURES
from .acquire import LOCAL
from .composite_history import CompositeHistory, RESEARCH_ROOT, publish_version
from .composite_inference import CompositePredictor
from .mapping import understat_shots, validate_staging
from .match_registry import (COMPLETE_STATISTICS, GROUPS, MatchRegistry, VERIFIED_COMPLETED,
                             canonical_key, require, validate_catalogue)
from .team_registry import identity_manifest, resolve


def load_snapshot(directory=LOCAL):
    directory = Path(directory)
    names = ["acquisition_manifest.json","independent_completed.json","audit_results.json",
             "processed/laliga_multisource_staging.csv","processed/feature_inputs.csv",
             "processed/frozen_lr_predictions.csv","processed/feature_exclusions.csv"]
    names += [f"raw/archive_{year}_fixtures.csv" for year in range(2019,2026)]
    names += ["raw/archive_2025_shots.csv","raw/current_2026_fixtures.csv"]
    missing = [name for name in names if not (directory/name).is_file()]
    require(not missing,"MISSING_INPUT_FILES","Required Phase 8.5.2 local files missing",files=missing)
    manifest = json.loads((directory/"acquisition_manifest.json").read_text(encoding="utf-8"))
    entries = {item["file"]:item for item in manifest if item["status"] == 200}
    for name in names:
        if name.startswith("raw/"):
            require(Path(name).name in entries and sha256(directory/name) == entries[Path(name).name]["sha256"],
                    "SOURCE_VERSION_MISMATCH","Cached source differs from its acquisition version")
    staging = validate_staging(pd.read_csv(directory/"processed/laliga_multisource_staging.csv"))
    old_results = json.loads((directory/"audit_results.json").read_text(encoding="utf-8"))
    require(len(staging)//2 == old_results["total_integrated_fixtures"] == 2779,
            "BASELINE_DIFFERENCE","Phase 8.5.2 fixture count changed; investigate before publishing")
    hashes = {name:sha256(directory/name) for name in names}
    hashes["data/laliga_processed_normalized.csv"] = sha256(ROOT/"data/laliga_processed_normalized.csv")
    registry = MatchRegistry()
    reviewed_at = datetime.now(timezone.utc).isoformat()
    archives = {}
    for year in range(2019,2026):
        frame = pd.read_csv(directory/f"raw/archive_{year}_fixtures.csv")
        archives[year] = frame
        entry = entries[f"archive_{year}_fixtures.csv"]
        require(frame.season.eq(year).all() and frame.competition.eq("la-liga").all(),"INVALID_REGISTRY","Archive scope changed")
        for r in frame.to_dict("records"):
            h,a = map(int,r["score"].split("-"))
            registry.observe(season=year,match_date=r["date"],home_team=r["home"],away_team=r["away"],
                             observed_status="completed",home_goals=h,away_goals=a,evidence_verified=True,
                             verification_source=entry["url"],source_version=entry["sha256"],verified_at=reviewed_at,
                             provider_fixture_id=r["understat_id"])
    frozen = staging.loc[staging.fixture_source.eq("FBref_frozen_snapshot") & staging.is_home.eq(1)]
    for r in frozen.to_dict("records"):
        registry.observe(season=r["season"],match_date=r["date"],home_team=r["team"],away_team=r["opponent"],
                         observed_status="completed",home_goals=r["gf"],away_goals=r["ga"],evidence_verified=True,
                         verification_source="local_frozen_FBref_snapshot",source_version=r["source_dataset_version"],verified_at=reviewed_at)
    current = pd.read_csv(directory/"raw/current_2026_fixtures.csv")
    entry = entries["current_2026_fixtures.csv"]
    for r in current.to_dict("records"):
        completed = r["status"] == "full_time"
        status = {"full_time":"completed","unplayed":"scheduled","live":"live",
                  "postponed":"postponed","cancelled":"cancelled"}.get(r["status"],"unverified")
        registry.observe(season=2026,match_date=r["date"],home_team=r["home"],away_team=r["away"],
                         observed_status=status,home_goals=r["home_goals"] if completed else None,
                         away_goals=r["away_goals"] if completed else None,evidence_verified=completed,
                         verification_source=entry["url"],source_version=entry["sha256"],verified_at=reviewed_at,
                         provider_fixture_id=r["fixture_id"])
    official_path = directory/"independent_completed.json"
    official = json.loads(official_path.read_text(encoding="utf-8"))
    for r in official["matches"]:
        key = canonical_key(r["season"],r["home"],r["away"])
        require(key in registry.fixtures and registry.fixtures[key]["match_date"] == r["date"],
                "INVALID_FIXTURE","Independent completion does not match source fixture identity")
        registry.observe(season=r["season"],match_date=r["date"],home_team=r["home"],away_team=r["away"],
                         observed_status="completed",home_goals=r["home_gf"],away_goals=r["away_gf"],evidence_verified=True,
                         verification_source=official["source_url"],source_version=sha256(official_path),verified_at=official["reviewed_at"])
    # The 2026 roster is independently reviewed against the official league club
    # list (see the documentation). Do not infer promoted identities by fuzziness.
    official_2026 = {"Athletic Club","Atletico Madrid","Osasuna","Celta Vigo","Alaves","Elche","Barcelona","Getafe",
                     "Levante","Malaga","Racing Santander","Rayo Vallecano","Deportivo La Coruna","Espanyol",
                     "Real Betis","Real Madrid","Real Sociedad","Sevilla","Valencia","Villarreal"}
    require(set(current.home.map(resolve)) == official_2026,"UNVERIFIED_TEAM_IDENTITY","2026 roster differs from reviewed official clubs")
    partial = []
    full_keys = set(staging.canonical_key)
    shot_stats = understat_shots(pd.read_csv(directory/"raw/archive_2025_shots.csv")).set_index("fixture_id")
    for key, fixture in registry.fixtures.items():
        if fixture["match_status"] != VERIFIED_COMPLETED or key in full_keys:
            continue
        year = fixture["season"]
        if year == 2025:
            candidates = archives[2025].loc[archives[2025].home.map(resolve).eq(fixture["home_team"])
                                          & archives[2025].away.map(resolve).eq(fixture["away_team"])]
            require(len(candidates)==1 and bool(candidates.iloc[0].totals_unreliable),"BASELINE_DIFFERENCE","Unexpected pending archive fixture")
            source_row = candidates.iloc[0]
            stats = shot_stats.loc[source_row.fixture_id]
            metadata = dict(fixture_source="Understat",xg_source="Understat_flagged_unreliable",
                            shots_source="Understat_shot_events",source_dataset_version="sha256:"+entries["archive_2025_fixtures.csv"]["sha256"]
                            +";shots_sha256:"+entries["archive_2025_shots.csv"]["sha256"],fetched_at=entries["archive_2025_fixtures.csv"]["retrieved_at"],
                            statistical_semantics="xg_unavailable_flagged;research_non_penalty_shot_mapping")
        else:
            require(year==2026,"BASELINE_DIFFERENCE","Unexpected pending season")
            stats = None
            metadata = dict(fixture_source="LaLiga_official_completion+xGTables_fixture_identity",xg_source="Sportmonks_pending",
                            shots_source="Sportmonks_pending",source_dataset_version="sha256:"+entry["sha256"]+";completion_sha256:"+sha256(official_path),
                            fetched_at=official["reviewed_at"],statistical_semantics="statistics_unavailable_no_imputation")
        for team, opponent, side, other, is_home in [(fixture["home_team"],fixture["away_team"],"home","away",1),
                                                    (fixture["away_team"],fixture["home_team"],"away","home",0)]:
            partial.append(dict(season=year,date=fixture["match_date"],team=team,opponent=opponent,is_home=is_home,
                                gf=fixture[side+"_goals"],ga=fixture[other+"_goals"],xg=None,xga=None,
                                sh=None if stats is None else int(stats[side+"_sh"]),
                                sot=None if stats is None else int(stats[side+"_sot"]),canonical_key=key,**metadata))
    statistics = registry.attach_statistics(pd.concat([staging,pd.DataFrame(partial)],ignore_index=True))
    require(sum(r["statistics_status"] == COMPLETE_STATISTICS for r in registry.fixtures.values()) == 2779,
            "BASELINE_DIFFERENCE","Valid Phase 8.5.2 statistics were lost")
    catalogues = {}
    for year in range(2019,2027):
        frame = archives[year] if year<2026 else current
        source = entries[f"archive_{year}_fixtures.csv" if year<2026 else "current_2026_fixtures.csv"]
        clubs = frame.home.map(resolve).unique().tolist()
        catalogues[year] = validate_catalogue(registry,year,clubs,source["url"],source["sha256"],reviewed_at)
    return registry,statistics,catalogues,hashes


def evaluate(store, directory=LOCAL, *, output=None):
    directory = Path(directory)
    output = Path(output) if output else directory/"phase853"/store.manifest["version_id"]
    output.mkdir(parents=True,exist_ok=True)
    predictor = CompositePredictor(store)
    original_predictions = pd.read_csv(directory/"processed/frozen_lr_predictions.csv")
    original_features = pd.read_csv(directory/"processed/feature_inputs.csv")
    originally_blocked = pd.read_csv(directory/"processed/feature_exclusions.csv")
    targets = store.query("SELECT * FROM registry WHERE season=2026 AND match_status=? ORDER BY match_date,canonical_fixture_key",(VERIFIED_COMPLETED,))
    results, predictions, features, parity, reevaluated = [], [], [], [], []
    for fixture in targets:
        key = fixture["canonical_fixture_key"]
        result = predictor.predict(fixture["home_team"],fixture["away_team"],fixture["match_date"],2026)
        results.append(result)
        if result["status"] != "success":
            continue
        for i, team in enumerate((fixture["home_team"],fixture["away_team"])):
            predictions.append(dict(canonical_key=key,team=team,raw_prediction=result["raw_predictions"][i],
                                    prediction=result["home_xg" if i==0 else "away_xg"]))
            features.append(dict(canonical_key=key,**result["features"][i]))
        old = original_features.loc[original_features.canonical_key.eq(key)].sort_values("is_home",ascending=False)
        if len(old):
            require(len(old)==2,"PARITY_REFERENCE_INVALID","Expected two Phase 8.5.2 feature rows")
            actual = np.asarray([[row[f] if row[f] is not None else np.nan for f in FEATURES] for row in result["features"]])
            expected = old[list(FEATURES)].to_numpy(dtype=float)
            previous = original_predictions.loc[original_predictions.canonical_key.eq(key)]
            previous = previous.set_index("team").loc[[fixture["home_team"],fixture["away_team"]]]
            feature_delta = float(np.nanmax(np.abs(actual-expected)))
            prediction_delta = float(np.max(np.abs(np.asarray(result["raw_predictions"])-previous.raw_prediction.to_numpy())))
            passed = np.allclose(actual,expected,rtol=0,atol=1e-12,equal_nan=True) and prediction_delta<=1e-12
            parity.append(dict(canonical_key=key,passed=bool(passed),max_feature_delta=feature_delta,max_prediction_delta=prediction_delta))
        if key in set(originally_blocked.canonical_key):
            history = result["history_summary"]["Villarreal"]
            pending = history["pending_outside_window"]
            reevaluated.append(dict(canonical_key=key,status="unlocked",matches_seen=history["matches_seen"],
                                    missing_fixture_keys=pending,
                                    missing_position_in_stint=[history["eligible_match_keys"].index(k)+1 for k in pending],
                                    missing_position_from_latest=[history["matches_seen"]-history["eligible_match_keys"].index(k) for k in pending],
                                    rolling_match_keys=history["rolling_match_keys"]))
    unlocked_keys = {r["canonical_key"] for r in reevaluated}
    for key in originally_blocked.canonical_key:
        if key not in unlocked_keys:
            f = next(r for r in targets if r["canonical_fixture_key"]==key)
            result = predictor.predict(f["home_team"],f["away_team"],f["match_date"],2026)
            reevaluated.append(dict(canonical_key=key,status="blocked",reason=result.get("error")))
    pd.DataFrame(predictions).to_csv(output/"predictions.csv",index=False)
    pd.DataFrame(features).to_csv(output/"features.csv",index=False)
    pd.DataFrame(parity).to_csv(output/"prediction_parity.csv",index=False)
    (output/"reevaluated_12.json").write_text(json.dumps(reevaluated,indent=2),encoding="utf-8")
    (output/"inference_records.json").write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    pd.DataFrame(store.manifest["coverage"]).to_csv(output/"coverage_by_team.csv",index=False)
    missing = store.query("SELECT * FROM registry WHERE match_status=? AND statistics_status<>?",(VERIFIED_COMPLETED,COMPLETE_STATISTICS))
    pd.DataFrame(missing).to_csv(output/"missing_history.csv",index=False)
    (output/"source_provenance_manifest.json").write_text(json.dumps(dict(input_hashes=store.manifest["input_hashes"],
        source_dataset_versions=store.manifest["source_dataset_versions"],identity_review=store.manifest["identity_review"]),indent=2),encoding="utf-8")
    summary = dict(version_id=store.manifest["version_id"],registry_fixtures=store.manifest["registry_fixtures"],
                   verified_completed=store.manifest["verified_completed"],complete_statistics=store.manifest["complete_statistics"],
                   pending_statistics=store.manifest["pending_statistics"],unverified=store.manifest["unverified"],
                   unresolved_conflicts=store.manifest["unresolved_conflicts"],targets=len(targets),
                   successful_fixtures=len(predictions)//2,predictions=len(predictions),
                   previously_blocked=len(originally_blocked),unlocked=sum(r["status"]=="unlocked" for r in reevaluated),
                   parity_fixtures=len(parity),parity_passed=sum(r["passed"] for r in parity),
                   max_feature_delta=max((r["max_feature_delta"] for r in parity),default=None),
                   max_prediction_delta=max((r["max_prediction_delta"] for r in parity),default=None),
                   artifact_sha256=predictor.metadata["artifact_sha256"],production_approved=False,strikerapi_credits=0)
    require(len(parity)==len(original_predictions)//2==111 and all(r["passed"] for r in parity),
            "PARITY_FAILED","Phase 8.5.2 parity failed; inspect private report before use")
    (output/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,default=LOCAL)
    parser.add_argument("--version",required=True)
    parser.add_argument("--parent",type=Path)
    args = parser.parse_args()
    registry,statistics,catalogues,hashes = load_snapshot(args.directory)
    parent = None if args.parent is None else CompositeHistory(args.parent)
    store = publish_version(registry,statistics,catalogues,version_id=args.version,input_hashes=hashes,
                            parent=parent,identity_review=identity_manifest(),
                            validator=lambda provisional:evaluate(provisional,args.directory))
    print(json.dumps(store.manifest["inference_validation"],indent=2))


if __name__ == "__main__":
    main()
