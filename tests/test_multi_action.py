"""Schema 1.0: several actions, assessments and verifications in one trace."""

from dataclasses import replace
import json

import pytest

from consequa_x import (
    ActionCapture, AssessmentStatus, Observation, OutcomeContract, RecorderError,
    RecordVerifier, SchemaVersionError, TimeBase, Trace, TraceRecorder, ValidationError,
    build_graph, capture_tool, explain, render_report,
)


VERIFIER = RecordVerifier(scope_fields=("order_id",))


def contract(contract_id, order_id):
    return OutcomeContract(contract_id=contract_id, predicate="record_present",
                           expected={"order_id": order_id}, deadline_ms=50, stability_ms=10)


def readback(observation_id, order_id, *records, watermark=100):
    return Observation(observation_id=observation_id, source="orders-replica", observed_at_ms=100,
                       as_of_ms=watermark, scope={"order_id": order_id}, records=tuple(records))


def two_action_run():
    """A refund that times out after committing, and an email that is never sent."""
    now = [0]
    rec = TraceRecorder("run-1", actor="support-agent", clock=lambda: now[0])
    message = rec.context("user_input", {"text": "refund o-1 and email me"})
    now[0] = 1
    decision = rec.decision({"plan": ["refund", "email"]}, inputs=(message,))
    now[0] = 2
    refund = rec.register("refund-1", "issue_refund", {"order_id": "o-1"},
                          contract=contract("refund-contract", "o-1"), decision=decision)
    email = rec.register("email-1", "send_email", {"order_id": "o-1-mail"},
                         contract=contract("email-contract", "o-1-mail"), decision=decision)
    now[0] = 5
    try:
        with refund.attempt() as attempt:
            refund_row = {"effect_id": "rf-1", "order_id": "o-1", "committed_at_ms": 10,
                          "action_id": "refund-1", "actor": "support-agent",
                          "attempt_id": attempt.attempt_id}
            now[0] = 20
            raise TimeoutError
    except TimeoutError:
        pass
    send = capture_tool(email)(lambda order_id: {"queued": True})
    now[0] = 21
    send("o-1-mail")
    now[0] = 25
    refund.assessment("unknown", rationale="Waiting for the payment provider.")
    now[0] = 30
    refund.assessment("failure", rationale="The refund timed out.")
    email.assessment("success")
    refund.verify(readback("refund-read", "o-1", refund_row), verifier=VERIFIER)
    email.verify(readback("email-read", "o-1-mail"), verifier=VERIFIER)
    return rec


def test_one_trace_holds_several_actions_with_separate_evidence():
    rec = two_action_run()
    trace = rec.trace()
    assert [action.action_id for action in trace.actions] == ["refund-1", "email-1"]
    assert trace.time_base is TimeBase.RELATIVE_MS
    assert [item.status.value for item in trace.responses_for("refund-1")] == ["timeout"]
    assert [item.status.value for item in trace.responses_for("email-1")] == ["success"]
    assert [item.status.value for item in trace.assessments_for("refund-1")] == ["unknown", "failure"]
    assert trace.latest_assessment("refund-1").status is AssessmentStatus.FAILURE
    assert trace.latest_verification("email-1").status.value == "violated"
    assert Trace.from_json(trace.to_json()) == trace
    with pytest.raises(ValidationError, match="2 actions"):
        trace.single_action
    with pytest.raises(ValidationError, match="no action"):
        trace.get_action("missing")


def test_explain_judges_each_action_from_its_own_latest_records():
    trace = two_action_run().trace()
    explanation = explain(trace, target_matcher=VERIFIER.target_matcher())
    refund = explanation.for_action("refund-1")
    email = explanation.for_action("email-1")
    assert (refund.consequence.status.value, refund.consequence.origin.value) == (
        "satisfied", "confirmed")
    assert refund.agent_assessment.status is AssessmentStatus.FAILURE  # the latest report
    assert refund.assessment_alignment == "contradicted"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in refund.diagnoses
    assert email.consequence.status.value == "violated"
    assert email.assessment_alignment == "contradicted"
    assert "RESPONSE_EFFECT_DIVERGENCE" in email.diagnoses
    with pytest.raises(ValidationError, match="2 actions"):
        explanation.single_action
    assert json.loads(json.dumps(explanation.to_dict()))["actions"][1]["action_id"] == "email-1"


