"""TraceRecorder arranges application-supplied records into an ordinary trace."""

import pytest

from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Event, EventType, Observation, OutcomeContract,
    ResponseStatus, ToolResponse, Trace, TraceRecorder, VerificationStatus, build_graph, explain,
)


EXPECTED = {"payment_id": "p1", "amount_minor": 1000, "currency": "INR"}


def contract():
    return OutcomeContract("contract-1", "refund_processed", dict(EXPECTED),
                           deadline_ms=50, stability_ms=20)


def readback(observation_id="readback-1", *, observed=100, watermark=100, attempt="refund-1:attempt-1"):
    return Observation(observation_id, "independent-ledger", observed, watermark,
                       {"payment_id": "p1"},
                       ({**EXPECTED, "effect_id": "effect-1", "committed_at_ms": 25,
                         "status": "processed", "action_id": "refund-1", "attempt_id": attempt,
                         "actor": "agent"},))


def recorded(**kwargs):
    rec = TraceRecorder("trace-1", actor="agent", **kwargs)
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
    response = ToolResponse("refund-1:attempt-1", ResponseStatus.TIMEOUT, 20, "refund-1:attempt-1")
    assessment = AgentAssessment(AssessmentStatus.FAILURE, 25, ("response-1",), "The tool timed out.")
    events = (
        Event("context-1", "trace-1", EventType.USER_INPUT, 0, None, (), {"text": "refund please"}),
        Event("decision-1", "trace-1", EventType.AGENT_DECISION, 2, "agent", ("context-1",),
              {"selected": True}),
        Event("intent-1", "trace-1", EventType.ACTION_INTENT, 5, "agent", ("decision-1",),
              {"action_id": "refund-1", "arguments": dict(EXPECTED)}),
        Event("dispatch-1", "trace-1", EventType.ACTION_DISPATCH, 5, "agent", ("intent-1",),
              {"action_id": "refund-1", "attempt_id": "refund-1:attempt-1"}),
        Event("response-1", "trace-1", EventType.TOOL_RESPONSE, 20, None, ("dispatch-1",),
              response.to_dict()),
        Event("assessment-1", "trace-1", EventType.AGENT_ASSESSMENT, 25, "agent", ("response-1",),
              assessment.to_dict()),
    )
    action = Action("refund-1", "trace-1", "agent", "refund", dict(EXPECTED), 5, contract())
    expected = Trace("trace-1", action, events, (response,), assessment, (readback(),), (receipt,))
    trace = rec.trace()
    assert trace == expected
    assert Trace.from_json(trace.to_json()) == trace


def test_recorded_trace_explains_and_links_the_effect_to_its_dispatch():
    rec = recorded()
    receipt = rec.verify(readback())
    trace = rec.trace()
    explanation = explain(trace)
    assert receipt.status is VerificationStatus.SATISFIED
    assert explanation.assessment_alignment == "contradicted"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in explanation.diagnoses
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
    assert trace.action.registered_at_ms == 0

    default = TraceRecorder("trace-2", actor="agent")
    default.register("refund-1", "refund", dict(EXPECTED), contract=contract())
    assert type(default.action.registered_at_ms) is int and default.action.registered_at_ms >= 0


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
    with pytest.raises(ValueError, match="exactly one registered action"):
        rec.register("refund-2", "refund", dict(EXPECTED), contract=contract(), at_ms=5)
    with pytest.raises(ValueError, match="undispatched attempt"):
        rec.response("missing", "success", at_ms=6)
    with pytest.raises(ValueError, match="assessment first"):
        rec.trace()
    rec.assessment("unknown", at_ms=7)
    with pytest.raises(ValueError, match="already recorded"):
        rec.assessment("success", at_ms=8)


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
