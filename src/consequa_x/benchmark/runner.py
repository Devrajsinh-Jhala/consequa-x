"""Offline fixture policies and full-world replay adapters.

These policies are transparent research fixtures, not LLMs. Evaluator truth is
returned separately and is never an input to verify(), explain(), or build_graph().
"""

from dataclasses import dataclass, replace
import math
import random

from ..attribution import Intervention, ReplayOutcome
from ..explanation import ConsequenceExplanation, explain
from ..models import (
    Action, AgentAssessment, AssessmentStatus, Event, EventType, OutcomeContract,
    ResponseStatus, Trace, VerificationStatus,
)
from ..verification import verify
from .payments import Fault, PaymentWorld


@dataclass(frozen=True)
class RefundContext:
    customer_request: bool = True
    vip_memory: bool = True
    vip_policy: bool = True
    retry_instruction: bool = False
    distractor: str = "Weather is pleasant today."

    def __post_init__(self):
        for name in ("customer_request", "vip_memory", "vip_policy", "retry_instruction"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if not isinstance(self.distractor, str):
            raise ValueError("distractor must be a string")


@dataclass(frozen=True)
class ScenarioConfig:
    name: str = "timeout_after_commit"
    fault: Fault = Fault.TIMEOUT_AFTER_COMMIT
    context: RefundContext = RefundContext()
    use_idempotency: bool = True
    timeout_assessment: AssessmentStatus = AssessmentStatus.FAILURE
    include_provenance: bool = True
    external_actor: bool = False
    compensate: bool = False
    reconcile_readback: bool = False
    read_lag_ms: int = 0
    deadline_ms: int = 100
    stability_ms: int = 0
    order_age_days: int = 43
    amount_minor: int = 500_000
    selection_probability: float = 1.0
    retry_probability: float = 1.0

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a nonempty string")
        if not isinstance(self.fault, Fault) or not isinstance(self.context, RefundContext):
            raise TypeError("fault and context require their typed records")
        if self.timeout_assessment not in {AssessmentStatus.FAILURE, AssessmentStatus.UNKNOWN}:
            raise ValueError("timeout assessment must be failure or unknown")
        for name in ("use_idempotency", "include_provenance", "external_actor", "compensate", "reconcile_readback"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        for name in ("read_lag_ms", "deadline_ms", "stability_ms", "order_age_days", "amount_minor"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.deadline_ms < 10 or not 0 < self.amount_minor <= 500_000:
            raise ValueError("deadline must be >=10ms and amount_minor in 1..500000")
        for name in ("selection_probability", "retry_probability"):
            value = getattr(self, name)
            if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite probability")


@dataclass(frozen=True)
class Episode:
    trace: Trace
    explanation: ConsequenceExplanation
    ground_truth: tuple[dict, ...]
    action_selected: bool
    config: ScenarioConfig
    seed: int


def _intervene(context: RefundContext, intervention: Intervention | None) -> RefundContext:
    if intervention is None:
        return context
    names = {"customer_request", "vip_memory", "vip_policy", "retry_instruction", "distractor"}
    if intervention.event_id not in names:
        raise ValueError("Only declared fixture context fields can be intervened on")
    if intervention.kind == "neutralize":
        value = "" if intervention.event_id == "distractor" else False
    else:
        value = intervention.replacement
    return replace(context, **{intervention.event_id: value})


def run_scenario(config: ScenarioConfig = ScenarioConfig(), *, seed: int = 0,
                 intervention: Intervention | None = None) -> Episode:
    """Run a fresh isolated simulated world with a fixed consequence contract.

    Context intervention takes place before its dependent decisions. All affected
    descendants are rerun. A non-selected action keeps the same outcome target,
    so replay does not condition on the agent choosing the original action.
    """
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    context = _intervene(config.context, intervention)
    world = PaymentWorld({"pay_42": 1_000_000, "pay_other": 1_000_000}, seed=seed)
    # Do not encode the injected fault label in explainer-visible identities.
    trace_id = f"trace:{seed}"
    events = []
    types = (
        ("customer_request", EventType.USER_INPUT),
        ("vip_memory", EventType.MEMORY_READ),
        ("vip_policy", EventType.RETRIEVAL),
        ("retry_instruction", EventType.SYSTEM_INSTRUCTION),
        ("distractor", EventType.RETRIEVAL),
    )
    for index, (name, kind) in enumerate(types):
        events.append(Event(name, trace_id, kind, index, data={"value": getattr(context, name)}))
    world.advance(len(types))
    # Separate keyed streams keep factual/counterfactual exogenous draws aligned.
    selection_draw = random.Random(f"selection:{seed}").random()
    retry_draw = random.Random(f"retry:{seed}").random()
    allowed = context.customer_request and (
        config.order_age_days <= 30 or (context.vip_memory and context.vip_policy)
    )
    selected = allowed and selection_draw < config.selection_probability
    events.append(Event("refund_decision", trace_id, EventType.AGENT_DECISION, world.time_ms,
                        actor="RefundAgent", parent_ids=("customer_request", "vip_memory", "vip_policy"),
                        data={"selected": selected, "order_age_days": config.order_age_days}))
    action = Action(
        action_id=f"refund:{seed}", trace_id=trace_id, actor="RefundAgent", name="refund",
        arguments={"payment_id": "pay_42", "amount_minor": config.amount_minor, "currency": "INR"},
        registered_at_ms=world.time_ms,
        contract=OutcomeContract(f"contract:{seed}", "refund_processed",
                                 {"payment_id": "pay_42", "amount_minor": config.amount_minor, "currency": "INR"},
                                 config.deadline_ms, stability_ms=config.stability_ms),
        idempotency_key=f"consequa-refund-{seed}" if config.use_idempotency else None,
    )
    responses = []
    assessment = AgentAssessment(AssessmentStatus.UNKNOWN, world.time_ms, ("refund_decision",),
                                 "No refund action was selected.")
    if selected:
        events.append(Event("refund_intent", trace_id, EventType.ACTION_INTENT, world.time_ms,
                            actor=action.actor, parent_ids=("refund_decision",),
                            data={"action_id": action.action_id, "arguments": action.arguments}))

        def attempt(number, fault, parent):
            nonlocal assessment
            attempt_id = f"attempt:{seed}:{number}"
            dispatch_time = world.time_ms
            response = world.refund(action, attempt_id, fault)
            dispatched = response.result.get("code") != "dispatch_failed"
            response_parent = parent
            if dispatched:
                response_parent = f"dispatch_{number}"
                events.append(Event(response_parent, trace_id, EventType.ACTION_DISPATCH, dispatch_time,
                                    actor=action.actor, parent_ids=(parent,),
                                    data={"action_id": action.action_id, "attempt_id": attempt_id}))
            response_event_id = f"response_{number}"
            events.append(Event(response_event_id, trace_id, EventType.TOOL_RESPONSE, response.time_ms,
                                parent_ids=(response_parent,), data=response.to_dict()))
            responses.append(response)
            status = (AssessmentStatus.SUCCESS if response.status is ResponseStatus.SUCCESS else
                      config.timeout_assessment if response.status is ResponseStatus.TIMEOUT else
                      AssessmentStatus.FAILURE)
            assessment = AgentAssessment(status, response.time_ms, (response_event_id,),
                                         "Fixture assessment based only on the returned response.")
            assessment_id = f"assessment_{number}"
            events.append(Event(assessment_id, trace_id, EventType.AGENT_ASSESSMENT, response.time_ms,
                                actor=action.actor, parent_ids=(response_event_id,), data=assessment.to_dict()))
            return response, assessment_id

        response, assessment_id = attempt(1, config.fault, "refund_intent")
        if (response.status is ResponseStatus.TIMEOUT and context.retry_instruction
                and retry_draw < config.retry_probability):
            events.append(Event("retry_decision", trace_id, EventType.AGENT_DECISION, world.time_ms,
                                actor=action.actor, parent_ids=(assessment_id, "retry_instruction"),
                                data={"selected": True, "reason": "retry_on_timeout"}))
            attempt(2, Fault.CLEAN, "retry_decision")

    if config.external_actor:
        world.external_refund("pay_42", config.amount_minor)
    if config.compensate:
        # Harness-owned fault injection may inspect truth. No gold enters explainer inputs.
        refunds = [record for record in world.ground_truth if record.get("kind") == "refund"]
        if refunds:
            world.advance(1)
            world.reverse(refunds[0]["effect_id"])
    world.advance(max(0, action.contract.horizon_ms - world.time_ms))
    observations = [world.read_refunds("pay_42", lag_ms=config.read_lag_ms,
                                       include_provenance=config.include_provenance)]
    verifications = [verify(action, observations[-1])]
    if config.reconcile_readback and verifications[-1].status is VerificationStatus.UNKNOWN:
        lag = observations[-1].scope.get("lag_ms", 0)
        world.advance(lag)
        observations.append(world.read_refunds("pay_42", lag_ms=config.read_lag_ms,
                                               include_provenance=config.include_provenance))
        verifications.append(verify(action, observations[-1]))
    trace = Trace(trace_id, action, tuple(events), tuple(responses), assessment,
                  tuple(observations), tuple(verifications))
    return Episode(trace, explain(trace), world.ground_truth, selected, config, seed)


class RefundReplayRunner:
    """Full-world fixture replay only; this class has no real provider adapter."""

    mode = "isolated_simulation"
    snapshot_isolation = True

    def __init__(self, config: ScenarioConfig = ScenarioConfig()):
        self.config = config

    def run(self, intervention: Intervention | None, seed: int) -> ReplayOutcome:
        episode = run_scenario(self.config, seed=seed, intervention=intervention)
        status = episode.trace.verifications[-1].status
        consequence = None if status is VerificationStatus.UNKNOWN else status is VerificationStatus.SATISFIED
        return ReplayOutcome(episode.action_selected, consequence)


def demo_scenarios() -> tuple[ScenarioConfig, ...]:
    retry = RefundContext(retry_instruction=True)
    return (
        ScenarioConfig("clean", Fault.CLEAN),
        ScenarioConfig(),
        ScenarioConfig("timeout_before_commit", Fault.TIMEOUT_BEFORE_COMMIT),
        ScenarioConfig("false_success", Fault.FALSE_SUCCESS),
        ScenarioConfig("partial_effect", Fault.PARTIAL_EFFECT),
        ScenarioConfig("delayed_visibility", Fault.DELAYED_VISIBILITY),
        ScenarioConfig("delayed_reconciled", Fault.DELAYED_VISIBILITY, reconcile_readback=True),
        ScenarioConfig("unsafe_retry", context=retry, use_idempotency=False),
        ScenarioConfig("safe_retry", context=retry),
        ScenarioConfig("external_actor", Fault.TIMEOUT_BEFORE_COMMIT, external_actor=True),
        ScenarioConfig("missing_provenance", Fault.CLEAN, include_provenance=False),
        ScenarioConfig("synthetic_compensation", Fault.CLEAN, compensate=True),
    )
