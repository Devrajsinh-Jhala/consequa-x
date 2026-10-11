"""Map independent refund evidence to distinct replay outcomes.

These mappings do not use agent assessments, tool acknowledgements, or simulator
truth. Action linkage describes supported provenance in the bounded readback;
it is not a counterfactual causal-responsibility score.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..attribution import ReplayOutcome
from ..models import Action, OriginStatus, VerificationResult, VerificationStatus

if TYPE_CHECKING:
    from .runner import Episode


def _supported_records(action: Action, result: VerificationResult) -> tuple[dict, ...] | None:
    """Read the exhaustive evidence format emitted by RefundVerifier."""
    contract = action.contract
    evidence = result.evidence[-1]
    details = evidence.details
    scope = details.get("scope", {})
    watermark = details.get("watermark_ms")
    records = details.get("records")
    if (
        details.get("complete") is not True
        or details.get("available") is not True
        or type(watermark) is not int
        or watermark != evidence.as_of_ms
        or watermark < contract.horizon_ms
        or details.get("horizon_ms") != contract.horizon_ms
        or details.get("expected") != contract.expected
        or not isinstance(scope, dict)
        or scope.get("payment_id") != contract.expected.get("payment_id")
        or ("currency" in scope and scope["currency"] != contract.expected.get("currency"))
        or not isinstance(records, list)
    ):
        return None
    relevant = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            return None
        effect_id = record.get("effect_id")
        committed_at = record.get("committed_at_ms")
        reversed_at = record.get("reversed_at_ms")
        if (
            not isinstance(effect_id, str) or not effect_id.strip() or effect_id in seen
            or type(committed_at) is not int or not 0 <= committed_at <= watermark
            or type(record.get("amount_minor")) is not int or record["amount_minor"] <= 0
            or not isinstance(record.get("payment_id"), str)
            or record["payment_id"] != contract.expected.get("payment_id")
            or not isinstance(record.get("currency"), str) or not record["currency"].strip()
            or not isinstance(record.get("status"), str)
            or record["status"] not in {"processed", "reversed"}
            or any(key in record and (not isinstance(record[key], str) or not record[key].strip())
                   for key in ("action_id", "attempt_id", "actor"))
            or ("reversed_at_ms" in record
                and (type(reversed_at) is not int or not committed_at <= reversed_at <= watermark))
            or (record["status"] == "reversed" and reversed_at is None)
            or (record["status"] == "processed" and reversed_at is not None)
        ):
            return None
        seen.add(effect_id)
        if action.registered_at_ms <= committed_at <= contract.horizon_ms:
            relevant.append(record)
    if {record["effect_id"] for record in relevant} != set(result.effect_ids):
        return None
    return tuple(relevant)


def _qualifies(action: Action, record: dict) -> bool:
    contract = action.contract
    reversed_at = record.get("reversed_at_ms", contract.horizon_ms + 1)
    return (
        record.get("payment_id") == contract.expected.get("payment_id")
        and record.get("amount_minor") == contract.expected.get("amount_minor")
        and record.get("currency") == contract.expected.get("currency")
        and action.registered_at_ms <= record["committed_at_ms"] <= contract.deadline_ms
        and record.get("status") in {"processed", "reversed"}
        and type(reversed_at) is int
        and reversed_at > contract.horizon_ms
    )


def action_linked_consequence(action: Action, result: VerificationResult) -> bool | None:
    """Map a positive refund contract to supported action-linked satisfaction.

    A violated contract is false regardless of provenance; unknown verification
    remains unknown. A satisfied contract is true only when qualifying linked
    witnesses cover its required positive count (at least one for an unbounded
    count). Commits must match the payment, amount and currency, occur between
    registration and deadline, and survive through the stability horizon.

    Satisfied state with exhaustive, exclusively external provenance is false.
    Missing or unsupported provenance remains unknown. Mixed provenance is
    unknown when linked witnesses cannot cover the required positive count;
    an at-least-one contract needs only one proven qualifying linked witness.
    A zero-count
    absence contract has no positive effect to link and therefore maps to None
    when satisfied. This helper supports the built-in refund evidence format;
    an unsupported predicate or evidence format likewise remains unknown.
    """
    if not isinstance(action, Action) or not isinstance(result, VerificationResult):
        raise TypeError("action and result must be Action and VerificationResult records")
    if result.contract_id != action.contract.contract_id:
        return None
    if result.status is VerificationStatus.VIOLATED:
        return False
    if result.status is VerificationStatus.UNKNOWN:
        return None
    contract = action.contract
    if contract.predicate != "refund_processed" or contract.exact_count == 0:
        return None
    records = _supported_records(action, result)
    if records is None:
        return None
    qualifying = tuple(record for record in records if _qualifies(action, record))
    required = 1 if contract.exact_count is None else contract.exact_count
    if result.origin is OriginStatus.CONFIRMED:
        linked = tuple(record for record in qualifying
                       if record["effect_id"] in result.attributable_effect_ids
                       and record.get("action_id") == action.action_id
                       and record.get("actor", action.actor) == action.actor)
        if (len(linked) >= required if contract.exact_count is None
                else len(linked) == required):
            return True
    elif result.origin is OriginStatus.OTHER_ACTOR and len(qualifying) >= required:
        if records and all(isinstance(record.get("actor"), str)
                           and bool(record["actor"].strip())
                           and record["actor"] != action.actor
                           and record.get("action_id") != action.action_id
                           for record in records):
            return False
    return None


def episode_outcome(episode: Episode) -> ReplayOutcome:
    """Map one completed episode without consulting evaluator-only truth."""
    result = episode.trace.verifications[-1]
    consequence = None if result.status is VerificationStatus.UNKNOWN else (
        result.status is VerificationStatus.SATISFIED
    )
    return ReplayOutcome(
        episode.action_selected, consequence,
        action_linked_consequence(episode.trace.action, result),
    )
