"""Offline Phase 8.5.6 entry point. Detailed outputs stay in ignored storage."""

import argparse
from collections import Counter
from contextlib import closing
import json
import re
import socket
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

import pandas as pd

from scripts.inference.common import InferenceError, ROOT, sha256, versions
from scripts.prepare_training_features import FEATURES
from .acquire import LOCAL
from .composite_history import RESEARCH_ROOT, CompositeHistory, dumps
from .composite_inference import CompositePredictor
from .mapping import understat_shots
from .match_registry import VERIFIED_COMPLETED, require
from .phase856_validation import COHORTS, TRAINING_REFERENCE_END, distribution, paired_statistics, pair_overlap, replay_cohort, summarize_scores
from .refresh_validation import archive_identities, checked_archive_shots
from .run_audit import snapshot_rows

BASE = "6c1d0614558d6904185beb8346d6c0dfd31e516c"
BRANCH = "phase8.5.6-provider-compatibility-validation"
V3 = RESEARCH_ROOT / "phase853_v3_20261122/laliga_composite.sqlite3"
OUTPUT_ROOT = LOCAL / "phase856"
EVALUATION_NAME = "Retrospective date-cutoff replay"
PROTECTED_MANIFESTS = ("outputs/inference/protected_files.json", "outputs/provider_poc/reports/protected_files.json")
ARCHIVES = {year:f"raw/archive_{year}_fixtures.csv" for year in range(2019,2026)}
REQUIRED_SOURCES = ("acquisition_manifest.json", "independent_completed.json", *ARCHIVES.values(),
                    "raw/archive_2025_shots.csv","raw/current_2026_fixtures.csv","data/laliga_processed_normalized.csv")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(dumps(value)+"\n",encoding="utf-8")


def protected_integrity():
    counts = {}
    checksums = {}
    for name in PROTECTED_MANIFESTS:
        baseline = subprocess.check_output(["git","show",BASE+":"+name],cwd=ROOT)
        entries = json.loads(baseline)
        for filename, checksum in entries.items():
            path = ROOT / filename
            require(path.is_file() and sha256(path) == checksum,"PROTECTED_ARTIFACT_MISMATCH",f"Protected hash mismatch: {filename}")
        counts[name] = len(entries)
        checksums.update(entries)
    return counts, checksums


def required_inputs():
    reference = read_json(ROOT/"docs/COMPOSITE_HISTORY_VALIDATION.json")
    checksums = {name:reference["source_input_sha256"][name] for name in REQUIRED_SOURCES}
    paths = {name:ROOT/name if name.startswith("data/") else LOCAL/name for name in checksums}
    v3_name = V3.relative_to(ROOT).as_posix()
    checksums[v3_name] = reference["database_sha256"]
    paths[v3_name] = V3
    blockers = []
    for name,path in paths.items():
        if not path.is_file() or sha256(path) != checksums[name]:
            blockers.append(dict(file=path.relative_to(ROOT).as_posix(),expected_sha256=checksums[name],
                                 reason="CHECKSUM_MISMATCH" if path.is_file() else "MISSING"))
    if not (V3.parent/"manifest.json").is_file():
        blockers.append(dict(file=(V3.parent/"manifest.json").relative_to(ROOT).as_posix(),
                             expected_sha256=None,reason="MISSING_SIDECAR_ATTESTED_BY_EMBEDDED_V3_MANIFEST"))
    return checksums, blockers


def overlap_report(rows):
    return dict(reference_fixtures=len({r["key"] for r in rows}),
                identity_matched_fixtures=len({r["key"] for r in rows if r["matched"]}),
                xg_all=paired_statistics(rows,"xg"),
                xg_by_season_and_side={str(year):{
                    side:paired_statistics([r for r in rows if r["season"]==year and
                         (side=="overall" or r["perspective"]==side)],"xg") for side in ("overall","home","away")}
                    for year in sorted({r["season"] for r in rows})},
                shots=dict(sh=paired_statistics(rows,"sh"),sot=paired_statistics(rows,"sot"),
                           verified_same_definition=False, scope="Descriptive paired counts in the reviewed 2025 shot-event overlap"))


def summarize_cohort(result):
    outcomes = result["outcomes"]
    fixture_scores = result["fixture_scores"]
    rows = [row for pair in fixture_scores for row in pair]
    composition = {}
    label_versions = Counter(row["label_provenance"]["source_dataset_version"] for row in rows)
    for key in ("fixture_source","xg_source","shots_source"):
        windows = [[item[key] for item in row["window"]] for row in rows]
        composition[key] = dict(history_team_rows=dict(sorted(Counter(v for window in windows for v in window).items())),
                                mixed_team_windows=sum(len(set(window))>1 for window in windows),
                                adjacent_source_changes=sum(a!=b for w in windows for a,b in zip(w,w[1:])),
                                empty_windows=sum(not w for w in windows))
    status_counts = Counter(r["status"] for r in outcomes)
    counts = {kind:dict(sorted(Counter(r["reason"] for r in outcomes if r["status"]==kind).items()))
              for kind in ("EXCLUDED","BLOCKED")}
    require(len(rows) == 2*len(fixture_scores) and len(fixture_scores) == status_counts["SCORED"]
            and len(outcomes) == result["candidate_fixtures"],"COHORT_ACCOUNTING_ERROR","Cohort counts do not reconcile")
    return dict(**{key:value for key,value in result.items() if key not in ("outcomes","fixture_scores")},
                scored_fixtures=len(fixture_scores), scored_team_observations=len(rows), excluded_fixtures=status_counts["EXCLUDED"],
                blocked_fixtures=status_counts["BLOCKED"], exclusions=counts, label_versions=dict(sorted(label_versions.items())),
                rolling_window_composition=composition, metrics=summarize_scores(fixture_scores),
                feature_distributions={side:{name:distribution([r["features"][name] for r in rows if r["perspective"]==side
                                       and r["features"][name] is not None]) for name in FEATURES} for side in ("home","away")})


