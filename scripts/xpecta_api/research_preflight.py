"""Inspect the real research binding and optionally prepare a private refresh candidate."""

import argparse
from collections import Counter
import json
from pathlib import Path

from scripts.inference.common import InferenceError
from scripts.multisource.acquire import LOCAL
from scripts.multisource.forecast_eligibility import FIXTURE_MAX_AGE, READY, utc, utc_text
from scripts.multisource.forecast_generation import generate_forecast
from scripts.multisource.match_registry import require
from scripts.multisource.refresh_composite import prepare
from scripts.multisource.refresh_validation import CURRENT, manifest
from scripts.prepare_training_features import FEATURES

from .services import ResearchService
from .settings import Mode, Settings


def catalogue_preflight(service, now):
    status = service.data_status(now=now)
    engine = service.forecast.eligibility
    rows = list(service.fixtures.values())
    upcoming = [row for row in rows if service._upcoming(row, now)]
    outcomes = [engine._evaluate(row["canonical_fixture_key"], service.store, rows, now) for row in upcoming]
    eligible = [
        dict(fixture_key=row["canonical_fixture_key"], kickoff_utc=row["target"]["kickoff_utc"],
             status=row["eligibility_status"], evidence_expires_at_utc=utc_text(
                 utc(row["fixture_reviewed_at_utc"]) + FIXTURE_MAX_AGE))
        for row in outcomes if row["eligibility_status"] in READY
    ]
    eligible.sort(key=lambda row: (utc(row["kickoff_utc"]), row["fixture_key"]))
    return dict(status, source_inputs=dict(
        schedule=dict(file=CURRENT, snapshot_sha256=service.store.manifest["input_hashes"].get("raw/" + CURRENT),
                      refresh_needed=status["schedule_freshness"] in {"PARTIAL", "UNVERIFIED"},
                      action="Get a newer public export and independently verify new completions."),
        history=dict(pending_statistics=status["pending_statistics"],
                     action="Review verified fixtures with missing rolling statistics and mixed-provider coverage.")),
        eligible_fixtures=eligible,
        eligibility_counts=dict(sorted(Counter(row["eligibility_status"] for row in outcomes).items())),
        blocking_reasons=dict(sorted(Counter(row["reason"] for row in outcomes if row["reason"]).items())),
        fixture_identity=dict(unverified=status["unverified"], conflicts=status["conflicts"]),
        snapshot_manifest_sha256=service.pins[1])


def source_readiness(directory, snapshot_manifest, schedule_evidence, now):
    entries, _ = manifest(directory)
    entry = entries[CURRENT]
    acquired = utc(entry["retrieved_at"])
    baseline = snapshot_manifest["input_hashes"].get("raw/" + CURRENT)
    earlier = max((utc(item["acquired_at_utc"]) for item in schedule_evidence), default=None)
    if entry["sha256"] == baseline:
        state = "SAME_SOURCE_BYTES"
    elif (earlier is not None and acquired <= earlier) or not now - FIXTURE_MAX_AGE <= acquired <= now:
        state = "SOURCE_ACQUISITION_NOT_CURRENT"
    else:
        state = "NEWER_BYTES_REVIEW_REQUIRED"
    return dict(status=state, acquired_at_utc=utc_text(acquired), expires_at_utc=utc_text(acquired + FIXTURE_MAX_AGE),
                source_url=entry["url"], sha256=entry["sha256"], http_last_modified=entry.get("last_modified"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--prepare", metavar="VERSION", help="Prepare only in a new ignored directory")
    parser.add_argument("--fixture", metavar="FIXTURE_KEY", help="Print private read-only forecast evidence")
    args = parser.parse_args(argv)
    if args.prepare and args.source_dir is None:
        parser.error("--prepare requires --source-dir")
    try:
        settings = Settings.from_env()
        require(settings.mode == Mode.REAL_RESEARCH, "INVALID_SCOPE", "Real research preflight only")
        service = ResearchService(settings)
        now = service.forecast.eligibility.now()
        report = catalogue_preflight(service, now)
        if args.fixture:
            service._require_fixture(args.fixture)
            report["read_only_fixture_probe"] = generate_forecast(
                args.fixture, service.version, eligibility=service.forecast.eligibility)
            report["ordered_features"] = FEATURES
        if args.source_dir:
            source = source_readiness(args.source_dir, service.store.manifest, report["schedule_evidence"], now)
            report["staged_source"] = source
            if args.prepare:
                if source["status"] == "NEWER_BYTES_REVIEW_REQUIRED":
                    report["candidate"] = prepare(service.store, candidate_id=args.prepare, candidate_version=args.prepare,
                                                  source_directory=args.source_dir, workspace=LOCAL / "phase96/candidates",
                                                  as_of=now.date().isoformat())
                else:
                    report["candidate"] = dict(PUBLISH_STATUS="BLOCKED", error=source["status"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return int(report.get("candidate", {}).get("PUBLISH_STATUS") == "BLOCKED")
    except (InferenceError, OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps(dict(status="BLOCKED", reason=getattr(exc, "code", type(exc).__name__))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
