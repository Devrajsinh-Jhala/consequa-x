"""Offline presentation must preserve evidence while omitting captured secrets."""

from dataclasses import replace
from html.parser import HTMLParser
import json
from unittest.mock import patch

import pytest

from consequa_x.graph import build_graph
from consequa_x.models import (
    Action,
    AgentAssessment,
    AssessmentStatus,
    Evidence,
    Event,
    EventType,
    Observation,
    OriginStatus,
    OutcomeContract,
    ResponseStatus,
    ToolResponse,
    Trace,
    VerificationResult,
    VerificationStatus,
)
from consequa_x.report import render_report


SECRET = "PRIVATE_SENTINEL_7a9f"
HOSTILE = SECRET + '</pre><script>alert("x")</script><img src="https://invalid.test/x" onerror="x">'


def captured_trace():
    """An application-defined target with conflicting successive witnesses."""
    action = Action(
        action_id=SECRET + "_action", trace_id=SECRET + "_trace", actor=SECRET + "_actor",
        name=SECRET + "_name", arguments={SECRET: HOSTILE, "arbitrary_number": 739124896},
        registered_at_ms=0,
        contract=OutcomeContract(SECRET + "_contract", SECRET + "_predicate",
                                 {SECRET: HOSTILE, "currency": SECRET}, 60, stability_ms=10),
        idempotency_key=SECRET + "_idempotency",
    )
    events = (
        Event(SECRET + "_dispatch", action.trace_id, EventType.ACTION_DISPATCH, 10,
              action.actor, data={"action_id": action.action_id, "attempt_id": SECRET + "_attempt",
                                  "payload": HOSTILE}),
        Event(SECRET + "_response", action.trace_id, EventType.TOOL_RESPONSE, 20,
              action.actor, parent_ids=(SECRET + "_dispatch",),
              data={"attempt_id": SECRET + "_attempt", "message": HOSTILE}),
    )
    record = {"effect_id": SECRET + "_effect", "committed_at_ms": 15,
              "action_id": action.action_id, "attempt_id": SECRET + "_attempt",
              "actor": action.actor, "file_path": SECRET + "/secret/file", "payload": HOSTILE}
    observations = (
        Observation(SECRET + "_view1", SECRET + "_source", 80, 70,
                    {SECRET: HOSTILE}, (record,)),
        Observation(SECRET + "_view2", SECRET + "_source", 100, 90,
                    {SECRET: HOSTILE}, (dict(record, actor=SECRET + "_other_actor"),)),
    )
    verifications = tuple(
        VerificationResult(
            action.contract.contract_id, VerificationStatus.SATISFIED, view.observed_at_ms,
            (Evidence(view.observation_id, view.source, view.as_of_ms,
                      {SECRET: HOSTILE, "error": SECRET}),),
            origin=OriginStatus.CONFIRMED if index == 0 else OriginStatus.OTHER_ACTOR,
            effect_ids=(SECRET + "_effect",),
            attributable_effect_ids=(SECRET + "_effect",) if index == 0 else (),
            reason=HOSTILE,
        )
        for index, view in enumerate(observations)
    )
    return Trace(
        action.trace_id, action, events,
        (ToolResponse(SECRET + "_attempt", ResponseStatus.TIMEOUT, 20,
                      SECRET + "_request", {SECRET: HOSTILE}),),
        AgentAssessment(AssessmentStatus.FAILURE, 25, (events[-1].id,), HOSTILE),
        observations, verifications,
    )


class ParsedReport(HTMLParser):
    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attributes = []
        self.scroll_regions = []
        self.text = []
        self.pre_text = []
        self.in_pre = False
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend((tag, key, value) for key, value in attrs)
        attributes = dict(attrs)
        if tag == "div" and attributes.get("class") in {"table-wrap", "graph-scroll"}:
            self.scroll_regions.append(attributes)
        if tag == "pre":
            self.in_pre = True

    def handle_endtag(self, tag):
        if tag == "pre":
            self.in_pre = False

    def handle_data(self, data):
        self.text.append(data)
        if self.in_pre:
            self.pre_text.append(data)


def test_default_file_omits_every_captured_string_even_in_hidden_content():
    trace = captured_trace()
    document = render_report(trace)
    assert SECRET not in document
    assert "739124896" not in document  # Arbitrary payload numbers are not structural fields.
    assert "invalid.test" not in document
    assert "secret/file" not in document
    assert "Captured details included" not in document
    assert "original trace as inert JSON" not in document
    assert "Minimal disclosure mode" in document
    assert "not a universal anonymization guarantee" in document
    assert "Keep the original trace separately as evidence" in document
    assert "Trace schema 0.1" in document


