"""Offline snapshot validation and business diffs, independent of baseline counts."""

import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from scripts.inference.common import InferenceError, sha256
from .acquire import LOCAL
from .composite_history import RESEARCH_ROOT
from .fixture_catalogue import checked_kickoff, fixture_catalogue, refresh_metadata
from .mapping import fixture_identity, number, understat_shots
from .match_registry import (COMPLETE_STATISTICS, GROUPS, MatchRegistry, VERIFIED_COMPLETED,
                             canonical_key, require, semantic_hash, timestamp, validate_catalogue)
from .revision_review import POLICY_VERSION, classify
from .team_registry import resolve

CURRENT = "current_2026_fixtures.csv"
STATUS = {"full_time":"completed", "unplayed":"scheduled", "live":"live",
          "postponed":"postponed", "cancelled":"cancelled"}
NUMERIC = ("gf", "ga", "xg", "xga", "sh", "sot")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def state(store):
    registry = MatchRegistry()
    registry.fixtures = {r["canonical_fixture_key"]:json.loads(r["payload"]) for r in store.query("SELECT * FROM registry")}
    registry.evidence = [json.loads(r["payload"]) for r in store.query("SELECT payload FROM evidence")]
    registry.conflicts = [json.loads(r["payload"]) for r in store.query("SELECT payload FROM conflicts")]
    statistics = {}
    for r in store.query("SELECT * FROM statistics ORDER BY canonical_fixture_key,team"):
        statistics.setdefault(r["canonical_fixture_key"], []).append(json.loads(r["payload"]))
    registry.statistics = statistics
    catalogues = {r["season"]:json.loads(r["payload"]) for r in store.query("SELECT * FROM catalogues")}
    schedule = {r["canonical_fixture_key"]:{k:r[k] for k in ("fixture_id", "kickoff_utc", "source_provider", "source_version")}
                for r in fixture_catalogue(store)}
    return registry, statistics, catalogues, schedule


def business(fixture, pair, schedule):
    return dict(fixture_id=schedule.get("fixture_id"), match_date=fixture["match_date"],
                kickoff_utc=schedule.get("kickoff_utc"), observed_status=fixture["observed_status"],
                match_status=fixture["match_status"], statistics_status=fixture["statistics_status"],
                score=[fixture["home_goals"], fixture["away_goals"]],
                statistics=[{k:r[k] for k in ("team", *NUMERIC)} for r in sorted(pair, key=lambda r:r["team"])],
                # Version hashes, retrieval times and completion URL updates are metadata.
                # Semantic families are selected by the explicit source adapters below.
                semantics=schedule.get("source_provider"))


def manifest(directory, *, synthetic=False):
    path = directory / "acquisition_manifest.json"
    entries = read_json(path)
    require(isinstance(entries, list) and bool(entries), "INVALID_MANIFEST", "Acquisition manifest must be a nonempty list")
    found = {}; hashes = {"acquisition_manifest.json":sha256(path)}
    for item in entries:
        name = item["file"]
        require(isinstance(name, str) and Path(name).name == name and name not in found,
                "INVALID_MANIFEST", "Unsafe or duplicate manifest filename")
        require(item["status"] == 200, "INVALID_MANIFEST", "Failed acquisition cannot be published")
        timestamp(item["retrieved_at"])
        url = urlparse(item["url"])
        accepted_names = {CURRENT, "archive_2025_shots.csv", *(f"archive_{s}_fixtures.csv" for s in range(2019,2026)),
                          "archive.html","current.html","sources.html","directory.html"}
        require(name in ({"synthetic_snapshot.json"} if synthetic else accepted_names), "INVALID_MANIFEST", "Unreviewed source file")
        require((synthetic and url.scheme == "synthetic") or
                (not synthetic and url.scheme == "https" and url.hostname == "www.xgtables.io"
                 and url.username is None and not url.query and not url.fragment),
                "SOURCE_CONFLICT", "Source outside reviewed provider scope")
        if not synthetic and name.startswith("archive_"):
            pieces = name.removesuffix(".csv").split("_")
            require(url.path == f"/history/la-liga/{pieces[1]}/{pieces[2]}.csv", "SOURCE_CONFLICT", "Archive source URL mismatch")
        source = directory / "raw" / name
        require(source.is_file(), "MISSING_INPUT_FILES", "Manifest source file missing", file=name)
        require(sha256(source) == item["sha256"] and source.stat().st_size == item["bytes"],
                "SOURCE_VERSION_MISMATCH", "Source does not match its own acquisition manifest", file=name)
        found[name] = item
        hashes["raw/"+name] = sha256(source)
    return found, hashes


