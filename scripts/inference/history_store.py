"""Kho lịch sử độc lập bằng SQLite, provenance, lịch thi đấu và attestations."""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pandas as pd

from .common import (HISTORY_PATH, SNAPSHOT_PROVIDER, TEAM_IDS, InferenceError, check,
                     fixture_key, parse_date, resolve_team)

DEFAULT_PROVIDER_POLICY = {SNAPSHOT_PROVIDER: dict(replay_approved=True, production_approved=False,
    xg_family="fbref_opta", review_status="frozen_research_snapshot_only",
    compatibility_review="Nguồn nghiên cứu FBref/Opta theo hồ sơ dự án, không phải live connector đã xác minh.")}

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS matches (
 canonical_key TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_match_id TEXT NOT NULL,
 date TEXT NOT NULL, season INTEGER NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
 semantic_sha256 TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(provider,provider_match_id));
CREATE TABLE IF NOT EXISTS team_records (
 canonical_key TEXT NOT NULL REFERENCES matches(canonical_key), team TEXT NOT NULL, date TEXT NOT NULL,
 season INTEGER NOT NULL, is_home INTEGER NOT NULL, gf INTEGER NOT NULL, ga INTEGER NOT NULL,
 xg REAL NOT NULL, xga REAL NOT NULL, sh INTEGER NOT NULL, sot INTEGER NOT NULL,
 PRIMARY KEY(canonical_key,team));
