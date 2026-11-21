"""Xây đúng hai dòng X trước trận, không yêu cầu target fixture hoặc prepare_features."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from scripts.prepare_training_features import FEATURES, HISTORY_FEATURES, OWN_HISTORY, read_history_config
from .common import check, fixture_key, parse_date, validate_fixture

ROLLING_SOURCES = {"xg_avg5":"xg", "xga_avg5":"xga", "gf_avg5":"gf", "ga_avg5":"ga", "shot_avg5":"sh", "sot_avg5":"sot"}


@dataclass
class FixtureFeatures:
    X: pd.DataFrame
    history: dict
    fixture: dict
    cutoff: str


def stint_history(records,season):
    if records.empty:
        return records.copy()
    # Stint cuối của các mùa liên tiếp; gap từ mùa cuối tới fixture cũng reset.
    records=records.sort_values(["date","canonical_key"],kind="stable")
    check(not records.date.duplicated().any(),"AMBIGUOUS_HISTORY","Cùng đội có nhiều trận cùng ngày, không suy diễn thứ tự kickoff.")
    seasons=records.season.to_numpy(dtype=int)
    check(np.all(np.diff(seasons)>=0),"INVALID_HISTORY","Ngày và season không tăng nhất quán.")
    if season-int(seasons[-1])>1:
        return records.iloc[:0].copy()
    gaps=np.flatnonzero(np.diff(seasons)>1)
    return records.iloc[int(gaps[-1])+1:] if len(gaps) else records.copy()


def build_fixture_features(home_team,away_team,match_date,season,history,*,prediction_cutoff=None,temporal_policy="date_only"):
    home,away,day=validate_fixture(home_team,away_team,match_date,season)
    check(temporal_policy=="date_only","UNSUPPORTED_TEMPORAL_POLICY",
          "Replay dùng ngày nghiêm ngặt. Kickoff mới chỉ lưu provenance, chưa bật thay đổi semantics.")
    cutoff=day if prediction_cutoff is None else parse_date(prediction_cutoff)
    check(cutoff<=day,"INVALID_CUTOFF","Prediction cutoff không được sau fixture date.")
    key=fixture_key(season,home,away)
    config=read_history_config()
    own=[]; audit={}
    for team,is_home in ((home,1),(away,0)):
        all_prior=history.prior_team_records(team,season,cutoff.isoformat(),key)
        records=stint_history(all_prior,season)
        check(records.empty or (records.date.lt(cutoff.isoformat()).all() and records.canonical_key.ne(key).all()),
              "INVALID_HISTORY","Lịch sử chứa current/future fixture.")
        count=len(records)
        row=dict(is_home=is_home,matches_seen=count,short_history=int(count<config.short_history_min))
        if count:
            numeric=records[["xg","xga","gf","ga","sh","sot"]].to_numpy(dtype=float)
            check(np.isfinite(numeric).all() and (numeric>=0).all(),"INVALID_NUMERIC","Lịch sử có outcome thiếu/không hợp lệ; không impute outcomes.")
        for feature,source in ROLLING_SOURCES.items():
            row[feature]=float(records.tail(config.window)[source].mean()) if count else np.nan
        # NaN ở zero-history tương đương khôi phục verified priors Phase 3;
        # không đưa hằng số prior hoặc target giả vào API completed-match.
        own.append(row)
        audit[team]=dict(matches_seen=count,short_history=int(count<5),
            first_date=None if not count else records.date.iloc[0],last_date=None if not count else records.date.iloc[-1],
            stint_start_season=None if not count else int(records.season.iloc[0]),
            eligible_match_keys=records.canonical_key.tolist(),rolling_match_keys=records.tail(5).canonical_key.tolist(),
            available_prior_last_date=None if all_prior.empty else all_prior.date.iloc[-1])
    rows=[]
    for i,row in enumerate(own):
        opponent=own[1-i]
        rows.append(dict(row,opponent_xg_avg5=opponent["xg_avg5"],opponent_xga_avg5=opponent["xga_avg5"],
                         opponent_matches_seen=opponent["matches_seen"],opponent_short_history=opponent["short_history"]))
    X=pd.DataFrame(rows,columns=list(FEATURES),dtype=float)
    check(list(X.columns)==list(FEATURES) and X.shape==(2,13),"FEATURE_SCHEMA_MISMATCH","Phải đúng hai dòng Home/Away và 13 features.")
    check(not np.isinf(X.to_numpy()).any(),"INVALID_NUMERIC","X không được vô hạn.")
    for i,row in enumerate(own):
        expected_nan=set(OWN_HISTORY) if row["matches_seen"]==0 else set()
        if own[1-i]["matches_seen"]==0:expected_nan|={"opponent_xg_avg5","opponent_xga_avg5"}
        check(set(X.columns[X.iloc[i].isna()])==expected_nan,"INVALID_NUMERIC","Chỉ zero-history đã xác định mới được NaN.")
    return FixtureFeatures(X,audit,dict(home_team=home,away_team=away,match_date=match_date,season=season,canonical_key=key),cutoff.isoformat())
