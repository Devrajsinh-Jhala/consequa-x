"""Policy-controlled episodes in fresh simulated payment worlds.

Only natural-language task context and public provider responses reach a policy.
Fault labels, readback, verifier results and evaluator truth are withheld until
the policy has finished acting. A policy failure aborts the episode; it is not a
negative consequence result. The payment provider is always ``PaymentWorld``.
"""

from __future__ import annotations

from copy import deepcopy

from ..attribution import Intervention, ReplayOutcome
from ..explanation import explain
from ..models import (
    Action, AgentAssessment, Event, EventType, OutcomeContract, Trace,
    VerificationStatus, to_dict,
)
from ..policies import Policy, PolicyError, PolicyRequest, validate_reply
from ..verification import verify
from .payments import Fault, PaymentWorld
from .runner import Episode, ScenarioConfig, _intervene
from .templates import DEFAULT_REFUND_TEMPLATE, RefundTaskTemplate


# Reserve six disjoint model phase seeds for each trial: selection plus at most
# five after-response decisions. This aligns corresponding replay phases while
# avoiding reuse between adjacent trials; it does not guarantee LLM determinism.
MAX_TRIAL_SEED = (2**31 - 1 - 5) // 6
_CONTEXT_TYPES = (
    ("customer_request", EventType.USER_INPUT),
    ("vip_memory", EventType.MEMORY_READ),
    ("vip_policy", EventType.RETRIEVAL),
    ("retry_instruction", EventType.SYSTEM_INSTRUCTION),
    ("distractor", EventType.RETRIEVAL),
)


def _validate_run(config: ScenarioConfig, seed: int, max_attempts: int) -> None:
    if not isinstance(config, ScenarioConfig):
        raise TypeError("config must be a ScenarioConfig")
    if type(seed) is not int or not 0 <= seed <= MAX_TRIAL_SEED:
        raise ValueError(f"seed must be an integer in 0..{MAX_TRIAL_SEED}")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be an integer in 1..5")


