"""Adapter riêng: box scores match-level, fallback shot xG chỉ khi đủ coverage."""

from datetime import datetime,timezone
import math

import pandas as pd

from scripts.inference.data_refresh import validate_completed_rows
from scripts.inference.common import InferenceError
from .sample_selector import provider_identity
from .strikerapi_client import POCError,need,digest


def number(value,*,integer=False,probability=False):
    return type(value) in (int,float) and math.isfinite(value) and value>=0 and (not integer or value%1==0) and (not probability or value<=1)


def box_scores(data,identity):
    need(isinstance(data.get("team_stats"),list),"INVALID_STATS_SCHEMA","get_game thiếu team_stats array.")
    rows=data["team_stats"]
    expected=[identity["home_team_id"],identity["away_team_id"]]
    need(len(rows)==2 and [row.get("team_id") for row in rows].count(expected[0])==1
         and [row.get("team_id") for row in rows].count(expected[1])==1,"INVALID_STATS_SCHEMA","Box score phải đủ đúng hai team IDs.")
    result=[next(row for row in rows if row["team_id"]==team) for team in expected]
    need(result[0].get("home") is True and result[1].get("home") is False,"INVALID_STATS_SCHEMA","Home/Away box scores không khớp.")
    return result


def aggregate_shot_xg(data,reference,identity,stats):
    """Không dùng outcome để đoán SOT, không gán totals chung cho một đội."""
    need(not data.get("goals_only") and not data.get("goals_only_note"),"INCOMPLETE_SHOTS","Shot map chỉ có goals, không đủ shots.")
    need(not any(data.get(k) for k in ("truncated","has_more","next_offset")),"INCOMPLETE_SHOTS","Shot map bị cắt hoặc còn trang chưa lấy.")
    shots=data.get("shots");totals=data.get("totals")
    need(isinstance(shots,list) and isinstance(totals,dict),"INCOMPLETE_SHOTS","Không có đầy đủ shot records/totals.")
    total=sum(row["shots"] for row in stats)
    need(len(shots)<2000 and data.get("shots_total")==total and totals.get("shots")==total
         and totals.get("located")==total and len(shots)==total and data.get("unlocated_shots",0)==0,
         "INCOMPLETE_SHOTS","Shot counts/located/unlocated không đủ khớp box scores; không impute xG thiếu.")
    abbreviations=[identity["home_abbrev"],identity["away_abbrev"]]
    need(all(isinstance(a,str) and a for a in abbreviations) and abbreviations[0]!=abbreviations[1],
         "UNVERIFIED_SHOT_TEAM","Chưa xác minh được mã team của shots từ fixture identity.")
    sums=[0.,0.];counts=[0,0];seen=set()
    for shot in shots:
        need(shot.get("game_id")==identity["provider_match_id"] and shot.get("date")==reference["date"],
             "INCOMPLETE_SHOTS","Shot thuộc game/date khác, không cộng lẫn mùa hoặc fixture.")
        need(shot.get("team") in abbreviations,"UNVERIFIED_SHOT_TEAM","Shot team không khớp hai abbrev đã xác minh.")
        need(number(shot.get("xg"),probability=True) and number(shot.get("x")) and number(shot.get("y")),
             "INCOMPLETE_SHOTS","Shot thiếu xG hoặc location; không coi thiếu xG là 0.")
        key=digest(shot)
        need(key not in seen,"DUPLICATE_SHOT","Shot records trùng/không phân biệt được; cần review, không dedup ngầm.")
        seen.add(key);position=abbreviations.index(shot["team"])
        sums[position]+=shot["xg"];counts[position]+=1
    need(counts==[row["shots"] for row in stats],"INCOMPLETE_SHOTS","Số shots từng team không khớp box scores.")
    need(number(totals.get("xg")) and abs(sum(sums)-totals["xg"])<=.011,
         "INCOMPLETE_SHOTS","Tổng shot xG khác tổng công bố quá dung sai làm tròn 0.01+float.")
    return sums,dict(shot_records=len(shots),located=totals["located"],unlocated=data.get("unlocated_shots",0),
        per_team_shot_counts=counts,per_team_raw_shot_xg=sums,published_combined_xg=totals["xg"],
        combined_rounding_atol=.011,sot_inferred_from_outcome=False)