def test_an_action_without_verification_is_reported_not_treated_as_success():
    rec = TraceRecorder("run-2", actor="agent", time_base="relative_ms")
    rec.register("refund-1", "issue_refund", {"order_id": "o-1"}, contract=contract("c", "o-1"),
                 at_ms=0)
    rec.assessment("success", at_ms=1)
    action = explain(rec.trace()).single_action
    assert action.consequence is None
    assert action.diagnoses == ("NO_VERIFICATION", "UNVERIFIED_ASSESSMENT")
    assert action.assessment_alignment == "unassessable"
    assert "no independent verification" in action.summary


def test_graph_and_report_cover_every_action():
    trace = two_action_run().trace()
    graph = build_graph(trace)
    contracts = sorted(node.id for node in graph.nodes if node.kind == "postcondition")
    assert contracts == ["contract:email-contract", "contract:refund-contract"]
    effect_links = [edge for edge in graph.edges if edge.kind == "EFFECT"]
    assert len(effect_links) == 1
    document = render_report(trace)
    assert "2 captured actions." in document
    assert "<h3>Action 1</h3>" in document and "<h3>Action 2</h3>" in document
    assert "Registered outcome contracts" in document
    assert "<td>Response 2</td><td>Action 2</td>" in document
    assert "refund-1" not in document and "o-1" not in document


def test_recorder_calls_need_a_handle_once_several_actions_exist():
    rec = TraceRecorder("run-3", actor="agent", time_base="relative_ms")
    first = rec.register("a1", "tool", {}, contract=contract("c1", "x"), at_ms=0)
    assert isinstance(first, ActionCapture) and first.action_id == "a1"
    attempt = rec.dispatch(at_ms=1)  # still unambiguous
    second = rec.register("a2", "tool", {}, contract=contract("c2", "y"), at_ms=2)
    for call in (lambda: rec.dispatch(at_ms=3), lambda: rec.assessment("unknown", at_ms=3),
                 lambda: rec.call(lambda: None)):
        with pytest.raises(RecorderError, match="several actions"):
            call()
    with pytest.raises(RecorderError, match="belongs to another action"):
        second.response(attempt, "success", at_ms=4)
    rec.response(attempt, "success", at_ms=4)  # the recorder finds the owning action
    assert rec.trace().responses[0].action_id == "a1"
    assert rec.capture_for("a2") is second
    with pytest.raises(RecorderError, match="no registered action"):
        rec.capture_for("a3")
    with pytest.raises(RecorderError, match="unrecorded event"):
        rec.register("a3", "tool", {}, contract=contract("c3", "z"), decision="missing")


def test_trace_validation_checks_every_cross_action_reference():
    trace = two_action_run().trace()
    response = trace.responses[0]
    with pytest.raises(ValidationError, match="at least one action"):
        replace(trace, actions=(), responses=(), assessments=(), verifications=(), events=())
    with pytest.raises(ValidationError, match="response.action_id"):
        replace(trace, responses=(replace(response, action_id="ghost"),))
    with pytest.raises(ValidationError, match="its action's contract"):
        replace(trace, verifications=(replace(trace.verifications[0], action_id="email-1"),))
    with pytest.raises(ValidationError, match="own contract_id"):
        replace(trace, actions=(trace.actions[0], replace(
            trace.actions[1], contract=replace(trace.actions[1].contract,
                                               contract_id="refund-contract"))))
    with pytest.raises(ValidationError, match="unique assessment_id"):
        replace(trace, assessments=trace.assessments + trace.assessments[:1])


def test_schema_0_1_traces_are_refused_with_the_migration_route():
    with pytest.raises(SchemaVersionError, match="consequa-x migrate"):
        Trace.from_json(json.dumps({"schema_version": "0.1", "trace_id": "old"}))
