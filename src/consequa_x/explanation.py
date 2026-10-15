"""Compose factual explanation records from captured assessments and readback."""

from dataclasses import dataclass
from typing import Iterable, Protocol

from .attribution import EffectEstimate, recency_attribution
from .graph import ConsequenceGraph, build_graph
from .models import (
    Action,
    AgentAssessment,
    AssessmentStatus,
    EventType,
    OriginStatus,
    ResponseStatus,
    Trace,
    VerificationResult,
    VerificationStatus,
    to_dict,
)


class TargetMatcher(Protocol):
    """Qualify observed, attributable effects against an application's target.

    Implementations check the domain's payload, deadline, and persistence
    semantics using captured evidence. Returned IDs must be a unique tuple and
    a subset of the verifier's ``attributable_effect_ids``. Neither a propagated
    action ID nor a satisfied state predicate alone establishes a target match.
    Supplying this adapter also declares that SUCCESS/FAILURE assessments refer
    to satisfaction of this action's outcome contract.
    """

    def matching_effect_ids(
        self, action: Action, verification: VerificationResult,
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class ConsequenceExplanation:
    action_id: str
    consequence: VerificationResult
    agent_assessment: AgentAssessment
    assessment_alignment: str
    diagnoses: tuple[str, ...]
    diagnosis: str
    summary: str
    graph: ConsequenceGraph
    recency_candidate_id: str | None
    attribution: tuple[EffectEstimate, ...] = ()
    schema_version: str = "0.1"

    def to_dict(self) -> dict:
        return to_dict(self)


def explain(
    trace: Trace, estimates: Iterable[EffectEstimate] = (), *,
    target_matcher: TargetMatcher | None = None,
) -> ConsequenceExplanation:
    """Explain the latest verification, with separate state and effect-origin claims.

    A reported assessment is not hidden chain of thought. Unknown outcomes do
    not establish an incorrect belief. This function neither replays a policy
    nor executes a tool; estimates must come from an explicit research runner.
    Refund target matching is built in. Other predicates remain unassessable
    unless an application explicitly supplies domain-specific target matching;
    their evidence is never interpreted as refund amounts or currencies.
    """
    if not isinstance(trace, Trace):
        raise TypeError("explain requires a Trace")
    matching_method = None
    if target_matcher is not None:
        matching_method = getattr(target_matcher, "matching_effect_ids", None)
        if not callable(matching_method):
            raise TypeError("A target matcher must provide a callable matching_effect_ids method")
    if not trace.verifications:
        raise ValueError("An explanation requires an independent verification record")
    verified = trace.verifications[-1]
    assessment = trace.assessment
    estimates = tuple(estimates)
    diagnoses = []
    alignment = "unassessable"
    details = verified.evidence[-1].details if verified.evidence else {}
    expected = trace.action.contract.expected
    is_refund = trace.action.contract.predicate == "refund_processed"
    linked_records, matching_ids = _refund_target(trace, verified) if is_refund else ([], ())
    if matching_method is not None and verified.status is not VerificationStatus.UNKNOWN:
        matching_ids = matching_method(trace.action, verified)
        if (type(matching_ids) is not tuple
                or any(not isinstance(item, str) or not item.strip() for item in matching_ids)
                or len(set(matching_ids)) != len(matching_ids)
                or not set(matching_ids).issubset(verified.attributable_effect_ids)):
            raise ValueError("Target matcher must return unique attributable effect IDs as a tuple")
    if verified.status is VerificationStatus.UNKNOWN:
        diagnoses.append("UNKNOWN_OUTCOME")
        if assessment.status is not AssessmentStatus.UNKNOWN:
            diagnoses.append("UNVERIFIED_ASSESSMENT")
    else:
        is_success = verified.status is VerificationStatus.SATISFIED
        origin_sufficient = (is_refund or target_matcher is not None) and (
            not is_success or bool(matching_ids)
        )
        if origin_sufficient and assessment.status in {AssessmentStatus.SUCCESS, AssessmentStatus.FAILURE}:
            contradicted = (assessment.status is AssessmentStatus.SUCCESS) != is_success
            alignment = "contradicted" if contradicted else "consistent"
            if contradicted:
                diagnoses.append("ASSESSMENT_DIVERGENCE")
        if (any(response.status is ResponseStatus.TIMEOUT for response in trace.responses)
                and is_success and matching_ids):
            diagnoses.append("ACKNOWLEDGEMENT_EFFECT_DIVERGENCE")
        if any(response.status is ResponseStatus.SUCCESS for response in trace.responses) and not is_success:
            diagnoses.append("RESPONSE_EFFECT_DIVERGENCE")
        if not is_success:
            diagnoses.append("CONSEQUENCE_VIOLATION")
        if not is_refund and alignment == "unassessable":
            diagnoses.append("UNASSESSABLE_ASSESSMENT")

    if verified.status is not VerificationStatus.UNKNOWN:
        if is_refund:
            count = details.get("peak_matching_count", details.get("matching_count", 0))
            exact = trace.action.contract.exact_count
            if exact is not None and count > exact:
                diagnoses.append("EXCESS_EFFECTS")
                if len(linked_records) > exact:
                    diagnoses.append("DUPLICATE_EFFECT")
            if linked_records and any(record["amount_minor"] != expected["amount_minor"]
                                      or record["currency"] != expected["currency"]
                                      for record in linked_records):
                diagnoses.append("PARAMETER_MISMATCH")
            if linked_records and any(0 < record["amount_minor"] < expected["amount_minor"]
                                      for record in linked_records):
                diagnoses.append("PARTIAL_EFFECT")
            if any(record.get("reversed_at_ms", trace.action.contract.horizon_ms + 1)
                   <= trace.action.contract.horizon_ms for record in linked_records):
                diagnoses.append("REVERSED_EFFECT")
        if verified.origin is OriginStatus.OTHER_ACTOR:
            diagnoses.append("EXTERNAL_ACTOR_EFFECT")
        elif verified.effect_ids and verified.origin is OriginStatus.UNKNOWN:
            diagnoses.append("UNCONFIRMED_ORIGIN")

    if not diagnoses:
        diagnoses.append("CONSISTENT_OUTCOME")
    if ("ASSESSMENT_DIVERGENCE" in diagnoses
            and "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in diagnoses):
        diagnosis = "BELIEF / RESPONSE DIVERGENCE"
    else:
        diagnosis = " / ".join(diagnoses)
    decision_times = [event.time_ms for event in trace.events if event.type is EventType.AGENT_DECISION]
    recency = recency_attribution(trace.events, before_ms=decision_times[0]) if decision_times else None
    summary = (
        f"Agent reported {assessment.status.value}; independent verification is "
        f"{verified.status.value}; effect origin is {verified.origin.value}."
    )
    return ConsequenceExplanation(
        action_id=trace.action.action_id,
        consequence=verified,
        agent_assessment=assessment,
        assessment_alignment=alignment,
        diagnoses=tuple(diagnoses),
        diagnosis=diagnosis,
        summary=summary,
        graph=build_graph(trace, estimates),
        recency_candidate_id=recency,
        attribution=estimates,
    )


def _refund_target(trace: Trace, verified: VerificationResult) -> tuple[list[dict], tuple[str, ...]]:
    """Validate known refund detail shapes before deriving refund diagnoses.

    An UNKNOWN receipt may deliberately contain malformed source records, so
    those records establish no target matches and are not interpreted here.
    Strict JSON trace validation is separate from domain evidence validation.
    """
    if verified.status is VerificationStatus.UNKNOWN:
        return [], ()
    expected = trace.action.contract.expected
    if (set(expected) != {"payment_id", "amount_minor", "currency"}
            or not isinstance(expected["payment_id"], str) or not expected["payment_id"].strip()
            or not isinstance(expected["currency"], str) or not expected["currency"].strip()
            or type(expected["amount_minor"]) is not int or expected["amount_minor"] <= 0
            or trace.action.contract.deadline_ms < trace.action.registered_at_ms):
        raise ValueError("Known refund explanations require a valid refund contract payload")
    details = verified.evidence[-1].details
    records = details.get("records", [])
    if type(records) is not list or any(type(record) is not dict for record in records):
        raise ValueError("Refund evidence records must be an array of objects")
    for field in ("matching_count", "peak_matching_count", "eligible_count", "relevant_count"):
        if field in details and (type(details[field]) is not int or details[field] < 0):
            raise ValueError(f"Refund evidence {field} must be a nonnegative integer")
    linked = [record for record in records
              if record.get("effect_id") in verified.attributable_effect_ids]
    for record in linked:
        if (type(record.get("amount_minor")) is not int or record["amount_minor"] <= 0
                or not isinstance(record.get("currency"), str) or not record["currency"].strip()
                or not isinstance(record.get("payment_id"), str) or not record["payment_id"].strip()
                or type(record.get("committed_at_ms")) is not int
                or not 0 <= record["committed_at_ms"] <= verified.evidence[-1].as_of_ms
                or not isinstance(record.get("status"), str)
                or record["status"] not in {"processed", "reversed"}
                or ("reversed_at_ms" in record and (
                    type(record["reversed_at_ms"]) is not int
                    or not record["committed_at_ms"] <= record["reversed_at_ms"]
                    <= verified.evidence[-1].as_of_ms))
                or (record["status"] == "reversed" and "reversed_at_ms" not in record)
                or (record["status"] == "processed" and "reversed_at_ms" in record)):
            raise ValueError("Linked refund evidence has an invalid payload or timestamp")
    matching = tuple(record["effect_id"] for record in linked
                     if record["payment_id"] == expected["payment_id"]
                     and record["amount_minor"] == expected["amount_minor"]
                     and record["currency"] == expected["currency"]
                     and trace.action.registered_at_ms <= record["committed_at_ms"]
                     <= trace.action.contract.deadline_ms
                     and record.get("reversed_at_ms", trace.action.contract.horizon_ms + 1)
                     > trace.action.contract.horizon_ms)
    return linked, matching
