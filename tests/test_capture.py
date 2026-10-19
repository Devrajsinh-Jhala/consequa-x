"""TraceRecorder arranges application-supplied records into an ordinary trace."""

import inspect
import time

import pytest

from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Event, EventType, Observation, OutcomeContract,
    ResponseStatus, ToolResponse, TimeBase, Trace, TraceRecorder, VerificationStatus, build_graph,
    capture_tool, explain,
)


EXPECTED = {"payment_id": "p1", "amount_minor": 1000, "currency": "INR"}


def contract():
    return OutcomeContract(contract_id="contract-1", predicate="refund_processed", expected=dict(EXPECTED),
                           deadline_ms=50, stability_ms=20)


def readback(observation_id="readback-1", *, observed=100, watermark=100, attempt="refund-1:attempt-1"):
    return Observation(observation_id=observation_id, source="independent-ledger", observed_at_ms=observed, as_of_ms=watermark,
                       scope={"payment_id": "p1"},
                       records=({**EXPECTED, "effect_id": "effect-1", "committed_at_ms": 25,
                         "status": "processed", "action_id": "refund-1", "attempt_id": attempt,
                         "actor": "agent"},))


def recorded(**kwargs):
    rec = TraceRecorder("trace-1", actor="agent", **{"time_base": "relative_ms", **kwargs})
    context = rec.context("user_input", {"text": "refund please"}, at_ms=0)
    rec.decision({"selected": True}, inputs=(context,), at_ms=2)
    rec.register("refund-1", "refund", dict(EXPECTED), contract=contract(), at_ms=5)
    attempt = rec.dispatch(at_ms=5)
    rec.response(attempt, "timeout", at_ms=20)
    rec.assessment("failure", at_ms=25, rationale="The tool timed out.")
    return rec


def test_recorder_trace_equals_the_hand_built_trace():
    rec = recorded()
    receipt = rec.verify(readback())
    response = ToolResponse(attempt_id="refund-1:attempt-1", status=ResponseStatus.TIMEOUT, time_ms=20, provider_request_id="refund-1:attempt-1", action_id="refund-1")
    assessment = AgentAssessment(status=AssessmentStatus.FAILURE, time_ms=25, evidence_event_ids=("response-1",), rationale="The tool timed out.", assessment_id="assessment-1", action_id="refund-1")
    events = (
        Event(id="context-1", type=EventType.USER_INPUT, time_ms=0, actor=None, parent_ids=(), data={"text": "refund please"}),
        Event(id="decision-1", type=EventType.AGENT_DECISION, time_ms=2, actor="agent", parent_ids=("context-1",),
              data={"selected": True}),
        Event(id="intent-1", type=EventType.ACTION_INTENT, time_ms=5, actor="agent", parent_ids=("decision-1",),
              data={"action_id": "refund-1", "arguments": dict(EXPECTED)}),
        Event(id="dispatch-1", type=EventType.ACTION_DISPATCH, time_ms=5, actor="agent", parent_ids=("intent-1",),
              data={"action_id": "refund-1", "attempt_id": "refund-1:attempt-1"}),
        Event(id="response-1", type=EventType.TOOL_RESPONSE, time_ms=20, actor=None, parent_ids=("dispatch-1",),
              data=response.to_dict()),
        Event(id="assessment-1", type=EventType.AGENT_ASSESSMENT, time_ms=25, actor="agent", parent_ids=("response-1",),
              data=assessment.to_dict()),
    )
    action = Action(action_id="refund-1", actor="agent", name="refund", arguments=dict(EXPECTED), registered_at_ms=5, contract=contract())
    expected = Trace(trace_id="trace-1", time_base=TimeBase.RELATIVE_MS, actions=(action,), events=events, responses=(response,), assessments=(assessment,), observations=(readback(),), verifications=(receipt,))
    trace = rec.trace()
    assert trace == expected
    assert Trace.from_json(trace.to_json()) == trace


def test_recorded_trace_explains_and_links_the_effect_to_its_dispatch():
    rec = recorded()
    receipt = rec.verify(readback())
    trace = rec.trace()
    explanation = explain(trace)
    assert receipt.status is VerificationStatus.SATISFIED
    assert explanation.single_action.assessment_alignment == "contradicted"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in explanation.single_action.codes
    edges = {(edge.source, edge.target, edge.kind) for edge in build_graph(trace).edges}
    assert ("dispatch-1", "response-1", "RESPONSE") in edges
    assert ("dispatch-1", "effect:effect-1", "EFFECT") in edges


