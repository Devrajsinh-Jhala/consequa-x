"""OpenTelemetry export and import, with and without the opentelemetry packages."""

import json

import pytest

from consequa_x import (
    OutcomeContract, Trace, TraceRecorder, ValidationError, explain, migrate_trace,
)
from consequa_x.otel import (
    SCOPE_NAME, ToolSpan, emit, from_otlp, record_tool_spans, to_otlp, trace_spans,
)
from test_multi_action import two_action_run
from test_compare_verify_redact import FIXTURES


def attributes(span):
    return {item["key"]: item["value"] for item in span["attributes"]}


def spans_of(document):
    return document["resourceSpans"][0]["scopeSpans"][0]["spans"]


def unix_trace():
    rec = TraceRecorder("run-otel", actor="support-agent", clock=lambda: 1_760_000_000_000,
                        time_base="unix_ms")
    rec.context("user_input", {"text": "refund o-17"})
    rec.decision({"tool": "issue_refund"})
    capture = rec.register("refund-1", "issue_refund", {"order_id": "o-17"}, contract=OutcomeContract(
        contract_id="c-1", predicate="record_present", expected={"order_id": "o-17"},
        deadline_ms=1_760_000_000_200))
    attempt = capture.dispatch(at_ms=1_760_000_000_010)
    capture.response(attempt, "timeout", at_ms=1_760_000_000_110,
                     result={"exception": "TimeoutError"})
    capture.assessment("failure", rationale="the call timed out", at_ms=1_760_000_000_120)
    return rec.trace()


def test_export_follows_the_genai_tool_span_shape_without_payloads():
    trace = unix_trace()
    document = to_otlp(trace, service_name="refund-service")
    resource = document["resourceSpans"][0]
    assert attributes(resource["resource"])["service.name"] == {"stringValue": "refund-service"}
    assert resource["scopeSpans"][0]["scope"]["name"] == SCOPE_NAME
    spans = spans_of(document)
    names = [span["name"] for span in spans]
    assert names == ["consequa_x trace run-otel", "consequa_x action issue_refund",
                     "execute_tool issue_refund"]
    root, action, tool = spans
    assert len(root["traceId"]) == 32 and len(tool["spanId"]) == 16
    assert {span["traceId"] for span in spans} == {root["traceId"]}
    assert action["parentSpanId"] == root["spanId"] and tool["parentSpanId"] == action["spanId"]
    assert all(span["kind"] == 1 for span in spans)
    tool_attributes = attributes(tool)
    assert tool_attributes["gen_ai.operation.name"] == {"stringValue": "execute_tool"}
    assert tool_attributes["gen_ai.tool.name"] == {"stringValue": "issue_refund"}
    assert tool_attributes["error.type"] == {"stringValue": "timeout"}
    assert "gen_ai.tool.call.id" not in tool_attributes  # only providers supply call IDs
    assert tool["status"]["code"] == 2
    assert tool["startTimeUnixNano"] == str(1_760_000_000_010 * 1_000_000)
    assert tool["endTimeUnixNano"] == str(1_760_000_000_110 * 1_000_000)
    action_attributes = attributes(action)
    assert action_attributes["consequa_x.verification.status"] == {"stringValue": "not_recorded"}
    assert action_attributes["consequa_x.diagnoses"] == {"arrayValue": {"values": [
        {"stringValue": "NO_VERIFICATION"}, {"stringValue": "UNVERIFIED_ASSESSMENT"}]}}
    assert [event["name"] for event in action["events"]] == ["consequa_x.assessment"]
    assert [event["name"] for event in root["events"]] == ["consequa_x.event"] * 2
    text = json.dumps(document)
    for secret in ("o-17", "the call timed out", "refund o-17", "consequa_x.trace\""):
        assert secret not in text
    assert to_otlp(trace, service_name="refund-service") == document  # deterministic


