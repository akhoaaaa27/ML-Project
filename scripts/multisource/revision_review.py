"""Deterministic hybrid policy and exact-content review receipts."""

from .match_registry import require, semantic_hash, timestamp

POLICY_VERSION = "phase854-v1"


def classify(old, new, *, unreliable=False):
    if old == new:
        return [], "NO_CHANGE"
    types = []
    if old["fixture_id"] is not None and old["fixture_id"] != new["fixture_id"]:
        return ["IDENTITY_CONFLICT"], "BLOCKED"
    if old["match_status"] == "VERIFIED_COMPLETED" and new["match_status"] != "VERIFIED_COMPLETED":
        return ["COMPLETION_REGRESSION"], "BLOCKED"
    if old["statistics_status"] == "COMPLETE_STATISTICS" and new["statistics_status"] != "COMPLETE_STATISTICS":
        return ["STATISTICS_REGRESSION"], "BLOCKED"
    if (old["match_date"], old["kickoff_utc"]) != (new["match_date"], new["kickoff_utc"]):
        types.append("SCHEDULE_CHANGE")
    was_complete = old["match_status"] == "VERIFIED_COMPLETED"
    if not was_complete and new["match_status"] == "VERIFIED_COMPLETED":
        types.append("NEW_COMPLETED" if new["statistics_status"] == "COMPLETE_STATISTICS" else "NEW_PENDING")
    elif was_complete:
        if old["score"] != new["score"]:
            types.append("FINAL_SCORE_CORRECTION")
        if old["statistics_status"] == "PENDING_UPDATE" and new["statistics_status"] == "COMPLETE_STATISTICS":
            types.append("UNRELIABLE_PENDING_RESOLVED" if unreliable else "PENDING_RESOLVED")
        elif old["statistics"] != new["statistics"]:
            types.append("STATISTICS_CORRECTION")
    if old["observed_status"] != new["observed_status"] and not types:
        types.append("STATUS_CHANGE")
    if old["semantics"] != new["semantics"]:
        return ["SOURCE_CONFLICT"], "BLOCKED"
    manual = {"SCHEDULE_CHANGE", "FINAL_SCORE_CORRECTION", "STATISTICS_CORRECTION", "UNRELIABLE_PENDING_RESOLVED"}
    if set(types) & manual:
        return types, "MANUAL_REVIEW"
    return types, "PENDING_UPDATE" if "NEW_PENDING" in types else "AUTO_ACCEPT"


def receipt(bundle, change, decision, reason, evidence_reference, reviewed_at):
    require(change["decision"] == "MANUAL_REVIEW", "NOT_REVIEWABLE", "Only manual items can be reviewed")
    require(decision in {"APPROVE", "REJECT"} and bool(reason.strip()) and bool(evidence_reference.strip()),
            "INVALID_REVIEW", "Decision, reason and evidence reference are required")
    timestamp(reviewed_at)
    return dict(change, parent_version=bundle["parent_version"], candidate_version=bundle["candidate_version"],
                candidate_content_sha256=semantic_hash(bundle), review_decision=decision, review_reason=reason,
                evidence_reference=evidence_reference, reviewed_at=reviewed_at)


def validate_receipts(bundle, reviews):
    expected = {r["change_id"]:r for r in bundle["changes"] if r["decision"] == "MANUAL_REVIEW"}
    require(set(reviews) <= set(expected), "STALE_APPROVAL", "Review references unknown change")
    for change_id, change in expected.items():
        require(change_id in reviews, "REVIEW_REQUIRED", "Manual review is unresolved", change_id=change_id)
        review = reviews[change_id]
        rebuilt = receipt(bundle, change, review["review_decision"], review["review_reason"],
                          review["evidence_reference"], review["reviewed_at"])
        require(rebuilt == review, "STALE_APPROVAL", "Approval does not match exact candidate content")
        require(review["review_decision"] == "APPROVE", "REVIEW_REJECTED", "Candidate contains rejected change")