def test_later_readback_is_added_without_rewriting_an_earlier_unknown():
    rec = recorded()
    first = rec.verify(readback("readback-1", observed=60, watermark=60))
    second = rec.verify(readback("readback-2", observed=120, watermark=120))
    trace = rec.trace()
    assert first.status is VerificationStatus.UNKNOWN
    assert second.status is VerificationStatus.SATISFIED
    assert trace.verifications == (first, second)
    assert [item.observation_id for item in trace.observations] == ["readback-1", "readback-2"]


def test_clock_supplies_times_when_none_are_given():
    ticks = iter([0, 4, 9, 30, 31])
    rec = TraceRecorder("trace-1", actor="agent", clock=lambda: next(ticks))
    rec.register("refund-1", "refund", dict(EXPECTED), contract=contract())
    attempt = rec.dispatch()
    rec.response(attempt, ResponseStatus.SUCCESS)
    rec.assessment(AssessmentStatus.SUCCESS)
    trace = rec.trace()
    assert [event.time_ms for event in trace.events] == [0, 4, 9, 30]
    assert trace.single_action.registered_at_ms == 0

    assert trace.time_base is TimeBase.RELATIVE_MS  # A custom clock claims no wall-clock origin.

    default = TraceRecorder("trace-2", actor="agent")
    default.register("refund-1", "refund", dict(EXPECTED), contract=contract())
    registered = default.actions[0].registered_at_ms
    assert default.time_base is TimeBase.UNIX_MS
    assert type(registered) is int and abs(registered - time.time() * 1000) < 60_000
    relative = TraceRecorder("trace-3", actor="agent", time_base="relative_ms")
    relative.register("refund-1", "refund", dict(EXPECTED), contract=contract())
    assert relative.time_base is TimeBase.RELATIVE_MS and relative.actions[0].registered_at_ms < 60_000
    with pytest.raises(ValueError, match="time_base"):
        TraceRecorder("trace-4", actor="agent", time_base="iso")


@pytest.mark.parametrize("bad_time", [-1, 1.5, True, "5"])
def test_times_must_be_nonnegative_integers(bad_time):
    rec = TraceRecorder("trace-1", actor="agent")
    with pytest.raises(ValueError, match="nonnegative integer"):
        rec.context("user_input", at_ms=bad_time)
    with pytest.raises(ValueError, match="nonnegative integer"):
        TraceRecorder("trace-1", actor="agent", clock=lambda: bad_time).context("retrieval")


def test_steps_out_of_order_are_refused():
    rec = TraceRecorder("trace-1", actor="agent")
    with pytest.raises(ValueError, match="register the action"):
        rec.dispatch(at_ms=1)
    with pytest.raises(ValueError, match="register the action"):
        rec.trace()
    rec.register("refund-1", "refund", dict(EXPECTED), contract=contract(), at_ms=5)
    with pytest.raises(ValueError, match="already registered"):
        rec.register("refund-1", "refund", dict(EXPECTED), contract=contract(), at_ms=5)
    with pytest.raises(ValueError, match="contract_id is already used"):
        rec.register("refund-2", "refund", dict(EXPECTED), contract=contract(), at_ms=5)
    with pytest.raises(ValueError, match="undispatched attempt"):
        rec.response("missing", "success", at_ms=6)
    assert rec.trace().assessments == ()  # An agent's report is optional in schema 1.0.
    rec.assessment("unknown", at_ms=7, assessment_id="first")
    with pytest.raises(ValueError, match="already recorded"):
        rec.assessment("success", at_ms=8, assessment_id="first")
    rec.assessment("success", at_ms=8)
    assert [item.status.value for item in rec.trace().assessments] == ["unknown", "success"]


