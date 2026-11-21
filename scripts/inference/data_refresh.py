"""Nhập CSV offline/refresh trung lập provider; không có scheduler hoặc retraining tự động."""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Protocol
import uuid

import numpy as np
import pandas as pd

from scripts.prepare_training_features import INPUT_PATH, load_dataset
from .common import (HISTORY_PATH, OUTPUT_DIR, SNAPSHOT_PROVIDER, InferenceError, check, cli_output,
                     fixture_key, resolve_team, sha256, utc_now, validate_fixture, write_json)
from .history_store import SCHEMA, HistoryStore, validate_coverage, validate_schedule

CSV_COLUMNS = ("provider","provider_match_id","season","date","team","opponent","is_home","status",
               "gf","ga","xg","xga","sh","sot","fetched_at","statistics_version","quality_status")


class CompletedMatchProvider(Protocol):
    """Connector tương lai phải trả schema hai góc nhìn chuẩn này; không chứa credentials."""
    def fetch_completed(self) -> pd.DataFrame: ...
    def source_identity(self) -> dict: ...


class CSVProvider:
    def __init__(self,path):
        self.path=Path(path)

    def fetch_completed(self):
        try:
            return pd.read_csv(self.path,keep_default_na=False,dtype=str)
        except (OSError,ValueError) as exc:
            raise InferenceError("INVALID_SCHEMA","Không đọc được CSV lịch sử.") from exc

    def source_identity(self):
        check(self.path.is_file(),"INVALID_SCHEMA","Không tìm thấy CSV.")
        return dict(kind="local_csv",filename=self.path.name,sha256=sha256(self.path))


class FrozenSnapshotProvider:
    """Bootstrap snapshot nghiên cứu sang kho riêng; legacy ID không phải FBref provider ID."""
    def fetch_completed(self):
        full=load_dataset()
        records=full[["season","date","team","opponent","is_home","gf","ga","xg","xga","sh","sot"]].copy()
        records["provider"]=SNAPSHOT_PROVIDER
        records["provider_match_id"]="legacy-local:"+full.match_id.astype(str)
        records["status"]="completed"
        records["fetched_at"]=utc_now()  # Lúc nhập snapshot, không giả làm thời điểm lấy dữ liệu gốc.
        records["statistics_version"]="normalized_sha256:"+sha256(INPUT_PATH)
        records["quality_status"]="verified"
        return records

    def source_identity(self):
        return dict(kind="frozen_snapshot",filename=INPUT_PATH.name,sha256=sha256(INPUT_PATH),
                    provenance="FBref/Opta-derived theo hồ sơ dự án; provider match ID gốc và thời điểm fetch gốc chưa được xác nhận")


