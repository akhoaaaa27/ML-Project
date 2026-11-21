"""Xuất review public bằng allowlist, không sao chép payload, headers hoặc statistics."""

from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re

from scripts.inference.common import ROOT,write_json

BRANCH="phase8.5.1-strikerapi-live-audit"
ENDPOINT_COSTS={"list_games":2,"get_game":5,"get_shot_map":10}
FIELD_STATES={"available_both_teams","partially_available","missing_both_teams","invalid","not_verified",
              "derived_from_validated_opponent_xg","reconstructed_from_complete_shots"}
MISSING_FIELDS={side+"."+field for side in ("home","away") for field in ("xg","xga","goals","shots","shots_on_target")}
VALIDATION_CODES={
    "AUTHENTICATION_CONFIRMED","FIXTURE_MATCH_CONFIRMED","NORMALIZATION_SUCCEEDED","COMPARISON_COMPLETED",
    "SCHEMA_DRIFT","SCHEMA_MISMATCH","PUBLIC_SCHEMA_UNAVAILABLE","MISSING_CREDENTIAL","INVALID_CREDENTIAL_FORMAT",
    "PROVIDER_BAD_REQUEST","PROVIDER_AUTH_FAILED","PROVIDER_INSUFFICIENT_CREDITS","PROVIDER_FORBIDDEN",
    "PROVIDER_RATE_LIMIT","PROVIDER_SERVER_ERROR","PROVIDER_HTTP_ERROR","INVALID_JSON","TRANSPORT_ERROR",
    "BUDGET_EXCEEDED","BUDGET_UNVERIFIABLE","PREVIOUS_ATTEMPT_UNRESOLVED","CACHE_CORRUPT",
    "NO_CONFIDENT_MATCH","UNKNOWN_PROVIDER_TEAM","TIMEZONE_AMBIGUOUS","FIXTURE_MISMATCH","SCORE_MISMATCH",
    "DUPLICATE_FIXTURE","INVALID_GAME_ID","NONFINAL_FIXTURE","UNEXPECTED_GAME_SCHEMA","INVALID_STATS_SCHEMA",
    "INCOMPLETE_SHOTS","UNVERIFIED_SHOT_TEAM","DUPLICATE_SHOT","INVALID_PROVENANCE",
    "MISSING_STATISTICS","INVALID_NUMERIC","INCONSISTENT_PAIR","INCOMPLETE_HISTORY",
    "SINGLE_FIXTURE_INSUFFICIENT","UNRECOGNIZED_VALIDATION_CODE","EVIDENCE_NOT_VERIFIED",
}


def truth(value):return value if type(value) is bool else None


def safe_integer(value,maximum=1000):
    return value if type(value) is int and 0<=value<=maximum else None


def safe_time(value):
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds") if parsed.tzinfo is not None else None
    except (AttributeError,TypeError,ValueError):return None


