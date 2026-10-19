"""Replay a captured decision prefix, then sample the same policy again.

This is an isolated simulator primitive for studying continuation distributions.
It is not a causal attribution estimator or a reproduction of CAR. Held decisions
are reused only at their exact public request boundary. Fresh decisions receive
new phase seeds while the payment-world seed and outcome contract stay fixed.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Literal

from ..models import AssessmentStatus, EventType, ResponseStatus, ToolResponse, Trace, to_dict
from ..policies import PolicyDecision, PolicyError, PolicyReply, PolicyRequest, validate_reply
from .evaluation import BudgetedPolicy, CallBudgetExceeded
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .runner import Episode
from .templates import DEFAULT_REFUND_TEMPLATE, RefundTaskTemplate


class DecisionPrefixMismatch(PolicyError):
    """A held decision was reached with a different public policy request."""


@dataclass(frozen=True)
class DecisionReplayReceipt:
    """One reached decision, including refused or failed fresh decisions."""

    index: int
    source: Literal["held_factual", "resampled"]
    stage: str
    continuation_model_seed: int
    factual_event_id: str | None
    factual_model_seed: int | None
    policy_calls: int
    request: dict
    reply: dict | None = None
    error_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class DecisionPrefixReplay:
    """One branch receipt; failure has no fabricated episode or outcome."""

    hold_count: int
    continuation_seed: int
    factual_seed: int
    factual_decision_count: int
    policy_metadata: dict
    decisions: tuple[DecisionReplayReceipt, ...]
    policy_calls: int
    episode: Episode | None = None
    error_type: str | None = None
    error: str | None = None
    budget_exhausted: bool = False

    @property
    def unreached_factual_indices(self) -> tuple[int, ...]:
        """Captured positions not reached, including after a failed decision."""
        return tuple(range(min(len(self.decisions), self.factual_decision_count),
                           self.factual_decision_count))

    def summary(self) -> dict:
        return {
            "status": "completed" if self.episode is not None else "failed",
            "hold_count": self.hold_count,
            "continuation_seed": self.continuation_seed,
            "factual_seed": self.factual_seed,
            "factual_decision_count": self.factual_decision_count,
            "reached_decisions": len(self.decisions),
            "held_decisions": sum(item.source == "held_factual" and item.reply is not None
                                  for item in self.decisions),
            "resampled_decisions": sum(item.source == "resampled" and item.reply is not None
                                       for item in self.decisions),
            "held_requests": sum(item.source == "held_factual" for item in self.decisions),
            "resampled_requests": sum(item.source == "resampled" for item in self.decisions),
            "failed_decisions": sum(item.error_type is not None for item in self.decisions),
            "unreached_factual_indices": list(self.unreached_factual_indices),
            "policy_calls": self.policy_calls,
            "budget_exhausted": self.budget_exhausted,
            "error_type": self.error_type,
            "error": self.error,
        }


@dataclass(frozen=True)
class _Capture:
    event_id: str
    model_seed: int
    request: PolicyRequest
    reply: PolicyReply
    policy_metadata: dict


def _json_key(value) -> str:
    # JSON comparison also distinguishes booleans from integers and integers
    # from floats; Python container equality alone would accept these changes.
    return json.dumps(to_dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object_fields(value, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"{label} must contain exactly {sorted(names)}")
    return value


def _request_from_capture(value) -> PolicyRequest:
    value = _object_fields(value, {"stage", "task", "context", "responses",
                                   "attempts_remaining"}, "captured policy_request")
    if not isinstance(value["responses"], list):
        raise ValueError("captured responses must be a JSON array")
    responses = []
    for item in value["responses"]:
        item = _object_fields(item, {"attempt_id", "status", "time_ms",
                                    "provider_request_id", "result"}, "captured response")
        responses.append(ToolResponse(
            item["attempt_id"], ResponseStatus(item["status"]), item["time_ms"],
            item["provider_request_id"], item["result"],
        ))
    return PolicyRequest(value["stage"], value["task"], value["context"], tuple(responses),
                         value["attempts_remaining"])


def _reply_from_capture(value) -> PolicyReply:
    value = _object_fields(value, {"decision", "metadata"}, "captured policy_reply")
    decision = _object_fields(value["decision"], {"operation", "assessment", "rationale"},
                              "captured decision")
    return PolicyReply(PolicyDecision(decision["operation"], AssessmentStatus(decision["assessment"]),
                                     decision["rationale"]), value["metadata"])


def _metadata(policy) -> dict:
    try:
        declared = policy.metadata
        if type(declared) is not dict:
            raise PolicyError("policy.metadata must be a JSON object")
        # PolicyReply validates strict JSON rather than silently coercing tuples.
        return PolicyReply(PolicyDecision("stop"), declared).metadata
    except (TypeError, ValueError) as error:
        raise PolicyError("policy.metadata must be a strict finite JSON object") from error


class _CapturedPolicy:
    """Validate recorded boundaries in a fresh world without calling a provider."""

    def __init__(self, captures: tuple[_Capture, ...], metadata: dict):
        self.captures = captures
        self.index = 0
        self._metadata = metadata

    @property
    def metadata(self):
        return deepcopy(self._metadata)

    def decide(self, request: PolicyRequest, *, seed: int) -> PolicyReply:
        if self.index >= len(self.captures):
            raise ValueError("factual trace is missing a reached decision capture")
        capture = self.captures[self.index]
        if seed != capture.model_seed or _json_key(request) != _json_key(capture.request):
            raise ValueError("factual captures do not match the declared world and template")
        self.index += 1
        return deepcopy(capture.reply)


def _validate_factual(factual: Episode, template: RefundTaskTemplate) -> tuple[_Capture, ...]:
    # Re-decode to check frozen records' mutable JSON dictionaries at the boundary.
    if not isinstance(factual.trace, Trace):
        raise TypeError("factual.trace must be a Trace")
    trace = Trace.from_dict(factual.trace.to_dict())
    events = tuple(event for event in trace.events if event.type is EventType.AGENT_DECISION)
    if not events:
        raise ValueError("factual trace must contain captured policy decisions")
    captures = []
    for index, event in enumerate(events):
        required = {"policy_request", "policy_reply", "policy", "model_seed", "selected"}
        if not required <= event.data.keys():
            raise ValueError("factual decision lacks a complete policy capture")
        model_seed = event.data["model_seed"]
        if type(model_seed) is not int or not 0 <= model_seed <= 2**31 - 1:
            raise ValueError("captured model_seed must be an integer in the model seed range")
        if index == 0:
            if model_seed % 6 or model_seed // 6 > MAX_TRIAL_SEED:
                raise ValueError("factual selection seed must start a valid phase schedule")
            first_seed = model_seed
        elif model_seed != first_seed + index:
            raise ValueError("factual model seeds must follow the recorded phase schedule")
        request = _request_from_capture(event.data["policy_request"])
        reply = _reply_from_capture(event.data["policy_reply"])
        validate_reply(request, reply)
        metadata = PolicyReply(PolicyDecision("stop"), event.data["policy"]).metadata
        if captures and _json_key(metadata) != _json_key(captures[0].policy_metadata):
            raise ValueError("factual policy metadata changed between decisions")
        if type(event.data["selected"]) is not bool or event.data["selected"] != (
            reply.decision.operation in {"refund", "retry"}
        ):
            raise ValueError("captured selected flag does not match its decision")
        captures.append(_Capture(event.id, model_seed, request, reply, metadata))
    captured = tuple(captures)
    attempts = captured[0].request.attempts_remaining
    if not 1 <= attempts <= 5:
        raise ValueError("factual initial attempt budget must be in 1..5")
    checker = _CapturedPolicy(captured, captured[0].policy_metadata)
    regenerated = run_policy_scenario(
        factual.config, checker, seed=factual.seed, policy_seed=captured[0].model_seed // 6,
        max_attempts=attempts, template=template,
    )
    if checker.index != len(captured):
        raise ValueError("factual trace contains unreachable decision captures")
    if (_json_key(regenerated.trace) != _json_key(trace)
            or type(factual.action_selected) is not bool
            or factual.action_selected != regenerated.action_selected):
        raise ValueError("factual trace is inconsistent with its captured policy and world")
    return captured


class _PrefixPolicy:
    def __init__(self, captures: tuple[_Capture, ...], policy: BudgetedPolicy, hold_count: int):
        self.captures = captures
        self.policy = policy
        self.hold_count = hold_count
        self.receipts: list[DecisionReplayReceipt] = []
        self._metadata = deepcopy(captures[0].policy_metadata)

    @property
    def metadata(self):
        return deepcopy(self._metadata)

    def decide(self, request: PolicyRequest, *, seed: int) -> PolicyReply:
        index = len(self.receipts)
        capture = self.captures[index] if index < len(self.captures) else None
        source = "held_factual" if index < self.hold_count else "resampled"
        before = self.policy.calls
        request_data = to_dict(request)
        reply = None
        error = None
        try:
            if source == "held_factual":
                if _json_key(request) != _json_key(capture.request):
                    raise DecisionPrefixMismatch("Held decision reached a different public request")
                reply = PolicyReply(deepcopy(capture.reply.decision), {
                    "decision_prefix_replay": {
                        "source": "held_factual", "provider_call": False,
                        "factual_event_id": capture.event_id,
                        "factual_model_seed": capture.model_seed,
                        "requested_continuation_model_seed": seed,
                        "factual_reply_metadata": deepcopy(capture.reply.metadata),
                    },
                })
            else:
                if _json_key(_metadata(self.policy)) != _json_key(self._metadata):
                    raise PolicyError("Continuation policy metadata differs from factual policy")
                reply = self.policy.decide(deepcopy(request), seed=seed)
                if _json_key(_metadata(self.policy)) != _json_key(self._metadata):
                    raise PolicyError("Continuation policy metadata changed during its decision")
            validate_reply(request, reply)
            reply = deepcopy(reply)
            return reply
        except PolicyError as caught:
            error = caught
            raise
        finally:
            self.receipts.append(DecisionReplayReceipt(
                index, source, request.stage, seed,
                capture.event_id if capture else None, capture.model_seed if capture else None,
                self.policy.calls - before, request_data,
                to_dict(reply) if reply is not None and error is None else None,
                type(error).__name__ if error else None, str(error) if error else None,
            ))


def replay_decision_prefix(
    factual: Episode,
    continuation_policy: BudgetedPolicy,
    *,
    hold_count: int,
    continuation_seed: int,
    template: RefundTaskTemplate = DEFAULT_REFUND_TEMPLATE,
) -> DecisionPrefixReplay:
    """Reset the factual world, hold N exact decisions, and resample the suffix.

    All captures, the template, and declared policy identity are checked before
    any supplied policy call. ``continuation_seed`` chooses model phase keys;
    ``factual.seed`` continues to choose the simulator world. A budgeted policy
    may be shared across branches, and only calls through that object count.
    Branches can end earlier or later than the factual trace. Failed branches
    retain their reached receipts and have no semantic outcome label.

    Metadata equality checks declared identity/configuration, not hidden model
    state. Sampling under seeds does not guarantee deterministic model output.
    """
    if not isinstance(factual, Episode):
        raise TypeError("factual must be an Episode")
    if not isinstance(continuation_policy, BudgetedPolicy):
        raise TypeError("continuation_policy must be a BudgetedPolicy")
    if type(hold_count) is not int or hold_count < 0:
        raise ValueError("hold_count must be a nonnegative integer")
    if type(continuation_seed) is not int or not 0 <= continuation_seed <= MAX_TRIAL_SEED:
        raise ValueError(f"continuation_seed must be an integer in 0..{MAX_TRIAL_SEED}")
    if type(factual.seed) is not int or not 0 <= factual.seed <= MAX_TRIAL_SEED:
        raise ValueError(f"factual seed must be an integer in 0..{MAX_TRIAL_SEED}")
    if not isinstance(template, RefundTaskTemplate):
        raise TypeError("template must be a RefundTaskTemplate")
    captures = _validate_factual(factual, template)
    if hold_count > len(captures):
        raise ValueError("hold_count exceeds the factual captured decision count")
    metadata = _metadata(continuation_policy)
    if _json_key(metadata) != _json_key(captures[0].policy_metadata):
        raise ValueError("Continuation policy metadata differs from factual policy")
    prefix_policy = _PrefixPolicy(captures, continuation_policy, hold_count)
    before = continuation_policy.calls
    episode = None
    error = None
    try:
        episode = run_policy_scenario(
            factual.config, prefix_policy, seed=factual.seed, policy_seed=continuation_seed,
            max_attempts=captures[0].request.attempts_remaining, template=template,
        )
    except PolicyError as caught:
        error = caught
    return DecisionPrefixReplay(
        hold_count, continuation_seed, factual.seed, len(captures), deepcopy(metadata),
        tuple(prefix_policy.receipts), continuation_policy.calls - before, episode,
        type(error).__name__ if error else None, str(error) if error else None,
        isinstance(error, CallBudgetExceeded),
    )
