# Five-minute offline quickstart

Use Python 3.11 or 3.12. No model, API key, provider account or runtime dependency
is required. Version 2.1.0 is public on PyPI. Traces use schema 1.0.

```console
python -m pip install consequa-x==2.1.0
consequa-x --version
```

Download and extract the [quickstart archive](https://consequa-x.onrender.com/quickstart.zip)
or use the three Python files in examples in this repository. Run from the folder
containing them:

```console
python report_quickstart.py --output my-first-capture
```

Open my-first-capture/verified.html in your browser, then compare unknown.html
and other-actor.html. All records are synthetic. The example reads fixture bytes
independently from the declared action, applies an explicit ArtifactVerifier,
and saves the captured trace separately from its HTML presentation. It executes
no delivery or payment. The unknown example has unavailable readback; the
other-actor example satisfies the requested state with a different actor's effect.

To render the saved trace again:

```console
consequa-x report my-first-capture/verified.json --output another-report.html
```

The output must be new. On systems where the console command is not on PATH,
use python -m consequa_x in its place. To start with the packaged refund fixtures:

```console
consequa-x demo --output sample-run
consequa-x report sample-run/traces/episode_00.json --output sample-report.html
```

## Capture an agent loop

agent_loop_sqlite.py runs a scripted support agent that calls an issue_refund
tool against a local SQLite database. TraceRecorder captures the loop as it runs,
and RecordVerifier checks the refund through a separate read-only connection:

```console
python agent_loop_sqlite.py --mode timeout_after_commit --output agent-run
```

The output folder receives the database, the trace, its explanation and an HTML
report. The tool times out after committing, so the agent reports failure while
readback shows the refund linked to this action. The other modes are other_actor
and stale_readback. No money moves; the refund is a row in a local file.

## Sharing and trust

Default reports omit arbitrary captured values and use local aliases. Timing,
counts, enum statuses and relationships remain visible; review before sharing.
This is deliberate field omission, not universal anonymization. The optional
--include-details flag includes the complete trace as escaped text and may
expose sensitive information. Keep the original trace separately as evidence.

Rendering performs no verifier call, application action or replay. It shows
captured verification; it does not establish source truth. Each action's
assessment alignment and diagnosis codes are computed from the recorded
receipts, exactly as explain(trace) computes them.

## Connect your own application

Declare the target contract before the action and register it with
TraceRecorder; register returns that action's ActionCapture. Wrap each tool call
in capture.attempt() or capture_tool, and record the agent's assessment as it was
stated. Obtain an independent readback with explicit source, scope, completeness,
watermark and origin metadata, or let poll_readback re-read a lagging source. Use
the built-in RecordVerifier for records such as rows, orders or tickets, or
implement a read-only Verifier for another domain that also records which effects
match the target. The artifact_delivery.py example implements one by hand.
An outcome with several required effects, such as a refund and a closed ticket,
is one all_of contract checked by CompositeVerifier, with one readback per
source.

Agents built with the OpenAI Agents SDK, LangChain or the Claude Agent SDK can
record their tool calls through optional integrations, installed as extras
such as consequa-x[langchain]; the framework integration guide shows each one.
consequa-x otel-export writes a trace as OpenTelemetry spans, and
consequa_x.otel can start a trace from the tool spans of other instrumentation.

The schema validates structure and identity linkage. Source authentication,
transaction guarantees and the truth of adapter-provided metadata remain your
application's responsibility. Unknown evidence must stay unknown.

Traces use schema 1.0. Convert traces saved by Consequa-X 1.x with
consequa-x migrate OLD.json --output NEW.json. Research replay
interfaces have separate assumptions; no baseline superiority or live-model
accuracy improvement is claimed. Platform validation is listed in release notes
using actual environments, rather than inferred from a pure-Python wheel.
