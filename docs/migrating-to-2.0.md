# Migrating to Consequa-X 2.0

2.0 makes the breaking changes planned in the [2.0 design](design-2.0.md) once.
Evidence discipline is unchanged: tool response, the agent's report, verified
state and effect origin stay separate, and unknown evidence stays unknown.

## Saved traces

Schema `0.1` traces (written by 1.x) are refused by `Trace.from_json` with a
`SchemaVersionError`. Convert them:

```console
consequa-x migrate old-trace.json --output new-trace.json
consequa-x validate new-trace.json
```

```python
from consequa_x import MigrationReport, RecordVerifier, migrate_trace

report = MigrationReport()
trace = migrate_trace(old_json_text, report=report,
                      verifiers={"record_present": RecordVerifier(scope_fields=("order_id",))})
```

The single action and assessment become one-item lists, responses and
verifications gain the action ID, and the time base is `relative_ms` because 0.1
never recorded one. Target matches and findings (new in 2.0) are added only when
the 2.0 verifier, re-run on the recorded observation, reproduces the recorded
receipt exactly; the refund verifier is used by default, and `verifiers=` supplies
others. No recorded conclusion is changed. A receipt that is not reproduced keeps
`target_effect_ids=None`, so its assessment alignment is `unassessable`.

## Records

| 1.x | 2.0 |
| --- | --- |
| `Trace(trace_id, action, events, responses, assessment, ...)` | `Trace(trace_id=..., time_base=TimeBase.UNIX_MS, actions=(...,), events=..., responses=..., assessments=(...), ...)` |
| `trace.action` | `trace.actions`, `trace.get_action(id)`, `trace.single_action` |
| `trace.assessment` | `trace.assessments`, `trace.latest_assessment(action_id)` (may be `None`) |
| positional constructors | keyword-only constructors for every record |
| `Action(..., trace_id=..., ...)`, `Event(..., trace_id=...)` | no `trace_id`; it is stated once, on the trace |
| `ToolResponse(attempt_id, ...)` | also `action_id` |
| `AgentAssessment(status, time_ms, ...)` | also `assessment_id` and `action_id`; zero or more per action |
| `VerificationResult(contract_id, ...)` | also `action_id`; new `target_effect_ids` and `findings` |
| payload dicts and lists could be mutated | read-only `FrozenDict`/`FrozenList`; `thaw(value)` gives an editable copy; `to_dict()` still exports plain JSON |
| `ValueError` / `TypeError` | typed errors under `ConsequaError` that still subclass `ValueError` or `TypeError` |

Times: `TimeBase.UNIX_MS` means milliseconds since the Unix epoch;
`TimeBase.RELATIVE_MS` means milliseconds from an unrecorded run origin. Every time
in a trace uses its declared base.

## Capture

```python
# 1.x
rec.register("refund-1", "issue_refund", args, contract=contract)   # returned Action
with rec.attempt() as attempt: ...

# 2.0
refund = rec.register("refund-1", "issue_refund", args, contract=contract)  # ActionCapture
with refund.attempt() as attempt: ...
refund.assessment("failure")
refund.verify(readback, verifier=verifier)
```

The recorder-level calls still work while exactly one action is registered; with
several, use each action's `ActionCapture` (or `rec.capture_for(action_id)`). The
recorder's default clock is now wall-clock `unix_ms`; with a custom `clock` the
time base is `relative_ms` unless you pass `time_base="unix_ms"`. An assessment
is optional: `trace()` no longer requires one. `capture_tool` accepts `async def`
tools, and `acall`/`averify`/`apoll_readback` serve async agents.

## Verification and explanation

| 1.x | 2.0 |
| --- | --- |
| `explain(trace, target_matcher=...)` | `explain(trace)`; target matching is recorded by the verifier in `target_effect_ids` |
| `TargetMatcher`, `RecordTargetMatcher`, `RecordVerifier.target_matcher()` | removed; a custom verifier sets `target_effect_ids` |
| `explain(...)` returned one `ConsequenceExplanation` | returns a `TraceExplanation`; use `.for_action(id)` or `.single_action` for an `ActionExplanation` |
| `explanation.diagnoses` (strings), `explanation.diagnosis` | `.diagnoses` are `Diagnosis(code, evidence, message)` records; `.codes` gives the strings; `.diagnosis` is a display label |
| refund findings derived inside `explain` | recorded by `RefundVerifier` as `findings`; `RecordVerifier` records its own |
| missing verification raised `ValueError` | reported as `NO_VERIFICATION` |
| `UNASSESSABLE_ASSESSMENT` only for non-refund predicates | for every predicate whenever the outcome is known but alignment cannot be judged |

A custom verifier from 1.x keeps working unchanged except that its
`VerificationResult` needs `action_id=action.action_id`. Without
`target_effect_ids`, alignment is `unassessable`, exactly as it was without a
target matcher. Move a 1.x matcher's logic into the verifier and set
`target_effect_ids` to the attributable effects that match the full target (for a
known outcome), or leave it `None`.

## Reports, research and the command line

- Reports cover every action and now show each action's alignment and diagnosis
  codes, computed from the recorded receipts. `redact=` blanks named keys in a
  details report.
- Research interfaces (`EffectEstimate`, `Intervention`, `leave_one_out`,
  `recency_attribution`, the policy types) are imported from
  `consequa_x.research`.
- New commands: `validate`, `migrate`, `summarize`, `compare` and `verify`.
