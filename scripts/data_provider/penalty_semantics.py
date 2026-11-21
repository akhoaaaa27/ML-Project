"""Offline research only; no provider calls or production adapter integration.

Callers must establish the statistical contract independently. Setting an
attestation to True does not verify a provider, a dataset, or an outcome mapping.
Unknown metadata is rejected, never inferred from goals or imputed.
"""

from dataclasses import dataclass
from numbers import Integral


class SemanticAuditError(ValueError):
    """Counts cannot be reconstructed under the supplied evidence."""


@dataclass(frozen=True)
class CountContract:
    """Explicit research attestations, all closed by default.

    The common scope must identify the same team and match, exclude shootouts,
    exclude annulled/retaken attempts not counted in the box score, and agree
    on regulation/extra time. Penalty totals must be complete for that scope.
    SOT classification must match the original training inputs, not merely
    share a field name. This class records evidence; it does not establish it.
    """

    source_shots_include_penalties: bool = False
    source_sot_include_penalties: bool = False
    target_excludes_penalties: bool = False
    same_scope_and_complete: bool = False
    sot_definition_matches_target: bool = False


@dataclass(frozen=True)
class NonPenaltyCounts:
    shots: int
    shots_on_target: int


def _count(name, value):
    if value is None:
        raise SemanticAuditError(f"Missing metadata: {name}")
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise SemanticAuditError(f"Invalid nonnegative integer: {name}")
    return int(value)


def reconstruct_non_penalty_counts(
    *, total_shots, total_sot, penalty_attempts, penalty_shots_on_target,
    contract, penalty_goals=None,
):
    """Subtract explicit PK counts only after the contract is established.

    Successful and saved penalties are on target under a compatible verified
    classification; off-target penalties are not. Goals alone are insufficient
    for a general conversion. Even zero PK SOT must be supplied explicitly.
    The result is a research value, not approval to write to the History Store.
    """
    if not isinstance(contract, CountContract) or not all(
        getattr(contract, field) is True for field in CountContract.__dataclass_fields__
    ):
        raise SemanticAuditError("Unverified statistical contract")
    shots = _count("total_shots", total_shots)
    sot = _count("total_sot", total_sot)
    attempts = _count("penalty_attempts", penalty_attempts)
    penalty_sot = _count("penalty_shots_on_target", penalty_shots_on_target)
    goals = None if penalty_goals is None else _count("penalty_goals", penalty_goals)
    if sot > shots or penalty_sot > attempts or (goals is not None and goals > penalty_sot):
        raise SemanticAuditError("Inconsistent shot/penalty subset counts")
    non_penalty_shots, non_penalty_sot = shots - attempts, sot - penalty_sot
    if min(non_penalty_shots, non_penalty_sot) < 0:
        raise SemanticAuditError("Negative reconstructed counts")
    if non_penalty_sot > non_penalty_shots:
        raise SemanticAuditError("Reconstructed SOT exceeds reconstructed shots")
    return NonPenaltyCounts(non_penalty_shots, non_penalty_sot)
