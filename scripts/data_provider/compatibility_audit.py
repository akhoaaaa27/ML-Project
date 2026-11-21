"""PoC đúng một fixture; mặc định chỉ xuất kế hoạch offline, không approve production."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.prepare_training_features import ROOT,load_dataset
from scripts.inference.common import write_json
from scripts.inference.data_refresh import validate_completed_rows
from .normalize_strikerapi import normalize_game
from .sample_selector import select_reference,discovery_params,match_fixture,expanded_plan
from .strikerapi_client import POC_DIR,POCError,StrikerAPIClient,need,digest,run_cli


def compare_sample(normalized,reference,frame=None):
    validate_completed_rows(normalized)
    need(len(normalized)==2 and normalized.provider.eq("strikerapi").all(),"INVALID_SAMPLE","Audit ban đầu chỉ nhận hai phía của đúng một StrikerAPI fixture.")
    frame=load_dataset() if frame is None else frame
    local=frame.loc[frame.match_id.eq(reference["local_match_id"])].copy()
    keys=["season","date","team","opponent","is_home"]
    fields=["xg","xga","gf","ga","sh","sot"]
    left=local[keys+fields].rename(columns={f:"fbref_"+f for f in fields})
    right=normalized[keys+fields].rename(columns={f:"strikerapi_"+f for f in fields})
    joined=left.merge(right,on=keys,how="outer",validate="one_to_one",indicator=True)
    need(len(joined)==2 and joined["_merge"].eq("both").all(),"FIXTURE_MISMATCH","Audit không join đủ đúng hai phía theo identity.")
    joined=joined.drop(columns="_merge").sort_values("is_home",ascending=False).reset_index(drop=True)
    need(joined.fbref_gf.eq(joined.strikerapi_gf).all() and joined.fbref_ga.eq(joined.strikerapi_ga).all(),
         "SCORE_MISMATCH","Goals không khớp; dừng audit identity trước so sánh xG.")
    joined["xg_difference"]=joined.strikerapi_xg-joined.fbref_xg
    joined["absolute_xg_difference"]=joined.xg_difference.abs()
    joined["xga_difference"]=joined.strikerapi_xga-joined.fbref_xga
    summary=dict(n_fixtures=1,n_team_rows=2,matched_rows=2,missing_required_values=int(joined.isna().sum().sum()),
        xg_mean_absolute_difference=float(joined.absolute_xg_difference.mean()),xg_mean_signed_difference=float(joined.xg_difference.mean()),
        xg_max_absolute_difference=float(joined.absolute_xg_difference.max()),
        goals_exact_agreement_rate=float((joined.fbref_gf.eq(joined.strikerapi_gf)&joined.fbref_ga.eq(joined.strikerapi_ga)).mean()),
        shots_exact_agreement_rate=float(joined.fbref_sh.eq(joined.strikerapi_sh).mean()),
        shots_on_target_exact_agreement_rate=float(joined.fbref_sot.eq(joined.strikerapi_sot).mean()),
        difference_direction="strikerapi_minus_fbref",metric_is_source_difference_not_model_prediction_mae=True,
        population_compatibility_established=False,production_approved=False)
    return joined,summary


def request_plan(reference,costs,spent=0):
    cumulative=spent;steps=[]
    for tool,params,conditional in [("list_games",discovery_params(reference),False),
        ("get_game",dict(league="laliga",game_id="<ID_ghép_chắc_chắn_từ_list_games>"),False),
        ("get_shot_map",dict(league="laliga",game_id="<cùng_ID>",include_shots=True),True)]:
        cumulative+=costs[tool]["credits"]
        steps.append(dict(tool=tool,params=params,documented_credits=costs[tool]["credits"],
            cumulative_estimated_max=cumulative,conditional_only_if_missing_team_xg=conditional))
    return steps


def run_poc(*,execute=False,max_credits=25,local_match_id=None,output_dir=POC_DIR):
    output_dir=Path(output_dir)
    frame=load_dataset();reference=select_reference(frame,local_match_id)
    client=StrikerAPIClient(execute=execute,max_credits=max_credits,output_dir=output_dir)
    plan=request_plan(reference,client.contract["tools"],client.spent())
    (output_dir/"samples").mkdir(parents=True,exist_ok=True)
    write_json(output_dir/"samples/reference_fixture.json",reference)
    expanded=expanded_plan(frame)
    expanded.to_csv(output_dir/"samples/expanded_sample_plan.csv",index=False)
    report=dict(status="dry_run",phase="8.5.1",reference=reference,plan=plan,max_credits=max_credits,
        worst_case_additional_credits_without_cache=17,estimated_max_fits_remaining_budget=plan[-1]["cumulative_estimated_max"]<=max_credits,
        expanded_sample_count=len(expanded),expanded_sample_executed=False,production_approved=False,
        real_sample_collected=False,population_compatibility_established=False,raw_responses_safe_to_commit=False)
    try:
        if execute:
            listing=client.call("list_games",discovery_params(reference))
            matched=match_fixture(listing["data"],reference)
            game_id=matched["identity"]["provider_match_id"]
            game=client.call("get_game",dict(league="laliga",game_id=game_id))
            table,diagnostic=normalize_game(game["data"],reference,provider_game_id=game_id,fetched_at=game["fetched_at"])
            report.update(real_sample_collected=True,provider_game_id=game_id,normalization=diagnostic)
            if table is None and diagnostic["needs_shot_map"] and not diagnostic["invalid_fields"]:
                shot=client.call("get_shot_map",dict(league="laliga",game_id=game_id,include_shots=True))
                table,diagnostic=normalize_game(game["data"],reference,provider_game_id=game_id,fetched_at=shot["fetched_at"],shot_map=shot["data"])
            report.update(status="sample_incomplete" if table is None else "sample_validated_not_equivalent",real_sample_collected=True,
                provider_game_id=game_id,normalization=diagnostic,
                pagination=dict(next_offset=matched["next_offset"],automatic_pagination=False))
            if table is not None:
                comparison,summary=compare_sample(table,reference,frame)
                name=digest(dict(game_id=game_id))[:16]
                table.to_csv(output_dir/"samples"/(name+"_team_matches.csv"),index=False)
                directory=output_dir/"comparisons";directory.mkdir(parents=True,exist_ok=True)
                comparison.to_csv(directory/(name+"_fbref_comparison.csv"),index=False)
                report["compatibility_summary"]=summary
        report.update(billable_posts_this_run=client.billable_posts,public_schema_gets_this_run=client.public_schema_gets,
                      cumulative_conservative_reserved_credits=client.spent(),request_history=client.request_history)
        write_json(output_dir/"reports/poc_summary.json",report)
        return report
    except POCError as exc:
        report.update(exc.result(),billable_posts_this_run=client.billable_posts,
            cumulative_conservative_reserved_credits=client.spent())
        write_json(output_dir/"reports/poc_summary.json",report)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true",help="Chỉ bật khi người dùng quyết định chi credits; mặc định không gọi mạng.")
    parser.add_argument("--max-credits",type=int,default=25)
    parser.add_argument("--local-match-id",type=int,help="Một fixture Development; không mở rộng hoặc tự đổi fixture.")
    args=parser.parse_args()
    return run_cli(lambda:run_poc(execute=args.execute,max_credits=args.max_credits,local_match_id=args.local_match_id))


if __name__=="__main__":raise SystemExit(main())
