"""Reproduce offline staging, coverage and frozen-LR feasibility from local files.

Run acquisition separately. All outputs stay under Git-ignored research data.
Never trains, refreshes a History Store, or calls a network/API client.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from itertools import permutations

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.inference.common import CANONICAL_TEAMS
from scripts.inference.model_artifact import load_trusted_pipeline
from .acquire import LOCAL, ROOT
from .features import build_features
from .mapping import RAW_FIELDS, mapped_fixture, reconcile_completion, team_name, understat_shots, validate_staging
from .mapping import fixture_identity


CURRENT_FIELDS = dict(date="date", home="home", away="away", home_gf="home_goals", away_gf="away_goals",
                      home_xg="home_xg", away_xg="away_xg", home_sh="home_shots", away_sh="away_shots",
                      home_sot="home_shots_on_target", away_sot="away_shots_on_target")
ARCHIVE_FIELDS = dict(CURRENT_FIELDS, home_sh="home_sh", away_sh="away_sh",
                      home_sot="home_sot", away_sot="away_sot")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_file(path, acquisition):
    data = pd.read_csv(path)
    shots = "shot_id" in data
    completed = (data.status.eq("full_time") if "status" in data else
                 data.score.astype(str).str.fullmatch(r"\d+-\d+") if "score" in data else pd.Series(True, index=data.index))
    dated = data
    date_basis = "native_fixture_date"
    if shots:
        dated = pd.read_csv(path.with_name(path.name.replace("shots.csv", "fixtures.csv")))
        dated = dated.loc[dated.fixture_id.isin(data.fixture_id)]
        if set(dated.fixture_id) != set(data.fixture_id):
            raise ValueError("Missing fixture dates for shot inventory")
        date_basis = "fixture_id_join_to_same_snapshot_fixture_export"
        completed = dated.score.astype(str).str.fullmatch(r"\d+-\d+")
    return dict(filename=path.name, format="CSV UTF-8", url=acquisition["url"],
                original_provider="Sportmonks" if path.name.startswith("current") else "Understat",
                retrieved_at=acquisition["retrieved_at"], sha256=digest(path), bytes=path.stat().st_size,
                rows=len(data), columns=data.columns.tolist(),
                unique_fixtures=int(data.fixture_id.nunique()),
                earliest_date=dated.date.min(), latest_date=dated.date.max(), date_basis=date_basis,
                completed_fixtures=int(completed.sum()),
                latest_completed_date=dated.loc[completed, "date"].max(),
                missing_values={k:int(v) for k,v in data.isna().sum().items()},
                duplicate_records=int(data.duplicated().sum()),
                duplicate_primary_ids=int(data["shot_id" if shots else "fixture_id"].duplicated().sum()))


def provenance(entry, source, *, shots=None):
    version = "sha256:" + entry["sha256"]
    if shots:
        version += ";shots_sha256:" + shots["sha256"]
    return dict(fixture_source=source, xg_source=source, shots_source=source if not shots else "Understat_shot_events",
                source_dataset_version=version, fetched_at=entry["retrieved_at"],
                statistical_semantics=("external_xg_model;reported_shots_penalty_inclusion_unverified"
                                       if source == "Sportmonks" else
                                       "external_xg_model;derived_non_penalty_non_own_goal_SH;Goal_SavedShot_SOT_research_mapping"))


def snapshot_rows():
    path = ROOT / "data/laliga_processed_normalized.csv"
    rows = pd.read_csv(path)[list(RAW_FIELDS)].copy()
    if rows.date.gt("2025-09-30").any():
        raise ValueError("Snapshot boundary changed; review required")
    for column in ("team", "opponent"):
        rows[column] = rows[column].map(team_name)
    home = rows.team.where(rows.is_home.eq(1), rows.opponent)
    away = rows.opponent.where(rows.is_home.eq(1), rows.team)
    rows["canonical_key"] = [f"research:laliga:{s}:{h}:{a}" for s,h,a in zip(rows.season,home,away)]
    for key in ("fixture_source", "xg_source", "shots_source"):
        rows[key] = "FBref_frozen_snapshot"
    rows["source_dataset_version"] = "sha256:" + digest(path)
    rows["fetched_at"] = "original_fetch_unknown_local_frozen_snapshot"
    rows["statistical_semantics"] = "training_snapshot_unchanged_non_penalty_SH_SOT_supported_by_original_PK_cases"
    return validate_staging(rows)


def inspect_calendar(frame, season):
    identities = [fixture_identity(season,r["date"],r["home"],r["away"]) for r in frame.to_dict("records")]
    pairs = [(identity[2],identity[3]) for identity in identities]
    if len(set(pairs)) != len(pairs):
        raise ValueError("Duplicate scheduled fixture pairing")
    clubs = {team for pair in pairs for team in pair}
    return dict(unique_fixtures=len(identities), clubs=len(clubs),
                full_double_round_robin=set(pairs)==set(permutations(clubs,2)))


def audit(directory=LOCAL, *, as_of="2026-11-22"):
    directory = Path(directory)
    output = directory / "processed"
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((directory/"acquisition_manifest.json").read_text(encoding="utf-8"))
    entries = {r["file"]:r for r in manifest if r["status"] == 200}
    files = []
    for name, entry in entries.items():
        if name.endswith(".csv"):
            path = directory/"raw"/name
            if digest(path) != entry["sha256"]:
                raise ValueError("Acquired file changed: " + name)
            files.append(inspect_file(path, entry))
    original = snapshot_rows()
    shots = pd.read_csv(directory/"raw/archive_2025_shots.csv")
    stats = understat_shots(shots)
    archives = {s:pd.read_csv(directory/"raw"/f"archive_{s}_fixtures.csv") for s in range(2019,2026)}
    for season, frame in archives.items():
        if (not frame.season.eq(season).all() or not frame.competition.eq("la-liga").all()
                or not frame.provider.eq("Understat").all() or frame.fixture_id.duplicated().any()):
            raise ValueError("Archive competition/season/provider scope mismatch")
    if not set(shots.fixture_id).issubset(archives[2025].fixture_id):
        raise ValueError("Orphan shot fixture")
    for column, expected_value in [("season", 2025), ("competition", "la-liga"), ("provider", "Understat")]:
        if not shots[column].eq(expected_value).all():
            raise ValueError("Shot scope mismatch")
    archive = archives[2025].merge(stats, on="fixture_id", how="left", validate="one_to_one")
    current = pd.read_csv(directory/"raw/current_2026_fixtures.csv")
    if not current.phase.eq("league").all() or not current.team_xg_source.eq("Sportmonks").all() or current.fixture_id.duplicated().any():
        raise ValueError("Current export scope or fixture identity mismatch")
    official_path = directory/"independent_completed.json"
    independent = json.loads(official_path.read_text(encoding="utf-8")) if official_path.exists() else None
    current = reconcile_completion(current, independent["matches"] if independent else [], season=2026)
    rows, exclusions, expected, overlap, coverage = [], [], [], [], []
    base_home = original.loc[original.is_home.eq(1)].assign(home=lambda d:d.team, away=lambda d:d.opponent)
    # Investigate overlap; never replace the frozen reference with an external source.
    for season, frame in archives.items():
        candidate = frame.assign(home=frame.home.map(team_name), away=frame.away.map(team_name))
        reference = base_home.loc[base_home.season.eq(season)]
        joined = candidate.merge(reference, on=["season", "date", "home", "away"], suffixes=("_ext", "_ref"), validate="one_to_one")
        scores = joined.score.str.extract(r"^(\d+)-(\d+)$").astype(int)
        overlap.append(dict(season=season, matched=len(joined), reference_fixtures=len(reference),
                            score_conflicts=int((scores[0].ne(joined.gf) | scores[1].ne(joined.ga)).sum()),
                            xg_numerical_differences=int((joined.home_xg.sub(joined.xg).abs().gt(1e-9)
                                                         | joined.away_xg.sub(joined.xga).abs().gt(1e-9)).sum())))
    for season, frame in [(2025, archive), (2026, current)]:
        name = f"archive_{season}_fixtures.csv" if season == 2025 else "current_2026_fixtures.csv"
        source = "Understat" if season == 2025 else "Sportmonks"
        metadata = provenance(entries[name], source, shots=entries["archive_2025_shots.csv"] if season == 2025 else None)
        for record in frame.to_dict("records"):
            home, away = team_name(record["home"]), team_name(record["away"])
            key = f"research:laliga:{season}:{home}:{away}"
            completed = (bool(re.fullmatch(r"\d+-\d+", str(record.get("score")))) if season == 2025
                         else record["status"] == "full_time" or record["independently_completed"])
            if not completed or record["date"] > as_of:
                exclusions.append(dict(season=season, canonical_key=key, date=record["date"], reason="not_completed_as_of_snapshot"))
                continue
            if record["date"] <= "2025-09-30":
                exclusions.append(dict(season=season, canonical_key=key, date=record["date"], reason="preserved_frozen_reference"))
                continue
            for team, opponent, is_home in [(home,away,1),(away,home,0)]:
                expected.append(dict(season=season, date=record["date"], team=team, opponent=opponent,
                                     is_home=is_home, canonical_key=key))
            try:
                if season == 2026 and record["independently_completed"]:
                    raise ValueError("official_completed_but_export_missing_xg_sh_sot")
                if season == 2025:
                    if record["totals_unreliable"]:
                        raise ValueError("provider_flagged_unreliable_team_xg")
                    h, a = map(int, record["score"].split("-"))
                    record.update(home_goals=h, away_goals=a)
                pair = mapped_fixture(record, ARCHIVE_FIELDS if season == 2025 else CURRENT_FIELDS,
                                      season=season, provenance=metadata)
                rows.extend(pair)
            except ValueError as exc:
                exclusions.append(dict(season=season, canonical_key=key, date=record["date"], reason=str(exc)))
    staging = validate_staging(pd.concat([original, pd.DataFrame(rows)], ignore_index=True))
    expectation = pd.concat([original[["season","date","team","opponent","is_home","canonical_key"]],
                             pd.DataFrame(expected)], ignore_index=True)
    if expectation.duplicated(["canonical_key", "team"]).any():
        raise ValueError("Conflicting expected fixtures")
    staging.to_csv(output/"laliga_multisource_staging.csv", index=False)
    pd.DataFrame(exclusions).to_csv(output/"excluded_fixtures.csv", index=False)
    expectation.to_csv(output/"expected_completed_history.csv", index=False)
    for season in range(2019,2027):
        source = archives[season] if season <= 2025 else current
        calendar = inspect_calendar(source, season)
        completed = source.score.str.fullmatch(r"\d+-\d+") if season <= 2025 else source.status.eq("full_time") & source.date.le(as_of)
        ready = staging.loc[staging.season.eq(season) & staging.is_home.eq(1)]
        xg_valid = source.home_xg.notna() & source.away_xg.notna() & completed
        raw_sh = len(ready) if season != 2025 else int(archive.home_sh.notna().sum())
        raw_sot = len(ready) if season != 2025 else int(archive.home_sot.notna().sum())
        coverage.append(dict(season=season, listed_fixtures=len(source), completed_in_source=int(completed.sum()),
                             listed_calendar=calendar,
                             known_completed_lower_bound=int(completed.sum()) + (int(current.independently_completed.sum()) if season == 2026 else 0),
                             external_valid_xg=int(xg_valid.sum()), valid_sh=raw_sh, valid_sot=raw_sot,
                             staging_all_fields=len(ready), missing_completed=int(completed.sum())-len(ready)
                             + (int(current.independently_completed.sum()) if season == 2026 else 0)))
    teams = expectation.groupby(["season", "team"]).size().rename("expected_completed").to_frame().join(
        staging.groupby(["season", "team"]).size().rename("integrated_completed")).fillna(0).reset_index()
    teams["missing"] = teams.expected_completed - teams.integrated_completed
    teams.to_csv(output/"coverage_by_team.csv", index=False)
    targets = expectation.loc[expectation.season.eq(2026) & expectation.is_home.eq(1)].sort_values(["date","canonical_key"])
    pipeline, model_metadata = load_trusted_pipeline()
    predictions, blocked, features = [], [], []
    short, zero, mixed, production_unknown = 0, 0, 0, 0
    for target in targets.to_dict("records"):
        if target["team"] not in CANONICAL_TEAMS or target["opponent"] not in CANONICAL_TEAMS:
            production_unknown += 1
        try:
            X, history = build_features(staging, target["team"], target["opponent"], target["date"], 2026, expected=expectation)
        except ValueError as exc:
            blocked.append(dict(canonical_key=target["canonical_key"], reason=str(exc)))
            continue
        short += int(X.short_history.gt(0).any())
        zero += int(X.matches_seen.eq(0).any())
        used = {key for item in history.values() for key in item["rolling_match_keys"]}
        sources = staging.loc[staging.canonical_key.isin(used), "xg_source"].unique()
        mixed += int(len(sources)>1)
        with threadpool_limits(limits=1):
            raw = np.asarray(pipeline.predict(X), dtype=float)
        if raw.shape != (2,) or not np.isfinite(raw).all():
            raise ValueError("Invalid frozen prediction")
        for i in range(2):
            predictions.append(dict(canonical_key=target["canonical_key"], team=target["team"] if i==0 else target["opponent"],
                                    raw_prediction=float(raw[i]), prediction=float(max(0,raw[i]))))
            features.append(dict(canonical_key=target["canonical_key"], **X.iloc[i].to_dict()))
    pd.DataFrame(predictions).to_csv(output/"frozen_lr_predictions.csv", index=False)
    pd.DataFrame(features).to_csv(output/"feature_inputs.csv", index=False)
    pd.DataFrame(blocked).to_csv(output/"feature_exclusions.csv", index=False)
    # Shot totals and archived xG can be different versions. Do not fit a correction.
    sums = shots.groupby(["fixture_id", "side"]).understat_xg.sum().unstack("side")
    check = archives[2025].merge(sums, on="fixture_id", validate="one_to_one")
    mismatched = (check.home_xg.sub(check.h).abs().gt(.01) | check.away_xg.sub(check.a).abs().gt(.01))
    results = dict(as_of=as_of, generated_at=datetime.now(timezone.utc).isoformat(),
                   branch_base="84f14fd0638661c44933f917ce69effe518252ff", files=files, coverage=coverage,
                   overlap=overlap, total_integrated_fixtures=len(staging)//2,
                   original_fixtures=len(original)//2, added_fixtures=len(rows)//2,
                   excluded_reasons=pd.Series([r["reason"] for r in exclusions]).value_counts().to_dict(),
                   feature_experiment=dict(target_fixtures=len(targets), successful_fixtures=len(predictions)//2,
                                           predictions=len(predictions), missing_history_fixtures=len(blocked),
                                           short_history_fixtures=short, zero_history_fixtures=zero,
                                           mixed_xg_window_fixtures=mixed, production_unknown_club_fixtures=production_unknown,
                                           artifact_sha256=model_metadata["artifact_sha256"],
                                           model_accepted_schema=True, predictive_accuracy_validated=False),
                   shot_audit=dict(fixtures=shots.fixture_id.nunique(), rows=len(shots),
                                   results=sorted(shots.result.unique().tolist()),
                                   shot_vs_archive_xg_mismatch_over_001=int(mismatched.sum()),
                                   completeness_independently_verified=False),
                   independent_verification=None if independent is None else dict(
                       source_url=independent["source_url"], reviewed_at=independent["reviewed_at"],
                       method=independent["method"], evidence_sha256=digest(official_path),
                       additional_completed=int(current.independently_completed.sum()),
                       unresolved_live_fixture_count=independent["unresolved_live_fixture_count"]),
                   known_missing_fixtures=len(expectation)//2-len(staging)//2,
                   team_coverage_gaps=teams.loc[teams.missing.gt(0)].to_dict("records"),
                   strikerapi_calls=0, strikerapi_credits=0, production_approved=False,
                   assessment="CONDITIONAL GO")
    # numpy scalars in diagnostic metadata are serialized explicitly, never raw rows.
    (directory/"audit_results.json").write_text(json.dumps(results, indent=2, default=lambda v:v.item()), encoding="utf-8")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=LOCAL)
    parser.add_argument("--as-of", default="2026-11-22")
    args = parser.parse_args()
    result = audit(args.directory, as_of=args.as_of)
    print(json.dumps({key:result[key] for key in ["assessment","total_integrated_fixtures","added_fixtures","feature_experiment","excluded_reasons"]}, indent=2))
