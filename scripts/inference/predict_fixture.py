"""API Python/CLI suy luận offline; không fit, không tuning và không đọc target fixture."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from .build_fixture_features import build_fixture_features
from .common import (HISTORY_PATH, MODEL_DIR, TEAM_IDS, InferenceError, check, cli_output,
                     parse_date, validate_fixture)
from .history_store import HistoryStore, load_provider_policy
from .model_artifact import load_trusted_pipeline

MAX_TEAM_HISTORY_AGE_DAYS = 45  # Gate vận hành, không phải feature/model hyperparameter.


class FixturePredictor:
    """Load trusted artifact một lần khi backend khởi động; predict chỉ đọc."""
    def __init__(self,history: HistoryStore,*,model_directory=MODEL_DIR,trusted_model_directory=MODEL_DIR):
        check(isinstance(history,HistoryStore),"INVALID_HISTORY","history phải là HistoryStore đã xác minh.")
        self.history=history
        self.pipeline,self.metadata=load_trusted_pipeline(model_directory,trusted_directory=trusted_model_directory)

    def _upcoming_gates(self,built,season,match_date):
        # Kiểm tra riêng từng đội; global max(date) không đủ xác nhận độ mới.
        cutoff=parse_date(built.cutoff)
        for team,audit in built.history.items():
            latest=audit["available_prior_last_date"]
            if latest is not None:
                age=(parse_date(match_date)-parse_date(latest)).days
                check(age<=MAX_TEAM_HISTORY_AGE_DAYS,"STALE_DATA","Lịch sử đội quá cũ cho yêu cầu upcoming.",
                      team=team,last_match_date=latest,history_cutoff=built.cutoff,age_days=age,max_age_days=MAX_TEAM_HISTORY_AGE_DAYS)
        provider,policy=self.history.check_provider("upcoming")
        check(not self.history.query("SELECT canonical_key FROM matches WHERE canonical_key=?",(built.fixture["canonical_key"],)),
              "INVALID_FIXTURE","Fixture đã completed trong history; dùng replay, không gắn nhãn upcoming.")
        schedule=self.history.schedule_fixture(built.fixture["home_team"],built.fixture["away_team"],match_date,season)
        fetched=datetime.fromisoformat(schedule["fetched_at"]).astimezone(timezone.utc)
        now=datetime.now(timezone.utc)
        check(cutoff-timedelta(days=1)<=fetched.date()<=cutoff and fetched<=now,
              "FIXTURE_UNVERIFIED","Lịch thi đấu chưa được xác minh lại gần cutoff hoặc có timestamp tương lai.")
        for team,audit in built.history.items():
            coverage=self.history.coverage_for(team,season)
            reviewed=datetime.fromisoformat(coverage["reviewed_at"]).astimezone(timezone.utc)
            check(cutoff-timedelta(days=1)<=reviewed.date()<=cutoff and reviewed<=now,
                  "COVERAGE_UNVERIFIED","Coverage chưa được review lại gần cutoff.",team=team)
            check(cutoff-timedelta(days=1)<=parse_date(coverage["verified_through"])<=cutoff,"COVERAGE_UNVERIFIED",
                  "Coverage từng đội chưa xác nhận đến ngày trước cutoff.",team=team)
            check(set(coverage["eligible_match_keys"])==set(audit["eligible_match_keys"]),"INCOMPLETE_HISTORY",
                  "Lịch sử thiếu/thừa trận so với danh sách completed matches được xác nhận.",team=team)
            if audit["matches_seen"]:
                check(coverage["stint_start_season"]==audit["stint_start_season"],"INCOMPLETE_HISTORY","Thiếu phần đầu stint được xác nhận.",team=team)
            else:
                check(coverage["stint_start_season"]==season and not coverage["eligible_match_keys"],"INCOMPLETE_HISTORY",
                      "Zero-history cần xác nhận explicit mùa lên hạng/khởi đầu stint.",team=team)
            # Không suy luận đã đủ form nếu trước target còn fixture chưa hoàn tất/hoãn.
            schedules=self.history.query("SELECT payload FROM schedule")
            import json
            for record in schedules:
                other=json.loads(record["payload"])
                if other["canonical_key"]==built.fixture["canonical_key"] or team not in (other["home_team"],other["away_team"]):
                    continue
                check(not (other["date"]<match_date and other["status"] in ("scheduled","postponed")),
                      "COVERAGE_UNVERIFIED","Có trận trước target chưa hoàn tất/hoãn, chưa xác nhận đủ lịch sử.",team=team)
                if other["date"]<built.cutoff and other["status"]=="completed":
                    check(other["canonical_key"] in audit["eligible_match_keys"] or other["season"]<coverage["stint_start_season"],
                          "INCOMPLETE_HISTORY","Schedule có trận completed nhưng store thiếu thống kê.",team=team)
        return provider,policy,schedule

    def predict(self,home_team,away_team,match_date,season,*,mode="replay",prediction_cutoff=None):
        try:
            check(mode in ("replay","upcoming"),"INVALID_MODE","Mode chỉ nhận replay/upcoming.")
            home,away,day=validate_fixture(home_team,away_team,match_date,season)
            cutoff=prediction_cutoff
            if mode=="upcoming":
                today=datetime.now(timezone.utc).date()
                check(day>=today,"INVALID_FIXTURE","Upcoming không nhận fixture đã qua ngày hiện tại UTC; dùng replay.")
                if cutoff is None:cutoff=min(day,today).isoformat()
                check(parse_date(cutoff)==min(day,today),"INVALID_CUTOFF",
                      "Upcoming yêu cầu cutoff ngày hiện tại UTC; không dùng cutoff cũ/tương lai để vượt freshness.")
            if mode=="replay":
                identity=self.history.fixture_identity(home,away,match_date,season)
                provider,policy=self.history.check_provider("replay")
            built=build_fixture_features(home,away,match_date,season,self.history,prediction_cutoff=cutoff)
            if mode=="upcoming":
                provider,policy,schedule=self._upcoming_gates(built,season,match_date)
            else:
                schedule=None
            with threadpool_limits(limits=1):
                raw=np.asarray(self.pipeline.predict(built.X),dtype=float)
            check(raw.shape==(2,) and np.isfinite(raw).all(),"INVALID_NUMERIC","Estimator trả kết quả không hữu hạn hoặc sai shape.")
            clipped=np.maximum(0,raw)
            keys=[key for v in built.history.values() for key in v["rolling_match_keys"]]
            provenance=self.history.provenance(keys)
            return dict(status="success",mode=mode,home_team=home,away_team=away,
                home_team_id=TEAM_IDS[home],away_team_id=TEAM_IDS[away],match_date=match_date,season=season,
                canonical_fixture_key=built.fixture["canonical_key"],home_xg=float(clipped[0]),away_xg=float(clipped[1]),
                model="Linear Regression",model_version=self.metadata["model_version"],
                target="total_team_match_xg",data_status="verified_historical_snapshot" if mode=="replay" else "verified",
                history_cutoff=built.cutoff,temporal_policy="date_only_strict_before_cutoff",provider=provider,
                artifact_sha256=self.metadata["artifact_sha256"],
                schedule_status="historical_completed_fixture" if mode=="replay" else "verified_scheduled",
                schedule_provider_fixture_id=None if schedule is None else schedule["provider_fixture_id"],
                history_summary={team:{k:v for k,v in value.items() if k!="eligible_match_keys"} for team,value in built.history.items()},
                history_provenance=provenance,clipping_applied=bool((raw<0).any()))
        except InferenceError as exc:
            return exc.result(mode)


def predict_fixture(home_team,away_team,match_date,season,history,mode="replay",*,prediction_cutoff=None,
                    model_directory=MODEL_DIR,trusted_model_directory=MODEL_DIR):
    """Facade JSON-safe; backend dùng FixturePredictor để tái sử dụng model đã load."""
    try:
        predictor=FixturePredictor(history,model_directory=model_directory,trusted_model_directory=trusted_model_directory)
        return predictor.predict(home_team,away_team,match_date,season,mode=mode,prediction_cutoff=prediction_cutoff)
    except InferenceError as exc:
        return exc.result(mode)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["replay","upcoming"])
    parser.add_argument("--home")
    parser.add_argument("--away")
    parser.add_argument("--date")
    parser.add_argument("--season",type=int)
    parser.add_argument("--match-id",type=int,help="Chỉ legacy-local snapshot ID cho replay, không phải provider ID.")
    parser.add_argument("--cutoff")
    parser.add_argument("--store",type=Path,default=HISTORY_PATH)
    parser.add_argument("--provider-config",type=Path,help="Policy do quản trị kiểm soát; không nhận từ frontend.")
    args=parser.parse_args()
    def run():
        history=HistoryStore(args.store,provider_policy=load_provider_policy(args.provider_config))
        if args.match_id is not None:
            check(args.mode=="replay" and not any(v is not None for v in (args.home,args.away,args.date,args.season)),
                  "INVALID_FIXTURE","match-id chỉ dùng riêng cho snapshot replay.")
            fixture=history.snapshot_fixture(args.match_id)
            home,away,day,season=(fixture[k] for k in ("home_team","away_team","date","season"))
        else:
            check(all(v is not None for v in (args.home,args.away,args.date,args.season)),"INVALID_FIXTURE","Thiếu home/away/date/season.")
            home,away,day,season=args.home,args.away,args.date,args.season
        result=predict_fixture(home,away,day,season,history,mode=args.mode,prediction_cutoff=args.cutoff)
        return result
    result_holder={}
    def execute():
        result_holder["value"]=run()
        return result_holder["value"]
    code=cli_output(execute)
    return 2 if result_holder.get("value",{}).get("status")=="error" else code


if __name__=="__main__":
    raise SystemExit(main())
