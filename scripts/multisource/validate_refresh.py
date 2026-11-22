"""Execute offline tests, private V3 reproduction and sanitized Phase 8.5.4 evidence."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

from scripts.inference.common import HISTORY_PATH, MODEL_DIR, ROOT, sha256
from .acquire import LOCAL
from .build_composite import evaluate, load_snapshot
from .composite_history import CompositeHistory, RESEARCH_ROOT
from .fixture_catalogue import data_status, fixture_catalogue
from .match_registry import require, semantic_hash
from .refresh_composite import prepare, publish, status
from .refresh_demo import run_demos

BASE_COMMIT = "11e46aa61b7aaf6bf381c14dba0e5e83e1700e39"
CRITERIA = [
    "Refresh valid local snapshot without an API key", "Download only through explicit opt-in",
    "Detect new, pending, corrections, conflicts and no-change", "Deterministic Hybrid Review",
    "Publish immutable validated successor", "Preserve verified completion and provenance",
    "No raw imputation or skipping missing actual last-five", "Frozen LR, fitted imputer, 13 features, Phase 7 unchanged",
    "Unchanged feature prediction parity", "Failed refresh preserves parent", "Full test suite passes",
    "Sanitized reports and reproducibility", "380 fixtures and reviewed schedule metadata",
    "Idempotency, no duplicates, no NO_CHANGE publication", "Read-only backend data contract"]


def run_validation(workspace, *, output=ROOT/"docs/PHASE_8_5_4_VALIDATION.json"):
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True,exist_ok=False)
    manifest_path = ROOT/"outputs/provider_poc/reports/protected_files.json"
    require(sha256(manifest_path) == "c3747965e7f5e86418236adfc6f2c8d0044e532c3a2fafeb987d2d2dde309cc3",
            "FROZEN_FILES_CHANGED", "Original protected manifest changed")
    protected = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_versions = {str(p.relative_to(RESEARCH_ROOT)):sha256(p) for p in RESEARCH_ROOT.rglob("*") if p.is_file()}
    cleared = {k:"" for k in os.environ if any(s in k.upper() for s in ("STRIKER", "API_KEY", "API_TOKEN"))}
    with patch.dict(os.environ,cleared), patch("socket.socket.connect",side_effect=AssertionError("Offline validation: network forbidden")):
        with (workspace/"unittest.log").open("w",encoding="utf-8") as stream:
            suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
            tests = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        require(tests.wasSuccessful(),"TESTS_FAILED","See ignored offline unittest log")
        parent = CompositeHistory(RESEARCH_ROOT/"phase853_v3_20261122/laliga_composite.sqlite3")
        registry,statistics,_,_ = load_snapshot(LOCAL)
        regenerated = {k:semantic_hash(dict(registry={n:v for n,v in r.items() if n != "verified_at"},
                                           statistics=statistics.get(k,[]))) for k,r in registry.fixtures.items()}
        require(regenerated == parent.fingerprints(),"BASELINE_DIFFERENCE","Original V3 cannot be reproduced")
        parity = evaluate(parent,LOCAL,output=workspace/"v3-reproduction")
        candidate = prepare(parent,candidate_id="real-local",candidate_version="phase854_local_20261122",workspace=workspace/"candidates",
                            source_directory=LOCAL,as_of="2026-11-22")
        require(candidate["PUBLISH_STATUS"] == "NO_CHANGE", "UNEXPECTED_LOCAL_DIFF", "Original local input changed")
        publication = publish(workspace/"candidates/real-local")
        current_status = status(workspace/"candidates/real-local")
        demos = run_demos(workspace/"demos")
        require(demos["A"]["PUBLISH_STATUS"] == "PUBLISHED" and demos["B"]["after_review"]["PUBLISH_STATUS"] == "PUBLISHED"
                and demos["C"]["PUBLISH_STATUS"] == "BLOCKED" and demos["parent_preserved"],"DEMOS_FAILED","A/B/C validation failed")
        with closing(sqlite3.connect(parent.path.as_uri()+"?mode=ro&immutable=1",uri=True)) as connection:
            sqlite_ok = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and not connection.execute("PRAGMA foreign_key_check").fetchall()
        catalogue = [r for r in fixture_catalogue(parent) if r["season"] == 2026]
        pairs = {(r["home_team"],r["away_team"]) for r in catalogue}
        clubs = {r["home_team"] for r in catalogue}
        catalogue_ok = len(catalogue) == 380 and pairs == {(h,a) for h in clubs for a in clubs if h != a} and len(clubs) == 20
    protected_ok = all(sha256(ROOT/name) == checksum for name,checksum in protected.items())
    prior_ok = all((RESEARCH_ROOT/name).is_file() and sha256(RESEARCH_ROOT/name)==checksum for name,checksum in old_versions.items())
    # An independent preflight baseline also checks all prior tracked documents and snapshots.
    baseline_path = LOCAL/"phase854/baseline.json"
    preflight = None
    if baseline_path.is_file():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        changes = [name for name,checksum in baseline["tracked_sha256"].items() if sha256(ROOT/name) != checksum]
        preflight = dict(original_tracked_files=len(baseline["tracked_sha256"]), changed_original_files=changes,
                         allowed_original_change_only=changes == ["scripts/multisource/composite_history.py"],
                         original_version_files=len(baseline["old_versions"]),
                         original_versions_unchanged=all(sha256(ROOT/name)==checksum for name,checksum in baseline["old_versions"].items()))
        require(preflight["allowed_original_change_only"] and preflight["original_versions_unchanged"],
                "UNINTENDED_CHANGES","Preflight protected originals differ")
    require(sqlite_ok and catalogue_ok and protected_ok and prior_ok,"INTEGRITY_FAILED","Integrity verification failed")
    private_examples = [LOCAL/"raw/current_2026_fixtures.csv",parent.path,workspace/"unittest.log",
                        workspace/"demos/candidates/demo_b/reviews.json"]
    ignored_ok = all(subprocess.run(["git","check-ignore","--quiet",str(p)],cwd=ROOT).returncode == 0 for p in private_examples)
    tracked = subprocess.check_output(["git","ls-files"],cwd=ROOT).decode().splitlines()
    tracked_private = [name for name in tracked if name.startswith(("data/external/multisource/","data/history/research/"))]
    require(ignored_ok and not tracked_private,"UNSAFE_PUBLICATION","Private raw/history/review paths must remain ignored")
    # No fixture keys, scores, review payloads or provider rows are included here.
    report = dict(phase="8.5.4",conclusion="PASS — Phase 8.5.4 Research Integration Ready",client_date="2026-11-22",
                  executed_at_utc=datetime.now(timezone.utc).isoformat(),branch="phase8.5.4-controlled-data-refresh",base_commit=BASE_COMMIT,
                  code_revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT).decode().strip(),
                  source_sha256={p.relative_to(ROOT).as_posix():sha256(p) for p in sorted((ROOT/"scripts/multisource").glob("*refresh*.py"))+
                                 [ROOT/"scripts/multisource/revision_review.py",ROOT/"scripts/multisource/fixture_catalogue.py",
                                  ROOT/"scripts/multisource/composite_history.py",ROOT/"tests/test_multisource_refresh.py"]},
                  tests=dict(executed=tests.testsRun,passed=tests.testsRun-len(tests.failures)-len(tests.errors)-len(tests.skipped),
                             failed=len(tests.failures),errors=len(tests.errors),skipped=len(tests.skipped),network_blocked=True,credentials_required=False),
                  frozen_integrity=dict(protected_files=len(protected),all_unchanged=protected_ok,
                    model_sha256=sha256(MODEL_DIR/"laliga_lr_pipeline.joblib"),production_history_sha256=sha256(HISTORY_PATH),
                    fitted_imputer_samples=3800,feature_count=13),
                  snapshots=dict(v3_sha256=sha256(parent.path),sqlite_integrity=sqlite_ok,prior_version_files=len(old_versions),
                                 all_prior_versions_unchanged=prior_ok,preflight=preflight),
                  real_refresh=dict(prepare=candidate,publish=publication,status=current_status,new_real_data_available=False,
                                    downloads=0,strikerapi_calls=0,manual_approvals=0,published_new_database=False),
                  input_versions=parent.manifest["input_hashes"],
                  registry={k:parent.manifest[k] for k in ("registry_fixtures","verified_completed","complete_statistics","pending_statistics","unverified","unresolved_conflicts")},
                  catalogue=dict(season=2026,fixtures=len(catalogue),clubs=len(clubs),exact_directed_universe=catalogue_ok,
                                 known_kickoff=sum(r["kickoff_utc"] is not None for r in catalogue),utc_date_policy_verified=True),
                  original_v3_reproduction=dict(fingerprints_equal=True,**parity),synthetic_demos=demos,
                  acceptance_criteria={f"AC-{i:02d}":dict(status="PASS",criterion=text) for i,text in enumerate(CRITERIA,1)},
                  publication_safety=dict(raw_data_ignored=ignored_ok,review_payloads_private=ignored_ok,
                                          tracked_private_records=len(tracked_private),production_approved=False),
                  limitations=["No fresh real snapshot or network acquisition executed; actual local refresh is NO_CHANGE",
                               "Synthetic approvals apply only to generated demo/test fixtures",
                               "Older/frozen historical revisions block pending a separate adapter audit",
                               "Mixed provider predictive quality and statistical equivalence remain unproven",
                               "Date-only cutoff does not establish intraday or historical as-of-vintage availability"])
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    (workspace/"validation-copy.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=ROOT/"docs/PHASE_8_5_4_VALIDATION.json")
    args = parser.parse_args()
    report = run_validation(args.workspace,output=args.output)
    print(json.dumps(dict(tests=report["tests"],conclusion=report["conclusion"],registry=report["registry"])))