def completion_evidence(directory, *, synthetic=False):
    path = directory / "independent_completed.json"
    if not path.is_file():
        return {}, None
    evidence = read_json(path)
    timestamp(evidence["reviewed_at"])
    url = urlparse(evidence["source_url"])
    require((synthetic and url.scheme == "synthetic") or
            (not synthetic and url.scheme == "https" and url.hostname in {"www.laliga.com", "laliga.com"}
             and url.username is None and not url.query),
            "SOURCE_CONFLICT", "Independent completion must use reviewed official league evidence")
    matches = {}
    for row in evidence["matches"]:
        key = canonical_key(row["season"], row["home"], row["away"])
        require(key not in matches, "DUPLICATE_FIXTURE", "Duplicate independent evidence")
        for field in ("home_gf", "away_gf"):
            number(row[field], field, integer=True)
        matches[key] = dict(row, source=evidence["source_url"], verified_at=evidence["reviewed_at"], version=sha256(path))
    return matches, sha256(path)


def numeric_pair(fixture, raw, metadata, *, fields=None):
    fields = fields or {"xg":"xg", "sh":"shots", "sot":"shots_on_target"}
    rows = []
    for team, opponent, side, other, home in [(fixture["home_team"],fixture["away_team"],"home","away",1),
                                             (fixture["away_team"],fixture["home_team"],"away","home",0)]:
        row = dict(canonical_key=fixture["canonical_fixture_key"], season=fixture["season"], date=fixture["match_date"],
                   team=team, opponent=opponent, is_home=home, gf=fixture[side+"_goals"], ga=fixture[other+"_goals"], **metadata)
        for field in ("xg", "sh", "sot"):
            value = raw.get(side+"_"+fields[field])
            row[field] = None if value is None else number(value, field, integer=field != "xg")
        value = raw.get(other+"_"+fields["xg"])
        row["xga"] = None if value is None else number(value, "xga")
        rows.append(row)
    return rows


