from dataclasses import replace
import json

import jsonschema
import pytest

from consequa_x.models import AssessmentStatus, ResponseStatus, ToolResponse, to_dict
from consequa_x.policies import (
    Policy, PolicyDecision, PolicyError, PolicyReply, PolicyRequest, ScriptedRefundPolicy,
    decision_from_json, get_decision_schema, validate_reply,
)


def response(status=ResponseStatus.TIMEOUT):
    return ToolResponse(attempt_id="attempt:1", status=status, time_ms=6, provider_request_id="request:1", result={"code": "timeout"}, action_id="refund:1")


def request(**changes):
    values = {
        "stage": "select", "task": {"order_age_days": 43},
        "context": {"customer_request": "Please refund my order.",
                    "vip_memory": "The customer has VIP status.",
                    "vip_policy": "VIP refunds are allowed through 60 days."},
    }
    values.update(changes)
    return PolicyRequest(**values)


def test_public_records_copy_json_and_export_without_aliasing():
    task = {"order_age_days": 43, "details": {"items": [1]}}
    context = {"customer_request": "Please refund."}
    original = replace(response(), result={**response().result, "nested": {"items": [1]}})
    captured = request(stage="after_response", task=task, context=context, responses=(original,))
    task["details"]["items"].append(2)
    context["customer_request"] = "Modified"
    with pytest.raises(TypeError, match="read-only"):
        original.result["nested"]["items"].append(2)
    assert captured.task["details"]["items"] == [1]
    assert captured.context["customer_request"] == "Please refund."
    assert captured.responses[0].result["nested"]["items"] == [1]
    exported = captured.to_dict()
    exported["task"]["details"]["items"].append(3)
    assert captured.task["details"]["items"] == [1]
    metadata = {"usage": {"tokens": [1]}}
    reply = PolicyReply(PolicyDecision("stop"), metadata)
    metadata["usage"]["tokens"].append(2)
    assert reply.metadata["usage"]["tokens"] == [1]
    assert to_dict(reply) == reply.to_dict()


@pytest.mark.parametrize("changes", [
    {"stage": "other"}, {"stage": []}, {"task": []},
    {"task": {"value": float("nan")}}, {"task": {1: "key"}},
    {"context": {"customer_request": True}}, {"context": []},
    {"responses": [response()]}, {"responses": ("not-response",)},
    {"responses": (response(),)}, {"stage": "after_response"},
    {"attempts_remaining": -1}, {"attempts_remaining": True},
])
def test_requests_reject_invalid_and_inconsistent_values(changes):
    with pytest.raises(PolicyError):
        request(**changes)


def test_requests_reject_cycles_and_python_containers():
    cyclic = {}
    cyclic["cycle"] = cyclic
    for value in (cyclic, {"items": (1, 2)}, {"items": {1, 2}}):
        with pytest.raises(PolicyError):
            request(task=value)


@pytest.mark.parametrize("arguments", [
    ("unsupported",), (True,), ("stop", "success"), ("stop", AssessmentStatus.UNKNOWN, None),
])
def test_decision_constructor_validates_types(arguments):
    with pytest.raises(PolicyError):
        PolicyDecision(*arguments)


@pytest.mark.parametrize("content", [
    '{}', '[]', '{"operation":"delete"}',
    '{"operation":"stop","unknown":1}',
    '{"operation":"stop","assessment":"complete"}',
    '{"operation":"stop","rationale":3}',
    '{"operation":"stop","operation":"refund"}',
    '{"operation":"stop","rationale":NaN}',
    '{"operation":"stop","rationale":Infinity}',
    '{"operation":"stop","extra":1e400}',
    '```json\n{"operation":"stop"}\n```',
    '{"operation":"stop"} trailing',
    '{"operation":"stop"}{"operation":"refund"}',
])
def test_parser_never_repairs_invalid_model_output(content):
    with pytest.raises(PolicyError):
        decision_from_json(content)


def test_parser_defaults_and_enum_conversion():
    assert decision_from_json(' {"operation":"stop"} ') == PolicyDecision("stop")
    assert decision_from_json(json.dumps({
        "operation": "retry", "assessment": "unknown", "rationale": "No acknowledgement."
    })).assessment is AssessmentStatus.UNKNOWN


