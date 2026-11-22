"""Reproduce scenarios A–F offline with an isolated synthetic ledger."""

import argparse
import json
from pathlib import Path
import platform
import subprocess

from scripts.inference.common import MODEL_DIR, ROOT, sha256, versions
from .acquire import LOCAL
from .build_composite import evaluate
from .composite_history import CompositeHistory, RESEARCH_ROOT, dumps
from .fixture_catalogue import CONTRACT_VERSION, fixture_catalogue
from .forecast_eligibility import POLICY_VERSION
from .forecast_examples import FIRST, TARGET, UPDATE, synthetic_snapshot
from .forecast_service import ForecastService
from .match_registry import require
from .refresh_composite import prepare, publish
from .refresh_demo import complete, save_source
from .refresh_validation import read_json

DEMO_ROOT = LOCAL / "forecasts" / "demos"


def refreshed_example(directory, parent):
    """Use the approved Phase 8.5.4 workflow to verify one generated new result."""
    records = []
    for row in fixture_catalogue(parent):
        if row["season"] != 2026:
            continue
        entry = dict(fixture_id=int(row["fixture_id"]),date=row["match_date"],kickoff_utc=row["kickoff_utc"],
                     home=row["home_team"],away=row["away_team"],source="synthetic",status="unplayed")
        index = int(row["fixture_id"][-2:])
        if row["observed_status"] == "completed" or index == 7:
            complete(entry,value=0.7+index/10)
        records.append(entry)
    source = directory / "refresh-input"
    save_source(source,records)
    for filename, field in (("acquisition_manifest.json","retrieved_at"),("independent_completed.json","reviewed_at")):
        path = source / filename
        data = read_json(path)
        for item in data if isinstance(data,list) else [data]:
            item[field] = UPDATE
        path.write_text(dumps(data),encoding="utf-8")
    workspace = directory / "refresh-candidates"
    report = prepare(parent,candidate_id="new-result",candidate_version="updated",source_directory=source,
                     workspace=workspace,as_of=UPDATE[:10],dataset_kind="synthetic")
    require(report["AUTO_ACCEPTED"] == 1 and report["MANUAL_REVIEW_REQUIRED"] == 0,
            "DEMO_FAILED","Expected one newly verified synthetic match")
    return publish(workspace/"new-result",root=parent.path.parent.parent)


def historical_replay(output):
    """Phase 8.5.3 replay remains separate from the pre-match ledger."""
    path = RESEARCH_ROOT / "phase853_v3_20261122/laliga_composite.sqlite3"
    if not path.is_file() or not all((LOCAL / "processed" / name).is_file() for name in
            ("feature_inputs.csv","frozen_lr_predictions.csv","feature_exclusions.csv")):
        return dict(status="BLOCKED",reason="ORIGINAL_PRIVATE_INPUTS_REQUIRED")
    history = CompositeHistory(path)
    result = evaluate(history,LOCAL,output=output)
    return dict(status="PASS",mode="HISTORICAL_REPLAY",snapshot_version=history.manifest["version_id"],
                database_sha256=sha256(history.path),targets=result["targets"],predictions=result["predictions"],
                parity=result["parity_passed"],max_feature_delta=result["max_feature_delta"],
                max_raw_prediction_delta=result["max_prediction_delta"],production_approved=False)


def run_demos(directory, *, replay=True):
    directory = Path(directory).resolve()
    require(directory.is_relative_to(DEMO_ROOT.resolve()),"INVALID_SCOPE","Keep demos in their ignored workspace")
    directory.mkdir(parents=True,exist_ok=False)
    root = directory / "history"
    clock = [FIRST]
    service = ForecastService(synthetic_history=root,synthetic_ledger_base=directory/"ledger",
                              simulated_clock=lambda:clock[0])
    parent = synthetic_snapshot(root,"initial")
    before = sha256(parent.path)
    a = service.generate_forecast(TARGET,"initial")
    require(a["status"] == "PUBLISHED" and a["forecast"]["eligibility_status"] == "EARLY_READY"
            and a["forecast"]["forecast_stage"] == "INITIAL","DEMO_FAILED","Demo A did not publish an early initial forecast")
    update = refreshed_example(directory,parent)
    clock[0] = UPDATE
    b = service.generate_forecast(TARGET,"updated")
    require(b["status"] == "PUBLISHED" and b["forecast"]["forecast_stage"] == "UPDATED",
            "DEMO_FAILED","Demo B did not publish an updated forecast")
    updated = service.eligibility.open("updated")
    clone = synthetic_snapshot(root,"same-features",completed=[*range(6),7],now=UPDATE,parent=updated)
    c = service.generate_forecast(TARGET,"same-features")
    require(c["status"] == "NO_CHANGE" and c["forecast_id"] == b["forecast_id"],
            "DEMO_FAILED","Demo C published a duplicate")
    synthetic_snapshot(root,"incomplete",completed=[*range(6),7],pending={(2026,7)},now=UPDATE)
    d = service.generate_forecast(TARGET,"incomplete")
    e = service.generate_forecast("unknown","initial")
    require(d["status"] == "WAITING_DATA" and d["eligibility"]["reason"] == "MISSING_ROLLING_STATISTICS"
            and e["status"] == "UNAVAILABLE","DEMO_FAILED","Blocked targets must not produce forecasts")
    comparison = service.compare_forecasts(TARGET,a["forecast_id"],b["forecast_id"])
    require(sha256(parent.path) == before and len(service.list_fixture_forecasts(TARGET)) == 2,
            "DEMO_FAILED","Parent changed or unexpected revision count")

    def describe(result):
        return {name:result["forecast"][name] for name in ("forecast_revision","forecast_stage","eligibility_status",
                 "generated_at_utc","history_snapshot_version","history_database_sha256")}

    manifest = dict(dataset_kind="synthetic",demo_label="SYNTHETIC_DEMO",production_approved=False,
                    code_revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                    eligibility_policy_version=POLICY_VERSION,fixture_catalogue_version=CONTRACT_VERSION,
                    model_artifact_sha256=sha256(MODEL_DIR/"laliga_lr_pipeline.joblib"),
                    environment=dict(platform=platform.system(),**versions()),
                    scenarios=dict(A=describe(a),B=dict(describe(b),history_publication=update["PUBLISH_STATUS"]),
                                   C=dict(status=c["status"],snapshot_version="same-features",database_sha256=sha256(clone.path)),
                                   D=dict(status=d["status"],reason=d["eligibility"]["reason"]),E=dict(status=e["status"]),
                                   F=historical_replay(directory/"historical-replay") if replay else {"status":"NOT_RUN"}),
                    revision_count=2,changed_feature_count=len(comparison["changed_features"]),parent_unchanged=True,
                    limitations=["Simulated clock for scenarios A–E","F is a historical replay, separate from current forecasts",
                                 "Date-only cutoff and mixed-provider research source semantics"])
    (directory/"demo-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name",required=True)
    args = parser.parse_args()
    from .forecast_eligibility import snapshot_id
    print(dumps(run_demos(DEMO_ROOT/snapshot_id(args.name))))