def test_payload_exports_round_trip_exactly():
    trace = unix_trace()
    document = to_otlp(trace, include_payloads=True)
    tool = spans_of(document)[2]
    assert attributes(tool)["gen_ai.tool.call.arguments"] == {"kvlistValue": {"values": [
        {"key": "order_id", "value": {"stringValue": "o-17"}}]}}
    assert from_otlp(document) == (trace,)
    assert from_otlp(json.dumps(document)) == (trace,)
    with pytest.raises(ValidationError, match="include_payloads=True"):
        from_otlp(to_otlp(trace))


def test_verified_multi_action_trace_exports_receipts_and_readback():
    trace = two_action_run().trace()
    with pytest.raises(ValidationError, match="origin_unix_ms"):
        to_otlp(trace)
    spans = trace_spans(trace, origin_unix_ms=1_700_000_000_000)
    verifications = [span for span in spans if span.name.startswith("consequa_x verify")]
    assert len(verifications) == len(trace.verifications)
    first = verifications[0]
    assert first.attributes["consequa_x.verification.status"] in {"satisfied", "violated",
                                                                  "unknown"}
    assert first.events[0][0] == "consequa_x.readback"
    assert first.start_ns >= 1_700_000_000_000 * 1_000_000
    judged = explain(trace)
    for action in trace.actions:
        span = next(item for item in spans
                    if item.attributes.get("consequa_x.action_id") == action.action_id
                    and item.name.startswith("consequa_x action"))
        assert span.attributes["consequa_x.diagnoses"] == list(
            judged.for_action(action.action_id).codes)
    document = to_otlp(trace, include_payloads=True, origin_unix_ms=1_700_000_000_000)
    assert from_otlp(document) == (trace,)


def test_migrated_fixture_exports():
    trace = migrate_trace((FIXTURES / "refund-timeout-after-commit.json").read_text(
        encoding="utf-8"))
    document = to_otlp(trace, origin_unix_ms=0)
    statuses = [attributes(span).get("consequa_x.verification.status")
                for span in spans_of(document)]
    assert {"stringValue": "satisfied"} in statuses