def build_public_review(evidence: dict,context: dict) -> dict:
    """evidence chỉ là dữ liệu local; context lấy từ baseline Git/runner, không từ provider."""
    if not isinstance(evidence,dict) or not isinstance(context,dict):raise ValueError("Evidence/context phải là JSON object.")
    source_commit=context.get("starting_commit")
    source_commit=source_commit if isinstance(source_commit,str) and re.fullmatch(r"[0-9a-f]{40}",source_commit) else None
    calls=[]
    for call in evidence.get("calls",[]) if isinstance(evidence.get("calls"),list) else []:
        if not isinstance(call,dict) or not isinstance(call.get("tool"),str) or call["tool"] not in ENDPOINT_COSTS:continue
        status=call.get("http_status")
        calls.append(dict(endpoint=call["tool"],documented_credits=ENDPOINT_COSTS[call["tool"]],
                          http_status=status if type(status) is int and 100<=status<=599 else None))
    if len(calls)>3:raise ValueError("Evidence vượt phạm vi một controlled PoC; cần review riêng trước xuất public.")
    normalization=truth(evidence.get("normalization_succeeded"))
    availability=evidence.get("availability",{})
    availability=availability if isinstance(availability,dict) else {}
    fields={field:availability.get(field) if isinstance(availability.get(field),str) and availability[field] in FIELD_STATES else "not_verified"
            for field in ("xg","xga","goals","sh","sot")}
    codes=[]
    for code in evidence.get("validation_codes",[]) if isinstance(evidence.get("validation_codes"),list) else []:
        selected=code if isinstance(code,str) and code in VALIDATION_CODES else "UNRECOGNIZED_VALIDATION_CODE"
        if selected not in codes:codes.append(selected)
    raw_missing=evidence.get("missing_fields",[])
    raw_missing=raw_missing if isinstance(raw_missing,list) else []
    missing=[field for field in sorted(MISSING_FIELDS) if field in raw_missing]
    xg_source={"get_game.published_team_stats.xg":"published_team_match",
               "raw_shot_aggregation_both_teams":"raw_shot_aggregation"}.get(evidence.get("xg_source") if isinstance(evidence.get("xg_source"),str) else None,"not_verified")
    tests=context.get("tests",{}) if isinstance(context.get("tests"),dict) else {}
    blocker=evidence.get("principal_blocker")
    blocker=blocker if isinstance(blocker,str) and blocker in VALIDATION_CODES else "EVIDENCE_NOT_VERIFIED"
    comparison=truth(evidence.get("comparison_executed"))
    return dict(schema_version=1,phase="8.5.1",report_language="vi",branch=BRANCH,source_commit=source_commit,
        execution_started_at_utc=safe_time(context.get("started_at")),
        execution_completed_at_utc=safe_time(context.get("execution_completed_at")),
        live_audit_command_executed=truth(evidence.get("live_command_executed")),
        billable_request_attempted=bool(calls),authentication_succeeded=truth(evidence.get("authentication_succeeded")),
        calls=calls,api_calls_attempted_or_reserved=len(calls),http_responses_confirmed=sum(c["http_status"] is not None for c in calls),
        maximum_cumulative_credit_budget=25,documented_credits_for_this_attempt=sum(c["documented_credits"] for c in calls),
        cumulative_reserved_credits=safe_integer(evidence.get("cumulative_reserved_credits"),25),
        actual_billed_credits=None,actual_billed_credits_reliably_confirmed=False,
        billing_note="Chỉ công bố documented/reserved credits; không suy diễn billing từ response headers chưa xác minh semantics.",
        reference_fixture_matched=truth(evidence.get("fixture_matched")),
        get_game_succeeded=truth(evidence.get("get_game_succeeded")),
        both_team_perspectives_returned=truth(evidence.get("both_team_perspectives")),
        field_availability=fields,xg_source=xg_source,
        shot_map_called=truth(evidence.get("shot_map_called")),shot_map_required=truth(evidence.get("shot_map_required")),
        normalization_succeeded=normalization,validation_codes=codes,missing_fields=missing,
        compatibility_audit_executed=comparison,
        structurally_usable_for_further_research=normalization,
        principal_compatibility_blocker=blocker,larger_sample_required=True,
        next_step="larger_sample_requires_separate_authorization_and_definition_rights_coverage_review" if normalization is True
            else "resolve_execution_or_validation_blocker_before_expanding_sample",
        production_approved=False,population_compatibility_established=False,
        exact_numerical_results_kept_private=comparison is True,
        provider_statistics_or_shots_published=False,complete_statistical_audit_published=False,
        limitations=["Một fixture không đại diện population hoặc xác nhận production compatibility.",
            "Báo cáo public chỉ đánh giá cấu trúc; numerical comparisons và provider records được giữ local.",
            "Cần review định nghĩa xG, as-of/revision behavior, coverage và quyền sử dụng trước nghiên cứu lớn hơn."],
        tests={key:safe_integer(tests.get(key)) for key in ("run","failures","errors","skipped")},
        protected_research_files_unchanged=truth(context.get("protected_research_files_unchanged")),
        model_and_history_unchanged=truth(context.get("model_and_history_unchanged")),
        private_dotenv_ignored_and_untracked=truth(context.get("private_dotenv_ignored_and_untracked")))


def vn_status(value):return "Có" if value is True else "Không" if value is False else "Chưa xác minh"


