"""Research forecast eligibility over the existing date-only Composite History."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from scripts.inference.common import InferenceError, sha256
from scripts.inference.predict_fixture import MAX_TEAM_HISTORY_AGE_DAYS
from .acquire import LOCAL
from .composite_features import build_composite_features
from .composite_history import CompositeHistory, RESEARCH_ROOT
from .fixture_catalogue import checked_kickoff, fixture_catalogue
from .match_registry import SOURCE_CONFLICT, VERIFIED_COMPLETED, canonical_key, require

POLICY_VERSION = "1.0"
FIXTURE_MAX_AGE = timedelta(hours=48)
READY = {"READY", "EARLY_READY"}
MODE = "RESEARCH_INFERENCE"


def utc(value):
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.utcoffset() is None:
        raise ValueError("A timezone-aware timestamp is required")
    return parsed.astimezone(timezone.utc)


def utc_text(value):
    return utc(value).isoformat().replace("+00:00", "Z")


def snapshot_id(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value),
            "INVALID_SNAPSHOT", "Use a snapshot version identifier")
    return value


class ForecastEligibility:
    """Construct in trusted application code. Requests select a version, never a path."""

    def __init__(self, *, synthetic_root=None, simulated_clock=None):
        self.dataset_kind = "real" if synthetic_root is None else "synthetic"
        self.root = RESEARCH_ROOT.resolve() if synthetic_root is None else Path(synthetic_root).resolve()
        require((synthetic_root is None) == (simulated_clock is None),
                "INVALID_SCOPE", "Only isolated synthetic forecasts support a simulated clock")
        if synthetic_root is not None:
            require(not self.root.is_relative_to(RESEARCH_ROOT.resolve())
                    and not RESEARCH_ROOT.resolve().is_relative_to(self.root),
                    "INVALID_SCOPE", "Synthetic history must be separate from real history")
        self._clock = simulated_clock

    def now(self):
        return utc(self._clock()) if self._clock is not None else datetime.now(timezone.utc)

    def open(self, version):
        directory = self.root / snapshot_id(version)
        path = directory / "laliga_composite.sqlite3"
        require(directory.resolve() == directory and path.resolve() == path,
                "INVALID_SNAPSHOT", "Snapshot must be a direct, immutable version")
        store = CompositeHistory(path, research_root=self.root)
        manifest = store.manifest
        kind = manifest.get("refresh", {}).get("dataset_kind",
                   manifest["identity_review"].get("dataset_kind", "real"))
        require(manifest["version_id"] == version and kind == self.dataset_kind,
                "INVALID_SCOPE", "Snapshot identity or dataset kind does not match")
        return store

    def _schedule_evidence(self, store, selected, catalogue):
        key = selected["canonical_fixture_key"]
        payload = json.loads(store.query("SELECT payload FROM registry WHERE canonical_fixture_key=?", (key,))[0]["payload"])
        schedule_review = payload.get("schedule_review")
        if schedule_review:
            if selected["kickoff_utc"] == schedule_review["kickoff_utc"]:
                return utc(schedule_review["reviewed_at"])
            return None
        csv_evidence = payload.get("fixture_provenance")
        if csv_evidence:
            return utc(csv_evidence["fetched_at"])
        if self.dataset_kind == "synthetic":
            return utc(selected["verified_at"])
        # For legacy rows use the attested acquisition, not the date someone rebuilt SQLite.
        name = "current_2026_fixtures.csv"
        manifest = LOCAL / "acquisition_manifest.json"
        csv = LOCAL / "raw" / name
        hashes = store.manifest["input_hashes"]
        version = hashes.get("raw/" + name)
        if (selected["season"] != 2026 or not manifest.is_file() or not csv.is_file()
                or sha256(manifest) != hashes.get("acquisition_manifest.json")
                or sha256(csv) != version or selected["source_version"] != version
                or catalogue["source_version"] != version):
            return None
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        found = [row for row in entries if row["file"] == name and row["sha256"] == version
                 and row["status"] == 200 and row["url"] == selected["source_provider"]]
        return utc(found[0]["retrieved_at"]) if len(found) == 1 else None

    def _evaluate(self, key, store, rows, now):
        matches = [row for row in rows if row["canonical_fixture_key"] == key]
        as_of = now.date().isoformat()
        result = dict(canonical_fixture_key=key, snapshot_version=store.manifest["version_id"],
                      generated_at_utc=utc_text(now), forecast_as_of_date=as_of,
                      dataset_kind=self.dataset_kind, eligibility_policy_version=POLICY_VERSION,
                      inference_mode=MODE, production_approved=False)
        if self.dataset_kind == "synthetic":
            result["demo_label"] = "SYNTHETIC_DEMO"

        def outcome(status, reason):
            return dict(result, eligibility_status=status, reason=reason)

        if len(matches) != 1:
            return outcome("UNAVAILABLE", "INVALID_FIXTURE")
        target = matches[0]
        day = target["match_date"]
        cutoff = min(as_of, day)
        result.update(target=target, history_cutoff=cutoff)
        if (canonical_key(target["season"], target["home_team"], target["away_team"]) != key
                or target["match_status"] in {VERIFIED_COMPLETED, SOURCE_CONFLICT}
                or target["statistics_status"] == SOURCE_CONFLICT
                or target["observed_status"] != "scheduled" or day < as_of):
            return outcome("UNAVAILABLE", "TARGET_NOT_UPCOMING")
        try:
            kickoff_text = checked_kickoff(target["kickoff_utc"], day)
            if not kickoff_text:
                return outcome("WAITING_DATA", "KICKOFF_UNVERIFIED")
            target["kickoff_utc"] = kickoff_text
            kickoff = utc(kickoff_text)
            if kickoff <= now:
                return outcome("UNAVAILABLE", "TARGET_ALREADY_STARTED")
            if self.dataset_kind == "real" and utc(store.manifest["build_timestamp"]) > now:
                return outcome("WAITING_DATA", "SNAPSHOT_NOT_YET_AVAILABLE")
            catalogues = store.query("SELECT payload FROM catalogues WHERE season=?", (target["season"],))
            if not catalogues:
                return outcome("WAITING_DATA", "REGISTRY_COVERAGE_UNVERIFIED")
            catalogue = json.loads(catalogues[0]["payload"])
            teams = {target["home_team"], target["away_team"]}
            if not teams <= set(catalogue["clubs"]):
                return outcome("UNAVAILABLE", "FIXTURE_OUTSIDE_ROSTER")
            reviewed = self._schedule_evidence(store, target, catalogue)
            if reviewed is None or not timedelta(0) <= now - reviewed <= FIXTURE_MAX_AGE:
                return outcome("WAITING_DATA", "FIXTURE_FRESHNESS_UNVERIFIED")
            args = target["home_team"], target["away_team"], day, target["season"]
            built = build_composite_features(*args, store, prediction_cutoff=cutoff)
            for summary in built.history.values():
                last = summary["last_date"]
                if last and (now.date() - datetime.fromisoformat(last).date()).days > MAX_TEAM_HISTORY_AGE_DAYS:
                    return outcome("WAITING_DATA", "HISTORY_STALE")
            eligible_keys = {key for summary in built.history.values() for key in summary["eligible_match_keys"]}
            for row in rows:
                if row["canonical_fixture_key"] in eligible_keys and utc(row["verified_at"]) > now:
                    return outcome("WAITING_DATA", "HISTORY_EVIDENCE_NOT_AVAILABLE")
            for item in built.provenance:
                # Frozen Phase 7 has an attested local snapshot and an unknown original fetch time.
                fetched = item["fetched_at"]
                if (fetched == "original_fetch_unknown_local_frozen_snapshot"
                        and item["fixture_source"] == "FBref_frozen_snapshot"):
                    continue
                if utc(fetched) > now:
                    return outcome("WAITING_DATA", "HISTORY_EVIDENCE_NOT_AVAILABLE")
            intermediate = []
            for row in rows:
                if (row["season"] != target["season"] or row["canonical_fixture_key"] == key
                        or not teams.intersection((row["home_team"], row["away_team"]))
                        or not as_of <= row["match_date"] <= day
                        or row["observed_status"] == "cancelled"):
                    continue
                when = checked_kickoff(row["kickoff_utc"], row["match_date"])
                if row["match_date"] == day and when and utc(when) >= kickoff:
                    continue
                if row["match_date"] in {as_of, day} and not when:
                    return outcome("WAITING_DATA", "INTERMEDIATE_ORDER_UNVERIFIED")
                if row["match_status"] == SOURCE_CONFLICT or row["observed_status"] == "unverified":
                    return outcome("WAITING_DATA", "INTERMEDIATE_STATUS_UNVERIFIED")
                intermediate.append(row["canonical_fixture_key"])
        except InferenceError as exc:
            return outcome("WAITING_DATA", exc.code)
        except (ValueError, KeyError, TypeError):
            return outcome("WAITING_DATA", "INVALID_SCHEDULE_OR_EVIDENCE")
        result.update(intermediate_fixtures=intermediate, fixture_reviewed_at_utc=utc_text(reviewed))
        return outcome("EARLY_READY" if intermediate else "READY", None)

    def evaluate_forecast_eligibility(self, canonical_fixture_key, snapshot_version):
        store = self.open(snapshot_version)
        return self._evaluate(canonical_fixture_key, store, fixture_catalogue(store), self.now())

    def list_eligible_fixtures(self, snapshot_version, *, season=None, include_unavailable=False):
        store = self.open(snapshot_version)
        rows = fixture_catalogue(store)
        now = self.now()
        evaluated = [self._evaluate(row["canonical_fixture_key"],store,rows,now) for row in rows
                     if season is None or row["season"] == season]
        return evaluated if include_unavailable else [r for r in evaluated if r["eligibility_status"] in READY]
