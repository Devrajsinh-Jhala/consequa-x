# Claude 2.0 changes: paper boundary and migration feasibility

Read-only review on **19 October 2026**, pinned to main
`85c6574101ebec53aa84a6cda8e23e438446bdf7`. The previous review was at `53c09ae`;
the new comparisons were collected with frozen **1.1.0**, including source
`940ebfcc0059c992977dd8e9f112361ff5b31edd`. No package, website, workflow,
collector, frozen source, raw study file or manuscript was changed by this
review. No package/fixture/corpus was executed and no new model calls were made.
`review.json` retains full source blobs, model-field/enum AST comparisons,
source/wheel inventories, release records and official publication checks.

## What is now current

**2.0.0 is a published breaking release**, not a metadata-only update.
The official [PyPI JSON](https://pypi.org/pypi/consequa-x/2.0.0/json) independently
matches both retained publication files:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Wheel | 191,053 | `b9d7a1c6676fc8de84df437acd48feef7a6a77e78fd625cac235cd647844793c` |
| Source distribution | 607,605 | `70868f903271f2ae9f9dc7f73fd2bb993e406934b115db89018aa76cdb0c9c45` |

Release build source is `87463bf290ff1a1da9b270a7b11f48c512549172`; upload was
19 October 2026 at 09:46 UTC (15:16 IST). Python 3.11+, MIT and no required
runtime dependencies remain declared. The repository is public. GitHub's
read-only Actions API still reports **`enabled:false`**.

The release record reports 1,888 passed, 21 skipped and 241 subtests, plus
installed-artifact checks on Windows Python 3.11.9/3.12.10 and one emulated
QEMU Alpine Linux 3.24.2/Python 3.14.8 guest. The Windows sdist check migrated
a saved released-1.2.0 trace. These are retained release receipts, not tests
rerun by this review, scientific replication, or evidence covering every saved
research trace. macOS is untested; MCP uses a stand-in session. Live framework
integrations, OpenTelemetry export and verifier composition are deferred.
The docs/support gate was pending at upload and met after publication. Render
still uses the separate site mirror according to the retained deployment record.

## Breaking data and API changes

| Area | Frozen 1.x | Current 2.0 |
| --- | --- | --- |
| Wire version | `schema_version="0.1"` | `schema_version="1.0"`; direct old-schema parsing is refused |
| Actions | One `trace.action` | One or more `trace.actions`; `get_action(id)`/`single_action` |
| Assessments | One `trace.assessment` | Zero or more, each with `assessment_id` and `action_id`; latest per action may be absent |
| Time | Unlabelled integer milliseconds | Declared `unix_ms` or `relative_ms`; integer milliseconds retained |
| Identity | `trace_id` repeated on actions/events | Trace owns that identity; responses/assessments/receipts name `action_id` |
| Model construction | Positional constructors, copied mutable payloads | Keyword-only wire records, deeply read-only `FrozenDict`/`FrozenList`; `thaw` exports editable copies |
| Errors | Bare value/type errors | Typed errors under `ConsequaError`, retaining value/type ancestry |
| Verification result | State, origin and effect lists | Adds `action_id`, `target_effect_ids` and `findings` |
| Target interpretation | Refund logic in explanation, optional `TargetMatcher`/`RecordTargetMatcher` | Verifier records target matches and findings; matcher protocols removed |
| Explanation result | `ConsequenceExplanation` for one action | `TraceExplanation`, with `ActionExplanation` per action and structured `Diagnosis` |
| Missing verification | Explanation raises an error | `NO_VERIFICATION`; missing evidence is never success |
| Capture | One action per recorder; `register` returns `Action` | Multiple action handles; `register` returns `ActionCapture`; default wall-clock time, optional relative clock |
| Research imports | Several top-level exports | `consequa_x.research`; benchmark modules remain declared research interfaces |

The main verification enums have **not been renamed**: state remains
`satisfied/violated/unknown`, origin `confirmed/other_actor/unknown`, responses
`success/error/timeout`, assessments `success/failure/partial/unknown`.
Do not describe these as new verdict categories. Their containers, routing and
interpretation boundary changed. `RecordTargetMatcher` existed in 1.2 and is
removed in 2.0; the frozen 1.1.0 export list did not contain it.

`explain` currently summarizes the **latest recorded** verification and
assessment for each action. It retains other assessment records in the trace,
but does not return an individual alignment for every historical assessment.
Avoid repeating the design document's broader 'every assessment with its own
alignment' wording as implemented behavior. Diagnosis objects provide `.codes`
for string codes; joined `.diagnosis` remains a display property rather than
an exported field.

2.0 also ships sync/async readback polling, async capture/verification,
receipt-based retry advice, trace summaries/comparison, an append-only JSONL
store, report detail redaction, and validate/migrate/summarize/compare/verify
commands. Implemented APIs do not complete the paper's proposed polling
latency/availability study, production controller comparison, late-commit
safety analysis, or multi-action empirical evaluation. Retry advice is not an
exactly-once guarantee and readback trust stays with the application.

## What changed in the research implementation

The frozen runtime has 37 payload paths; current 2.0 has 48. In both source and
wheels, **18 existing paths are byte-identical, 18 modified, one old schema path
removed and 12 paths added**. The old `trace-v0.1.json` is replaced by
`trace-v1.0.json`; history and old wheels still retain the original schema.
The 1.2 '36 existing files unchanged' statement must remain historical only.

The following estimator modules are byte-identical to the frozen source:

- `benchmark/decision_contrastive.py`, `decision_shapley.py`, `decision_coalition.py`;
- `benchmark/intervals.py`, `interval_comparison.py`;
- calibration, calibration export/mechanisms, interaction mechanisms/export,
  assessment metrics, study definitions and templates;
- the local Ollama adapter.

`attribution.py` only adds the typed-error base to
`InsufficientEvidenceError`; its numerical calculations are unchanged.
A separate AI-assisted read-only source review found schema construction and
access changes in replay, policy, payment, target and summary code: frozen
container support, response action IDs, keyword constructors, and
`single_action`/latest-assessment access. No changed estimator formula,
permutation/seed draw law, stochastic fault, commit or retry law was found.

This is **static source evidence**, not end-to-end equivalence. Verification,
explanation, accepted inputs, JSON transport and model validation changed.
The three current study runners were ported too, so their bytes no longer
match the original prospective protocols. The existing studies must continue
to use and cite the original frozen source and manifests. A historical trace
lacks the required response `action_id` and cannot directly enter current
replay decoding without an explicit migration/adapter.

## Feasible offline check on the 503 saved factual traces

A complete post-hoc migration/re-verification check can use the existing
readback bytes without generating any new model response or consequential
write. It must be frozen and reported as a separate conformance study.

1. Pin exactly the 503 previously completed trace files and their recorded
   explanations/receipts from the original 504-slot schedule. Keep the original
   failed slot visible; do not manufacture its trace or replace failures.
2. Run the public migration API with a `MigrationReport`. Validate the new
   schema and round trip, retaining every failure and the original file hash.
3. Separately run current `verify` against each saved observation. Build a
   separate trace with those fresh receipts and run current `explain`.
4. Compare named canonical semantics to the frozen outputs; retain changed
   diagnoses and migration losses separately. Do not silently force new output
   to equal the expected old result.
5. Retain all converted traces, fresh receipts, findings, summaries and input
   hashes in a new output directory, with zero model calls and no source-file
   overwrite or rejected-input substitution.

Public API/result mapping for one selected observation/receipt (the full
audit must fresh-verify every receipt and preserve their original order):

```python
from dataclasses import replace
from consequa_x import MigrationReport, explain, migrate_trace, verify
from consequa_x.benchmark.targets import action_linked_consequence

report = MigrationReport()
migrated = migrate_trace(old_json_text, report=report)
action = migrated.single_action
fresh = verify(action, stored_observation)
current_trace = replace(migrated, verifications=(fresh,))
current = explain(current_trace).for_action(action.action_id)
canonical = {
    "state": {"satisfied": True, "violated": False}.get(fresh.status.value),
    "origin": fresh.origin.value,
    "action_linked": action_linked_consequence(action, fresh),
    "assessment_alignment": current.assessment_alignment,
}
```

The target helper is a declared research function, not a stable top-level core
API. Its action-linked mapping is unchanged: violated is false, unknown stays
unknown, and satisfied requires the qualifying positive count/provenance.
**`bool(target_effect_ids)` is not equivalent**: it collapses unavailable and
external-origin cases and ignores exact-count semantics. The 503 matched traces
use the built-in refund predicate; custom predicates need explicit current
verifier mappings rather than importing a legacy matcher unchanged.

Two distinct checks are necessary. `migrate_trace` preserves the old status,
origin and effect lists by construction, so structural migration parity alone
would not test the current verifier. Its enrichment step re-runs the configured
verifier and compares **only four fields**—`status`, `origin`, `effect_ids` and
`attributable_effect_ids`—before copying target matches/findings. It does not
require byte equality of the whole receipt despite the migration guide's
shorthand 'reproduces the receipt exactly'. Fresh verification must therefore
be checked independently of the preserved migrated receipt.

Migration loss/failure cases to expose:

- Epoch origin was never recorded in 0.1, so migrated time is `relative_ms`.
- Missing historical actions/assessments cannot be reconstructed into new
  multi-action observations.
- Unsupported predicates or absent custom verifier mappings leave target
  matches `None` and alignment unassessable; zero is not the same as unknown.
- A receipt with multiple evidence witnesses, unavailable supporting
  observation, or a nonmatching four-field current result does not gain target
  matches/findings. Its original conclusions remain unchanged.
- Unknown/malformed readback stays unknown. Strict legacy field, identity,
  timestamp or new schema validation failures stay failures.
- New explanation adds `UNASSESSABLE_ASSESSMENT` for known refund outcomes when
  alignment is unavailable, including unknown/partial reports; legacy refund
  explanation omitted that extra code. Compare diagnostic changes separately
  from canonical state/origin/linked/alignment parity.
- Only the latest recorded assessment/receipt per action determines the
  explanation summary. Preserve original ordering rather than selecting by a
  different rule or timestamp maximum.

This corpus is already exposed to development. Even complete parity would
support **post-hoc software migration and saved-evidence conformance**, not
held-out task generalization, a new LLM result, all-2.0 compatibility, or
validation of multi-action/polling/controller/async/store features. Freeze the
plan before measured corpus execution, keep mismatches and exact denominators,
and do not use evaluator truth to repair inputs. No such measured corpus run
was performed by this review.

## Recommended paper strategy

Keep the paper's protocol contribution and describe the current 2.0 data model,
with clear boundaries around its evaluation. Present all existing numerical
results as the frozen **1.1.0 reference implementation** for the newly matched
comparisons; retain earlier studies' own original versions and sources. If the
new offline conformance study is executed, add it as a separate subsection
with its own source/protocol/output hashes and exposed-data limitation.
Do not rename the original 503/504 study or native judge/tau/CAR results as 2.0
experiments. A single-action legacy corpus does not test multi-action safety
or effects spanning multiple contracts.

Suggested availability/limitations wording:

> Consequa-X 2.0.0 is publicly available under MIT with trace schema 1.0,
> multiple actions per trace, explicit time bases and verifier-owned target
> matches and findings. The matched model, local-judge, native tool-transfer
> and native-CAR studies retain their original version 1.1.0 source/protocol
> pins and schema 0.1 artifacts. They evaluate that frozen reference
> implementation; current 2.0 features are not retroactively covered by those
> results. An offline post-hoc migration/re-verification study, if completed,
> is reported separately with all failures and mismatches retained.

Use version-specific [2.0.0 PyPI](https://pypi.org/project/consequa-x/2.0.0/)
for the current artifact bibliography entry. Preserve 1.1.1 and 1.2 release
reviews as historical records. Keep platform scope at Windows plus one
emulated Alpine guest, live MCP/framework claims absent, and Actions disabled.
Immutable archival DOI, independent human checks and venue-specific author
metadata are still separate submission work.

## State of prior support-doc edits

Before the 2.0 steering arrived, the five assigned support docs had already
received the 1.2 availability updates and closed-CAR-inventory/final-audit-pending
wording. They were left unchanged after the stop instruction; root was notified.
Those five docs need current-2.0 wording now. The earlier edit left a blank line
before the added 1.2 row in `paper/source-audit.md`; remove it when updating that
table. Manuscript Markdown/TeX/bibliography remain root-owned.