def test_reply_enforces_stage_and_attempt_budget():
    initial = request()
    final = request(stage="after_response", responses=(response(),), attempts_remaining=0)
    for supplied, decision in ((initial, "retry"), (final, "refund"), (final, "retry")):
        with pytest.raises(PolicyError):
            validate_reply(supplied, PolicyReply(PolicyDecision(decision)))
    retry_request = replace(final, attempts_remaining=1)
    reply = PolicyReply(PolicyDecision("retry"))
    assert validate_reply(retry_request, reply) is reply
    assert validate_reply(final, PolicyReply(PolicyDecision("stop"))).decision.operation == "stop"
    reply.metadata["invalid"] = float("nan")
    with pytest.raises(PolicyError):
        validate_reply(retry_request, reply)


def test_stage_schema_excludes_unavailable_operations():
    final = request(stage="after_response", responses=(response(),), attempts_remaining=0)
    assert get_decision_schema(request())["properties"]["operation"]["enum"] == ["refund", "stop"]
    assert get_decision_schema(final)["properties"]["operation"]["enum"] == ["stop"]
    schema = get_decision_schema(replace(final, attempts_remaining=1))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(PolicyDecision("retry").to_dict(), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(PolicyDecision("refund").to_dict(), schema)


def test_reply_boundary_rechecks_decision_even_for_custom_policy_tampering():
    decision = PolicyDecision("refund")
    reply = PolicyReply(decision)
    object.__setattr__(decision, "assessment", "success")
    with pytest.raises(PolicyError):
        validate_reply(request(), reply)


def test_scripted_policy_rechecks_mutable_request_containers():
    supplied = request()
    supplied.context["customer_request"] = True
    with pytest.raises(PolicyError):
        ScriptedRefundPolicy().decide(supplied, seed=0)


@pytest.mark.parametrize("age,context,operation", [
    (30, {"customer_request": "Please refund."}, "refund"),
    (31, {"customer_request": "Please refund."}, "stop"),
    (43, {"customer_request": "Please refund.", "vip_memory": "VIP", "vip_policy": "60 days"}, "refund"),
    (60, {"customer_request": "Please refund.", "vip_memory": "VIP", "vip_policy": "60 days"}, "refund"),
    (61, {"customer_request": "Please refund.", "vip_memory": "VIP", "vip_policy": "60 days"}, "stop"),
    (43, {"customer_request": "Please refund.", "vip_memory": "VIP"}, "stop"),
    (43, {"customer_request": "Please refund.", "vip_policy": "60 days"}, "stop"),
    (10, {"customer_request": "   "}, "stop"),
    (10, {}, "stop"),
])
def test_scripted_policy_reads_only_visible_eligibility(age, context, operation):
    policy = ScriptedRefundPolicy()
    assert isinstance(policy, Policy)
    reply = policy.decide(request(task={"order_age_days": age}, context=context), seed=3)
    assert reply.decision.operation == operation
    assert reply.decision.assessment is AssessmentStatus.UNKNOWN
    assert reply.metadata["provider"] == "scripted"


@pytest.mark.parametrize("status,retry,remaining,operation,assessment", [
    (ResponseStatus.SUCCESS, True, 1, "stop", AssessmentStatus.SUCCESS),
    (ResponseStatus.ERROR, True, 1, "stop", AssessmentStatus.FAILURE),
    (ResponseStatus.TIMEOUT, False, 1, "stop", AssessmentStatus.FAILURE),
    (ResponseStatus.TIMEOUT, True, 1, "retry", AssessmentStatus.UNKNOWN),
    (ResponseStatus.TIMEOUT, True, 0, "stop", AssessmentStatus.FAILURE),
])
def test_scripted_policy_assesses_latest_public_response(status, retry, remaining, operation, assessment):
    supplied = request(stage="after_response", responses=(response(status),),
                       context={"retry_instruction": "Retry on timeout." if retry else ""},
                       attempts_remaining=remaining)
    result = ScriptedRefundPolicy().decide(supplied, seed=0).decision
    assert result.operation == operation
    assert result.assessment is assessment


@pytest.mark.parametrize("seed", [-1, True, 2**31, 0.5])
def test_scripted_policy_rejects_invalid_seed(seed):
    with pytest.raises(PolicyError):
        ScriptedRefundPolicy().decide(request(), seed=seed)


def test_scripted_policy_is_explicitly_a_presence_fixture_not_a_text_interpreter():
    supplied = request(context={"customer_request": "Not a refund request.",
                                "vip_memory": "Any nonempty memory.",
                                "vip_policy": "Any nonempty policy."})
    # This deliberate fixture behavior must not be presented as an LLM result.
    assert ScriptedRefundPolicy().decide(supplied, seed=0).decision.operation == "refund"