def sportmonks_shots(current, store):
    require(current.phase.eq("league").all() and current.team_xg_source.eq("Sportmonks").all()
            and current.fixture_id.notna().all() and current.fixture_id.is_unique,
            "INVALID_CURRENT_SOURCE","Unexpected current provider scope")
    completed = current[current.status.eq("full_time")]
    observed = [(r[side+"_shots"],r[side+"_shots_on_target"]) for r in completed.to_dict("records") for side in ("home","away")]
    valid = sum(pd.notna(sh) and pd.notna(sot) and 0 <= sot <= sh and sh%1==sot%1==0 for sh,sot in observed)
    verified = store.query("SELECT COUNT(*) AS n FROM registry WHERE season=2026 AND match_status=?",(VERIFIED_COMPLETED,))[0]["n"]
    return dict(cross_provider_pairs=0, structurally_valid_team_observations=valid,
                missing_or_invalid_within_full_time=len(observed)-valid, export_full_time_fixtures=len(completed),
                non_full_time_export_rows=len(current)-len(completed), verified_completed_registry_fixtures=verified,
                penalty_metadata_nonnull=int(current[["home_penalties","away_penalties"]].notna().sum().sum()),
                penalty_semantics="UNVERIFIED", paired_comparison_status="NO_ATTESTED_SAME_FIXTURE_FBREF_OVERLAP")


def historical_reference():
    protocol = read_json(ROOT/"outputs/final_test/evaluation_protocol.json")
    require(protocol["baseline"]["feature"] == "xg_avg5"
            and protocol["baseline"]["preprocessing"] == "reuse_development_fitted_primary_preprocessor"
            and protocol["features"] == list(FEATURES), "BASELINE_PROTOCOL_CHANGED", "Phase 7 baseline contract differs")
    metrics = pd.read_csv(ROOT/"outputs/final_test/final_test_metrics.csv")
    return metrics.loc[metrics.model.eq("Linear Regression"),["test_split","n_matches","n_observations","mae","rmse"]].to_dict("records")


def snapshot_hashes():
    return {p.relative_to(ROOT).as_posix():sha256(p) for p in sorted(RESEARCH_ROOT.rglob("*")) if p.is_file()}