def test_identities_and_references_are_checked():
    rec = TraceRecorder("trace-1", actor="agent")
    rec.context("memory_read", at_ms=0, event_id="memory")
    with pytest.raises(ValueError, match="already recorded"):
        rec.context("retrieval", at_ms=1, event_id="memory")
    with pytest.raises(ValueError, match="context kind"):
        rec.context("agent_decision", at_ms=1)
    with pytest.raises(ValueError):
        rec.context("not-a-kind", at_ms=1)
    with pytest.raises(ValueError, match="unrecorded events"):
        rec.decision(inputs=("missing",), at_ms=2)
    rec.register("refund-1", "refund", dict(EXPECTED), contract=contract(), at_ms=5)
    with pytest.raises(ValueError, match="cannot override"):
        rec.dispatch(at_ms=5, data={"attempt_id": "spoofed"})
    attempt = rec.dispatch(at_ms=5, attempt_id="a1", data={"tool": "issue_refund"})
    with pytest.raises(ValueError, match="already dispatched"):
        rec.dispatch(at_ms=6, attempt_id=attempt)
    with pytest.raises(ValueError):
        rec.response(attempt, "maybe", at_ms=7)
    with pytest.raises(ValueError, match="unrecorded events"):
        rec.assessment("failure", at_ms=8, evidence=("missing",))
    rec.observe(readback())
    rec.observe(readback())
    with pytest.raises(ValueError, match="different observation"):
        rec.observe(readback(watermark=90))
    with pytest.raises(TypeError):
        rec.observe({"observation_id": "readback-1"})


def registered(clock_values=None):
    ticks = iter(clock_values or range(0, 1000, 5))
    rec = TraceRecorder("trace-1", actor="agent", clock=lambda: next(ticks))
    rec.register("refund-1", "refund", dict(EXPECTED), contract=contract())
    return rec


def test_call_records_a_successful_attempt_and_returns_the_result():
    rec = registered()

    def issue_refund(order_id, *, amount):
        return {"refund_id": "rf-1", "order_id": order_id, "amount": amount}

    value = rec.call(issue_refund, "o-17", amount=5000)
    assert value == {"refund_id": "rf-1", "order_id": "o-17", "amount": 5000}
    rec.assessment("success")
    trace = rec.trace()
    (response,) = trace.responses
    assert response.status is ResponseStatus.SUCCESS
    assert response.result == value
    dispatch = next(event for event in trace.events if event.type is EventType.ACTION_DISPATCH)
    assert dispatch.data == {"tool": "issue_refund", "action_id": "refund-1",
                             "attempt_id": "refund-1:attempt-1"}


@pytest.mark.parametrize("error,status", [
    (TimeoutError("gateway timed out"), ResponseStatus.TIMEOUT),
    (ConnectionError("reset"), ResponseStatus.ERROR),
])
def test_exceptions_are_recorded_and_reraised(error, status):
    rec = registered()

    def flaky():
        raise error

    with pytest.raises(type(error)):
        rec.call(flaky)
    rec.assessment("failure")
    (response,) = rec.trace().responses
    assert response.status is status
    # Only the exception type is kept; its message may contain sensitive data.
    assert response.result == {"exception": type(error).__name__}


def test_attempt_allows_explicit_status_identity_payload_and_time():
    rec = registered()
    with rec.attempt(attempt_id="a1", data={"tool": "issue_refund"}, at_ms=100) as attempt:
        attempt.status = "error"
        attempt.result = {"code": "card_declined"}
        attempt.provider_request_id = "req-9"
        attempt.at_ms = 140
    assert attempt.response == ToolResponse(attempt_id="a1", status=ResponseStatus.ERROR, time_ms=140, provider_request_id="req-9",
                                            result={"code": "card_declined"}, action_id="refund-1")
    with pytest.raises(ValueError):
        with rec.attempt(classify=lambda error: "timeout") as second:
            raise ValueError("bad input")
    assert second.response.status is ResponseStatus.TIMEOUT


def test_capture_tool_decorates_synchronous_tools_only():
    rec = registered()

    @capture_tool(rec)
    def lookup(order_id):
        """Find an order."""
        return [order_id, object()]

    assert lookup.__name__ == "lookup" and lookup.__doc__ == "Find an order."
    first = lookup("o-17")
    assert first[0] == "o-17"
    rec.assessment("unknown")
    (response,) = rec.trace().responses
    assert response.result == {"type": "list"}

    async def remote(order_id):
        return order_id

    assert inspect.iscoroutinefunction(capture_tool(rec)(remote))  # wrapped as async
    with pytest.raises(TypeError, match="acall"):
        rec.call(remote, "o-17")
    with pytest.raises(TypeError, match="TraceRecorder"):
        capture_tool(object())


def test_now_reads_the_recorder_clock():
    ticks = iter([7, 8])
    rec = TraceRecorder("trace-1", actor="agent", clock=lambda: next(ticks))
    assert rec.now() == 7
    assert rec.now() == 8
