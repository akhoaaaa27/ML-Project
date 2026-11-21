"""Immutable research SQLite versions, explicit provenance and registry coverage."""

from contextlib import closing
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile

import pandas as pd

from scripts.inference.common import HISTORY_PATH, ROOT, sha256
from .match_registry import (COMPLETE_STATISTICS, PENDING_UPDATE, SOURCE_CONFLICT, UNVERIFIED,
                             VERIFIED_COMPLETED, MatchRegistry, require, semantic_hash, timestamp, validate_catalogue)
from .team_registry import resolve

RESEARCH_ROOT = ROOT / "data/history/research"
SCHEMA_VERSION = 1
LOGICAL_PROVIDER = "laliga_composite_v1"
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE registry(canonical_fixture_key TEXT PRIMARY KEY, season INTEGER NOT NULL, match_date TEXT NOT NULL,
 home_team TEXT NOT NULL, away_team TEXT NOT NULL, match_status TEXT NOT NULL, statistics_status TEXT NOT NULL,
 observed_status TEXT NOT NULL, home_goals INTEGER, away_goals INTEGER,
 verification_source TEXT NOT NULL, source_version TEXT NOT NULL, verified_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX registry_date ON registry(season,match_date);
CREATE TABLE statistics(canonical_fixture_key TEXT NOT NULL REFERENCES registry, team TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(canonical_fixture_key,team));
CREATE TABLE evidence(id INTEGER PRIMARY KEY, canonical_fixture_key TEXT NOT NULL REFERENCES registry, payload TEXT NOT NULL);
CREATE TABLE catalogues(season INTEGER PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE conflicts(id INTEGER PRIMARY KEY, canonical_fixture_key TEXT NOT NULL REFERENCES registry, payload TEXT NOT NULL);
CREATE TABLE revisions(canonical_fixture_key TEXT PRIMARY KEY, change_kind TEXT NOT NULL,
 previous_sha256 TEXT, current_sha256 TEXT);
CREATE TABLE metadata(name TEXT PRIMARY KEY, payload TEXT NOT NULL);
"""


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def guarded_root(root):
    root = Path(root).resolve()
    production_parent = HISTORY_PATH.resolve().parent
    require(root != production_parent and not (root.is_relative_to(production_parent)
            and not root.is_relative_to(RESEARCH_ROOT.resolve())),
            "PRODUCTION_STORE_PROTECTED", "Composite versions must not be published in the production namespace")
    return root


def publish_version(registry, statistics, catalogues, *, version_id, input_hashes,
                    root=RESEARCH_ROOT, parent=None, identity_review=None, validator=None):
    """Build and validate a temporary snapshot, publish only a new version dir.

    Sources change by building a successor; there is no in-place update method.
    The manifest is also embedded in SQLite. A writer lock serializes publishers.
    """
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", version_id or "") is not None,
            "INVALID_VERSION", "Invalid version ID")
    root = guarded_root(root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / version_id
    require(not destination.exists(), "VERSION_EXISTS", "Existing versions cannot be overwritten")
    require(bool(input_hashes) and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in input_hashes.values()),
            "INVALID_PROVENANCE", "Input hashes are required")
    seasons = {row["season"] for row in registry.fixtures.values()}
    require(set(catalogues) == seasons, "REGISTRY_COVERAGE_UNVERIFIED", "Missing season catalogue")
    for season, catalogue in catalogues.items():
        checked = validate_catalogue(registry, season, catalogue["clubs"], catalogue["verification_source"],
                                     catalogue["source_version"], catalogue["verified_at"])
        require(catalogue == checked, "REGISTRY_COVERAGE_UNVERIFIED", "Coverage attestation does not match registry")
    # Recompute completeness and provenance before trusting caller state flags.
    review = MatchRegistry()
    review.fixtures = copy.deepcopy(registry.fixtures)
    recheck_rows = [row for key,pair in statistics.items() for row in pair
                   if key not in registry.fixtures or registry.fixtures[key]["statistics_status"] != SOURCE_CONFLICT]
    if recheck_rows:
        review.attach_statistics(pd.DataFrame(recheck_rows))
    require(all(row["statistics_status"] == review.fixtures[key]["statistics_status"] for key,row in registry.fixtures.items()),
            "INVALID_STATISTICS", "Statistics completeness flags differ from actual values")
    versions = sorted({row["source_dataset_version"] for pair in statistics.values() for row in pair})
    counts = {name: sum(row["statistics_status"] == name for row in registry.fixtures.values())
              for name in (COMPLETE_STATISTICS, PENDING_UPDATE, SOURCE_CONFLICT, UNVERIFIED)}
    verified = sum(row["match_status"] == VERIFIED_COMPLETED for row in registry.fixtures.values())
    for key, row in registry.fixtures.items():
        require(row["statistics_status"] != COMPLETE_STATISTICS or (key in statistics and len(statistics[key]) == 2),
                "INVALID_STATISTICS", "Complete state without two statistics records")
    current_fingerprints = {key: semantic_hash(dict(registry={k:v for k,v in row.items() if k != "verified_at"}, statistics=statistics.get(key, [])))
                            for key, row in registry.fixtures.items()}
    previous = {} if parent is None else parent.fingerprints()
    revisions = []
    for key in sorted(set(previous) | set(current_fingerprints)):
        old, new = previous.get(key), current_fingerprints.get(key)
        if old != new:
            revisions.append((key, "added" if old is None else "removed" if new is None else "modified", old, new))
    coverage = []
    for season, catalogue in sorted(catalogues.items()):
        for team in catalogue["clubs"]:
            fixtures = [r for r in registry.fixtures.values() if r["season"] == season and team in (r["home_team"], r["away_team"])]
            coverage.append(dict(season=season, team=team, verified_completed=sum(r["match_status"] == VERIFIED_COMPLETED for r in fixtures),
                                 complete_statistics=sum(r["statistics_status"] == COMPLETE_STATISTICS for r in fixtures),
                                 pending_statistics=sum(r["statistics_status"] == PENDING_UPDATE for r in fixtures),
                                 verified_before=catalogue["verified_before_by_team"][team]))
    code_files = sorted((ROOT/"scripts/multisource").glob("*.py"))
    core = dict(version_id=version_id, build_timestamp=datetime.now(timezone.utc).isoformat(),
                schema_version=SCHEMA_VERSION, logical_provider=LOGICAL_PROVIDER,
                code_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
                code_sha256={str(p.relative_to(ROOT)):sha256(p) for p in code_files}, input_hashes=input_hashes,
                source_dataset_versions=versions, registry_fixtures=len(registry.fixtures),
                verified_completed=verified, complete_statistics=counts[COMPLETE_STATISTICS],
                pending_statistics=counts[PENDING_UPDATE], unresolved_conflicts=len(registry.conflicts),
                unverified=counts[UNVERIFIED], coverage=coverage,
                parent_version=None if parent is None else parent.manifest["version_id"],
                revision_counts={kind:sum(r[1] == kind for r in revisions) for kind in ("added", "modified", "removed")},
                research_validation_status="validated_export_catalogue_scope", production_approved=False,
                identity_review=identity_review or {}, history_origin_season=min(seasons))
    lock_path = root / ".publish.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    temp = None
    try:
        require(not destination.exists(), "VERSION_EXISTS", "Existing version cannot be replaced")
        temp = Path(tempfile.mkdtemp(prefix=".building-", dir=root)).resolve()
        database = temp / "laliga_composite.sqlite3"
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.executescript(SCHEMA)
            for key, row in sorted(registry.fixtures.items()):
                connection.execute("INSERT INTO registry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    key,row["season"],row["match_date"],row["home_team"],row["away_team"],row["match_status"],
                    row["statistics_status"],row["observed_status"],row["home_goals"],row["away_goals"],
                    row["verification_source"],row["source_version"],row["verified_at"],dumps(row)))
            for key, records in sorted(statistics.items()):
                for row in records:
                    connection.execute("INSERT INTO statistics VALUES (?,?,?)", (key,row["team"],dumps(row)))
            for row in registry.evidence:
                connection.execute("INSERT INTO evidence(canonical_fixture_key,payload) VALUES (?,?)", (row["canonical_fixture_key"],dumps(row)))
            for season, catalogue in sorted(catalogues.items()):
                connection.execute("INSERT INTO catalogues VALUES (?,?)", (season,dumps(catalogue)))
            for row in registry.conflicts:
                connection.execute("INSERT INTO conflicts(canonical_fixture_key,payload) VALUES (?,?)", (row["canonical_fixture_key"],dumps(row)))
            connection.executemany("INSERT INTO revisions VALUES (?,?,?,?)", revisions)
            connection.execute("INSERT INTO metadata VALUES (?,?)", ("manifest",dumps(core)))
            connection.execute("INSERT INTO metadata VALUES (?,?)", ("fingerprints",dumps(current_fingerprints)))
            require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    and not connection.execute("PRAGMA foreign_key_check").fetchall(), "DATABASE_INVALID", "SQLite validation failed")
        sidecar = dict(core_manifest=core, database_sha256=sha256(database))
        (temp/"manifest.json").write_text(dumps(sidecar)+"\n", encoding="utf-8")
        provisional = CompositeHistory(database, research_root=root)
        if validator is not None:
            # A failing integration/parity check leaves no published version.
            validation = validator(provisional)
            core["inference_validation"] = validation
            core["research_validation_status"] = "validated_registry_rolling_features_and_frozen_inference_parity"
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("UPDATE metadata SET payload=? WHERE name='manifest'", (dumps(core),))
            (temp/"manifest.json").write_text(dumps(dict(core_manifest=core,database_sha256=sha256(database)))+"\n",encoding="utf-8")
            CompositeHistory(database,research_root=root)
        os.rename(temp, destination)  # Lock + absent destination: no in-use version replaced.
        temp = None
    finally:
        os.close(lock)
        lock_path.unlink()
        if temp is not None and temp.exists():
            require(temp.parent == root and temp.name.startswith(".building-"), "UNSAFE_CLEANUP", "Invalid temporary build target")
            shutil.rmtree(temp)
    return CompositeHistory(destination/"laliga_composite.sqlite3", research_root=root)


class CompositeHistory:
    """Read-only research adapter; never a subclass/override of production HistoryStore."""
    def __init__(self, path, *, research_root=RESEARCH_ROOT):
        self.path = Path(path).resolve()
        root = guarded_root(research_root)
        require(self.path != HISTORY_PATH.resolve() and self.path.is_relative_to(root),
                "PRODUCTION_STORE_PROTECTED", "Only a trusted research version can be opened")
        require(self.path.is_file(), "HISTORY_MISSING", "Composite version is missing")
        self._sidecar = json.loads((self.path.parent/"manifest.json").read_text(encoding="utf-8"))
        self.verify_integrity()
        self.manifest = self._sidecar["core_manifest"]
        require(self.manifest["schema_version"] == SCHEMA_VERSION and self.manifest["production_approved"] is False,
                "INVALID_HISTORY", "Unapproved composite schema/policy")
        stored = json.loads(self.query("SELECT payload FROM metadata WHERE name='manifest'")[0]["payload"])
        require(stored == self.manifest, "HISTORY_CORRUPT", "Manifest differs from embedded version")

    def verify_integrity(self):
        require(sha256(self.path) == self._sidecar["database_sha256"], "HISTORY_CORRUPT", "Composite checksum mismatch")

    def query(self, sql, parameters=()):
        with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro&immutable=1", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            # Read-only main DB alone does not forbid ATTACH/VACUUM INTO from
            # creating other files. Restrict the query interface to reads too.
            allowed = {sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE}
            connection.set_authorizer(lambda action,*args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
            return [dict(row) for row in connection.execute(sql,parameters)]

    def fixture(self, home, away, day, season):
        from .match_registry import canonical_key
        records = self.query("SELECT * FROM registry WHERE canonical_fixture_key=?",(canonical_key(season,home,away),))
        require(len(records) == 1 and records[0]["match_date"] == day, "INVALID_FIXTURE", "Unverified fixture identity/date")
        require(records[0]["match_status"] != SOURCE_CONFLICT, "SOURCE_CONFLICT", "Conflicting target identity")
        return records[0]

    def assert_coverage(self, team, season, cutoff):
        team = resolve(team)
        catalogues = {r["season"]:json.loads(r["payload"]) for r in self.query("SELECT * FROM catalogues")}
        origin = self.manifest["history_origin_season"]
        require(all(s in catalogues for s in range(origin,season+1)) and season >= origin,
                "REGISTRY_COVERAGE_UNVERIFIED", "Missing season roster/coverage")
        require(team in catalogues[season]["clubs"], "REGISTRY_COVERAGE_UNVERIFIED", "Team membership is unverified")
        start = season
        while start > origin and team in catalogues[start-1]["clubs"]:
            start -= 1
        for s in range(start,season+1):
            catalogue = catalogues[s]
            required_before = min(cutoff, f"{s+1}-07-01")
            require(catalogue.get("calendar_verified") is True
                    and required_before <= catalogue["verified_before_by_team"].get(team,""),
                    "REGISTRY_COVERAGE_UNVERIFIED", "Unverified completed-fixture coverage", team=team, season=s)
        return dict(stint_start_season=start, zero_history_basis="verified_season_membership_and_calendar",
                    scope="research_export_catalogue", production_approved=False)

    def prior_registry(self, team, season, cutoff, exclude_key):
        rows = self.query("SELECT * FROM registry WHERE (home_team=? OR away_team=?) AND season<=? AND match_date<? "
                          "AND canonical_fixture_key<>? AND match_status=? ORDER BY match_date,canonical_fixture_key",
                          (team,team,season,cutoff,exclude_key,VERIFIED_COMPLETED))
        result = []
        for r in rows:
            result.append(dict(canonical_key=r["canonical_fixture_key"],date=r["match_date"],season=r["season"],team=team,
                               statistics_status=r["statistics_status"],is_home=int(r["home_team"]==team)))
        return pd.DataFrame(result,columns=["canonical_key","date","season","team","statistics_status","is_home"])

    def statistics_for(self, key, team):
        rows = self.query("SELECT payload FROM statistics WHERE canonical_fixture_key=? AND team=?",(key,team))
        return None if not rows else json.loads(rows[0]["payload"])

    def fingerprints(self):
        return json.loads(self.query("SELECT payload FROM metadata WHERE name='fingerprints'")[0]["payload"])