def current_updates(directory, entries, parent_registry, schedule, evidence, *, synthetic=False):
    if synthetic:
        records = read_json(directory / "raw/synthetic_snapshot.json")
        entry = entries["synthetic_snapshot.json"]
    else:
        frame = pd.read_csv(directory / "raw" / CURRENT)
        required = {"fixture_id", "date", "kickoff_utc", "status", "home", "away", "source",
                    "home_goals", "away_goals", "home_xg", "away_xg", "home_shots", "away_shots",
                    "home_shots_on_target", "away_shots_on_target", "team_xg_source"}
        require(required <= set(frame), "INVALID_SCHEMA", "Current source schema missing fields")
        records = frame.astype(object).where(frame.notna(), None).to_dict("records")
        entry = entries[CURRENT]
        require(urlparse(entry["url"]).path == "/data/v1/la-liga/2026/fixtures.csv", "SOURCE_CONFLICT", "Wrong current export URL")
    expected = {k for k,r in parent_registry.fixtures.items() if r["season"] == 2026}
    found = set(); ids = set(); updates = []
    for raw in records:
        season, day, home, away = fixture_identity(2026, raw["date"], resolve(raw["home"]), resolve(raw["away"]))
        key = canonical_key(season, home, away)
        require(key in expected, "IDENTITY_CONFLICT", "Fixture outside reviewed season universe")
        require(key not in found, "DUPLICATE_FIXTURE", "Duplicate directed fixture")
        found.add(key)
        require(raw["fixture_id"] is not None, "IDENTITY_CONFLICT", "Missing provider fixture ID")
        fixture_id = str(number(raw["fixture_id"], "fixture_id", integer=True))
        require(fixture_id not in ids, "IDENTITY_CONFLICT", "Provider ID reused for different fixture")
        ids.add(fixture_id)
        old = parent_registry.fixtures[key]
        old_id = schedule[key].get("fixture_id")
        require(old_id is None or fixture_id == old_id, "IDENTITY_CONFLICT", "Provider ID reassigned")
        require(raw["status"] in STATUS, "INVALID_STATUS", "Unknown source match status")
        require(raw["source"] == ("synthetic" if synthetic else "Sportmonks"), "SOURCE_CONFLICT", "Unexpected current provider")
        if not synthetic:
            require(raw["team_xg_source"] in (None,"Sportmonks") and
                    all(raw.get(k) is None for k in ("divergence_status","home_derived","away_derived","result_note","awarded_winner")),
                    "SOURCE_CONFLICT", "Unreviewed xG provenance, derivation or outcome warning")
        status = STATUS[raw["status"]]
        independent = evidence.get(key)
        if independent is not None:
            require(independent["date"] == day, "SOURCE_CONFLICT", "Independent evidence date conflicts")
        completed = status == "completed"
        if completed:
            goals = tuple(number(raw[s+"_goals"], "score", integer=True) for s in ("home", "away"))
            if independent:
                require(goals == (independent["home_gf"], independent["away_gf"]), "SOURCE_CONFLICT", "Independent final score conflicts")
            require(independent is not None or (old["match_status"] == VERIFIED_COMPLETED and
                    goals == (old["home_goals"],old["away_goals"]) and day == old["match_date"]),
                    "UNVERIFIED_COMPLETION", "New completion or corrected score/date requires independent evidence")
        elif independent:
            status = "completed"; completed = True
            goals = (independent["home_gf"], independent["away_gf"])
        elif old["match_status"] == VERIFIED_COMPLETED:
            # A stale scheduled row cannot undo an independently verified result.
            require(day == old["match_date"], "SOURCE_CONFLICT", "Schedule conflicts with verified result")
            status = "completed"; completed = True
            goals = (old["home_goals"], old["away_goals"])
        else:
            goals = (None, None)
        single = MatchRegistry()
        single.observe(season=season,match_date=day,home_team=home,away_team=away,observed_status=status,
                       verification_source=entry["url"] if independent is None else independent["source"],
                       source_version=entry["sha256"],verified_at=entry["retrieved_at"],evidence_verified=completed,
                       home_goals=goals[0],away_goals=goals[1],provider_fixture_id=fixture_id)
        pair = []
        if completed:
            # Never resurrect previously missing numbers from an unplayed row.
            values = raw if raw["status"] == "full_time" else {}
            metadata = dict(fixture_source="Sportmonks" if not synthetic else "synthetic",
                            xg_source="Sportmonks",shots_source="Sportmonks",source_dataset_version="sha256:"+entry["sha256"],
                            fetched_at=entry["retrieved_at"],statistical_semantics="research_mixed_provider_total_xg_shots_not_fbref_equivalent")
            pair = numeric_pair(single.fixtures[key], values, metadata)
            single.attach_statistics(pd.DataFrame(pair))
            pair = single.statistics[key]
        extra = dict(fixture_id=fixture_id, kickoff_utc=checked_kickoff(raw.get("kickoff_utc"), day),
                     source_provider=schedule[key]["source_provider"], source_version=entry["sha256"])
        updates.append((key, single, pair, extra))
    require(found == expected, "REGISTRY_COVERAGE_UNVERIFIED", "Candidate must preserve complete directed fixture catalogue")
    require(set(evidence) <= set(parent_registry.fixtures), "IDENTITY_CONFLICT", "Evidence contains unknown fixture")
    return updates