CREATE INDEX IF NOT EXISTS team_date_idx ON team_records(team,date);
CREATE TABLE IF NOT EXISTS schedule (
 canonical_key TEXT PRIMARY KEY, provider TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS coverage (
 team TEXT NOT NULL, season INTEGER NOT NULL, provider TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(team,season));
CREATE TABLE IF NOT EXISTS refresh_runs (
 run_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, status TEXT NOT NULL, manifest TEXT NOT NULL);
"""


def load_provider_policy(path=None):
    if path is None:
        return DEFAULT_PROVIDER_POLICY.copy()
    try:
        policy=json.loads(Path(path).read_text(encoding="utf-8"))
        check(isinstance(policy,dict),"INCOMPATIBLE_PROVIDER","Provider policy phải là object do quản trị phê duyệt.")
        for name, config in policy.items():
            check(isinstance(name,str) and isinstance(config,dict),"INCOMPATIBLE_PROVIDER","Sai provider policy.")
            if config.get("production_approved"):
                check(config.get("compatible_with_training") is True and bool(config.get("reviewed_by"))
                      and bool(config.get("compatibility_review")) and bool(config.get("xg_family")),
                      "INCOMPATIBLE_PROVIDER","Phải có compatibility review tường minh trước production.")
        return policy
    except InferenceError:
        raise
    except (OSError,ValueError) as exc:
        raise InferenceError("INCOMPATIBLE_PROVIDER","Không đọc được provider policy tin cậy.") from exc


class HistoryStore:
    """Mọi phương thức suy luận chỉ mở database read-only; cập nhật ở data_refresh."""

    def __init__(self,path=HISTORY_PATH,*,provider_policy=None):
        self.path=Path(path).resolve()
        self.provider_policy=DEFAULT_PROVIDER_POLICY.copy() if provider_policy is None else provider_policy
        check(self.path.is_file(),"HISTORY_MISSING","Chưa có history store. Chạy bootstrap-snapshot hoặc import CSV.")
        try:
            self.query("SELECT canonical_key FROM matches LIMIT 1")
        except sqlite3.Error as exc:
            raise InferenceError("INVALID_HISTORY","History store không đúng schema.") from exc

    def query(self,sql,parameters=()):
        with closing(sqlite3.connect(self.path.as_uri()+"?mode=ro",uri=True)) as connection:
            connection.row_factory=sqlite3.Row
            return [dict(row) for row in connection.execute(sql,parameters)]

    def provider(self):
        providers=self.query("SELECT DISTINCT provider FROM matches")
        check(len(providers)==1,"INCOMPATIBLE_PROVIDER","Kho phải có đúng một provider thống kê, không trộn xG.")
        return providers[0]["provider"]

    def check_provider(self,mode):
        name=self.provider()
        policy=self.provider_policy.get(name)
        check(policy is not None,"UNSUPPORTED_PROVIDER","Provider chưa có compatibility policy.",provider=name)
        key="replay_approved" if mode=="replay" else "production_approved"
        check(policy.get(key) is True,"INCOMPATIBLE_PROVIDER","Provider chưa được phê duyệt cho chế độ này.",provider=name,mode=mode)
        if mode=="upcoming":
            check(policy.get("compatible_with_training") is True and bool(policy.get("reviewed_by"))
                  and bool(policy.get("compatibility_review")),"INCOMPATIBLE_PROVIDER","Thiếu review tương thích xG với training.")
        return name,policy

    def fixture_identity(self,home,away,match_date,season):
        key=fixture_key(season,home,away)
        found=self.query("SELECT canonical_key,provider,provider_match_id,date,season,home_team,away_team FROM matches WHERE canonical_key=?",(key,))
        check(len(found)==1 and found[0]["date"]==match_date,"INVALID_FIXTURE","Không tìm thấy completed fixture đúng định danh/ngày.")
        return found[0]

    def snapshot_fixture(self,legacy_match_id):
        found=self.query("SELECT canonical_key,date,season,home_team,away_team FROM matches WHERE provider=? AND provider_match_id=?",
                         (SNAPSHOT_PROVIDER,f"legacy-local:{legacy_match_id}"))
        check(len(found)==1,"INVALID_FIXTURE","Không tìm thấy legacy match ID trong snapshot; đây không phải provider ID.")
        return found[0]

    def prior_team_records(self,team,season,before_date,exclude_key):
        # WHERE lọc identity/ngày trước khi lấy bất kỳ outcome nào của lịch sử.
        rows=self.query("SELECT canonical_key,team,date,season,is_home,gf,ga,xg,xga,sh,sot FROM team_records "
            "WHERE team=? AND season<=? AND date<? AND canonical_key<>? ORDER BY date,canonical_key",
            (team,season,before_date,exclude_key))
        return pd.DataFrame(rows,columns=["canonical_key","team","date","season","is_home","gf","ga","xg","xga","sh","sot"])

    def provenance(self,keys):
        # Dùng cho các trận lịch sử đã được chọn; không đọc target fixture.
        records=[]
        for key in sorted(set(keys)):
            rows=self.query("SELECT payload FROM matches WHERE canonical_key=?",(key,))
            check(len(rows)==1,"INVALID_HISTORY","Thiếu provenance của match lịch sử.")
            payload=json.loads(rows[0]["payload"])
            records.append({k:payload[k] for k in ("canonical_key","provider","provider_match_id","fetched_at","statistics_version","quality_status")})
        return records

    def schedule_fixture(self,home,away,day,season):
        rows=self.query("SELECT provider,payload FROM schedule WHERE canonical_key=?",(fixture_key(season,home,away),))
        check(len(rows)==1,"FIXTURE_UNVERIFIED","Chưa có lịch thi đấu đã xác minh cho fixture này.")
        schedule=json.loads(rows[0]["payload"])
        check(schedule["date"]==day and schedule["status"]=="scheduled" and schedule["quality_status"]=="verified",
              "FIXTURE_UNVERIFIED","Ngày/trạng thái fixture chưa xác minh hoặc đã thay đổi/hoãn.")
        check(rows[0]["provider"]==self.provider(),"INCOMPATIBLE_PROVIDER","Schedule và history khác provider; cần connector/review riêng.")
        return schedule

    def coverage_for(self,team,season):
        rows=self.query("SELECT provider,payload FROM coverage WHERE team=? AND season=?",(team,season))
        check(len(rows)==1,"COVERAGE_UNVERIFIED","Thiếu xác nhận lịch sử đầy đủ cho từng đội.",team=team)
        result=json.loads(rows[0]["payload"])
        check(rows[0]["provider"]==self.provider(),"INCOMPATIBLE_PROVIDER","Coverage và history khác provider.")
        return result

    def data_status(self):
        counts=self.query("SELECT COUNT(*) n_matches,MIN(date) first_date,MAX(date) last_date FROM matches")[0]
        teams=self.query("SELECT team,COUNT(*) n_matches,MIN(date) first_date,MAX(date) last_date FROM team_records GROUP BY team ORDER BY team")
        return dict(status="success",history_store=str(self.path),provider=self.provider(),
            provider_policy=self.provider_policy.get(self.provider(),{}),**counts,teams=teams,
            production_readiness="requires_per_team_coverage_and_verified_schedule",automatic_refresh_enabled=False)


def validate_schedule(items,provider):
    check(isinstance(items,list),"INVALID_SCHEMA","Schedule phải là JSON array.")
    result=[]; keys=set()
    for item in items:
        from .common import validate_fixture
        try:
            home,away,_=validate_fixture(item["home_team"],item["away_team"],item["date"],item["season"])
            check(item["provider"]==provider and item["status"] in {"scheduled","postponed","cancelled","completed"}
                  and item["quality_status"]=="verified" and bool(item["provider_fixture_id"]) and bool(item["verified_by"]),
                  "INVALID_SCHEMA","Schedule thiếu provenance hoặc xác minh.")
            from datetime import datetime
            fetched=datetime.fromisoformat(item["fetched_at"])
            check(fetched.tzinfo is not None,"INVALID_SCHEMA","fetched_at cần timezone.")
            kickoff=item.get("kickoff_utc")
            if kickoff:
                parsed=datetime.fromisoformat(kickoff)
                check(parsed.tzinfo is not None,"INVALID_SCHEMA","Kickoff phải có timezone; không tự suy đoán múi giờ.")
            key=fixture_key(item["season"],home,away)
            check(key not in keys,"DUPLICATE_FIXTURE","Schedule trùng canonical key.")
            keys.add(key)
            result.append(dict(item,home_team=home,away_team=away,canonical_key=key))
        except (KeyError,TypeError,ValueError) as exc:
            if isinstance(exc,InferenceError):raise
            raise InferenceError("INVALID_SCHEMA","Schedule sai schema.") from exc
    return result


def validate_coverage(items,provider):
    check(isinstance(items,list),"INVALID_SCHEMA","Coverage phải là JSON array.")
    result=[]; keys=set()
    for item in items:
        try:
            team=resolve_team(item["team"])
            check(type(item["season"]) is int and type(item["stint_start_season"]) is int
                  and 1900<=item["stint_start_season"]<=item["season"]<=2200,
                  "INVALID_SCHEMA","Coverage season/stint không hợp lệ.")
            through=parse_date(item["verified_through"])
            check(through.year in (item["season"],item["season"]+1) and item["provider"]==provider
                  and bool(item["verified_by"]) and isinstance(item["eligible_match_keys"],list)
                  and len(item["eligible_match_keys"])==len(set(item["eligible_match_keys"]))
                  and all(isinstance(key,str) for key in item["eligible_match_keys"]),
                  "INVALID_SCHEMA","Coverage thiếu danh sách trận đầy đủ/provenance.")
            from datetime import datetime
            reviewed=datetime.fromisoformat(item["reviewed_at"])
            check(reviewed.tzinfo is not None,"INVALID_SCHEMA","reviewed_at cần timezone.")
            key=(team,item["season"])
            check(key not in keys,"DUPLICATE_FIXTURE","Coverage trùng team/season.")
            keys.add(key); result.append(dict(item,team=team))
        except (KeyError,TypeError,ValueError) as exc:
            if isinstance(exc,InferenceError):raise
            raise InferenceError("INVALID_SCHEMA","Coverage sai schema.") from exc
    return result
