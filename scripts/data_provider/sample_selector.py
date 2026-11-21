"""Chọn một trận Development và kế hoạch mở rộng offline; không gọi API."""

from datetime import datetime
from zoneinfo import ZoneInfo
import math

import pandas as pd

from scripts.prepare_training_features import load_dataset
from scripts.inference.common import InferenceError,resolve_team
from .strikerapi_client import POCError,need


def canonical_team(value):
    try:return resolve_team(value)
    except InferenceError:raise POCError("UNKNOWN_PROVIDER_TEAM","Tên đội provider chưa có alias tường minh; không fuzzy matching.") from None


def reference_fixture(frame,match_id):
    rows=frame.loc[frame.match_id.eq(match_id)]
    need(len(rows)==2 and set(rows.is_home)=={0,1},"INVALID_REFERENCE","Fixture FBref phải có đúng hai phía.")
    values=rows[["xg","xga","gf","ga","sh","sot"]].to_numpy(dtype=float)
    need(pd.notna(values).all() and all(math.isfinite(v) and v>=0 for v in values.ravel()),"INVALID_REFERENCE","Thống kê FBref không hợp lệ.")
    home=rows.loc[rows.is_home.eq(1)].iloc[0];away=rows.loc[rows.is_home.eq(0)].iloc[0]
    return dict(local_match_id=int(match_id),season=int(home.season),date=str(home.date),home_team=str(home.team),
        away_team=str(away.team),home_goals=int(home.gf),away_goals=int(away.gf),
        source_rows=[int(home.name),int(away.name)],total_fbref_xg=float(home.xg+away.xg))


def select_reference(frame=None,local_match_id=None):
    frame=load_dataset() if frame is None else frame
    candidates=frame.loc[frame.season.isin([2019,2020,2021,2022,2023])&frame.is_home.eq(1)].sort_values(["date","match_id"],kind="stable")
    if local_match_id is None:
        preferred=candidates.loc[candidates.season.eq(2023)]
        local_match_id=int((preferred if not preferred.empty else candidates).iloc[0].match_id)
    need(local_match_id in set(candidates.match_id),"INVALID_REFERENCE","Chỉ chọn một completed fixture thuộc Development 2019–2023.")
    return reference_fixture(frame,local_match_id)


def discovery_params(reference):
    return dict(league="laliga",season=reference["season"],date=reference["date"],timezone="Europe/Madrid",status="final",limit=20)


def provider_identity(game,reference,*,expected_game_id=None):
    try:
        need(isinstance(game,dict) and isinstance(game["game_id"],str) and bool(game["game_id"]),"INVALID_GAME_ID","Provider không có game_id string hợp lệ.")
        need(expected_game_id is None or game["game_id"]==expected_game_id,"FIXTURE_MISMATCH","game_id trả về khác ID đã ghép.")
        need(game["status"]=="final" and game.get("status_detail") in (None,"FT"),"NONFINAL_FIXTURE","Chỉ nhận final/FT, không trộn extra time hoặc shootout.")
        need(game.get("league","laliga")=="laliga","FIXTURE_MISMATCH","Response không thuộc La Liga.")
        need(type(game["season"]) in (int,float) and game["season"]==reference["season"],"FIXTURE_MISMATCH","Season provider không khớp FBref.")
        home,away=game["home"],game["away"]
        need(canonical_team(home["name"])==reference["home_team"] and canonical_team(away["name"])==reference["away_team"],
             "FIXTURE_MISMATCH","Home/Away provider không khớp canonical teams của FBref.")
        need(home["team_id"]!=away["team_id"] and all(isinstance(side["team_id"],str) and side["team_id"] for side in [home,away]),
             "INVALID_GAME_ID","Không xác định được hai team IDs độc lập.")
        need(game["date"]==reference["date"],"TIMEZONE_AMBIGUOUS","Ngày provider khác ngày FBref; dừng để review, không tự ghép lệch ngày.")
        kickoff=game.get("starts_at")
        if kickoff:
            stamp=datetime.fromisoformat(kickoff.replace("Z","+00:00"))
            need(stamp.tzinfo is not None,"TIMEZONE_AMBIGUOUS","Kickoff không có timezone.")
            need(stamp.astimezone(ZoneInfo("Europe/Madrid")).date().isoformat()==reference["date"],
                 "TIMEZONE_AMBIGUOUS","Kickoff đổi sang Europe/Madrid không cùng ngày nguồn; không đoán thứ tự/date.")
        for side,field in ((home,"home_goals"),(away,"away_goals")):
            score=side["score"]
            need(type(score) in (int,float) and math.isfinite(score) and score>=0 and score%1==0
                 and score==reference[field],"SCORE_MISMATCH","Final score không khớp FBref; không thay fixture khác ngầm.")
        return dict(provider_match_id=game["game_id"],home_team_id=home["team_id"],away_team_id=away["team_id"],
            home_abbrev=home.get("abbrev"),away_abbrev=away.get("abbrev"),kickoff_utc=kickoff,
            date_match_policy="exact_reference_date_and_verified_kickoff_local_date_when_present")
    except POCError:raise
    except (KeyError,ValueError,TypeError):raise POCError("UNEXPECTED_GAME_SCHEMA","Thiếu/sai trường identity trong game response.") from None


def match_fixture(data,reference):
    need(isinstance(data,dict) and isinstance(data.get("games"),list),"UNEXPECTED_GAME_SCHEMA","list_games thiếu games array.")
    need(data.get("count")==len(data["games"]),"UNEXPECTED_GAME_SCHEMA","Count không khớp số game records.")
    ids=[game.get("game_id") for game in data["games"]]
    need(len(ids)==len(set(ids)),"DUPLICATE_FIXTURE","Provider trả game_id trùng.")
    candidates=[];rejections=[]
    for game in data["games"]:
        try:candidates.append((game,provider_identity(game,reference)))
        except POCError as exc:rejections.append(exc.code)
    need(len(candidates)==1,"NO_CONFIDENT_MATCH","Không có đúng một fixture ghép chắc chắn; không tự gọi trang khác hoặc đổi trận.")
    return dict(game=candidates[0][0],identity=candidates[0][1],rejection_codes=rejections,
                next_offset=data.get("next_offset"),automatic_pagination=False)


def expanded_plan(frame=None,n=24):
    frame=load_dataset() if frame is None else frame
    records=[reference_fixture(frame,int(row.match_id)) for row in frame.loc[frame.is_home.eq(1)&frame.season.between(2019,2023)].sort_values(["season","date","match_id"]).itertuples()]
    for row in records:row["xg_range"]="lt_2" if row["total_fbref_xg"]<2 else "2_to_4" if row["total_fbref_xg"]<4 else "ge_4"
    pools={key:list(group) for key,group in __import__("itertools").groupby(sorted(records,key=lambda r:(r["season"],r["xg_range"],r["date"],r["local_match_id"])),key=lambda r:(r["season"],r["xg_range"]))}
    chosen=[]
    while len(chosen)<n:
        added=False
        for key in sorted(pools):
            if pools[key] and len(chosen)<n:chosen.append(pools[key].pop(0));added=True
        if not added:break
    return pd.DataFrame([{k:v for k,v in r.items() if k!="source_rows"} for r in chosen])