def archive_updates(directory, entries, parent, registry, schedule):
    """Only selected Understat history may change; frozen FBref selection is protected."""
    updates = []
    changed = {name for name in entries if name.startswith("archive_") and
               parent.manifest["input_hashes"].get("raw/"+name) != entries[name]["sha256"]}
    if not changed:
        return updates
    require(changed <= {"archive_2025_fixtures.csv", "archive_2025_shots.csv"}, "FROZEN_SOURCE_SCOPE",
            "Earlier historical source revisions require a separate controlled adapter audit")
    frames = pd.read_csv(directory / "raw/archive_2025_fixtures.csv")
    require(frames.season.eq(2025).all() and frames.competition.eq("la-liga").all()
            and frames.provider.eq("Understat").all(), "SOURCE_CONFLICT", "Archive provider/season changed")
    shot_stats = understat_shots(pd.read_csv(directory / "raw/archive_2025_shots.csv")).set_index("fixture_id")
    source = entries["archive_2025_fixtures.csv"]
    seen = set()
    baseline = LOCAL / "raw/archive_2025_fixtures.csv"
    baseline_sha = (refresh_metadata(parent) or {}).get("frozen_archive_baseline_sha256",
                    parent.manifest["input_hashes"].get("raw/archive_2025_fixtures.csv"))
    require(baseline.is_file() and sha256(baseline) == baseline_sha,
            "BASELINE_SOURCE_REQUIRED", "Legacy frozen source comparison requires original attested archive")
    old_rows = pd.read_csv(baseline).set_index("fixture_id")
    for raw in frames.astype(object).where(frames.notna(), None).to_dict("records"):
        key = canonical_key(2025, raw["home"], raw["away"])
        require(key in registry.fixtures and key not in seen, "IDENTITY_CONFLICT", "Archive duplicate or unknown identity")
        seen.add(key)
        old = registry.fixtures[key]
        old_pair = registry.statistics.get(key, [])
        if any(r["fixture_source"] == "FBref_frozen_snapshot" for r in old_pair):
            original = old_rows.loc[raw["fixture_id"]]
            require(all(str(raw[f]) == str(original[f]) for f in ("date","score","home_xg","away_xg","totals_unreliable")),
                    "FROZEN_SOURCE_SCOPE", "Revision overlaps frozen FBref-selected inputs")
            continue
        require(raw["totals_unreliable"] in (True, False), "INVALID_SCHEMA", "Unreliable flag must be boolean")
        goals = [number(v,"score",integer=True) for v in raw["score"].split("-")]
        single = MatchRegistry()
        single.observe(season=2025,match_date=raw["date"],home_team=raw["home"],away_team=raw["away"],observed_status="completed",
                       verification_source=source["url"],source_version=source["sha256"],verified_at=source["retrieved_at"],
                       evidence_verified=True,home_goals=goals[0],away_goals=goals[1],provider_fixture_id=old.get("provider_fixture_id"))
        shots = shot_stats.loc[raw["fixture_id"]]
        values = {s+"_"+f:(raw[s+"_xg"] if f == "xg" and not raw["totals_unreliable"] else
                           None if f == "xg" else shots[s+"_"+f]) for s in ("home","away") for f in ("xg","sh","sot")}
        metadata = dict(fixture_source="Understat",xg_source="Understat_flagged_unreliable" if raw["totals_unreliable"] else "Understat",
                        shots_source="Understat_shot_events",source_dataset_version="sha256:"+source["sha256"]+";shots_sha256:"+entries["archive_2025_shots.csv"]["sha256"],
                        fetched_at=source["retrieved_at"],statistical_semantics="research_non_penalty_shot_mapping")
        pair = numeric_pair(single.fixtures[key], values, metadata, fields={"xg":"xg","sh":"sh","sot":"sot"})
        single.attach_statistics(pd.DataFrame(pair))
        updates.append((key,single,single.statistics[key],dict(schedule[key],source_version=source["sha256"])))
    require(seen == {k for k,r in registry.fixtures.items() if r["season"] == 2025},
            "REGISTRY_COVERAGE_UNVERIFIED", "Archive directed catalogue incomplete")
    return updates


