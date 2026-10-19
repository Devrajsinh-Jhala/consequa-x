"""Export traces to OpenTelemetry and bring tool spans back in.

ConseqaX traces can travel through an OpenTelemetry pipeline next to the
rest of an agent's telemetry. Each tool attempt becomes an ``execute_tool``
span named as the OpenTelemetry GenAI semantic conventions describe (those
conventions are still in *development* status upstream); ConseqaX's own
findings use ``consequa_x.*`` attributes.

- :func:`to_otlp` returns an OTLP/JSON document (``resourceSpans``), the body
  an OTLP/HTTP collector accepts at ``/v1/traces``. It needs no dependency.
- :func:`emit` creates the same spans through the ``opentelemetry-api``
  package (``pip install "consequa-x[otel]"``), so the application's configured
  exporter sends them.
- :func:`from_otlp` restores traces exported with ``include_payloads=True``
  exactly; such exports carry the complete trace on their root span.
- :func:`record_tool_spans` reads ``execute_tool`` spans written by any GenAI
  instrumentation into a :class:`~consequa_x.capture.TraceRecorder`: one
  action per tool span that the application gives an outcome contract.

Payloads are opt-in, as in the GenAI conventions: by default an export holds
identifiers, times, statuses, counts and diagnosis codes, but no tool
arguments, results, readback records or rationale. Tool spans say what a tool
returned; they never establish an outcome. That still needs readback.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Callable, Iterable

from . import __version__
from .capture import ActionCapture, TraceRecorder
from .errors import ConsequaTypeError, ValidationError
from .explanation import explain
from .models import (
    EventType,
    OutcomeContract,
    ResponseStatus,
    TimeBase,
    Trace,
    _json_copy,
    thaw,
)


SCOPE_NAME = "consequa-x"
TRACE_ATTRIBUTE = "consequa_x.trace"
_INTERNAL, _UNSET, _ERROR = 1, 0, 2


@dataclass(frozen=True)
class SpanRecord:
    """One span in the plain form this module writes and reads.

    Times are Unix nanoseconds; identifiers are lowercase hexadecimal.
    ``attributes`` and event attributes hold plain JSON values.
    """

    trace_id: str
    span_id: str
    name: str
    start_ns: int
    end_ns: int
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: tuple[tuple[str, int, dict[str, Any]], ...] = ()
    error: bool = False
    status_message: str = ""


@dataclass(frozen=True)
class ToolSpan:
    """An ``execute_tool`` span offered to ``contract_for`` by ``record_tool_spans``."""

    tool_name: str
    arguments: dict[str, Any]
    started_at_ms: int
    ended_at_ms: int
    call_id: str | None
    agent_name: str | None
    span_id: str
    trace_id: str
    attributes: dict[str, Any]


# Building spans from a trace -----------------------------------------------------------


def _hex(*parts: str, length: int) -> str:
    value = sha256("\x1f".join(("consequa-x", *parts)).encode("utf-8")).hexdigest()[:length]
    return value if value.strip("0") else "1".rjust(length, "0")


def _clock(trace: Trace, origin_unix_ms: int | None) -> Callable[[int], int]:
    if origin_unix_ms is not None and (type(origin_unix_ms) is not int or origin_unix_ms < 0):
        raise ValidationError("origin_unix_ms must be a nonnegative integer")
    if trace.time_base is TimeBase.UNIX_MS:
        if origin_unix_ms is not None:
            raise ValidationError("origin_unix_ms applies only to relative_ms traces")
        return lambda ms: ms * 1_000_000
    if origin_unix_ms is None:
        raise ValidationError("A relative_ms trace has no wall-clock origin; pass "
                              "origin_unix_ms to place it in time")
    return lambda ms: (origin_unix_ms + ms) * 1_000_000


def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def trace_spans(trace: Trace, *, include_payloads: bool = False,
                origin_unix_ms: int | None = None) -> tuple[SpanRecord, ...]:
    """The spans an export of ``trace`` contains, in parent-before-child order.

    One root span for the trace, one span per action, an ``execute_tool``
    span per attempt and a verification span per receipt. Assessments,
    readback observations and context events are span events.
    """
    if not isinstance(trace, Trace):
        raise ConsequaTypeError("trace_spans requires a Trace")
    if type(include_payloads) is not bool:
        raise ConsequaTypeError("include_payloads must be a boolean")
    to_ns = _clock(trace, origin_unix_ms)
    explanation = explain(trace)
    otel_trace = _hex("trace", trace.trace_id, length=32)
    root_id = _hex("span", trace.trace_id, "root", length=16)
    times = [action.registered_at_ms for action in trace.actions]
    times += [event.time_ms for event in trace.events]
    times += [item.time_ms for item in trace.responses]
    times += [item.time_ms for item in trace.assessments]
    times += [item.observed_at_ms for item in trace.observations]
    times += [item.observed_at_ms for item in trace.verifications]
    root_attributes: dict[str, Any] = {
        "consequa_x.trace_id": trace.trace_id,
        "consequa_x.schema_version": trace.schema_version,
        "consequa_x.time_base": trace.time_base.value,
        "consequa_x.action_count": len(trace.actions),
    }
    if include_payloads:
        root_attributes[TRACE_ATTRIBUTE] = trace.to_json()
    root_events = tuple(
        ("consequa_x.event", to_ns(event.time_ms), {
            "consequa_x.event_id": event.id, "consequa_x.event_type": event.type.value,
            **({"consequa_x.actor": event.actor} if event.actor else {}),
            **({"consequa_x.data": _compact(thaw(event.data))} if include_payloads else {}),
        })
        for event in trace.events
        if event.type in (EventType.USER_INPUT, EventType.SYSTEM_INSTRUCTION,
                          EventType.RETRIEVAL, EventType.MEMORY_READ, EventType.AGENT_DECISION)
    )
    spans = [SpanRecord(otel_trace, root_id, f"consequa_x trace {trace.trace_id}",
                        to_ns(min(times)), to_ns(max(times)), None, root_attributes, root_events)]
    dispatches = {event.data.get("attempt_id"): event for event in trace.events
                  if event.type is EventType.ACTION_DISPATCH}
    observations = {item.observation_id: item for item in trace.observations}
    for action in trace.actions:
        judged = explanation.for_action(action.action_id)
        span_id = _hex("span", trace.trace_id, "action", action.action_id, length=16)
        latest = judged.consequence
        responses = trace.responses_for(action.action_id)
        assessments = trace.assessments_for(action.action_id)
        verifications = trace.verifications_for(action.action_id)
        own = [action.registered_at_ms, *(item.time_ms for item in responses),
               *(item.time_ms for item in assessments),
               *(item.observed_at_ms for item in verifications)]
        contract = action.contract
        attributes: dict[str, Any] = {
            "consequa_x.action_id": action.action_id,
            "consequa_x.actor": action.actor,
            "gen_ai.tool.name": action.name,
            "consequa_x.contract.id": contract.contract_id,
            "consequa_x.contract.predicate": contract.predicate,
            "consequa_x.contract.deadline_ms": contract.deadline_ms,
            "consequa_x.contract.horizon_ms": contract.horizon_ms,
            "consequa_x.verification.status": latest.status.value if latest else "not_recorded",
            "consequa_x.verification.origin": latest.origin.value if latest else "not_recorded",
            "consequa_x.assessment.status": (judged.agent_assessment.status.value
                                             if judged.agent_assessment else "not_recorded"),
            "consequa_x.assessment.alignment": judged.assessment_alignment,
            "consequa_x.diagnoses": list(judged.codes),
        }
        if action.idempotency_key is not None:
            attributes["consequa_x.idempotency_key"] = action.idempotency_key
        if include_payloads:
            attributes["consequa_x.contract.expected"] = thaw(contract.expected)
            attributes["gen_ai.tool.call.arguments"] = thaw(action.arguments)
        events = tuple(
            ("consequa_x.assessment", to_ns(item.time_ms), {
                "consequa_x.assessment_id": item.assessment_id,
                "consequa_x.assessment.status": item.status.value,
                **({"consequa_x.rationale": item.rationale} if include_payloads else {}),
            }) for item in assessments)
        failed = bool(latest) and latest.status.value == "violated"
        spans.append(SpanRecord(
            otel_trace, span_id, f"consequa_x action {action.name}",
            to_ns(min(own)), to_ns(max(own)), root_id, attributes, events, failed,
            "Verification found the outcome contract violated" if failed else ""))
        seen = set()
        for response in responses:
            seen.add(response.attempt_id)
            dispatch = dispatches.get(response.attempt_id)
            start = dispatch.time_ms if dispatch is not None else response.time_ms
            spans.append(_tool_span(otel_trace, trace.trace_id, span_id, action, response.attempt_id,
                                    to_ns(start), to_ns(response.time_ms), response,
                                    include_payloads))
        for attempt_id, dispatch in dispatches.items():
            if dispatch.data.get("action_id") == action.action_id and attempt_id not in seen:
                spans.append(_tool_span(otel_trace, trace.trace_id, span_id, action, attempt_id,
                                        to_ns(dispatch.time_ms), to_ns(dispatch.time_ms), None,
                                        include_payloads))
        for index, receipt in enumerate(verifications):
            read = [observations[item.observation_id] for item in receipt.evidence]
            spans.append(SpanRecord(
                otel_trace,
                _hex("span", trace.trace_id, "verification", action.action_id, str(index),
                     length=16),
                f"consequa_x verify {contract.predicate}",
                to_ns(min(item.observed_at_ms for item in read)), to_ns(receipt.observed_at_ms),
                span_id, {
                    "consequa_x.action_id": action.action_id,
                    "consequa_x.contract.id": receipt.contract_id,
                    "consequa_x.verification.status": receipt.status.value,
                    "consequa_x.verification.origin": receipt.origin.value,
                    "consequa_x.verification.effect_ids": list(receipt.effect_ids),
                    "consequa_x.verification.attributable_effect_ids":
                        list(receipt.attributable_effect_ids),
                    "consequa_x.verification.target_matched": receipt.target_effect_ids is not None,
                    "consequa_x.verification.findings": [item.code for item in receipt.findings],
                    **({"consequa_x.verification.reason": receipt.reason}
                       if include_payloads else {}),
                },
                tuple(("consequa_x.readback", to_ns(item.observed_at_ms), {
                    "consequa_x.observation_id": item.observation_id,
                    "consequa_x.readback.source": item.source,
                    "consequa_x.readback.as_of_ms": item.as_of_ms,
                    "consequa_x.readback.complete": item.complete,
                    "consequa_x.readback.available": item.available,
                    "consequa_x.readback.record_count": len(item.records),
                }) for item in read)))
    return tuple(spans)


def _tool_span(otel_trace, trace_id, parent, action, attempt_id, start, end, response,
               include_payloads) -> SpanRecord:
    status = response.status.value if response is not None else "not_recorded"
    attributes: dict[str, Any] = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": action.name,
        "gen_ai.agent.name": action.actor,
        "consequa_x.action_id": action.action_id,
        "consequa_x.attempt_id": attempt_id,
        "consequa_x.response.status": status,
    }
    error = status in ("error", "timeout")
    if error:
        attributes["error.type"] = ("timeout" if status == "timeout" else
                                    str(response.result.get("exception") or "_OTHER"))
    if include_payloads:
        attributes["gen_ai.tool.call.arguments"] = thaw(action.arguments)
        if response is not None and status == "success":
            attributes["gen_ai.tool.call.result"] = thaw(response.result)
    return SpanRecord(otel_trace, _hex("span", trace_id, "attempt", attempt_id, length=16),
                      f"execute_tool {action.name}", start, end, parent, attributes, (), error,
                      f"Tool {status}" if error else "")


# OTLP/JSON -----------------------------------------------------------------------------


def _any_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_any_value(item) for item in value]}}
    if isinstance(value, dict):
        return {"kvlistValue": {"values": [{"key": key, "value": _any_value(item)}
                                           for key, item in value.items()]}}
    if value is None:
        return {}
    raise ConsequaTypeError(f"Cannot encode {type(value).__name__} as an OTLP value")


def _attributes(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": key, "value": _any_value(value)} for key, value in values.items()]


def to_otlp(trace: Trace, *, service_name: str = "consequa-x", include_payloads: bool = False,
            origin_unix_ms: int | None = None) -> dict[str, Any]:
    """Encode a trace as an OTLP/JSON ``ExportTraceServiceRequest`` document.

    Span and trace identifiers are derived from the trace's identifiers, so
    exporting the same trace twice gives the same document. A ``relative_ms``
    trace needs ``origin_unix_ms``, the wall-clock time its zero stands for.
    With ``include_payloads=True`` the export also carries tool arguments and
    results, readback rationale and the complete trace (on the root span), and
    :func:`from_otlp` can restore it; it may then contain sensitive data.
    """
    if not isinstance(service_name, str) or not service_name.strip():
        raise ValidationError("service_name must be a nonempty string")
    spans = trace_spans(trace, include_payloads=include_payloads, origin_unix_ms=origin_unix_ms)
    return {"resourceSpans": [{
        "resource": {"attributes": _attributes({"service.name": service_name})},
        "scopeSpans": [{
            "scope": {"name": SCOPE_NAME, "version": __version__},
            "spans": [_otlp_span(span) for span in spans],
        }],
    }]}


def _otlp_span(span: SpanRecord) -> dict[str, Any]:
    encoded: dict[str, Any] = {
        "traceId": span.trace_id, "spanId": span.span_id, "name": span.name,
        "kind": _INTERNAL, "startTimeUnixNano": str(span.start_ns),
        "endTimeUnixNano": str(span.end_ns), "attributes": _attributes(span.attributes),
        "events": [{"timeUnixNano": str(time_ns), "name": name,
                    "attributes": _attributes(values)}
                   for name, time_ns, values in span.events],
        "status": ({"code": _ERROR, "message": span.status_message} if span.error
                   else {"code": _UNSET}),
    }
    if span.parent_span_id:
        encoded["parentSpanId"] = span.parent_span_id
    return encoded


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or len(value) > 1:
        raise ValidationError("OTLP attribute values must be AnyValue objects")
    if not value:
        return None
    kind, item = next(iter(value.items()))
    if kind == "stringValue" and isinstance(item, str):
        return item
    if kind == "boolValue" and isinstance(item, bool):
        return item
    if kind == "intValue" and (type(item) is int or (isinstance(item, str)
                                                     and item.lstrip("-").isdigit())):
        return int(item)
    if kind == "doubleValue" and isinstance(item, (int, float)) and not isinstance(item, bool):
        return float(item)
    if kind == "bytesValue" and isinstance(item, str):
        return base64.b64decode(item, validate=True).hex()
    if kind == "arrayValue" and isinstance(item, dict):
        return [_decode_value(entry) for entry in item.get("values", [])]
    if kind == "kvlistValue" and isinstance(item, dict):
        return dict(_decode_pairs(item.get("values", [])))
    raise ValidationError(f"Unsupported OTLP value: {kind!r}")


def _decode_pairs(values: Any) -> list[tuple[str, Any]]:
    if not isinstance(values, list):
        raise ValidationError("OTLP attributes must be a list")
    pairs = []
    for entry in values:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
            raise ValidationError("OTLP attributes need a string key")
        pairs.append((entry["key"], _decode_value(entry.get("value", {}))))
    return pairs


def _nanos(value: Any, label: str) -> int:
    if type(value) is int or (isinstance(value, str) and value.isdigit()):
        return int(value)
    raise ValidationError(f"{label} must be integer nanoseconds")


def _identifier(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ValidationError(f"{label} must be {length} hexadecimal characters")
    try:
        int(value, 16)
    except ValueError:
        raise ValidationError(f"{label} must be {length} hexadecimal characters") from None
    return value.lower()


def _spans(data: Any) -> list[SpanRecord]:
    """Accept an OTLP/JSON document (dict or JSON text) or OpenTelemetry SDK spans."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as error:
            raise ValidationError(f"OTLP document is not valid JSON: {error}") from error
    if isinstance(data, dict):
        resource_spans = data.get("resourceSpans")
        if not isinstance(resource_spans, list):
            raise ValidationError("OTLP document needs a resourceSpans list")
        records = []
        for resource in resource_spans:
            for scope in (resource or {}).get("scopeSpans", []):
                for span in (scope or {}).get("spans", []):
                    records.append(_json_span(span))
        return records
    if isinstance(data, Iterable):
        return [_sdk_span(span) for span in data]
    raise ConsequaTypeError("Expected an OTLP/JSON document or OpenTelemetry SDK spans")