def markdown_review(review):
    fields=review["field_availability"]
    lines=["# Review công khai: StrikerAPI Live PoC La Liga", "",
        "Báo cáo dùng allowlist. Không công bố response, provider game ID, dataset từng dòng, shot records, auth headers hoặc numerical source comparisons.","",
        f"Phiên bản code được chạy: `{review['source_commit']}`; nhánh `{review['branch']}`.","",
        f"Bắt đầu UTC: `{review['execution_started_at_utc']}`; hoàn tất UTC: `{review['execution_completed_at_utc']}`.","",
        "## Kết quả thực thi", "", "| Câu hỏi | Quan sát |", "|---|---|",
        f"| Đã chạy controlled live audit? | {vn_status(review['live_audit_command_executed'])} |",
        f"| Authentication đã được xác nhận? | {vn_status(review['authentication_succeeded'])} |",
        f"| Reference fixture đã ghép đúng? | {vn_status(review['reference_fixture_matched'])} |",
        f"| get_game thành công? | {vn_status(review['get_game_succeeded'])} |",
        f"| Đủ hai team perspectives? | {vn_status(review['both_team_perspectives_returned'])} |",
        f"| Normalization theo Phase 8 schema thành công? | {vn_status(review['normalization_succeeded'])} |",
        f"| Comparison với FBref đã chạy? | {vn_status(review['compatibility_audit_executed'])} |",
        f"| get_shot_map được gọi / cần thiết? | {vn_status(review['shot_map_called'])} / {vn_status(review['shot_map_required'])} |",
        f"| Có cấu trúc phù hợp để nghiên cứu tiếp? | {vn_status(review['structurally_usable_for_further_research'])} |",
        "| Đã approve production? | Không |", "", "## Endpoint và credits", "",
        "| Endpoint | HTTP status | Documented credits |", "|---|---:|---:|"]
    for call in review["calls"]:lines.append(f"| {call['endpoint']} | {call['http_status']} | {call['documented_credits']} |")
    lines += ["",f"Số calls đã thử/reserve: **{review['api_calls_attempted_or_reserved']}**. Documented cost của lượt này: **{review['documented_credits_for_this_attempt']}**; cumulative reserved: **{review['cumulative_reserved_credits']}**; trần cộng dồn **25**.",
        "",review["billing_note"],"Actual billed total: **chưa xác nhận độc lập**. Không đăng credit/auth headers.","",
        "## Field availability", "", "| Field | Trạng thái kiểm chứng |", "|---|---|"]
    for field,value in fields.items():lines.append(f"| {field} | `{value}` |")
    lines += ["",f"Nguồn xG đã xác minh ở mức phương thức: `{review['xg_source']}`. xGA có thể là opponent reversal đã validate, không nhất thiết là native field của provider.",
        "", "Mã kiểm tra: " + (", ".join(f"`{code}`" for code in review["validation_codes"]) or "chưa xác minh")+".",
        "", "Missing fields: " + (", ".join(f"`{name}`" for name in review["missing_fields"]) or "không ghi nhận trong evidence hiện có; xem trạng thái availability ở trên")+".",
        "", "## Compatibility và giới hạn công bố", "",
        f"Principal blocker: `{review['principal_compatibility_blocker']}`.","",
        "Nếu comparison đã chạy, đó là source difference StrikerAPI − FBref, không phải predictive error/MAE của frozen LR. Exact metrics, thống kê và bảng từng phía được giữ trong private local evidence; báo cáo public không chứa toàn bộ statistical audit.","",
        "Một fixture không đủ để chấp nhận tính tương đương xG hoặc production compatibility. Cấu trúc đủ dùng chỉ là căn cứ để cân nhắc mẫu nghiên cứu lớn hơn, với review định nghĩa, as-of/revision behavior, completeness và quyền dữ liệu. `production_approved: false`.","",
        "## Kiểm thử và bảo toàn", "",
        f"Full suite: run={review['tests']['run']}, failures={review['tests']['failures']}, errors={review['tests']['errors']}, skipped={review['tests']['skipped']}.","",
        f"File nghiên cứu giữ nguyên: {vn_status(review['protected_research_files_unchanged'])}; model và history store giữ nguyên: {vn_status(review['model_and_history_unchanged'])}; .env ignored/untracked: {vn_status(review['private_dotenv_ignored_and_untracked'])}.","",
        "## Bước tiếp theo", "",
        "Cần mẫu compatibility lớn hơn theo phạm vi/budget được cho phép riêng. Nếu lần này chưa xác minh được dữ liệu, phải xử lý blocker trước; không tự retry, mở rộng mẫu hoặc bỏ qua validation. Không backfill, scheduler, retraining, migration production hoặc Phase 9 trong lượt này.","",
        "Lệnh đã dùng cho live attempt:","","```powershell",
        ".\\.venv\\Scripts\\python.exe -m scripts.data_provider.compatibility_audit --execute --max-credits 25","```","",
        "[Báo cáo JSON public](../outputs/provider_poc/reports/live_review_public.json)",""]
    return "\n".join(lines)


def export_review(evidence_path,context_path,*,json_path=ROOT/"outputs/provider_poc/reports/live_review_public.json",
                  markdown_path=ROOT/"docs/STRIKERAPI_LIVE_POC_REVIEW.md"):
    evidence=json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    context=json.loads(Path(context_path).read_text(encoding="utf-8"))
    review=build_public_review(evidence,context)
    write_json(json_path,review)
    Path(markdown_path).parent.mkdir(parents=True,exist_ok=True)
    Path(markdown_path).write_text(markdown_review(review),encoding="utf-8")
    return review


def main():
    import sys
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",type=Path,required=True)
    parser.add_argument("--context",type=Path,required=True)
    args=parser.parse_args()
    review=export_review(args.evidence,args.context)
    print(json.dumps(dict(status="public_review_exported",production_approved=review["production_approved"]),ensure_ascii=False))


if __name__=="__main__":main()
