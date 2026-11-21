"""Responses tổng hợp chỉ dùng offline tests; không phải dữ liệu StrikerAPI thật."""

import copy
import json
from unittest.mock import Mock

from scripts.data_provider.strikerapi_client import CONTRACT_PATH,BASE_URL

TEST_CREDENTIAL="unit-test-only-placeholder-not-a-real-key"
REFERENCE=dict(local_match_id=99,season=2023,date="2023-10-28",home_team="Barcelona",away_team="Real Madrid",
               home_goals=1,away_goals=2,source_rows=[0,1],total_fbref_xg=2.6)


def game_fixture():
    return dict(game=dict(game_id="synthetic-game",season=2023,date="2023-10-28",starts_at="2023-10-28T14:00:00Z",
        status="final",status_detail="FT",league="laliga",home=dict(team_id="home-test",abbrev="TH",name="Barcelona",score=1),
        away=dict(team_id="away-test",abbrev="TA",name="Real Madrid",score=2)),
        team_stats=[dict(team_id="home-test",home=True,goals=1,xg=1.0,shots=3,shots_on_target=2),
                    dict(team_id="away-test",home=False,goals=2,xg=1.5,shots=2,shots_on_target=2)],
        players=[],key_events=[],odds=[])


def listing_fixture():
    return dict(games=[game_fixture()["game"]],count=1,next_offset=None)


def shot_fixture():
    shots=[]
    for i,(team,xg) in enumerate([("TH",.1),("TH",.2),("TH",.3),("TA",.4),("TA",.5)]):
        shots.append(dict(game_id="synthetic-game",date="2023-10-28",minute=i+1,team=team,
            player_id="test-player-"+str(i),outcome="undocumented-test-outcome",xg=xg,x=.2,y=.5))
    return dict(season=None,zones=[],shots_total=5,totals=dict(shots=5,located=5,xg=1.5,on_target=4),
                shots=shots,unlocated_shots=0,shots_note="Synthetic only, not a provider response")


def mock_response(data=None,status=200,headers=None):
    response=Mock();response.status_code=status;response.headers=headers or {}
    response.json.return_value=copy.deepcopy(data)
    return response


def session_fixture(payload=None,status=200):
    pinned=json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    tools=dict(base_url=BASE_URL,tools=[dict(name=name,credits=spec["credits"],input_schema=spec["request"])
                                         for name,spec in pinned["tools"].items()])
    paths={"/v1/"+name:dict(post={"x-credits":spec["credits"],"requestBody":{"content":{"application/json":{"schema":spec["request"]}}},
        "responses":{"200":{"content":{"application/json":{"schema":spec["response"]}}}}}) for name,spec in pinned["tools"].items()}
    session=Mock();session.get.side_effect=[mock_response(tools),mock_response(dict(paths=paths))]
    session.post.return_value=mock_response({"data":payload if payload is not None else listing_fixture()},status=status,
        headers={"x-credits-remaining":"498","x-api-key":TEST_CREDENTIAL,"set-cookie":"must-not-be-recorded"})
    return session
