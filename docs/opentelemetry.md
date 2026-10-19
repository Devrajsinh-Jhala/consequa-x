# OpenTelemetry export and import

`consequa_x.otel` (added in 2.1) moves ConseqaX traces through an
OpenTelemetry pipeline, next to the rest of an agent's telemetry, and reads
tool spans from other instrumentation back into a recorder. The OTLP/JSON
functions need no dependency; `emit` needs `opentelemetry-api`
(`pip install "consequa-x[otel]"`).

Tool spans follow the OpenTelemetry GenAI semantic conventions for
`execute_tool` spans. Those conventions are still in *development* status
upstream, so attribute names may change in later OpenTelemetry releases. Every
ConseqaX finding uses its own `consequa_x.*` attributes.

## What an export contains

| Span | Name | Holds |
| --- | --- | --- |
| Root | `consequa_x trace <trace_id>` | trace ID, schema version, time base, action count; context and decision events as span events |
| One per action | `consequa_x action <tool>` | action ID, actor, contract ID, predicate, deadline and horizon, latest verification state and origin, the agent's latest assessment, alignment, diagnosis codes; assessments as span events. Its status is `ERROR` when verification found the contract violated |
| One per attempt | `execute_tool <tool>` | `gen_ai.operation.name`, `gen_ai.tool.name`, `gen_ai.agent.name`, attempt ID and response status; `error.type` is `timeout` for a timeout and the exception name (or `_OTHER`) for an error, with span status `ERROR` |
| One per verification | `consequa_x verify <predicate>` | state, origin, effect IDs, attributable effect IDs, whether target matching was done, finding codes; each readback as a span event (source, watermark, completeness, availability, record count) |

`gen_ai.tool.call.id` is never set on exported spans: the conventions reserve
it for an identifier the model or provider supplied, and attempt IDs are not
that.

Payloads are opt-in, as in the conventions. By default an export holds
identifiers, times, statuses, counts and diagnosis codes, but no tool arguments
or results, contract values, readback records, rationale or verifier reasons.
With `include_payloads=True` it also carries those, plus the complete trace as
JSON on the root span (`consequa_x.trace`), so that `from_otlp` can restore it.
Such an export may contain sensitive data; your collector or backend may also
limit attribute sizes.

Span and trace identifiers are derived from the trace's own identifiers, so
exporting the same trace twice gives the same document. Times are the trace's
own: a `unix_ms` trace exports as recorded, and a `relative_ms` trace needs
`origin_unix_ms`, the wall-clock time its zero stands for.

## Export

```python
from consequa_x.otel import emit, to_otlp

document = to_otlp(trace, service_name="refund-service")   # OTLP/JSON dict
```

`document` is the body an OTLP/HTTP collector accepts at `/v1/traces`
(`Content-Type: application/json`). From the command line:

```sh
consequa-x otel-export trace.json --output spans.json
consequa-x otel-export trace.json --output spans.json --include-payloads
```

With an OpenTelemetry SDK already configured in your application, `emit`
creates the same spans through the API, nested under the current span, and your
exporter sends them:

```python
from opentelemetry import trace as otel

emit(trace, otel.get_tracer("refund-service"))
```

Through the API, structured payloads are recorded as JSON strings, which the
conventions allow where an SDK takes no structured attribute values.

## Import

`from_otlp(document)` restores every trace in an export made with
`include_payloads=True` and validates it exactly like a trace file. It also
accepts OpenTelemetry SDK spans, for example from an in-memory exporter. From the
command line:

```sh
consequa-x otel-import spans.json --output-dir restored
```

Spans written by other instrumentation hold no ConseqaX trace, but their tool
spans can still start one. `record_tool_spans` reads `execute_tool` spans into
a `TraceRecorder` (which must use the default `unix_ms` time base). You decide
which calls are consequential and what their outcome contract is:

```python
from consequa_x import OutcomeContract, RecordVerifier, TraceRecorder
from consequa_x.otel import record_tool_spans


def contract_for(span):
    if span.tool_name != "issue_refund":
        return None                       # not consequential: not recorded
    return OutcomeContract(contract_id=f"refund-{span.span_id}", predicate="record_present",
                           expected={"order_id": span.arguments["order_id"]},
                           deadline_ms=span.started_at_ms + 30_000, stability_ms=5_000)


rec = TraceRecorder("from-telemetry", actor="support-agent")
for capture in record_tool_spans(document, rec, contract_for=contract_for):
    capture.verify(read_orders(capture.action), verifier=RecordVerifier(scope_fields=("order_id",)))
trace = rec.trace()
```

Each recorded span becomes one action (its `gen_ai.tool.call.id` as the action
ID when present) with one attempt, dispatched at the span's start and answered
at its end. An error status whose `error.type` names a timeout is recorded as
`timeout`, any other error as `error`, and otherwise `success`. Arguments and
results are kept only when the span recorded them as JSON objects. When the
document holds several OpenTelemetry traces, pass `otel_trace_id`.

A tool span says what a tool returned. It never establishes the outcome: that
still needs readback from your system of record, verified as above.

## Tested with

The OTLP/JSON functions are tested without any OpenTelemetry package; `emit` and
reading SDK spans were tested with `opentelemetry-api` and `opentelemetry-sdk`
1.45.1, using the SDK's in-memory exporter. No collector or tracing backend was
part of the tests.
