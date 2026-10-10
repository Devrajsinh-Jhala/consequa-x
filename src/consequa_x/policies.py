"""Small, inspectable policy boundary for simulated refund episodes.

Policies see only the public task, visible context, and tool responses. They do
not receive fault labels, readback observations, or evaluator truth. A rationale
is a short reported reason, not evidence of a model's internal reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from typing import Any, Literal, Protocol, runtime_checkable

from .models import AssessmentStatus, ResponseStatus, ToolResponse, to_dict


class PolicyError(ValueError):
    """A policy request, decision, or provider response could not be used safely."""


def _copy_json(value: Any, label: str = "value", active: set[int] | None = None) -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) not in (dict, list):
        raise PolicyError(f"{label} must contain strict, finite JSON values")
    active = set() if active is None else active
    if id(value) in active:
        raise PolicyError(f"{label} must not contain circular references")
    active.add(id(value))
    try:
        if type(value) is list:
            return [_copy_json(item, f"{label}[{i}]", active) for i, item in enumerate(value)]
        if any(type(key) is not str for key in value):
            raise PolicyError(f"{label} object keys must be strings")
        return {key: _copy_json(item, f"{label}.{key}", active) for key, item in value.items()}
    finally:
        active.remove(id(value))


def _object(value: Any, label: str) -> dict:
    if type(value) is not dict:
        raise PolicyError(f"{label} must be a JSON object")
    return _copy_json(value, label)


def validate_seed(seed: int) -> None:
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise PolicyError("seed must be an integer in 0..2147483647")


@dataclass(frozen=True)
class PolicyRequest:
    stage: Literal["select", "after_response"]
    task: dict
    context: dict[str, str]
    responses: tuple[ToolResponse, ...] = ()
    attempts_remaining: int = 2

    def __post_init__(self) -> None:
        if self.stage not in ("select", "after_response") or type(self.stage) is not str:
            raise PolicyError("stage must be select or after_response")
        object.__setattr__(self, "task", _object(self.task, "task"))
        copied_context = _object(self.context, "context")
        if any(type(text) is not str for text in copied_context.values()):
            raise PolicyError("context values must be natural-language strings")
        object.__setattr__(self, "context", copied_context)
        if type(self.attempts_remaining) is not int or self.attempts_remaining < 0:
            raise PolicyError("attempts_remaining must be a nonnegative integer")
        if type(self.responses) is not tuple or any(
            not isinstance(response, ToolResponse) for response in self.responses
        ):
            raise PolicyError("responses must be a tuple of ToolResponse records")
        if (self.stage == "select" and self.responses) or (
            self.stage == "after_response" and not self.responses
        ):
            raise PolicyError("select requires no responses; after_response requires a response")
        # ToolResponse is frozen, but its JSON result is mutable: copy it too.
        responses = tuple(
            ToolResponse(response.attempt_id, response.status, response.time_ms,
                         response.provider_request_id, _object(response.result, "response.result"))
            for response in self.responses
        )
        object.__setattr__(self, "responses", responses)

    def to_dict(self) -> dict:
        return to_dict(self)


@dataclass(frozen=True)
class PolicyDecision:
    operation: Literal["refund", "retry", "stop"]
    assessment: AssessmentStatus = AssessmentStatus.UNKNOWN
    rationale: str = ""

    def __post_init__(self) -> None:
        if type(self.operation) is not str or self.operation not in ("refund", "retry", "stop"):
            raise PolicyError("operation must be refund, retry, or stop")
        if not isinstance(self.assessment, AssessmentStatus):
            raise PolicyError("assessment must be an AssessmentStatus")
        if type(self.rationale) is not str:
            raise PolicyError("rationale must be a string")

    def to_dict(self) -> dict:
        return to_dict(self)


@dataclass(frozen=True)
class PolicyReply:
    decision: PolicyDecision
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PolicyDecision):
            raise PolicyError("decision must be a PolicyDecision")
        object.__setattr__(self, "metadata", _object(self.metadata, "metadata"))

    def to_dict(self) -> dict:
        return to_dict(self)


@runtime_checkable
class Policy(Protocol):
    @property
    def metadata(self) -> dict: ...

    def decide(self, request: PolicyRequest, *, seed: int) -> PolicyReply: ...


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("JSON objects must not contain duplicate keys")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise PolicyError("JSON must not contain nonfinite numbers")


def strict_json_loads(text: str) -> Any:
    """Parse one JSON value; do not repair fences, duplicate keys, or extra text."""
    if type(text) is not str:
        raise PolicyError("JSON response must be a string")
    try:
        value = json.loads(text, object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        return _copy_json(value)
    except (TypeError, ValueError, RecursionError) as error:
        raise PolicyError("Response is not strict JSON") from error


def decision_from_json(text: str) -> PolicyDecision:
    data = strict_json_loads(text)
    if type(data) is not dict or not {"operation"} <= data.keys():
        raise PolicyError("Decision must be an object containing operation")
    if data.keys() - {"operation", "assessment", "rationale"}:
        raise PolicyError("Decision contains unsupported fields")
    try:
        assessment = AssessmentStatus(data.get("assessment", "unknown"))
    except (TypeError, ValueError) as error:
        raise PolicyError("Decision has an invalid assessment") from error
    return PolicyDecision(data["operation"], assessment, data.get("rationale", ""))


def validate_reply(request: PolicyRequest, reply: PolicyReply) -> PolicyReply:
    if not isinstance(request, PolicyRequest) or not isinstance(reply, PolicyReply):
        raise PolicyError("Expected a PolicyRequest and PolicyReply")
    if not isinstance(reply.decision, PolicyDecision):
        raise PolicyError("Expected a PolicyDecision")
    PolicyDecision(reply.decision.operation, reply.decision.assessment, reply.decision.rationale)
    request = PolicyRequest(request.stage, request.task, request.context, request.responses,
                            request.attempts_remaining)
    allowed = ("refund", "stop") if request.stage == "select" else ("retry", "stop")
    if reply.decision.operation not in allowed:
        raise PolicyError(f"Operation is not allowed during {request.stage}")
    if reply.decision.operation == "retry" and request.attempts_remaining == 0:
        raise PolicyError("Retry exceeds the available attempt budget")
    # Recheck mutable JSON payloads at the boundary before recording them.
    _object(reply.metadata, "metadata")
    return reply


def get_decision_schema(request: PolicyRequest) -> dict:
    if not isinstance(request, PolicyRequest):
        raise PolicyError("Expected a PolicyRequest")
    operations = ["refund", "stop"] if request.stage == "select" else ["stop"]
    if request.stage == "after_response" and request.attempts_remaining:
        operations.insert(0, "retry")
    return {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "enum": operations},
            "assessment": {"type": "string", "enum": [status.value for status in AssessmentStatus]},
            "rationale": {"type": "string"},
        },
        "required": ["operation", "assessment", "rationale"],
        "additionalProperties": False,
    }


class ScriptedRefundPolicy:
    """Visible-context fixture baseline; this is not a language model."""

    @property
    def metadata(self) -> dict:
        return {"provider": "scripted", "policy": "visible-refund-fixture", "version": "1"}

    def decide(self, request: PolicyRequest, *, seed: int) -> PolicyReply:
        if not isinstance(request, PolicyRequest):
            raise PolicyError("Expected a PolicyRequest")
        validate_seed(seed)
        request = PolicyRequest(request.stage, request.task, request.context, request.responses,
                                request.attempts_remaining)
        if request.stage == "select":
            age = request.task.get("order_age_days")
            if type(age) is not int or age < 0:
                raise PolicyError("task.order_age_days must be a nonnegative integer")
            requested = bool(request.context.get("customer_request", "").strip())
            vip = bool(request.context.get("vip_memory", "").strip()) and bool(
                request.context.get("vip_policy", "").strip()
            )
            eligible = requested and (age <= 30 or (vip and age <= 60))
            decision = PolicyDecision("refund" if eligible else "stop", rationale=(
                "The visible request and refund policy allow this order."
                if eligible else "The visible request and policy do not allow this refund."
            ))
        else:
            status = request.responses[-1].status
            if status is ResponseStatus.SUCCESS:
                decision = PolicyDecision("stop", AssessmentStatus.SUCCESS,
                                          "The tool returned a successful response.")
            elif status is ResponseStatus.TIMEOUT:
                retry = bool(request.context.get("retry_instruction", "").strip()) and bool(
                    request.attempts_remaining
                )
                decision = PolicyDecision("retry" if retry else "stop",
                                          AssessmentStatus.UNKNOWN if retry else AssessmentStatus.FAILURE,
                                          "The tool timed out; following the visible retry instruction."
                                          if retry else "The tool timed out without an acknowledgement.")
            else:
                decision = PolicyDecision("stop", AssessmentStatus.FAILURE,
                                          "The tool returned an error.")
        return validate_reply(request, PolicyReply(decision, {**self.metadata, "seed": seed}))