def validate_completed_rows(frame):
    check(isinstance(frame,pd.DataFrame) and not frame.empty and frame.columns.is_unique
          and set(CSV_COLUMNS).issubset(frame.columns) and set(frame.columns).issubset(set(CSV_COLUMNS)|{"kickoff_utc"}),
          "INVALID_SCHEMA","CSV thiếu cột bắt buộc hoặc chứa cột không hỗ trợ.")
    working=frame.copy(deep=True)
    check(not working[list(CSV_COLUMNS)].isna().any().any()
          and not working[list(CSV_COLUMNS)].astype(str).apply(lambda s:s.str.strip().eq("")).any().any(),
          "MISSING_STATISTICS","Thiếu thống kê/provenance bắt buộc; không impute outcomes.")
    for column in ("season","is_home","gf","ga","xg","xga","sh","sot"):
        try:
            working[column]=pd.to_numeric(working[column],errors="raise")
        except (ValueError,TypeError) as exc:
            raise InferenceError("INVALID_NUMERIC",f"Cột {column} không phải số.") from exc
        check(np.isfinite(working[column].to_numpy(dtype=float)).all() and working[column].ge(0).all(),
              "INVALID_NUMERIC",f"Cột {column} có số thiếu, âm hoặc không hữu hạn.")
        if column not in ("xg","xga"):
            check(working[column].mod(1).eq(0).all(),"INVALID_NUMERIC",f"Cột {column} phải là số nguyên.")
            working[column]=working[column].astype(int)
    check(working.is_home.isin([0,1]).all() and working.sh.ge(working.sot).all(),"INVALID_NUMERIC","Sai Home/Away hoặc sot > sh.")
    check(working.status.eq("completed").all() and working.quality_status.eq("verified").all(),
          "INVALID_HISTORY","Chỉ nhập completed fixtures có quality_status=verified.")
    check(working.provider.nunique()==1 and working.provider.astype(str).str.fullmatch(r"[a-zA-Z0-9_-]+").all(),
          "INCOMPATIBLE_PROVIDER","Một import chỉ được có một provider hợp lệ.")
    for column in ("team","opponent"):
        working[column]=working[column].map(resolve_team)
    check(not working.duplicated(["provider","provider_match_id","team"]).any(),"DUPLICATE_FIXTURE","CSV trùng team/provider match ID.")
    result=[]; seen=set()
    for (_,provider_id),group in working.groupby(["provider","provider_match_id"],sort=True):
        check(len(group)==2 and set(group.is_home)=={0,1},"INCOMPLETE_HISTORY","Provider fixture phải đủ đúng hai phía Home/Away.")
        home=group.loc[group.is_home.eq(1)].iloc[0]; away=group.loc[group.is_home.eq(0)].iloc[0]
        season=int(home.season)
        validate_fixture(home.team,away.team,str(home.date),season)
        check(home.opponent==away.team and away.opponent==home.team and home.date==away.date and home.season==away.season,
              "INVALID_FIXTURE","Hai phía không khớp identity/ngày/mùa.")
        check(home.gf==away.ga and home.ga==away.gf and np.isclose(home.xg,away.xga,rtol=0,atol=1e-9)
              and np.isclose(home.xga,away.xg,rtol=0,atol=1e-9),"INCONSISTENT_PAIR","gf/ga hoặc xG/xGA của hai phía không khớp.")
        for column in ("fetched_at","statistics_version","quality_status"):
            check(group[column].nunique()==1,"INVALID_SCHEMA",f"Provenance {column} phải thống nhất hai phía.")
        try:
            fetched=datetime.fromisoformat(str(home.fetched_at))
            check(fetched.tzinfo is not None,"INVALID_SCHEMA","fetched_at phải có timezone.")
            kickoff=str(home.get("kickoff_utc","") or "")
            check("kickoff_utc" not in group or group.kickoff_utc.fillna("").nunique()==1,"INVALID_SCHEMA","Kickoff không khớp hai phía.")
            if kickoff:
                check(datetime.fromisoformat(kickoff).tzinfo is not None,"INVALID_SCHEMA","Kickoff cần timezone đã xác minh.")
        except (TypeError,ValueError) as exc:
            if isinstance(exc,InferenceError):raise
            raise InferenceError("INVALID_SCHEMA","Timestamp provenance không hợp lệ.") from exc
        key=fixture_key(season,home.team,away.team)
        check(key not in seen,"DUPLICATE_FIXTURE","Nhiều provider IDs ánh xạ cùng fixture; cần review định danh.")
        seen.add(key)
        payload=dict(canonical_key=key,provider=str(home.provider),provider_match_id=str(provider_id),date=str(home.date),
            season=season,home_team=home.team,away_team=away.team,status="completed",fetched_at=str(home.fetched_at),
            statistics_version=str(home.statistics_version),quality_status="verified",kickoff_utc=kickoff,rows=[])
        for row in (home,away):
            payload["rows"].append(dict(team=row.team,is_home=int(row.is_home),gf=int(row.gf),ga=int(row.ga),
                xg=float(row.xg),xga=float(row.xga),sh=int(row.sh),sot=int(row.sot)))
        semantic={k:v for k,v in payload.items() if k!="fetched_at"}
        payload["semantic_sha256"]=hashlib.sha256(json.dumps(semantic,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        result.append(payload)
    return result


def refresh_history(provider: CompletedMatchProvider,store_path=HISTORY_PATH,*,schedule=None,coverage=None,manifest_dir=None):
    path=Path(store_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    run=dict(run_id=uuid.uuid4().hex,timestamp=utc_now(),status="started",automatic=False,model_retrained=False)
    # Bootstrap schema trước transaction; mọi thay đổi fixtures/schedule/coverage là một commit.
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(SCHEMA)
        try:
            run["source"]=provider.source_identity()
            records=validate_completed_rows(provider.fetch_completed())
            name=records[0]["provider"]
            connection.execute("BEGIN IMMEDIATE")  # Serialize writers trước kiểm tra provider/dedup.
            old={row[0] for row in connection.execute("SELECT DISTINCT provider FROM matches")}
            check(not old or old=={name},"INCOMPATIBLE_PROVIDER","Không tự trộn providers; nhập provider mới vào kho staging riêng.")
            schedules=validate_schedule(schedule or [],name)
            coverages=validate_coverage(coverage or [],name)
            inserted=unchanged=0
            with connection:
                for record in records:
                    existing=connection.execute("SELECT semantic_sha256 FROM matches WHERE canonical_key=?",(record["canonical_key"],)).fetchone()
                    if existing:
                        check(existing[0]==record["semantic_sha256"],"CORRECTION_REQUIRES_REVIEW",
                              "Completed record đã xác minh khác nội dung/version/ID; không tự ghi đè. Review correction và tạo kho mới có version.",canonical_key=record["canonical_key"])
                        unchanged+=1
                        continue
                    connection.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?)",tuple(record[k] for k in (
                        "canonical_key","provider","provider_match_id","date","season","home_team","away_team","semantic_sha256"))
                        +(json.dumps(record,ensure_ascii=False,allow_nan=False),))
                    for row in record["rows"]:
                        connection.execute("INSERT INTO team_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (record["canonical_key"],row["team"],record["date"],record["season"],row["is_home"],
                             row["gf"],row["ga"],row["xg"],row["xga"],row["sh"],row["sot"]))
                    inserted+=1
                for item in schedules:
                    connection.execute("INSERT INTO schedule VALUES (?,?,?) ON CONFLICT(canonical_key) DO UPDATE SET provider=excluded.provider,payload=excluded.payload",
                                       (item["canonical_key"],name,json.dumps(item,ensure_ascii=False)))
                for item in coverages:
                    for key in item["eligible_match_keys"]:
                        found=connection.execute("SELECT date,season FROM team_records WHERE canonical_key=? AND team=?",(key,item["team"])).fetchone()
                        check(found is not None and found[0]<=item["verified_through"] and found[1]>=item["stint_start_season"],
                              "INCOMPLETE_HISTORY","Coverage tham chiếu trận thiếu/không đủ điều kiện.",team=item["team"],canonical_key=key)
                    connection.execute("INSERT INTO coverage VALUES (?,?,?,?) ON CONFLICT(team,season) DO UPDATE SET provider=excluded.provider,payload=excluded.payload",
                                       (item["team"],item["season"],name,json.dumps(item,ensure_ascii=False)))
                run.update(status="success",provider=name,input_matches=len(records),inserted_matches=inserted,
                           unchanged_matches=unchanged,schedule_records=len(schedules),coverage_records=len(coverages))
                connection.execute("INSERT INTO refresh_runs VALUES (?,?,?,?)",(run["run_id"],run["timestamp"],run["status"],json.dumps(run,ensure_ascii=False)))
        except Exception as exc:
            connection.rollback()
            error=exc if isinstance(exc,InferenceError) else InferenceError("REFRESH_FAILED","Refresh bị từ chối; transaction fixtures/schedule/coverage đã rollback.")
            run.update(status="error",error_code=error.code,inserted_matches=0,transaction_rolled_back=True)
            with connection:
                connection.execute("INSERT INTO refresh_runs VALUES (?,?,?,?)",(run["run_id"],run["timestamp"],run["status"],json.dumps(run,ensure_ascii=False)))
            if manifest_dir is not None:write_json(Path(manifest_dir)/(run["run_id"]+".json"),run,exclusive=True)
            raise error from exc
    if manifest_dir is not None:write_json(Path(manifest_dir)/(run["run_id"]+".json"),run,exclusive=True)
    return run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("bootstrap-snapshot","import-csv","status"):
        mode=sub.add_parser(name)
        mode.add_argument("--store",type=Path,default=HISTORY_PATH)
        if name=="import-csv":
            mode.add_argument("--csv",type=Path,required=True)
            mode.add_argument("--schedule",type=Path,help="JSON lịch đã xác minh, không tự lấy qua mạng.")
            mode.add_argument("--coverage",type=Path,help="JSON xác nhận đầy đủ từng đội do backend quản lý.")
    args=parser.parse_args()
    def run():
        if args.command=="status":return HistoryStore(args.store).data_status()
        schedule=coverage=None
        if args.command=="import-csv":
            try:
                schedule=json.loads(args.schedule.read_text(encoding="utf-8")) if args.schedule else None
                coverage=json.loads(args.coverage.read_text(encoding="utf-8")) if args.coverage else None
            except (OSError,ValueError) as exc:
                raise InferenceError("INVALID_SCHEMA","Không đọc được schedule/coverage JSON.") from exc
        provider=FrozenSnapshotProvider() if args.command=="bootstrap-snapshot" else CSVProvider(args.csv)
        return refresh_history(provider,args.store,schedule=schedule,coverage=coverage,manifest_dir=OUTPUT_DIR/"refresh_runs")
    return cli_output(run)


if __name__ == "__main__":
    raise SystemExit(main())