@pytest.mark.parametrize("include_details", [False, True])
def test_report_has_no_scripts_remote_resources_forms_or_captured_attributes(include_details):
    parsed = ParsedReport(render_report(captured_trace(), include_details=include_details))
    assert not set(parsed.tags) & {"script", "iframe", "img", "link", "object", "embed", "form"}
    for _, key, value in parsed.attributes:
        assert not key.startswith("on")
        assert key not in {"src", "srcset", "action", "formaction", "style"}
        assert SECRET not in str(value)
        if key == "href":
            assert value.startswith("#")
    csp = next(value for tag, key, value in parsed.attributes
               if tag == "meta" and key == "content" and "default-src" in value)
    assert "default-src 'none'" in csp
    assert "script-src 'none'" in csp
    assert "connect-src 'none'" in csp


def test_opt_in_details_preserve_every_original_value_as_inert_text():
    trace = captured_trace()
    document = render_report(trace, include_details=True)
    assert SECRET in document
    assert "&lt;/pre&gt;&lt;script&gt;" in document
    assert "<script>" not in document
    parsed = ParsedReport(document)
    assert "pre" in parsed.tags
    recovered = json.loads(''.join(parsed.pre_text))
    assert recovered == trace.to_dict()
    assert "may contain sensitive data" in document
    assert "Collapsing this panel does not remove its contents" in document


def test_successive_witnesses_and_their_provenance_remain_individually_visible():
    trace = captured_trace()
    graph = build_graph(trace)
    document = render_report(trace)
    assert document.count('<td>effect witness</td>') == 2
    assert '<td>Witness 1</td><td>effect witness</td><td>15 ms</td><td>Observation 1</td>' in document
    assert '<td>Witness 2</td><td>effect witness</td><td>15 ms</td><td>Observation 2</td>' in document
    assert '<td>Event 1</td><td>Witness 1</td><td>Provider origin metadata</td>' in document
    assert '<td>Event 1</td><td>Witness 2</td><td>Provider origin metadata</td>' not in document
    assert f'Complete graph: {len(graph.nodes)} nodes' in document
    assert f'Complete graph: {len(graph.edges)} links' in document
    assert document.count('<td>Shared effect identifier</td>') == 2
    assert "other_actor" in document
    assert "unassessable in this report" in document


def test_all_captured_verifications_remain_visible_including_unknown():
    trace = captured_trace()
    first = replace(trace.verifications[0], status=VerificationStatus.UNKNOWN,
                    origin=OriginStatus.UNKNOWN, effect_ids=(), attributable_effect_ids=())
    document = render_report(replace(trace, verifications=(first, trace.verifications[1])))
    assert '<td>Verification 1</td><td>80 ms</td><td><span class="pill status-unknown">unknown' in document
    assert '<td>Verification 2</td><td>100 ms</td><td><span class="pill status-satisfied">satisfied' in document
    assert "origin unknown" in document
    assert "origin other_actor" in document


def test_latest_summary_uses_verification_time_not_tuple_position():
    trace = captured_trace()
    later = replace(trace.verifications[1], status=VerificationStatus.UNKNOWN,
                    origin=OriginStatus.UNKNOWN, effect_ids=(), attributable_effect_ids=())
    trace = replace(trace, verifications=(later, trace.verifications[0]))
    document = render_report(trace)
    assert 'Latest verified state</h3><div class="value"><span class="pill status-unknown">' in document
    assert 'Latest effect origin</h3><div class="value"><span class="pill status-unknown">' in document
    assert '<td>Verification 1</td><td>100 ms</td>' in document
    assert '<td>Verification 2</td><td>80 ms</td>' in document


def test_equal_time_latest_summary_uses_last_capture_without_reordering_records():
    trace = captured_trace()
    first = replace(trace.verifications[0], observed_at_ms=100)
    trace = replace(trace, verifications=(trace.verifications[1], first))
    document = render_report(trace)
    assert 'Latest effect origin</h3><div class="value"><span class="pill status-confirmed">' in document
    assert '<td>Verification 1</td><td>100 ms</td>' in document
    assert '<td>Verification 2</td><td>100 ms</td>' in document


@pytest.mark.parametrize("event_type", list(EventType))
def test_every_public_event_type_is_supported_by_generic_report(event_type):
    trace = captured_trace()
    event = replace(trace.events[0], type=event_type, data={SECRET: HOSTILE})
    trace = replace(trace, events=(event,),
                    assessment=replace(trace.assessment, evidence_event_ids=(event.id,)))
    document = render_report(trace)
    assert event_type.value.replace("_", " ") in document
    assert SECRET not in document


def test_valid_empty_generic_trace_and_unconstrained_contract():
    trace = captured_trace()
    trace = replace(trace, action=replace(trace.action,
                    contract=replace(trace.action.contract, exact_count=None)),
                    events=(), responses=(), observations=(), verifications=(),
                    assessment=replace(trace.assessment, evidence_event_ids=()))
    document = render_report(trace)
    assert document.count("not recorded") == 2
    assert "not constrained" in document
    assert "None recorded" in document
    assert "Action 1 registered" in document
    assert "No intervention estimates were supplied" in document
    assert SECRET not in document