def evaluate(directory):
    counts, frozen = protected_integrity()
    expected, blockers = required_inputs()
    preliminary = dict(phase="8.5.6", branch=BRANCH, base_commit=BASE,
                       code_revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                       evaluation=EVALUATION_NAME, production_approved=False, expected_input_sha256=expected,
                       environment=versions(), protected_manifest_entries=counts)
    if blockers:
        return dict(preliminary,implementation_verdict="BLOCKED",scientific_conclusion="EVIDENCE_INSUFFICIENT",
                    missing_or_unverified_inputs=blockers,rerun=f"python -m scripts.multisource.phase856_reporting --run-id {directory.name}-retry")
    snapshots = snapshot_hashes()
    store = CompositeHistory(V3)
    require(store.manifest["version_id"] == V3.parent.name
            and all(store.manifest["input_hashes"][n] == expected[n] for n in REQUIRED_SOURCES),
            "V3_INPUTS_MISMATCH","V3 manifest is not bound to the attested sources")
    with closing(sqlite3.connect(V3.as_uri()+"?mode=ro&immutable=1",uri=True)) as conn:
        require(conn.execute("PRAGMA integrity_check").fetchone()[0]=="ok" and not conn.execute("PRAGMA foreign_key_check").fetchall(),
                "V3_SQLITE_INVALID","Immutable SQLite integrity check failed")
    acquisition = read_json(LOCAL/"acquisition_manifest.json")
    pinned_sources = read_json(ROOT/"docs/MULTISOURCE_LALIGA_DATASET_MANIFEST.json")["files"]
    by_name = {row["file"]:row for row in acquisition}
    entries = {}
    for source in pinned_sources:
        name = source["filename"]
        entry = by_name[name]
        require(entry["status"] == 200 and entry["sha256"] == expected["raw/"+name] == source["sha256"]
                and entry["url"] == source["url"] and entry["retrieved_at"] == source["retrieved_at"],
                "SOURCE_VERSION_MISMATCH","Acquisition entries differ from public attestation")
        entries[name] = entry
    archives = {year:pd.read_csv(LOCAL/name) for year,name in ARCHIVES.items()}
    shots = checked_archive_shots(pd.read_csv(LOCAL/"raw/archive_2025_shots.csv"),archive_identities(archives[2025]))
    rows = pair_overlap(snapshot_rows(),archives,shot_totals=understat_shots(shots))
    overlap = overlap_report(rows)
    previous_overlap = read_json(ROOT/"docs/MULTISOURCE_LALIGA_DATASET_MANIFEST.json")["overlap"]
    require(overlap["identity_matched_fixtures"] == sum(r["matched"] for r in previous_overlap)
            and overlap["reference_fixtures"]==sum(r["reference_fixtures"] for r in previous_overlap),
            "OVERLAP_SCOPE_CHANGED","Overlap must reproduce the prereviewed cohort")
    predictor = CompositePredictor(store)
    cohorts = {}
    for cohort in COHORTS:
        result = replay_cohort(store,predictor,cohort)
        write_json(directory/(cohort.name+"-private.json"),result)
        cohorts[cohort.name] = summarize_cohort(result)
        checked_version = "sha256:" + expected[(ARCHIVES[2025] if cohort.name=="B1" else "raw/current_2026_fixtures.csv")]
        if cohort.name=="B1":
            checked_version += ";shots_sha256:" + expected["raw/archive_2025_shots.csv"]
        require(set(cohorts[cohort.name]["label_versions"]) <= {checked_version},
                "TARGET_PROVENANCE_INVALID","Scored labels differ from the attested source version")
    current_shots = sportmonks_shots(pd.read_csv(LOCAL/"raw/current_2026_fixtures.csv"),store)
    write_json(directory/"overlap-private.json",rows)
    pending = store.query("SELECT COUNT(*) AS n FROM registry WHERE statistics_status='PENDING_UPDATE'")[0]["n"]
    require(pending==4 and snapshot_hashes()==snapshots and protected_integrity()[1]==frozen,
            "ARTIFACT_CHANGED","Pending records or existing artifacts changed")
    return dict(preliminary,implementation_verdict="PASS",scientific_conclusion="SUPPORTED_WITH_LIMITATIONS",
                production_approved=False,training_reference_end=TRAINING_REFERENCE_END,
                verified_source_versions={name:dict(provider="Sportmonks" if name.startswith("current_") else "Understat",
                    sha256=row["sha256"],retrieved_at=row["retrieved_at"],url=row["url"])
                    for name,row in entries.items() if name.endswith(".csv")},
                artifact_sha256=predictor.metadata["artifact_sha256"], model_version=predictor.metadata["model_version"],
                production_history_sha256=frozen["data/history/laliga_history.sqlite3"],
                model_metadata_sha256=frozen["models/model_metadata.json"],research_snapshot_version=store.manifest["version_id"],
                v3_sqlite_integrity=True,previous_snapshot_files_unchanged=len(snapshots),pending_fixtures_unchanged=pending,
                overlap=overlap,sportmonks_shots=current_shots,cohorts=cohorts,
                phase7_reference_only=historical_reference(),
                assumptions=dict(residual="clipped LR xG minus provider-reported xG", baseline="frozen preprocessing -> xg_avg5",
                    bootstrap_unit="fixture, retaining both perspectives",source_equivalence="INCONCLUSIVE",
                    feature_comparison="Same feature schema by role across B1/B2, confounded by roster, period and selection",
                    vintage="No proof of historical as-of-vintage availability",production_approved=False))


def run_full_suite(directory):
    suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
    with (directory/"unittest.log").open("w",encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    return dict(executed=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                exit_code=int(not result.wasSuccessful()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--full-suite",action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",args.run_id):
        parser.error("Use a simple, new run identifier")
    directory = OUTPUT_ROOT / args.run_id
    require(directory.resolve() == directory,"INVALID_OUTPUT_SCOPE","Outputs require a direct ignored workspace")
    directory.mkdir(parents=True,exist_ok=False)
    with patch.object(socket.socket,"connect",side_effect=AssertionError("Phase 8.5.6 is offline")):
        try:
            result = evaluate(directory)
        except (InferenceError, ValueError, KeyError, OSError, sqlite3.Error) as exc:
            write_json(directory/"failure-private.json",dict(error=getattr(exc,"code",type(exc).__name__),message=str(exc)))
            result = dict(implementation_verdict="FAIL",scientific_conclusion="EVIDENCE_INSUFFICIENT",
                          production_approved=False,error=getattr(exc,"code",type(exc).__name__))
        if args.full_suite:
            result["full_suite"] = run_full_suite(directory)
            if result["full_suite"]["exit_code"]:
                result["implementation_verdict"] = "FAIL"
            protected_integrity()
    write_json(directory/"summary.json",result)
    print(dumps({k:result[k] for k in ("implementation_verdict","scientific_conclusion","production_approved")}))
    return {"PASS":0,"FAIL":1,"BLOCKED":2}[result["implementation_verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