def genai_document(*tools, trace_id="ab" * 16):
    spans = []
    for index, (name, arguments, error_type, call_id) in enumerate(tools):
        values = [{"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
                  {"key": "gen_ai.tool.name", "value": {"stringValue": name}},
                  {"key": "gen_ai.agent.name", "value": {"stringValue": "Billing Agent"}},
                  {"key": "gen_ai.tool.call.arguments",
                   "value": {"stringValue": json.dumps(arguments)}}]
        if call_id:
            values.append({"key": "gen_ai.tool.call.id", "value": {"stringValue": call_id}})
        if error_type:
            values.append({"key": "error.type", "value": {"stringValue": error_type}})
        start = 1_760_000_000_000 + index * 1000
        spans.append({"traceId": trace_id, "spanId": f"{index + 1:016x}",
                      "name": f"execute_tool {name}", "kind": 1,
                      "startTimeUnixNano": str(start * 1_000_000),
                      "endTimeUnixNano": str((start + 300) * 1_000_000),
                      "attributes": values,
                      "status": {"code": 2} if error_type else {"code": 0}})
    spans.append({"traceId": trace_id, "spanId": "f" * 16, "name": "chat gpt",
                  "startTimeUnixNano": "1", "endTimeUnixNano": "2",
                  "attributes": [{"key": "gen_ai.operation.name",
                                  "value": {"stringValue": "chat"}}]})
    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def test_genai_tool_spans_become_actions_for_consequential_tools():
    document = genai_document(
        ("lookup_order", {"order_id": "o-17"}, None, "call_1"),
        ("issue_refund", {"order_id": "o-17"}, "TimeoutError", "call_2"),
        ("issue_refund", {"order_id": "o-18"}, "PermissionError", None))
    offered = []

    def contract_for(span: ToolSpan):
        offered.append(span)
        if span.tool_name != "issue_refund":
            return None
        return OutcomeContract(contract_id=f"contract-{span.span_id}", predicate="record_present",
                               expected=span.arguments, deadline_ms=span.started_at_ms + 5000)

    rec = TraceRecorder("imported", actor="importer")
    captures = record_tool_spans(document, rec, contract_for=contract_for)
    assert [span.tool_name for span in offered] == ["lookup_order", "issue_refund",
                                                    "issue_refund"]
    assert offered[1].arguments == {"order_id": "o-17"} and offered[1].call_id == "call_2"
    assert [capture.action_id for capture in captures] == [
        "call_2", "span-0000000000000003"]
    trace = rec.trace()
    assert [item.status.value for item in trace.responses] == ["timeout", "error"]
    assert trace.responses[0].provider_request_id == "call_2"
    assert trace.actions[0].actor == "Billing Agent"
    assert trace.actions[0].registered_at_ms == 1_760_000_001_000
    assert trace.responses[0].time_ms == 1_760_000_001_300
    assert explain(trace).for_action("call_2").codes == ("NO_VERIFICATION",)
    with pytest.raises(ValidationError, match="unix_ms"):
        record_tool_spans(document, TraceRecorder("x", actor="a", clock=lambda: 1),
                          contract_for=contract_for)
    two = genai_document(("issue_refund", {}, None, "a"))
    two["resourceSpans"] += genai_document(("issue_refund", {}, None, "b"),
                                           trace_id="cd" * 16)["resourceSpans"]
    with pytest.raises(ValidationError, match="otel_trace_id"):
        record_tool_spans(two, TraceRecorder("y", actor="a"), contract_for=contract_for)
    chosen = record_tool_spans(two, TraceRecorder("z", actor="a"), contract_for=contract_for,
                               otel_trace_id="CD" * 16)
    assert [capture.action_id for capture in chosen] == ["b"]


def test_malformed_otlp_is_refused():
    for bad in ({}, {"resourceSpans": [{"scopeSpans": [{"spans": [{"traceId": "x"}]}]}]}, "{"):
        with pytest.raises(ValidationError):
            from_otlp(bad)


def test_otel_cli_round_trip(tmp_path, capsys):
    from consequa_x import cli

    trace = unix_trace()
    source = tmp_path / "trace.json"
    source.write_text(trace.to_json(), encoding="utf-8")
    exported = tmp_path / "spans.json"
    assert cli.main(["otel-export", str(source), "--output", str(exported),
                     "--include-payloads"]) == 0
    assert "3 spans" in capsys.readouterr().out
    restored = tmp_path / "restored"
    assert cli.main(["otel-import", str(exported), "--output-dir", str(restored)]) == 0
    files = sorted(restored.glob("*.json"))
    assert [Trace.from_json(path.read_text(encoding="utf-8")) for path in files] == [trace]
    assert cli.main(["otel-export", str(source), "--output", str(exported)]) == 2
    assert "new file" in capsys.readouterr().err


def test_emit_through_the_opentelemetry_sdk():
    sdk = pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = sdk.TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace = unix_trace()
    emit(trace, provider.get_tracer("test"), include_payloads=True)
    finished = exporter.get_finished_spans()
    assert sorted(span.name for span in finished) == sorted(
        item.name for item in trace_spans(trace))
    tool = next(span for span in finished if span.name.startswith("execute_tool"))
    assert tool.attributes["error.type"] == "timeout"
    assert json.loads(tool.attributes["gen_ai.tool.call.arguments"]) == {"order_id": "o-17"}
    assert tool.start_time == 1_760_000_000_010 * 1_000_000
    root = next(span for span in finished if span.parent is None)
    assert all(span.context.trace_id == root.context.trace_id for span in finished)
    assert from_otlp(finished) == (trace,)
    rec = TraceRecorder("from-sdk", actor="importer")
    captures = record_tool_spans(finished, rec, contract_for=lambda span: OutcomeContract(
        contract_id="c", predicate="record_present", expected=span.arguments,
        deadline_ms=span.started_at_ms + 1000))
    assert [item.status.value for item in rec.trace().responses] == ["timeout"]
    assert captures[0].action.arguments == {"order_id": "o-17"}