def run_policy_scenario(
    config: ScenarioConfig,
    policy: Policy,
    *,
    seed: int = 0,
    intervention: Intervention | None = None,
    max_attempts: int = 2,
    template: RefundTaskTemplate = DEFAULT_REFUND_TEMPLATE,
    policy_seed: int | None = None,
) -> Episode:
    """Let a policy select the refund, retries, and reported outcome assessment.

    Every call is stateless with the declared task, intervened context and public
    response history. Each trial starts with a fresh payment world. Seeded model
    requests are best effort: backend versions and hardware can affect responses.
    Context replacement reruns dependent decisions under the same phase keys.
    ``policy_seed`` optionally selects independent model phase keys while
    ``seed`` retains the factual world's identities and deterministic dynamics.
    ``selection_probability``, ``retry_probability`` and ``timeout_assessment``
    belong to the old fixture runner and do not control this policy's decisions.
    """
    _validate_run(config, seed, max_attempts)
    if policy_seed is not None:
        _validate_run(config, policy_seed, max_attempts)
    effective_policy_seed = seed if policy_seed is None else policy_seed
    if not isinstance(template, RefundTaskTemplate):
        raise TypeError("template must be a RefundTaskTemplate")
    context = _intervene(config.context, intervention)
    visible_context = template.render_context(context)
    world = PaymentWorld({"pay_42": 1_000_000, "pay_other": 1_000_000}, seed=seed)
    trace_id = f"trace:{seed}"
    events = [
        Event(name, trace_id, kind, index, data={"value": visible_context[name]})
        for index, (name, kind) in enumerate(_CONTEXT_TYPES)
    ]
    context_ids = tuple(name for name, _ in _CONTEXT_TYPES)
    world.advance(len(_CONTEXT_TYPES))
    action = Action(
        action_id=f"refund:{seed}", trace_id=trace_id, actor="RefundAgent", name="refund",
        arguments={"payment_id": "pay_42", "amount_minor": config.amount_minor, "currency": "INR"},
        registered_at_ms=world.time_ms,
        contract=OutcomeContract(
            f"contract:{seed}", "refund_processed",
            {"payment_id": "pay_42", "amount_minor": config.amount_minor, "currency": "INR"},
            config.deadline_ms, stability_ms=config.stability_ms,
        ),
        idempotency_key=f"consequa-refund-{seed}" if config.use_idempotency else None,
    )
    task = {
        **action.arguments,
        "order_age_days": config.order_age_days,
        "base_refund_policy": template.base_refund_policy,
        "idempotency_available": config.use_idempotency,
        "deadline_ms": action.contract.deadline_ms,
        "horizon_ms": action.contract.horizon_ms,
    }
    responses = []
    response_ids = []

    def decide(stage: str, number: int):
        request = PolicyRequest(
            stage=stage, task=deepcopy(task), context=deepcopy(visible_context),
            responses=tuple(deepcopy(responses)), attempts_remaining=max_attempts - number,
        )
        # A custom policy must not be able to rewrite the captured prompt or the
        # simulator's response history by mutating ordinary JSON containers.
        request_data = to_dict(request)
        declared_metadata = policy.metadata
        if type(declared_metadata) is not dict:
            raise PolicyError("policy.metadata must be a JSON object")
        try:
            policy_metadata = to_dict(declared_metadata)
        except (TypeError, ValueError) as error:
            raise PolicyError("policy.metadata must contain finite JSON values") from error
        model_seed = effective_policy_seed * 6 + number
        reply = policy.decide(deepcopy(request), seed=model_seed)
        validate_reply(request, reply)
        reply = deepcopy(reply)
        decision_id = "refund_decision" if stage == "select" else f"response_decision_{number}"
        events.append(Event(
            decision_id, trace_id, EventType.AGENT_DECISION, world.time_ms,
            actor=action.actor, parent_ids=context_ids + tuple(response_ids),
            data={
                "selected": reply.decision.operation in {"refund", "retry"},
                "model_seed": model_seed,
                "policy": policy_metadata,
                "policy_request": request_data,
                "policy_reply": to_dict(reply),
            },
        ))
        assessment = AgentAssessment(
            reply.decision.assessment, world.time_ms,
            tuple(response_ids) or (decision_id,), reply.decision.rationale,
        )
        events.append(Event(
            f"assessment_{number}", trace_id, EventType.AGENT_ASSESSMENT, world.time_ms,
            actor=action.actor, parent_ids=(decision_id,), data=assessment.to_dict(),
        ))
        return reply.decision, decision_id, assessment

    decision, decision_id, assessment = decide("select", 0)
    selected = decision.operation == "refund"
    if selected:
        for number in range(1, max_attempts + 1):
            intent_id = "refund_intent" if number == 1 else f"retry_intent_{number}"
            events.append(Event(
                intent_id, trace_id, EventType.ACTION_INTENT, world.time_ms,
                actor=action.actor, parent_ids=(decision_id,),
                data={"action_id": action.action_id, "arguments": action.arguments},
            ))
            attempt_id = f"attempt:{seed}:{number}"
            dispatch_time = world.time_ms
            response = world.refund(action, attempt_id, config.fault if number == 1 else Fault.CLEAN)
            response_parent = intent_id
            if response.result.get("code") != "dispatch_failed":
                response_parent = f"dispatch_{number}"
                events.append(Event(
                    response_parent, trace_id, EventType.ACTION_DISPATCH, dispatch_time,
                    actor=action.actor, parent_ids=(intent_id,),
                    data={"action_id": action.action_id, "attempt_id": attempt_id},
                ))
            response_id = f"response_{number}"
            events.append(Event(
                response_id, trace_id, EventType.TOOL_RESPONSE, response.time_ms,
                parent_ids=(response_parent,), data=response.to_dict(),
            ))
            responses.append(response)
            response_ids.append(response_id)
            decision, decision_id, assessment = decide("after_response", number)
            if decision.operation == "stop":
                break

    if config.external_actor:
        world.external_refund("pay_42", config.amount_minor)
    if config.compensate:
        # Only evaluator-owned fault injection sees hidden fixture state.
        refunds = [record for record in world.ground_truth if record.get("kind") == "refund"]
        if refunds:
            world.advance(1)
            world.reverse(refunds[0]["effect_id"])
    world.advance(max(0, action.contract.horizon_ms - world.time_ms))
    observations = [world.read_refunds(
        "pay_42", lag_ms=config.read_lag_ms, include_provenance=config.include_provenance,
    )]
    verifications = [verify(action, observations[-1])]
    if config.reconcile_readback and verifications[-1].status is VerificationStatus.UNKNOWN:
        world.advance(observations[-1].scope.get("lag_ms", 0))
        observations.append(world.read_refunds(
            "pay_42", lag_ms=config.read_lag_ms, include_provenance=config.include_provenance,
        ))
        verifications.append(verify(action, observations[-1]))
    trace = Trace(
        trace_id, action, tuple(events), tuple(responses), assessment,
        tuple(observations), tuple(verifications),
    )
    return Episode(trace, explain(trace), world.ground_truth, selected, config, seed)


class RefundPolicyReplayRunner:
    """Rerun policy decisions with fresh simulated payments, never live payments.

    Snapshot isolation describes the simulated world. The supplied policy should
    be stateless over its request and seed; external model runtimes may remain
    nondeterministic even when the same phase seeds are requested.
    """

    mode = "isolated_simulation"
    snapshot_isolation = True

    def __init__(self, config: ScenarioConfig, policy: Policy, *, max_attempts: int = 2,
                 template: RefundTaskTemplate = DEFAULT_REFUND_TEMPLATE):
        _validate_run(config, 0, max_attempts)
        if not isinstance(template, RefundTaskTemplate):
            raise TypeError("template must be a RefundTaskTemplate")
        self.config = config
        self.policy = policy
        self.max_attempts = max_attempts
        self.template = template

    def run(self, intervention: Intervention | None, seed: int) -> ReplayOutcome:
        episode = run_policy_scenario(
            self.config, self.policy, seed=seed, intervention=intervention,
            max_attempts=self.max_attempts, template=self.template,
        )
        from .targets import episode_outcome

        return episode_outcome(episode)
