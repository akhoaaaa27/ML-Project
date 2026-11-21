"""Dữ liệu nhỏ nhân tạo; không phải lịch thi đấu hoặc kết quả thật."""

from datetime import date,timedelta
import pandas as pd

from scripts.inference.common import fixture_key
from scripts.inference.data_refresh import refresh_history
from scripts.inference.history_store import HistoryStore

POLICY={"test_provider":dict(replay_approved=True,production_approved=True,compatible_with_training=True,
    reviewed_by="synthetic_test_only",compatibility_review="Fixture nhân tạo, không cấp phép provider thực.",xg_family="synthetic")}


def completed_rows(home="Barcelona",away="Real Madrid",day="2026-10-08",season=2026,provider_id="1",provider="test_provider",value=1.0):
    common=dict(provider=provider,provider_match_id=provider_id,season=season,date=day,status="completed",
        fetched_at="2026-11-21T00:00:00+00:00",statistics_version="synthetic-v1",quality_status="verified")
    return [dict(common,team=home,opponent=away,is_home=1,gf=2,ga=1,xg=value,xga=.7,sh=12,sot=4),
            dict(common,team=away,opponent=home,is_home=0,gf=1,ga=2,xg=.7,xga=value,sh=8,sot=2)]


def rows_fixture():
    opponents=["Real Madrid","Valencia","Sevilla","Girona","Getafe","Mallorca","Athletic Club"]
    rows=[]
    for i,opponent in enumerate(opponents):
        day=(date(2026,10,8)+timedelta(days=i*7)).isoformat()
        rows.extend(completed_rows(away=opponent,day=day,provider_id=f"barca-{i}",value=.4+i*.2))
    for i,opponent in enumerate(["Valencia","Sevilla","Girona","Getafe","Mallorca","Athletic Club","Osasuna"]):
        day=(date(2026,10,9)+timedelta(days=i*7)).isoformat()
        rows.extend(completed_rows(home="Real Madrid",away=opponent,day=day,provider_id=f"madrid-{i}",value=.8+i*.15))
    return pd.DataFrame(rows)


class MemoryProvider:
    def __init__(self,frame):self.frame=frame
    def fetch_completed(self):return self.frame.copy(deep=True)
    def source_identity(self):return dict(kind="synthetic_fixture",sha256="not_real_data")


def store_fixture(path,*,with_schedule=False,with_coverage=False):
    rows=rows_fixture()
    schedule=[];coverage=[]
    if with_schedule:
        schedule=[dict(provider="test_provider",provider_fixture_id="future-test-only",home_team="Real Madrid",away_team="Barcelona",
            date="2026-11-28",season=2026,status="scheduled",quality_status="verified",verified_by="synthetic_test_only",
            fetched_at="2026-11-21T00:00:00+00:00")]
    if with_coverage:
        for team in ["Real Madrid","Barcelona"]:
            subset=rows.loc[rows.team.eq(team)]
            keys=[]
            for row in subset.itertuples():
                home,away=(row.team,row.opponent) if row.is_home else (row.opponent,row.team)
                keys.append(fixture_key(int(row.season),home,away))
            coverage.append(dict(team=team,season=2026,provider="test_provider",stint_start_season=2026,
                verified_through="2026-11-20",eligible_match_keys=keys,verified_by="synthetic_test_only",
                reviewed_at="2026-11-21T00:00:00+00:00"))
    refresh_history(MemoryProvider(rows),path,schedule=schedule,coverage=coverage)
    return HistoryStore(path,provider_policy=POLICY)