def test_renderer_does_not_mutate_trace_or_execute_verifiers_or_replay():
    trace = captured_trace()
    before = trace.to_json()
    with patch("consequa_x.verification.verify", side_effect=AssertionError("verifier called")), \
         patch("consequa_x.explanation.explain", side_effect=AssertionError("matcher called")), \
         patch("socket.socket", side_effect=AssertionError("network called")):
        structural = render_report(trace)
        detailed = render_report(trace, include_details=True)
    assert trace.to_json() == before
    assert structural != detailed
    assert render_report(trace) == structural


@pytest.mark.parametrize("value", [None, {}, "{}", 12, False])
def test_report_requires_typed_trace(value):
    with pytest.raises(TypeError, match="requires a Trace"):
        render_report(value)


@pytest.mark.parametrize("value", [None, "yes", 1, [], {}])
def test_details_opt_in_requires_actual_boolean(value):
    with pytest.raises(TypeError, match="include_details must be a boolean"):
        render_report(captured_trace(), include_details=value)


def test_mutated_nested_payload_is_revalidated_without_exposing_its_error():
    trace = captured_trace()
    with pytest.raises(TypeError, match="read-only"):
        trace.action.arguments[SECRET] = float("nan")
    dict.__setitem__(trace.action.arguments, SECRET, float("nan"))  # Deliberate bypass.
    with pytest.raises(ValueError) as error:
        render_report(trace)
    assert str(error.value) == "Cannot render an invalid trace"
    assert SECRET not in str(error.value)


def test_forged_enum_value_cannot_inject_a_status_class_or_text():
    trace = captured_trace()
    object.__setattr__(trace.assessment, "status", HOSTILE)
    with pytest.raises(ValueError, match="Cannot render an invalid trace") as error:
        render_report(trace)
    assert SECRET not in str(error.value)


def test_graph_identity_refusal_does_not_echo_captured_secret():
    trace = captured_trace()
    collision = replace(trace.events[0], id=f"contract:{trace.action.contract.contract_id}")
    trace = replace(trace, events=(*trace.events, collision))
    with pytest.raises(ValueError, match="conflicting evidence graph identities") as error:
        render_report(trace)
    assert SECRET not in str(error.value)


def test_large_graph_overview_is_bounded_but_full_evidence_tables_remain():
    trace = captured_trace()
    events = tuple(Event(f"{SECRET}_{index}", trace.trace_id, EventType.AGENT_DECISION,
                         index, data={SECRET: HOSTILE}) for index in range(50))
    trace = replace(trace, events=events, assessment=replace(trace.assessment, evidence_event_ids=()))
    graph = build_graph(trace)
    document = render_report(trace)
    assert document.count('<rect class="node') == 32
    assert '<td>Event 50</td>' in document
    assert f'Complete graph: {len(graph.nodes)} nodes' in document
    assert f'Complete graph: {len(graph.edges)} links' in document
    assert SECRET not in document


def test_accessible_text_tables_keyboard_navigation_print_and_wrapping():
    document = render_report(captured_trace(), include_details=True)
    parsed = ParsedReport(document)
    assert 'lang="en"' in document
    assert 'aria-label="Report sections"' in document
    assert 'role="img"' in document
    assert 'aria-labelledby="graph-title graph-description"' in document
    assert "caption" in parsed.tags
    assert "summary" in parsed.tags
    assert 'scope="col"' in document
    assert ":focus-visible" in document
    assert ".table-wrap:focus-visible" in document
    assert ".graph-scroll:focus-visible" in document
    assert len(parsed.scroll_regions) == 6
    assert {region["aria-label"] for region in parsed.scroll_regions} == {
        "Every captured tool response",
        "Every captured observation",
        "Every captured verification; earlier unknown results are retained",
        "Captured evidence graph overview",
        f"Complete graph: {len(build_graph(captured_trace()).nodes)} nodes",
        f"Complete graph: {len(build_graph(captured_trace()).edges)} links",
    }
    assert all(region["role"] == "region" and region["tabindex"] == "0"
               for region in parsed.scroll_regions)
    assert "@media print" in document
    assert "nav,.graph-scroll,.overview-description{display:none}" in document
    assert ".print-only{display:none}" in document
    assert ".print-only{display:block}" in document
    assert '<p class="print-only">Visual overview omitted in print; complete node and relationship tables follow.</p>' in document
    assert "overflow-wrap:anywhere" in document
    assert "does not establish causation" in document
    assert "not a proof of source authenticity or causal necessity" in document


def test_very_long_hostile_details_are_retained_and_escaped_without_attributes():
    trace = captured_trace()
    long_payload = HOSTILE * 500
    trace = replace(trace, action=replace(trace.action, arguments={"payload": long_payload}))
    structural = render_report(trace)
    detailed = render_report(trace, include_details=True)
    assert SECRET not in structural
    parsed = ParsedReport(detailed)
    assert json.loads(''.join(parsed.pre_text))["action"]["arguments"]["payload"] == long_payload
    assert "script" not in parsed.tags
