"""Compose factual explanation records from captured assessments and readback.

Explanation is domain-independent. Everything domain-specific (which effects
match the target, and domain findings such as excess or reversed effects) is
established by the verifier and recorded in its receipt; ``explain`` combines
those receipts with the captured responses and the agent's own reports.
"""

from dataclasses import dataclass
from typing import Iterable

from .errors import ConsequaTypeError, ValidationError
from .attribution import EffectEstimate, recency_attribution
from .graph import ConsequenceGraph, build_graph
from .models import (
    SCHEMA_VERSION,
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


CORE_DIAGNOSES = {
    "NO_VERIFICATION": "No independent verification was recorded for this action.",
    "UNKNOWN_OUTCOME": "Captured readback could not establish whether the outcome holds.",
    "UNVERIFIED_ASSESSMENT": "The agent made a claim the evidence cannot confirm or refute.",
    "ASSESSMENT_DIVERGENCE": "The agent's report contradicts the verified outcome.",
    "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE": ("A tool call timed out, yet a matching effect from "
                                          "this action is present."),
    "RESPONSE_EFFECT_DIVERGENCE": "The tool reported success, but the outcome is not satisfied.",
    "CONSEQUENCE_VIOLATION": "Verification found the outcome contract violated.",
    "UNASSESSABLE_ASSESSMENT": ("The outcome is known, but the verifier did not tie it to this "
                                "action's target, so the agent's report cannot be judged."),
    "EXTERNAL_ACTOR_EFFECT": "Another actor produced the observed effect.",
    "UNCONFIRMED_ORIGIN": "The observed effect is not linked to this action or another actor.",
    "CONSISTENT_OUTCOME": "Responses, the agent's report and verification agree.",
}
"""Diagnosis codes ``explain`` itself produces, with their standard messages."""


@dataclass(frozen=True)
class Diagnosis:
    """One diagnosis: a code, the records it rests on, and a sentence.

    ``evidence`` names attempt, assessment, observation or effect identifiers
    from the trace. Codes other than ``CORE_DIAGNOSES`` come from verifier
    findings.
    """

    code: str
    evidence: tuple[str, ...]
    message: str

    def to_dict(self) -> dict:
        return to_dict(self)


@dataclass(frozen=True)
class ActionExplanation:
    """What the captured evidence supports about one action."""

    action_id: str
    consequence: VerificationResult | None
    agent_assessment: AgentAssessment | None
    assessment_alignment: str
    diagnoses: tuple[Diagnosis, ...]
    summary: str
    recency_candidate_id: str | None

    @property
    def codes(self) -> tuple[str, ...]:
        """The diagnosis codes, in order."""
        return tuple(item.code for item in self.diagnoses)

    @property
    def diagnosis(self) -> str:
        """The diagnosis codes joined into one line for display; not part of the exported record."""
        return " / ".join(self.codes)

    def to_dict(self) -> dict:
        return to_dict(self)


@dataclass(frozen=True)
class TraceExplanation:
    """One explanation per action, plus the trace's evidence graph."""

    trace_id: str
    actions: tuple[ActionExplanation, ...]
    graph: ConsequenceGraph
    attribution: tuple[EffectEstimate, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def for_action(self, action_id: str) -> ActionExplanation:
        for item in self.actions:
            if item.action_id == action_id:
                return item
        raise ValidationError(f"explanation has no action {action_id!r}")

    @property
    def single_action(self) -> ActionExplanation:
        """The explanation of the trace's only action."""
        if len(self.actions) != 1:
            raise ValidationError(
                f"explanation covers {len(self.actions)} actions; use for_action()")
        return self.actions[0]

    def to_dict(self) -> dict:
        return to_dict(self)


def explain(trace: Trace, estimates: Iterable[EffectEstimate] = ()) -> TraceExplanation:
    """Explain every action from its latest verification and assessment.

    State and effect origin stay separate claims. Assessment alignment is
    judged only when the verifier recorded target matching
    (``target_effect_ids``) and, for a satisfied outcome, at least one matching
    effect from this action; otherwise it is ``unassessable``. A reported
    assessment is not hidden chain of thought, and unknown outcomes do not
    establish an incorrect belief. An action without verification is reported
    as ``NO_VERIFICATION``; missing readback is never treated as success. This
    function neither replays a policy nor executes a tool; estimates must come
    from an explicit research runner.
    """
    if not isinstance(trace, Trace):
        raise ConsequaTypeError("explain requires a Trace")
    estimates = tuple(estimates)
    return TraceExplanation(
        trace_id=trace.trace_id,
        actions=tuple(_explain_action(trace, action) for action in trace.actions),
        graph=build_graph(trace, estimates),
        attribution=estimates,
    )


def _recency_candidate(trace: Trace, action: Action) -> str | None:
    decisions = {event.id: event for event in trace.events
                 if event.type is EventType.AGENT_DECISION}
    intent = next((event for event in trace.events if event.type is EventType.ACTION_INTENT
                   and event.data.get("action_id") == action.action_id), None)
    decision = next((decisions[parent] for parent in intent.parent_ids if parent in decisions),
                    None) if intent else None
    if decision is None and decisions:
        decision = next(iter(decisions.values()))
    return recency_attribution(trace.events, before_ms=decision.time_ms) if decision else None


def _core(code: str, evidence=()) -> Diagnosis:
    return Diagnosis(code, tuple(evidence), CORE_DIAGNOSES[code])


def _explain_action(trace: Trace, action: Action) -> ActionExplanation:
    verified = trace.latest_verification(action.action_id)
    assessment = trace.latest_assessment(action.action_id)
    responses = trace.responses_for(action.action_id)
    reported = assessment.status if assessment else AssessmentStatus.UNKNOWN
    reported_text = assessment.status.value if assessment else "nothing"
    claim = (assessment.assessment_id,) if assessment else ()
    diagnoses: list[Diagnosis] = []
    alignment = "unassessable"
    if verified is None:
        diagnoses.append(_core("NO_VERIFICATION"))
        if reported is not AssessmentStatus.UNKNOWN:
            diagnoses.append(_core("UNVERIFIED_ASSESSMENT", claim))
        summary = f"Agent reported {reported_text}; no independent verification was recorded."
    else:
        observations = tuple(item.observation_id for item in verified.evidence)
        if verified.status is VerificationStatus.UNKNOWN:
            diagnoses.append(_core("UNKNOWN_OUTCOME", observations))
            if reported is not AssessmentStatus.UNKNOWN:
                diagnoses.append(_core("UNVERIFIED_ASSESSMENT", claim))
        else:
            is_success = verified.status is VerificationStatus.SATISFIED
            matched = verified.target_effect_ids
            if (matched is not None and (not is_success or matched)
                    and reported in (AssessmentStatus.SUCCESS, AssessmentStatus.FAILURE)):
                contradicted = (reported is AssessmentStatus.SUCCESS) != is_success
                alignment = "contradicted" if contradicted else "consistent"
                if contradicted:
                    diagnoses.append(_core("ASSESSMENT_DIVERGENCE", claim + observations))
            timeouts = tuple(item.attempt_id for item in responses
                             if item.status is ResponseStatus.TIMEOUT)
            if timeouts and is_success and matched:
                diagnoses.append(_core("ACKNOWLEDGEMENT_EFFECT_DIVERGENCE", timeouts + matched))
            successes = tuple(item.attempt_id for item in responses
                              if item.status is ResponseStatus.SUCCESS)
            if successes and not is_success:
                diagnoses.append(_core("RESPONSE_EFFECT_DIVERGENCE", successes + observations))
            if not is_success:
                diagnoses.append(_core("CONSEQUENCE_VIOLATION", observations))
            if alignment == "unassessable":
                diagnoses.append(_core("UNASSESSABLE_ASSESSMENT", claim))
            for finding in verified.findings:
                diagnoses.append(Diagnosis(finding.code, finding.effect_ids,
                                           finding.detail or finding.code.replace("_", " ").lower()))
            if verified.origin is OriginStatus.OTHER_ACTOR:
                diagnoses.append(_core("EXTERNAL_ACTOR_EFFECT", verified.effect_ids))
            elif verified.effect_ids and verified.origin is OriginStatus.UNKNOWN:
                diagnoses.append(_core("UNCONFIRMED_ORIGIN", verified.effect_ids))
        summary = (f"Agent reported {reported_text}; independent verification is "
                   f"{verified.status.value}; effect origin is {verified.origin.value}.")
    if not diagnoses:
        diagnoses.append(_core("CONSISTENT_OUTCOME"))
    return ActionExplanation(
        action_id=action.action_id,
        consequence=verified,
        agent_assessment=assessment,
        assessment_alignment=alignment,
        diagnoses=tuple(diagnoses),
        summary=summary,
        recency_candidate_id=_recency_candidate(trace, action),
    )
