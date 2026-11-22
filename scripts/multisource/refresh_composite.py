"""Manual offline research refresh: prepare, review, publish, status, export."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

import numpy as np

from scripts.inference.common import InferenceError, sha256
from scripts.inference.model_artifact import load_trusted_pipeline
from scripts.prepare_training_features import FEATURES
from .acquire import LOCAL, acquire
from .composite_history import CompositeHistory, RESEARCH_ROOT, dumps, publish_version
from .composite_inference import CompositePredictor
from .fixture_catalogue import data_status, fixture_catalogue, refresh_metadata
from .match_registry import MatchRegistry, require, semantic_hash
from .refresh_validation import build_candidate, read_json
from .revision_review import receipt, validate_receipts


def safe_id(value):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value or "") is not None,
            "INVALID_VERSION", "Unsafe version or candidate ID")
    return value


def write_json(path, data):
    """Atomic private receipt/report replacement (history is never replaced)."""
    path = Path(path)
    temporary = path.with_name(path.name+".writing")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(dumps(data)+"\n")
    os.replace(temporary, path)


def summary(bundle, *, publish_status=None):
    changes = bundle["changes"]
    return dict(CURRENT_VERSION=bundle["parent_version"], CANDIDATE_VERSION=bundle["candidate_version"],
                CHANGES_FOUND=len(changes), AUTO_ACCEPTED=sum(c["decision"] == "AUTO_ACCEPT" for c in changes),
                MANUAL_REVIEW_REQUIRED=sum(c["decision"] == "MANUAL_REVIEW" for c in changes),
                PENDING_STATISTICS=sum(r["statistics_status"] == "PENDING_UPDATE" for r in bundle["registry"].values()),
                CONFLICTS=0, BLOCKED_ITEMS=0, PUBLISH_STATUS=publish_status or ("NO_CHANGE" if not changes else "PREPARED"),
                candidate_content_sha256=semantic_hash(bundle), effect_sha256=bundle["effect_sha256"],
                production_approved=False)


def prepare(parent, *, candidate_id, candidate_version, source_directory=LOCAL, workspace=LOCAL/"refresh/candidates",
            as_of=None, download=False, dataset_kind="real"):
    safe_id(candidate_id); safe_id(candidate_version)
    as_of = as_of or datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    work = Path(workspace) / candidate_id
    work.mkdir(parents=True, exist_ok=False)
    try:
        if download:
            require(dataset_kind == "real", "INVALID_SCOPE", "Downloads are for real public exports only")
            # Never let acquire reuse an existing directory, even if its manifest is absent.
            source_directory = work / "download"
            require(not source_directory.exists(), "VERSION_EXISTS", "Download destination exists")
            acquire(source_directory)
        bundle = build_candidate(parent, source_directory, candidate_version, as_of, dataset_kind=dataset_kind)
        write_json(work/"candidate.json", bundle)
        write_json(work/"reviews.json", {})
        report = summary(bundle)
    except (InferenceError, ValueError, KeyError, TypeError, OSError) as exc:
        report = dict(CURRENT_VERSION=parent.manifest["version_id"],CANDIDATE_VERSION=candidate_version,
                      CHANGES_FOUND=0,AUTO_ACCEPTED=0,MANUAL_REVIEW_REQUIRED=0,PENDING_STATISTICS=None,
                      CONFLICTS=int(getattr(exc,"code","") in {"SOURCE_CONFLICT","IDENTITY_CONFLICT"}),
                      BLOCKED_ITEMS=1,PUBLISH_STATUS="BLOCKED",error=getattr(exc,"code",type(exc).__name__),
                      message=str(exc),production_approved=False)
    write_json(work/"report.json", report)
    return report


def checked_bundle(work):
    work = Path(work)
    bundle = read_json(work/"candidate.json")
    parent_path = Path(bundle["parent_database"])
    parent = CompositeHistory(parent_path, research_root=parent_path.parent.parent)
    require(sha256(parent.path) == bundle["parent_sha256"], "STALE_CANDIDATE", "Parent changed since preparation")
    fresh = build_candidate(parent,bundle["source_directory"],bundle["candidate_version"],bundle["as_of"],
                            dataset_kind=bundle["dataset_kind"])
    require(fresh == bundle, "STALE_CANDIDATE", "Candidate or source changed; prepare and review again")
    return bundle, parent


def review(work, change_id, decision, reason, evidence_reference, *, reviewed_at=None):
    bundle, _ = checked_bundle(work)
    changes = [c for c in bundle["changes"] if c["change_id"] == change_id]
    require(len(changes) == 1, "INVALID_REVIEW", "Unknown change ID")
    item = receipt(bundle,changes[0],decision,reason,evidence_reference,
                   reviewed_at or datetime.now(timezone.utc).isoformat())
    lock_path = Path(work)/".review.lock"
    lock = os.open(lock_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        reviews = read_json(Path(work)/"reviews.json")
        require(change_id not in reviews, "REVIEW_EXISTS", "Review receipt is immutable; prepare a new candidate to revise it")
        reviews[change_id] = item
        write_json(Path(work)/"reviews.json", reviews)
    finally:
        os.close(lock); lock_path.unlink()
    return item


def validate_inference(parent, candidate, as_of):
    """Dynamic cohort: equal X implies parity; updated X may change predictions."""
    before, after = CompositePredictor(parent), CompositePredictor(candidate)
    require(tuple(FEATURES) == tuple(after.pipeline.feature_names_in_), "FEATURE_SCHEMA_CHANGED", "Frozen feature order changed")
    report = dict(targets=0,success=0,expected_blocked=0,unchanged_features=0,changed_features=0,
                  max_raw_parity_delta=0.0,max_clipped_parity_delta=0.0,production_approved=False)
    latest = max(r["season"] for r in candidate.query("SELECT season FROM registry"))
    allowed = {"REGISTRY_COVERAGE_UNVERIFIED", "MISSING_ROLLING_STATISTICS", "AMBIGUOUS_HISTORY"}
    for row in candidate.query("SELECT * FROM registry WHERE season=? AND match_date<=? ORDER BY match_date,canonical_fixture_key",(latest,as_of)):
        report["targets"] += 1
        args = row["home_team"],row["away_team"],row["match_date"],row["season"]
        old, new = before.predict(*args), after.predict(*args)
        if new["status"] != "success":
            code = new.get("error",{}).get("code")
            require(code in allowed, "INFERENCE_VALIDATION_FAILED", "Unexpected inference error", result=new)
            report["expected_blocked"] += 1
            continue
        report["success"] += 1
        if old["status"] != "success":
            report["changed_features"] += 1
            continue
        x = lambda r: np.array([[np.nan if f[k] is None else f[k] for k in FEATURES] for f in r["features"]], dtype=float)
        if np.array_equal(x(old),x(new),equal_nan=True):
            report["unchanged_features"] += 1
            raw_delta = float(np.max(np.abs(np.array(old["raw_predictions"])-new["raw_predictions"])))
            clipped_delta = max(abs(old[k]-new[k]) for k in ("home_xg","away_xg"))
            require(max(raw_delta,clipped_delta) <= 1e-12, "PARITY_FAILED", "Equal feature inputs changed frozen predictions")
            report["max_raw_parity_delta"] = max(report["max_raw_parity_delta"],raw_delta)
            report["max_clipped_parity_delta"] = max(report["max_clipped_parity_delta"],clipped_delta)
        else:
            report["changed_features"] += 1
    require(sha256(parent.path) == parent._sidecar["database_sha256"], "HISTORY_CORRUPT", "Parent was modified")
    return report


def publish(work, *, root=RESEARCH_ROOT, validator=validate_inference):
    work = Path(work)
    bundle, parent = checked_bundle(work)
    reviews = read_json(work/"reviews.json")
    validate_receipts(bundle, reviews)
    root = Path(root).resolve()
    require(root == parent.path.parent.parent, "INVALID_SCOPE", "Successor must use the parent's version namespace")
    load_trusted_pipeline()  # Artifact + imputer + dependency + metadata integrity, even for NO_CHANGE.
    if not bundle["changes"]:
        result = summary(bundle,publish_status="NO_CHANGE")
        write_json(work/"report.json", result)
        return result
    root.mkdir(parents=True,exist_ok=True)
    lock_path = root / ".refresh.lock"
    lock = os.open(lock_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        # Published manifests are the authoritative idempotency journal; no mutable pointer.
        for path in sorted(root.glob("*/manifest.json")):
            header = read_json(path)["core_manifest"]
            if header.get("refresh",{}).get("effect_sha256") == bundle["effect_sha256"]:
                existing = CompositeHistory(path.parent/"laliga_composite.sqlite3",research_root=root)
                result = summary(bundle,publish_status="ALREADY_PUBLISHED")
                result["published_version"] = existing.manifest["version_id"]
                write_json(work/"report.json", result)
                return result
        registry = MatchRegistry()
        registry.fixtures = bundle["registry"]; registry.evidence = bundle["evidence"]
        registry.statistics = bundle["statistics"]
        metadata = dict(candidate_content_sha256=semantic_hash(bundle),effect_sha256=bundle["effect_sha256"],
                        dataset_kind=bundle["dataset_kind"],schedule=bundle["schedule"],reviews=reviews,
                        changes=bundle["changes"],policy_version=bundle["policy_version"],as_of=bundle["as_of"],
                        parent_sha256=bundle["parent_sha256"],inherited_input_hashes=parent.manifest["input_hashes"],
                        frozen_archive_baseline_sha256=(refresh_metadata(parent) or {}).get("frozen_archive_baseline_sha256",
                            parent.manifest["input_hashes"].get("raw/archive_2025_fixtures.csv")))
        store = publish_version(registry,bundle["statistics"],{int(k):v for k,v in bundle["catalogues"].items()},
                                version_id=bundle["candidate_version"],input_hashes=bundle["source_hashes"],root=root,
                                parent=parent,identity_review=parent.manifest["identity_review"],refresh_metadata=metadata,
                                validator=lambda provisional:validator(parent,provisional,bundle["as_of"]))
        result = summary(bundle,publish_status="PUBLISHED")
        result.update(published_version=store.manifest["version_id"],database_sha256=sha256(store.path),
                      inference_validation=store.manifest["inference_validation"])
        write_json(work/"report.json", result)
        return result
    finally:
        os.close(lock); lock_path.unlink()


def status(work):
    work = Path(work)
    report = read_json(work/"report.json")
    if not (work/"candidate.json").is_file():
        return report
    try:
        bundle, _ = checked_bundle(work)
        try:
            validate_receipts(bundle,read_json(work/"reviews.json"))
            report["REVIEW_STATUS"] = "SATISFIED"
        except InferenceError as exc:
            report["REVIEW_STATUS"] = exc.code
        report["candidate_content_sha256"] = semantic_hash(bundle)
    except (InferenceError, ValueError, KeyError, TypeError, OSError) as exc:
        report.update(PUBLISH_STATUS="BLOCKED",BLOCKED_ITEMS=1,error=getattr(exc,"code",type(exc).__name__))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--parent",type=Path,required=True)
    prep.add_argument("--candidate-id",required=True)
    prep.add_argument("--version",required=True)
    prep.add_argument("--source-dir",type=Path,default=LOCAL)
    prep.add_argument("--workspace",type=Path,default=LOCAL/"refresh/candidates")
    prep.add_argument("--as-of")
    prep.add_argument("--download",action="store_true")
    rev = sub.add_parser("review")
    rev.add_argument("--candidate",type=Path,required=True)
    rev.add_argument("--change-id",required=True)
    rev.add_argument("--decision",choices=["APPROVE","REJECT"],required=True)
    rev.add_argument("--reason",required=True)
    rev.add_argument("--evidence-reference",required=True)
    for name in ("publish","status"):
        item = sub.add_parser(name); item.add_argument("--candidate",type=Path,required=True)
    export = sub.add_parser("export")
    export.add_argument("--database",type=Path,required=True)
    export.add_argument("--output",type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            parent = CompositeHistory(args.parent,research_root=args.parent.resolve().parent.parent)
            result = prepare(parent,candidate_id=args.candidate_id,candidate_version=args.version,source_directory=args.source_dir,
                             workspace=args.workspace,as_of=args.as_of,download=args.download)
        elif args.command == "review":
            result = review(args.candidate,args.change_id,args.decision,args.reason,args.evidence_reference)
        elif args.command == "publish":
            bundle = read_json(args.candidate/"candidate.json")
            result = publish(args.candidate,root=Path(bundle["parent_database"]).parent.parent)
        elif args.command == "status":
            result = status(args.candidate)
        else:
            store = CompositeHistory(args.database,research_root=args.database.resolve().parent.parent)
            args.output.mkdir(parents=True,exist_ok=False)
            write_json(args.output/"fixtures.json",dict(contract_version="1.0",fixtures=fixture_catalogue(store)))
            write_json(args.output/"data-status.json",data_status(store))
            result = dict(status="EXPORTED",production_approved=False)
        print(dumps(result))
        return int(result.get("PUBLISH_STATUS") == "BLOCKED")
    except (InferenceError, ValueError, KeyError, TypeError, OSError) as exc:
        result = dict(PUBLISH_STATUS="BLOCKED",BLOCKED_ITEMS=1,error=getattr(exc,"code",type(exc).__name__),message=str(exc))
        if getattr(args,"candidate",None) and args.candidate.is_dir():
            previous = read_json(args.candidate/"report.json")
            previous.update(result); write_json(args.candidate/"report.json",previous)
        print(dumps(result))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
