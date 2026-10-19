# Consequa-X 2.0 design

Status: agreed direction, built on the `release-2.0` branch. Decided 19 October
2026, after publishing 1.2.0. The package leads: the paper will be reshaped
around 2.0 rather than 2.0 waiting for the paper. Research code (benchmark,
replay, attribution, policies) is ported to the 2.0 data model, not split out.

2.0 makes the breaking changes once, with a migration path for every schema
`0.1` trace. Evidence discipline does not change: tool response, the agent's
assessment, verified state and effect origin stay separate, and unknown
evidence stays unknown.

## Data model: schema `1.0`

| Change | 0.1 | 1.0 |
| --- | --- | --- |
| Actions per trace (A1) | exactly one `action` | `actions`: one or more, each with its own contract |
| Assessments (A6) | exactly one `assessment` | `assessments`: zero or more, each naming its `action_id` |
| Responses | `attempt_id` only | also `action_id` |
| Verifications | contract ID only | also `action_id`; contract must belong to that action |
| Time (A5) | unlabelled integer milliseconds | integer milliseconds with a declared `time_base`: `unix_ms` (UTC epoch) or `relative_ms` |
| Redundant identity | `trace_id` repeated on every action and event | stated once, on the trace |
| Construction (A2) | positional dataclass arguments | keyword-only arguments |
| Payloads (A9) | copied on input, mutable afterwards | deeply read-only: `FrozenDict` and `FrozenList` still compare equal to and serialize like dicts and lists, but cannot change; `thaw()` gives an editable copy |
| Errors (A8) | bare `ValueError`/`TypeError` | typed exceptions under `ConsequaError`, still subclassing `ValueError`/`TypeError` |

Times stay integers so ordering and arithmetic remain exact. A `unix_ms` trace
can be shown as wall-clock time; a `relative_ms` trace cannot, and migrated
`0.1` traces are `relative_ms` because their origin was never recorded.

Identity rules: action IDs, contract IDs, event IDs, attempt IDs, assessment
IDs and observation IDs are unique within a trace. Every response, assessment
and verification names a declared action. Event dependencies stay acyclic.

## Verification and explanation (A3, A4)

1.x `explain()` contains refund-only branches and a separate `TargetMatcher`.
In 2.0 the verifier owns all domain interpretation and records it in the
receipt; `explain()` becomes domain-independent.

- `VerificationResult.target_effect_ids`: `None` when the verifier did no target
  matching (assessment alignment stays unassessable), otherwise the
  attributable effects that match the full target: payload, timing and
  persistence. Replaces the `TargetMatcher` protocol.
- `VerificationResult.findings`: domain findings the verifier established, each
  with a code and the effect IDs it rests on, such as `EXCESS_EFFECTS`,
  `DUPLICATE_EFFECT`, `PARAMETER_MISMATCH`, `PARTIAL_EFFECT`, `REVERSED_EFFECT`.
  `RefundVerifier` and `RecordVerifier` produce them; custom verifiers can add
  their own codes.
- `explain(trace)` returns a `TraceExplanation` with one `ActionExplanation` per
  action: the latest verification, every assessment with its own alignment, and
  structured `Diagnosis` records (code, action, evidence references, message).
  The joined diagnosis string is removed. An action without verification gets
  `NO_VERIFICATION` instead of an exception: missing readback is reported, never
  treated as success.

Explanations trust recorded receipts exactly as 1.x trusted recorded status and
origin: a verifier is application code, and the receipt is its claim.

## Capture, reports and tools

- `TraceRecorder` captures several actions. Calls that concern an action take
  `action=`; it may be omitted while exactly one action is registered. The
  default clock is wall-clock `unix_ms`; a custom clock must declare its time base.
- Async capture (B7): `attempt()` already wraps an `await`; add async
  `capture_tool`/`call` support and async verifier calls.
- Reports render every action, with per-action contract, responses,
  assessments, readback and diagnoses (D1).
- CLI: `validate` and `migrate` (D5), `summarize` with text, Markdown and JSON
  output (B8, D3), `verify` from a contract and readback file (D4).
- Research APIs leave the top-level namespace and are imported from
  `consequa_x.research` (A7, reduced to an import-path change because the
  research code is ported, not split out).

## Migration

`consequa_x.migrate.migrate_trace(data)` and `consequa-x migrate OLD --output NEW`
convert a schema `0.1` trace: the single action becomes `actions[0]`, the
assessment gains an ID and the action ID, responses and verifications gain the
action ID, and the time base is `relative_ms`. Refund receipts are re-derived
only when their recorded evidence supports it; otherwise `target_effect_ids`
stays `None` and alignment stays unassessable. `Trace.from_json` rejects `0.1`
with a `SchemaVersionError` that names the migrate command.

## Build order

Each step lands as reviewed commits with the full suite passing.

1. Typed exceptions (A8).
2. Deeply immutable payloads (A9).
3. Schema `1.0` with keyword-only records, several actions and assessments, time
   base, recorder, graph, report, CLI and research port (A1, A2, A5, A6, D1).
4. Verifier-owned target matching and findings, structured diagnoses (A3, A4).
5. Migration and `validate`/`migrate` commands (D5); `consequa_x.research` (A7).
6. Additive tools: verifier composition (B4), readback polling (B5), retry
   guard (B6), async capture (B7), `summarize` (B8, D3), trace comparison (D2),
   `verify` command (D4), report redaction rules (D6), JSONL store (D7).
7. Integrations as optional extras (C1–C3) and OpenTelemetry export (C5),
   if time allows before 2.0.0; otherwise 2.1.
8. Docs, website, migration guide, release checks, publication on approval.

## Effect on research and the paper

Retained study receipts under `output/` were produced with 1.x and stay bound to
their recorded revisions; they are not regenerated. After the port, research
modules produce schema `1.0` traces, so new studies and the reshaped paper
should name 2.0. Frozen study runners hash `src/consequa_x/**/*.py`, so merging
`release-2.0` into `main` must wait until no study is running there.