def normalize_game(data,reference,*,provider_game_id,fetched_at,shot_map=None):
    """Không có import-ready rows khi bất kỳ mandatory statistic nào chưa xác minh."""
    diagnostic=dict(status="unavailable",provider="strikerapi",production_approved=False,
        provider_compatibility_approved=False,missing_fields=[],invalid_fields=[],needs_shot_map=False,
        provider_revision_id_available=False,xg_is_as_of=False)
    try:
        need(isinstance(data,dict) and isinstance(data.get("game"),dict),"INVALID_STATS_SCHEMA","get_game thiếu game object.")
        identity=provider_identity(data["game"],reference,expected_game_id=provider_game_id)
        diagnostic["identity"]=identity
        stats=box_scores(data,identity)
        for position,row in enumerate(stats):
            side="home" if position==0 else "away"
            for field in ("goals","shots","shots_on_target","xg"):
                value=row.get(field)
                if value is None:diagnostic["missing_fields"].append(side+"."+field)
                elif not number(value,integer=field!="xg"):diagnostic["invalid_fields"].append(side+"."+field)
            if number(row.get("shots"),integer=True) and number(row.get("shots_on_target"),integer=True) and row["shots"]<row["shots_on_target"]:
                diagnostic["invalid_fields"].append(side+".shots_lt_sot")
            if number(row.get("goals"),integer=True) and row["goals"]!=reference["home_goals" if position==0 else "away_goals"]:
                diagnostic["invalid_fields"].append(side+".goals_mismatch")
        if diagnostic["invalid_fields"]:return None,diagnostic
        non_xg=[name for name in diagnostic["missing_fields"] if not name.endswith(".xg")]
        if non_xg:
            diagnostic["limitation"]="Thiếu match-level goals/shots/SOT; shot outcome không được dùng để suy đoán SOT."
            return None,diagnostic
        published=[row.get("xg") for row in stats]
        if any(value is None for value in published):
            diagnostic["needs_shot_map"]=True
            if shot_map is None:return None,diagnostic
            values,coverage=aggregate_shot_xg(shot_map,reference,identity,stats)
            diagnostic.update(xg_source="raw_shot_aggregation_both_teams",shot_coverage=coverage,
                              published_team_xg=published,rounding_difference_not_forced_to_zero=True)
        else:
            values=published
            diagnostic["xg_source"]="get_game.published_team_stats.xg"
        stamp=datetime.fromisoformat(fetched_at.replace("Z","+00:00"))
        need(stamp.tzinfo is not None,"INVALID_PROVENANCE","fetched_at phải có timezone.")
        version="response_sha256:"+digest(dict(game=data["game"],team_stats=stats,shot_map=shot_map))
        records=[]
        for i,row in enumerate(stats):
            team=reference["home_team" if i==0 else "away_team"]
            opponent=reference["away_team" if i==0 else "home_team"]
            records.append(dict(provider="strikerapi",provider_match_id=provider_game_id,season=reference["season"],date=reference["date"],
                team=team,opponent=opponent,is_home=1-i,status="completed",gf=int(row["goals"]),ga=int(stats[1-i]["goals"]),
                xg=float(values[i]),xga=float(values[1-i]),sh=int(row["shots"]),sot=int(row["shots_on_target"]),
                fetched_at=stamp.astimezone(timezone.utc).isoformat(),statistics_version=version,quality_status="verified"))
        if identity["kickoff_utc"]:
            for record in records:record["kickoff_utc"]=identity["kickoff_utc"]
        table=pd.DataFrame(records)
        validate_completed_rows(table)  # Chỉ adapter output đã đủ outcomes, không đổi Phase 8 schema.
        diagnostic.update(status="validated_sample_only",import_ready=True,quality_status_meaning="mandatory_identity_and_statistics_validated_not_provider_equivalence",
            local_statistics_version=version,provider_revision_id_available=False)
        return table,diagnostic
    except (POCError,InferenceError,ValueError,TypeError,KeyError) as exc:
        diagnostic.update(status="unavailable",import_ready=False,error_code=exc.code if isinstance(exc,(POCError,InferenceError)) else "INVALID_STATS_SCHEMA")
        return None,diagnostic
