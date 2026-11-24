"""Read-only research contract; no HTTP server or production activation."""

from datetime import datetime, timezone
import json

from scripts.inference.common import sha256
from .acquire import LOCAL
from .match_registry import require, semantic_hash, timestamp

CONTRACT_VERSION = "1.0"
FIELDS = ("fixture_id", "canonical_fixture_key", "season", "home_team", "away_team",
          "match_date", "kickoff_utc", "observed_status", "match_status", "statistics_status",
          "source_provider", "source_version", "snapshot_version", "verified_at")


def refresh_metadata(store):
    rows = store.query("SELECT payload FROM metadata WHERE name='refresh'")
    if not rows:
        return None
    result = json.loads(rows[0]["payload"])
    require(semantic_hash(result) == store.manifest["refresh"]["metadata_sha256"],
            "HISTORY_CORRUPT", "Refresh metadata checksum mismatch")
    return result


def checked_kickoff(value, day):
    """Source contract uses UTC calendar dates, never infer a local timezone."""
    if value is None or value == "":
        return None
    timestamp(value)
    parsed = datetime.fromisoformat(value).astimezone(timezone.utc)
    require(parsed.date().isoformat() == day, "INVALID_KICKOFF", "UTC kickoff/date mismatch")
    return parsed.isoformat().replace("+00:00", "Z")


def fixture_catalogue(store, *, legacy_directory=LOCAL):
    store.verify_integrity()
    metadata = refresh_metadata(store)
    schedule = {} if metadata is None else metadata["schedule"]
    # Legacy V3 did not persist kickoff. Hydrate only its exact attested CSV.
    if metadata is None:
        import pandas as pd
        source = legacy_directory / "raw/current_2026_fixtures.csv"
        expected = store.manifest["input_hashes"].get("raw/current_2026_fixtures.csv")
        if source.is_file() and sha256(source) == expected:
            from .match_registry import canonical_key
            for row in pd.read_csv(source).to_dict("records"):
                key = canonical_key(2026, row["home"], row["away"])
                schedule[key] = dict(fixture_id=str(row["fixture_id"]),
                                     kickoff_utc=checked_kickoff(None if pd.isna(row["kickoff_utc"]) else row["kickoff_utc"], row["date"]))
    result = []
    for item in store.query("SELECT payload FROM registry ORDER BY season,match_date,canonical_fixture_key"):
        row = json.loads(item["payload"])
        extra = schedule.get(row["canonical_fixture_key"], {})
        # New rows keep CSV identity provenance separately. Export one coherent
        # verification tuple instead of mixing evidence URL/time with CSV hash.
        verification = "fixture_provenance" in row
        result.append(dict(fixture_id=extra.get("fixture_id", row.get("provider_fixture_id")),
                           canonical_fixture_key=row["canonical_fixture_key"], season=row["season"],
                           home_team=row["home_team"], away_team=row["away_team"], match_date=row["match_date"],
                           kickoff_utc=extra.get("kickoff_utc"), observed_status=row["observed_status"],
                           match_status=row["match_status"], statistics_status=row["statistics_status"],
                           source_provider=row["verification_source"] if verification else extra.get("source_provider", row["verification_source"]),
                           source_version=row["source_version"] if verification else extra.get("source_version", row["source_version"]),
                           snapshot_version=store.manifest["version_id"], verified_at=row["verified_at"]))
    return result


def data_status(store):
    digest = store.verify_integrity()
    m = store.manifest
    return dict(contract_version=CONTRACT_VERSION, snapshot_version=m["version_id"],
                parent_version=m["parent_version"], database_sha256=digest,
                build_timestamp=m["build_timestamp"],
                latest_verified_completed_date=max((r["match_date"] for r in store.query(
                    "SELECT match_date FROM registry WHERE match_status='VERIFIED_COMPLETED'")), default=None),
                registry_fixtures=m["registry_fixtures"], verified_completed=m["verified_completed"],
                complete_statistics=m["complete_statistics"], pending_statistics=m["pending_statistics"],
                conflicts=m["unresolved_conflicts"], unverified=m["unverified"],
                coverage=m["coverage"], input_hashes=m["input_hashes"],
                source_versions=m["source_dataset_versions"],research_validation_status=m["research_validation_status"],
                production_approved=False, mode="RESEARCH_INFERENCE",
                temporal_policy="date_only_strict_before_cutoff_not_as_of_vintage")
