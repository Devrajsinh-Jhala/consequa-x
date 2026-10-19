# Stable core API: version 2

This is the core compatibility contract for version 2. Release-specific build,
validation and publication status belong in the release notes and the release
receipts under `output/`. The changes from version 1 are listed in
[migrating to 2.0](migrating-to-2.0.md).

## Supported public interface

Everything exported from `consequa_x` is stable through 2.x:

- **Records and statuses:** `Trace`, `Action`, `OutcomeContract`, `Event`,
  `ToolResponse`, `AgentAssessment`, `Observation`, `Evidence`,
  `VerificationResult`, `Finding`, `EventType`, `ResponseStatus`,
  `AssessmentStatus`, `VerificationStatus`, `OriginStatus`, `TimeBase`,
  `FrozenDict`, `FrozenList`, `thaw`.
- **Capture:** `TraceRecorder`, `ActionCapture`, `Attempt`, `capture_tool`, and
  `consequa_x.mcp_capture.call_mcp_tool`.
- **Verification:** `Verifier`, `verify`, `averify`, `RefundVerifier`,
  `RecordVerifier`, `poll_readback`, `apoll_readback`, and (since 2.1)
  `CompositeVerifier`, `all_of`, `any_of` and `contract_parts`. `verify`,
  `averify`, `ActionCapture.verify` and `poll_readback` accept several readbacks
  for a verifier that provides `verify_readbacks`.
- **Explanation and presentation:** `explain`, `TraceExplanation`,
  `ActionExplanation`, `Diagnosis`, `CORE_DIAGNOSES`, `build_graph`,
  `ConsequenceGraph`, `render_report`.
- **Acting on evidence and collections:** `retry_advice`, `RetryAdvice`,
  `RetryDecision`, `summarize`, `Summary`, `compare`, `Comparison`,
  `ActionChange`, `TraceStore`.
- **Migration:** `migrate_trace`, `MigrationReport`.
- **Errors:** `ConsequaError` and its subclasses `ConsequaTypeError`,
  `ValidationError`, `SchemaVersionError`, `ContractError`, `ReceiptError` and
  `RecorderError`.
- `consequa_x.schema.get_trace_schema`, `generate_trace_schema` and
  `validate_trace`.
- Since 2.1: `consequa_x.otel` (`to_otlp`, `from_otlp`, `record_tool_spans`,
  `emit`, `trace_spans`, `SpanRecord`, `ToolSpan`) and `consequa_x.integrations`
  (`ToolCallCapture`, `ToolCall`, `PendingCall`, `classify_exception`, and the
  `openai_agents`, `langchain` and `claude_agent_sdk` modules). The integration
  modules follow their frameworks' public APIs; a framework release that changes
  those APIs may need a ConseqaX update, and each module states the version it
  was tested with. The OpenTelemetry GenAI conventions are in development
  upstream, so exported `gen_ai.*` attribute names follow them as they change;
  `consequa_x.*` attributes are stable through 2.x.

All records are frozen, keyword-only dataclasses with deeply read-only payloads.

## Wire schema `1.0`

A trace holds one or more actions, each with its own outcome contract.
Responses, assessments and verifications name their `action_id`; every time is
an integer number of milliseconds in the trace's declared `time_base`
(`unix_ms` or `relative_ms`). Identities are unique within a trace, event
dependencies are acyclic, and verification evidence must resolve to an
observation with the same source and watermark. Unsupported schema versions,
unknown record fields, invalid identities and dependency cycles fail validation;
schema `0.1` is refused with a pointer to `migrate_trace`. Enums are
string-valued; money is integer minor units.

The software version and the schema version are separate. Valid schema `1.0`
records stay readable through 2.x. An incompatible wire format requires a new
schema version and a migration path; old records are never silently
reinterpreted.

## Verification and explanation

`verify(action, observation, *, verifier=None)` uses the refund verifier by
default and accepts a trusted application verifier. A verifier is application
code: `verify` checks that its receipt binds to the supplied action, contract
and observation (identity, source, watermark and timing), not that its
conclusions are true. The receipt carries the verifier's domain interpretation:
`target_effect_ids` (`None` when it did no target matching) and `findings`.

`explain(trace, estimates=())` is domain-independent and performs no replay. It
reads the latest receipt and assessment of each action. Alignment is judged only
when the receipt records target matching and, for a satisfied outcome, at least
one matching effect from this action; otherwise it is `unassessable`. An action
without verification is reported as `NO_VERIFICATION`, never as success. Codes
produced by `explain` itself are listed in `CORE_DIAGNOSES`; other codes come
from verifier findings.

`render_report` presents a revalidated snapshot offline. By default it omits
every captured string, identifier and payload; `include_details=True` embeds the
whole trace as escaped text, and `redact=` blanks named keys in it. See
[offline reports](offline-reports.md).

## Errors

Every intentional error derives from `ConsequaError` and also from `ValueError`
or `TypeError`:

- `ConsequaTypeError`: an argument or record field has the wrong type.
- `ValidationError`: an invalid record, trace, relationship or setting, including
  malformed JSON; `SchemaVersionError` for an unsupported schema version.
- `ContractError`: a verifier cannot evaluate this contract.
- `ReceiptError`: a receipt crosses its identity boundary, or recorded evidence
  cannot support the interpretation asked of it.
- `RecorderError`: the recorder was used out of order or with conflicting
  identities.

File errors produce `OSError`. The CLI reports controlled errors with exit status
2. Exceptions raised inside application code (tools, verifiers, readers)
propagate unchanged.

## Output preservation

CLI commands that write files require a new output file or an empty output
directory and never replace their inputs. `TraceStore` only appends. Commands
assume one process owns an output path.

## Research interfaces

`consequa_x.research` (replay attribution and policy adapters) and
`consequa_x.benchmark` are declared research interfaces. Their protocols and
artifacts pin source revisions; they may change between minor versions, and
method changes must be named, recorded and preserve historical data.

Python 3.11+ is declared; release receipts identify the exact tested
interpreters and platforms. A pure-Python wheel does not establish a test
result on every platform. Optional local Ollama inference requires a configured
server and model; core imports and offline examples need no credentials or
runtime dependencies.