def _json_span(span: Any) -> SpanRecord:
    if not isinstance(span, dict):
        raise ValidationError("OTLP spans must be JSON objects")
    parent = span.get("parentSpanId") or None
    status = span.get("status") or {}
    return SpanRecord(
        trace_id=_identifier(span.get("traceId"), 32, "traceId"),
        span_id=_identifier(span.get("spanId"), 16, "spanId"),
        name=str(span.get("name", "")),
        start_ns=_nanos(span.get("startTimeUnixNano"), "startTimeUnixNano"),
        end_ns=_nanos(span.get("endTimeUnixNano"), "endTimeUnixNano"),
        parent_span_id=_identifier(parent, 16, "parentSpanId") if parent else None,
        attributes=dict(_decode_pairs(span.get("attributes", []))),
        events=tuple((str(event.get("name", "")),
                      _nanos(event.get("timeUnixNano"), "timeUnixNano"),
                      dict(_decode_pairs(event.get("attributes", []))))
                     for event in span.get("events", [])),
        error=status.get("code") in (_ERROR, "STATUS_CODE_ERROR"),
        status_message=str(status.get("message", "")),
    )


def _sdk_span(span: Any) -> SpanRecord:
    try:
        context, parent = span.context, span.parent
        status = span.status
        return SpanRecord(
            trace_id=f"{context.trace_id:032x}", span_id=f"{context.span_id:016x}",
            name=span.name, start_ns=int(span.start_time), end_ns=int(span.end_time),
            parent_span_id=f"{parent.span_id:016x}" if parent is not None else None,
            attributes={key: _plain(value) for key, value in (span.attributes or {}).items()},
            events=tuple((event.name, int(event.timestamp),
                          {key: _plain(value) for key, value in (event.attributes or {}).items()})
                         for event in span.events),
            error=getattr(status.status_code, "name", "") == "ERROR",
            status_message=status.description or "",
        )
    except AttributeError as error:
        raise ConsequaTypeError("Expected OpenTelemetry SDK ReadableSpan objects") from error