def build_candidate(parent, source_directory, candidate_version, as_of, *, dataset_kind="real"):
    directory = Path(source_directory).resolve()
    as_of = date.fromisoformat(as_of).isoformat()
    parent.verify_integrity()
    require(dataset_kind in {"real","synthetic"}, "INVALID_SCOPE", "Unknown dataset kind")
    synthetic = dataset_kind == "synthetic"
    parent_kind = (refresh_metadata(parent) or parent.manifest.get("identity_review", {})).get("dataset_kind", "real")
    require(parent_kind == dataset_kind, "INVALID_SCOPE", "Cannot mix synthetic and real histories")
    require(not synthetic or not parent.path.is_relative_to(RESEARCH_ROOT.resolve()),
            "INVALID_SCOPE", "Synthetic data cannot enter the real research namespace")
    entries, hashes = manifest(directory, synthetic=synthetic)
    if not synthetic:
        expected = {CURRENT, "archive_2025_shots.csv", *(f"archive_{s}_fixtures.csv" for s in range(2019,2026))}
        require(expected <= set(entries), "MISSING_INPUT_FILES", "Missing reviewed current/archive source files")
        for year in range(2019,2026):
            frame = pd.read_csv(directory / "raw" / f"archive_{year}_fixtures.csv")
            require({"season","competition","home","away","date","score"} <= set(frame), "INVALID_SCHEMA", "Invalid archive schema")
            require(frame.season.eq(year).all() and frame.competition.eq("la-liga").all(), "SOURCE_CONFLICT", "Archive scope changed")
    evidence, evidence_hash = completion_evidence(directory, synthetic=synthetic)
    if evidence_hash:
        hashes["independent_completed.json"] = evidence_hash
    registry, statistics, catalogues, schedule = state(parent)
    require(not registry.conflicts, "SOURCE_CONFLICT", "Parent has unresolved conflicts")
    changes = []; before = {k:business(r,statistics.get(k,[]),schedule[k]) for k,r in registry.fixtures.items()}
    updates = current_updates(directory, entries, registry, schedule, evidence, synthetic=synthetic)
    if not synthetic:
        updates += archive_updates(directory, entries, parent, registry, schedule)
    for key, single, pair, extra in updates:
        row = single.fixtures[key]
        after = business(row,pair,extra)
        unreliable = any("unreliable" in r["xg_source"].lower() for r in statistics.get(key,[]))
        kinds, decision = classify(before[key], after, unreliable=unreliable)
        require(decision != "BLOCKED", kinds[0] if kinds else "INVALID_TRANSITION", "Candidate violates transition or semantic invariants", key=key)
        if decision == "NO_CHANGE":
            continue
        change = dict(canonical_fixture_key=key, change_type=kinds, decision=decision,
                      old_values=before[key],new_values=after,source_provenance=dict(source_version=extra["source_version"],
                      verification_source=row["verification_source"], statistics=[{k:r[k] for k in GROUPS} for r in pair]))
        change["change_id"] = semantic_hash(change)
        changes.append(change)
        registry.fixtures[key] = row
        if pair:
            statistics[key] = pair
        registry.evidence.extend(single.evidence)
        schedule[key] = extra
    # Validate the full result, including unchanged history, not just changed rows.
    completed_dates = set()
    for key,row in registry.fixtures.items():
        fixture_identity(row["season"],row["match_date"],row["home_team"],row["away_team"])
        if row["match_status"] == VERIFIED_COMPLETED:
            require(row["match_date"] <= as_of, "FUTURE_COMPLETION", "Completed fixture after explicit as-of date")
            for team in (row["home_team"],row["away_team"]):
                token = (team,row["match_date"])
                require(token not in completed_dates, "AMBIGUOUS_HISTORY", "Same team has two completed fixtures on one date")
                completed_dates.add(token)
        for r in statistics.get(key,[]):
            require(r["season"] == row["season"] and r["date"] == row["match_date"], "INVALID_STATISTICS", "Statistics season/date mismatch")
    check = MatchRegistry(); check.fixtures = copy.deepcopy(registry.fixtures)
    if statistics:
        check.attach_statistics(pd.DataFrame([r for pair in statistics.values() for r in pair]))
    require(not check.conflicts, "SOURCE_CONFLICT", "Contradictory final scores/statistics")
    for season, catalogue in list(catalogues.items()):
        catalogues[season] = validate_catalogue(registry,season,catalogue["clubs"],catalogue["verification_source"],
                                               catalogue["source_version"],catalogue["verified_at"])
    after = {k:business(r,statistics.get(k,[]),schedule[k]) for k,r in registry.fixtures.items()}
    effect = semantic_hash(dict(parent_sha256=sha256(parent.path), business=after, policy=POLICY_VERSION))
    changes.sort(key=lambda r:r["change_id"])
    bundle = dict(policy_version=POLICY_VERSION, dataset_kind=dataset_kind, as_of=as_of,
                  source_directory=str(directory), parent_database=str(parent.path), parent_sha256=sha256(parent.path),
                  parent_version=parent.manifest["version_id"],candidate_version=candidate_version,source_hashes=hashes,
                  effect_sha256=effect,changes=changes,registry=registry.fixtures,statistics=statistics,
                  catalogues=catalogues,schedule=schedule,evidence=registry.evidence)
    require(all((directory/name).is_file() and sha256(directory/name) == checksum for name,checksum in hashes.items()),
            "STALE_CANDIDATE", "Source changed while preparing candidate")
    parent.verify_integrity()
    # Normalize integer dictionary keys and numeric scalar representations before binding.
    return json.loads(json.dumps(bundle, ensure_ascii=False, allow_nan=False))
