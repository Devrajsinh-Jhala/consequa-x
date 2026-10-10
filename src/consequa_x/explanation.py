"""Compose factual explanation records from captured assessments and readback."""

from dataclasses import dataclass
from typing import Iterable

from .attribution import EffectEstimate, recency_attribution
from .graph import ConsequenceGraph, build_graph
from .models import (
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


def explain(trace: Trace, estimates: Iterable[EffectEstimate] = ()) -> ConsequenceExplanation:
    """Explain the latest verification, with separate state and effect-origin claims.

    A reported assessment is not hidden chain of thought. Unknown outcomes do
    not establish an incorrect belief. This function neither replays a policy
    nor executes a tool; estimates must come from an explicit research runner.
    """
    if not trace.verifications:
        raise ValueError("An explanation requires an independent verification record")
    verified = trace.verifications[-1]
    assessment = trace.assessment
    estimates = tuple(estimates)
    diagnoses = []
    alignment = "unassessable"
    details = verified.evidence[-1].details if verified.evidence else {}
    records = details.get("records", [])
    expected = trace.action.contract.expected
    linked_records = [record for record in records
                      if record.get("effect_id") in verified.attributable_effect_ids]
    matching_linked_records = [record for record in linked_records
                               if record.get("amount_minor") == expected.get("amount_minor")
                               and record.get("currency") == expected.get("currency")
                               and record.get("committed_at_ms", -1) <= trace.action.contract.deadline_ms
                               and record.get("reversed_at_ms", trace.action.contract.horizon_ms + 1)
                               > trace.action.contract.horizon_ms]
    if verified.status is VerificationStatus.UNKNOWN:
        diagnoses.append("UNKNOWN_OUTCOME")
        if assessment.status is not AssessmentStatus.UNKNOWN:
            diagnoses.append("UNVERIFIED_ASSESSMENT")
    else:
        is_success = verified.status is VerificationStatus.SATISFIED
        origin_sufficient = not is_success or bool(matching_linked_records)
        if origin_sufficient and assessment.status in {AssessmentStatus.SUCCESS, AssessmentStatus.FAILURE}:
            contradicted = (assessment.status is AssessmentStatus.SUCCESS) != is_success
            alignment = "contradicted" if contradicted else "consistent"
            if contradicted:
                diagnoses.append("ASSESSMENT_DIVERGENCE")
        if (any(response.status is ResponseStatus.TIMEOUT for response in trace.responses)
                and is_success and matching_linked_records):
            diagnoses.append("ACKNOWLEDGEMENT_EFFECT_DIVERGENCE")
        if any(response.status is ResponseStatus.SUCCESS for response in trace.responses) and not is_success:
            diagnoses.append("RESPONSE_EFFECT_DIVERGENCE")
        if not is_success:
            diagnoses.append("CONSEQUENCE_VIOLATION")

    if verified.status is not VerificationStatus.UNKNOWN:
        count = details.get("peak_matching_count", details.get("matching_count", 0))
        exact = trace.action.contract.exact_count
        if exact is not None and count > exact:
            diagnoses.append("EXCESS_EFFECTS")
            if len(linked_records) > exact:
                diagnoses.append("DUPLICATE_EFFECT")
        if linked_records and any(record.get("amount_minor") != expected.get("amount_minor")
                                  or record.get("currency") != expected.get("currency")
                                  for record in linked_records):
            diagnoses.append("PARAMETER_MISMATCH")
        if linked_records and any(0 < record.get("amount_minor", 0) < expected.get("amount_minor", 0)
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