def _plain(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def from_otlp(data: Any) -> tuple[Trace, ...]:
    """Restore the traces in an export made with ``include_payloads=True``.

    ``data`` is an OTLP/JSON document (a dict or JSON text) or OpenTelemetry
    SDK spans. Each root span carrying ``consequa_x.trace`` yields one trace,
    validated exactly like a trace read from a file. Exports without payloads,
    and spans from other instrumentations, hold no complete trace: read their
    tool spans with :func:`record_tool_spans` instead.
    """
    traces = []
    for span in _spans(data):
        value = span.attributes.get(TRACE_ATTRIBUTE)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValidationError(f"{TRACE_ATTRIBUTE} must be the trace's JSON text")
        traces.append(Trace.from_json(value))
    if not traces:
        raise ValidationError("No span carries a complete ConseqaX trace; export with "
                              "include_payloads=True, or read tool spans with "
                              "record_tool_spans")
    return tuple(traces)


# Reading GenAI tool spans --------------------------------------------------------------


def _object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    try:
        copied = _json_copy(value, "value")
    except (TypeError, ValueError):
        return None
    return copied if type(copied) is dict else None


def _timeout(error_type: Any) -> bool:
    text = str(error_type or "").lower()
    return text == "timeout" or text.endswith("timeouterror") or text.endswith(".timeout")


def record_tool_spans(data: Any, recorder: TraceRecorder, *,
                      contract_for: Callable[[ToolSpan], OutcomeContract | None],
                      otel_trace_id: str | None = None) -> tuple[ActionCapture, ...]:
    """Record ``execute_tool`` spans as actions, attempts and responses.

    ``data`` is an OTLP/JSON document or OpenTelemetry SDK spans from any
    instrumentation that follows the GenAI conventions. Spans are read in
    start-time order. ``contract_for(span)`` returns the outcome contract for a
    consequential tool call, or ``None`` to skip it. Each recorded call becomes
    one action (``gen_ai.tool.call.id`` as its ID when the span has one) with one
    attempt: dispatched at the span's start, answered at its end. An error
    status with an ``error.type`` naming a timeout records ``timeout``, any other
    error ``error``, and otherwise ``success``. Arguments and results are kept
    only when the span recorded them as JSON objects.

    The recorder must use the ``unix_ms`` time base, since span times are wall
    clock. When ``data`` holds several OpenTelemetry traces, name one with
    ``otel_trace_id``. Returns the new actions' capture handles, so their
    readback can be verified next; the spans themselves establish no outcome.
    """
    if not isinstance(recorder, TraceRecorder):
        raise ConsequaTypeError("record_tool_spans requires a TraceRecorder")
    if recorder.time_base is not TimeBase.UNIX_MS:
        raise ValidationError("Span times are wall clock; use a unix_ms TraceRecorder")
    if not callable(contract_for):
        raise ConsequaTypeError("contract_for must be callable")
    spans = [span for span in _spans(data)
             if span.attributes.get("gen_ai.operation.name") == "execute_tool"]
    traces = sorted({span.trace_id for span in spans})
    if otel_trace_id is not None:
        otel_trace_id = _identifier(otel_trace_id, 32, "otel_trace_id")
        spans = [span for span in spans if span.trace_id == otel_trace_id]
    elif len(traces) > 1:
        raise ValidationError(f"The spans belong to {len(traces)} OpenTelemetry traces; "
                              "choose one with otel_trace_id")
    captures = []
    for span in sorted(spans, key=lambda item: (item.start_ns, item.span_id)):
        name = span.attributes.get("gen_ai.tool.name")
        if not isinstance(name, str) or not name.strip():
            continue
        call_id = span.attributes.get("gen_ai.tool.call.id")
        call_id = call_id if isinstance(call_id, str) and call_id.strip() else None
        agent = span.attributes.get("gen_ai.agent.name")
        agent = agent if isinstance(agent, str) and agent.strip() else None
        started, ended = span.start_ns // 1_000_000, span.end_ns // 1_000_000
        offered = ToolSpan(
            tool_name=name, arguments=_object(span.attributes.get("gen_ai.tool.call.arguments"))
            or {}, started_at_ms=started, ended_at_ms=ended, call_id=call_id, agent_name=agent,
            span_id=span.span_id, trace_id=span.trace_id, attributes=dict(span.attributes))
        contract = contract_for(offered)
        if contract is None:
            continue
        if not isinstance(contract, OutcomeContract):
            raise ConsequaTypeError("contract_for must return an OutcomeContract or None")
        action_id = call_id or f"span-{span.span_id}"
        capture = recorder.register(action_id, name, offered.arguments, contract=contract,
                                    at_ms=started, actor=agent)
        attempt = capture.dispatch(attempt_id=f"{action_id}:span-{span.span_id}", at_ms=started,
                                   data={"otel_span_id": span.span_id,
                                         "otel_trace_id": span.trace_id})
        if span.error:
            status = (ResponseStatus.TIMEOUT if _timeout(span.attributes.get("error.type"))
                      else ResponseStatus.ERROR)
            result = {"error_type": str(span.attributes["error.type"])} \
                if "error.type" in span.attributes else {}
        else:
            status = ResponseStatus.SUCCESS
            result = _object(span.attributes.get("gen_ai.tool.call.result")) or {}
        capture.response(attempt, status, at_ms=max(ended, started),
                         provider_request_id=call_id, result=result)
        captures.append(capture)
    return tuple(captures)


# Emitting through the OpenTelemetry API ------------------------------------------------


def emit(trace: Trace, tracer: Any = None, *, include_payloads: bool = False,
         origin_unix_ms: int | None = None) -> None:
    """Create the export's spans through the ``opentelemetry-api`` package.

    Spans keep the trace's recorded times and nest under the current span, so
    the application's tracer provider and exporter send them on. ``tracer``
    defaults to ``opentelemetry.trace.get_tracer("consequa-x")``. Structured
    payloads (``include_payloads=True``) are recorded as JSON strings, which
    the conventions allow where an SDK takes no structured attribute values.
    Install with ``pip install "consequa-x[otel]"``.
    """
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.trace import SpanKind, Status, StatusCode
    except ImportError as error:  # pragma: no cover - exercised without the extra
        raise ImportError('emit needs opentelemetry-api: pip install "consequa-x[otel]"') \
            from error
    spans = trace_spans(trace, include_payloads=include_payloads, origin_unix_ms=origin_unix_ms)
    tracer = tracer or otel_trace.get_tracer(SCOPE_NAME, __version__)
    started: dict[str, Any] = {}
    for span in spans:
        parent = started.get(span.parent_span_id) if span.parent_span_id else None
        context = otel_trace.set_span_in_context(parent) if parent is not None else None
        live = tracer.start_span(span.name, context=context, kind=SpanKind.INTERNAL,
                                 attributes=_api_attributes(span.attributes),
                                 start_time=span.start_ns)
        for name, time_ns, values in span.events:
            live.add_event(name, _api_attributes(values), timestamp=time_ns)
        if span.error:
            live.set_status(Status(StatusCode.ERROR, span.status_message))
        started[span.span_id] = live
    for span in reversed(spans):
        started[span.span_id].end(end_time=span.end_ns)


def _api_attributes(values: dict[str, Any]) -> dict[str, Any]:
    converted = {}
    for key, value in values.items():
        if isinstance(value, dict) or (isinstance(value, list) and any(
                not isinstance(item, str) for item in value)):
            converted[key] = _compact(value)
        else:
            converted[key] = value
    return converted
