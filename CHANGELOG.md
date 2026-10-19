# Changes

## Unreleased (2.0.0, breaking)

Built on the `release-2.0` branch; see [the 2.0 design](docs/design-2.0.md).

- Typed exceptions: every intentional error derives from `ConsequaError` and
  still from `ValueError` or `TypeError`. `ValidationError` (invalid records,
  traces and settings; malformed JSON is now one too), `SchemaVersionError`,
  `ConsequaTypeError`, `ContractError` (a verifier cannot evaluate the
  contract), `ReceiptError` (a verifier or matcher result crosses its identity
  boundary, or recorded evidence cannot support the interpretation) and
  `RecorderError`. `InsufficientEvidenceError` and `PolicyError` join the
  hierarchy.
- Captured payloads are deeply read-only. Event data, arguments, contract
  expectations, results, readback records, scopes and evidence details are
  `FrozenDict` and `FrozenList` values: they compare equal to and serialize
  like ordinary dicts and lists, but any change raises `ConsequaTypeError`.
  `copy.deepcopy` returns the same read-only value; `thaw()` returns an
  editable copy, and `to_dict()` still exports ordinary dicts and lists.
- Trace schema `1.0`. A trace holds one or more `actions`, each with its own
  contract; `responses`, `assessments` (zero or more per action) and
  `verifications` each name their `action_id`. A required `time_base`
  (`unix_ms` or `relative_ms`) says what the integer millisecond times count
  from. `trace_id` is no longer repeated on actions and events. All records
  are keyword-only. Schema `0.1` input is refused with a `SchemaVersionError`
  that names the migration route; the packaged schema is `trace-v1.0.json`.
  New helpers: `Trace.get_action`, `single_action`, `responses_for`,
  `assessments_for`, `verifications_for`, `latest_assessment`,
  `latest_verification`.
- `TraceRecorder.register` can be called for several actions and returns an
  `ActionCapture` whose `attempt`, `call`, `dispatch`, `response`,
  `assessment` and `verify` record for that action. The recorder-level methods
  still work while exactly one action is registered. Assessments are optional
  and may be repeated. The default clock is wall-clock `unix_ms`; a custom
  clock records `relative_ms` unless told otherwise. `capture_tool` and
  `call_mcp_tool` accept an `ActionCapture`.
- `explain()` returns a `TraceExplanation` with one `ActionExplanation` per
  action (`for_action`, `single_action`). An action without verification is
  reported as `NO_VERIFICATION` instead of raising. The evidence graph has a
  contract node per action, and offline reports show every action, with an
  Action column for responses and verifications and the time base in the
  footer.
- Verifiers own domain interpretation. `VerificationResult` gains
  `target_effect_ids` (`None` when the verifier did no target matching,
  otherwise this action's effects that match the full target) and `findings`
  (`Finding(code, effect_ids, detail)`). `RefundVerifier` records refund
  matches and the `EXCESS_EFFECTS`, `DUPLICATE_EFFECT`, `PARAMETER_MISMATCH`,
  `PARTIAL_EFFECT` and `REVERSED_EFFECT` findings; `RecordVerifier` records
  record matches and `EXCESS_EFFECTS`, `DUPLICATE_EFFECT`,
  `PARAMETER_MISMATCH` and `REMOVED_EFFECT`. `TargetMatcher`,
  `RecordTargetMatcher`, `RecordVerifier.target_matcher()` and
  `explain(..., target_matcher=...)` are removed; a custom verifier sets
  `target_effect_ids` instead.
- `explain()` is domain-independent: it reads receipts, responses and
  assessments and never reinterprets evidence details. Diagnoses are
  structured `Diagnosis(code, evidence, message)` records; `codes` gives the
  codes and `diagnosis` a display label. `UNASSESSABLE_ASSESSMENT` now applies
  to every predicate whenever the outcome is known but alignment cannot be
  judged (1.x omitted it for refunds). `CORE_DIAGNOSES` lists the codes
  `explain()` produces.
- Offline reports show each action's assessment alignment and diagnosis
  codes, computed from the recorded receipts. Codes from custom verifiers are
  counted rather than printed.
- Migration: `migrate_trace()` and `consequa-x migrate OLD --output NEW`
  convert schema `0.1` traces. Target matches and findings are added only when
  the 2.0 verifier (the refund verifier by default; pass others with
  `verifiers=`) reproduces the recorded receipt exactly; no recorded conclusion
  is changed. `consequa-x validate` checks trace files. Migrated traces of the
  1.x demo reproduce their 1.x explanations; fixtures written by the released
  1.2.0 package are in `tests/fixtures/v0.1`.
- `summarize(traces)` and `consequa-x summarize PATH... [--format text|markdown|json]`
  count verified state, origin, alignment, tool responses and diagnoses over
  every action, with stated denominators; `unknown` and `unverified` stay
  separate from failures, and actions with divergences or violations are
  listed. Folders (non-trace JSON is skipped and counted) and `.jsonl` stores
  are accepted; invalid inputs are listed by path and error type only and make
  the command exit 2.
- `TraceStore(path)`: an append-only JSON Lines file of validated traces with
  unique trace IDs; reading reports the line number of an invalid entry.
- Research interfaces (`EffectEstimate`, `Intervention`, `leave_one_out`,
  `recency_attribution`, the policy types) are imported from
  `consequa_x.research` instead of the top-level namespace.
- Research code (benchmark, replay, policies, studies and their audit
  scripts) produces and reads schema `1.0` traces. Retained 1.x study outputs
  under `output/` are unchanged.

## 1.2.0 - 19 October 2026

Additive only: the 1.x API and trace schema `0.1` are unchanged.

- Added `TraceRecorder` (`consequa_x.capture`), which records one action as it
  happens (context, decision, registration with its outcome contract,
  dispatches, tool responses, the agent's assessment, readbacks and
  verification) and returns an ordinary validated `Trace`. Events are linked
  as in the package fixtures, so graphs, reports and `explain()` work unchanged.
- Added tool-call capture: `TraceRecorder.attempt()` (context manager),
  `TraceRecorder.call()` and the `capture_tool` decorator record the dispatch
  and the response (success, `timeout` for `TimeoutError`, or `error`) around
  a synchronous tool, keep JSON results, keep only exception type names, and
  re-raise. A recorded timeout says nothing about whether the effect happened.
- Added `RecordVerifier` and `RecordTargetMatcher` for a generic `record_present`
  predicate: records with given field values, an exact or minimum count,
  a commit deadline and a persistence window, with configurable field names.
  Unavailable, out-of-scope, incomplete, stale or malformed readback stays
  `unknown`, and origin stays a separate conclusion, as for refunds.
- Added `examples/agent_loop_sqlite.py`: a stdlib-only, offline tool-calling
  loop that writes to a real SQLite database, is captured with `TraceRecorder`,
  and is verified through a separate read-only connection with `RecordVerifier`.
  Modes: `timeout_after_commit`, `other_actor` and `stale_readback`.
  It is also in the website's quickstart download.
- README section on capturing a real agent's tool call.
- Added `TraceRecorder.now()`, the recorder clock for readback times.
- Added `consequa_x.mcp_capture.call_mcp_tool`, which records an awaited MCP
  tool call from any session exposing `call_tool(name, arguments)` without an
  MCP dependency. Tool content is not copied into the trace.
- Added a framework integration guide (`docs/framework-integration.md`).
- The website's workflow cards, documentation and quickstart show the capture
  API. `scripts/check_installed_release.py` now also exercises the recorder,
  tool capture and record verifier from the installed wheel.
- Published to PyPI with registry hashes verified; see the
  [release record](output/release-1.2.0-2026-10-19/README.md). Installed checks
  passed on Windows Python 3.11.9 and 3.12.10, on one Alpine Linux 3.24.2 QEMU
  guest with Python 3.14.8 and from a fresh PyPI install. macOS has never been
  tested.

## 1.1.1 - 18 October 2026

- Documentation and metadata release. Runtime code and schema `0.1` are
  identical to 1.1.0 apart from the version number.
- Rewrote the package description for PyPI with absolute links that work outside
  the repository. Project URLs now point to the public source repository and to
  <https://consequa-x.onrender.com>.
- The source repository is public. Its issue forms and security policy replace
  the separate community repository, whose quickstart and release notes moved to
  `docs/quickstart.md` and `docs/release-notes.md`.
- The website inspector and live demo replay recorded output from real package
  runs, generated by `scripts/build_site_demo.py` and pinned by
  `tests/test_site_demo.py`. The site deploys from this repository.
- The snapshot-integrity test now verifies every committed manifest format and
  ignores uncommitted study outputs.
- Published to PyPI with registry hashes verified; see the
  [release record](output/release-1.1.1-2026-10-18/README.md). Installed checks
  passed on Windows Python 3.11.9 and 3.12.10 and from a fresh PyPI install.
  Linux and macOS were not rerun for 1.1.1; macOS has never been tested.

## 1.1.0 - 17 October 2026

- Added `render_report(trace, include_details=False)` and
  `consequa-x report trace.json --output report.html`, with a self-contained
  chronology, contract, responses, assessment, readback, verification/origin and
  SVG evidence graph plus complete accessible graph tables.
- Default reports omit arbitrary captured values throughout the file. Explicit
  details mode includes the full trace as escaped inert JSON. No report executes
  actions, verifiers, target matchers or replay; alignment remains unassessable
  in the report. The original trace remains separate evidence.
- Preserved source and existing output files with exclusive creation. Invalid
  schema data is refused before an output directory is created, with captured
  values omitted from report-command decoding errors.
- Added a synthetic artifact-delivery visual quickstart and public documentation,
  support and security routes, while retaining the private research repository.
- Added installed-package release checks and browser/report security gates.
  Release receipts bind the final artifact, actual platform checks and
  publication state; public release notes report the tested environments.
- Preserved the dependency-free version-1 core and portable wire schema `0.1`.
  GitHub Actions stays disabled.

## Post-release research update - 16 October 2026

The predeclared physical-interaction study finished collection on 15 October
2026 at frozen runtime source `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`.
It retained all 2,048 trials and 655,360 planned branch slots, with 628,535 actual
scripted policy calls, no model calls and no additional comparison calls.
The [protocol](output/interaction-sampling-2026-10-15/protocol.json),
[complete summary](output/interaction-sampling-2026-10-15/summary.json) and
[execution receipt](output/interaction-sampling-2026-10-15-execution.json) retain
the collection identity separately from the public stable release. The
[independent audit](output/interaction-sampling-audits-2026-10-15/independent.json)
passed 44,698,925 assertions, covering every planned trial/branch and 4,210
preselected complete traces. The
[derived findings](output/interaction-sampling-findings-2026-10-15/FINDINGS.md)
retain coverage, width, detection and refusal denominators. The defined
framework and protocol/software paper scope is complete on 16 October 2026:
the [illustrated eight-page IEEE PDF](output/pdf/Consequa-X_IEEE_Paper.pdf) compiled and all
rendered pages passed visual review. The [QA receipt](output/pdf/qa.json) binds
it to the frozen [editable source](paper/consequa-x-ieee.tex) and four vector
figures. Actual venue selection, final human
review, reviewer access and submission remain maintainer steps. These results
do not establish held-out model performance, a new estimator or baseline
superiority.

## 1.0.0 - 15 October 2026

Runtime source is frozen at `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`.
The [stable release is public on PyPI](https://pypi.org/project/consequa-x/1.0.0/),
built from `85ce6c316838c995782aadc8c10770acc708339b` with all 36 runtime files
matching that freeze. Both downloads were independently hash/size checked;
[publication](output/release-1.0.0-2026-10-15/publication.json) and
[fresh registry-install](output/release-1.0.0-2026-10-15/registry-install.json)
receipts record the achieved release. PR #8 merged as `708d064`; GitHub remains
private. Published artifacts retain their original reviewed bytes and dated
build-time documentation.

- Defined the version 1 stable evidence-core API while retaining wire schema
  `0.1`. Benchmark procedures, exact policy prompts and study commands remain
  explicitly scoped research interfaces.
- Added explicit application verifiers to `verify(..., verifier=...)`, with
  receipt checks for contract, observation identity, source, watermark and
  capture time. Adapter semantics and source authentication remain application
  responsibilities.
- Added `TargetMatcher` and `explain(..., target_matcher=...)`. Non-refund
  predicates remain domain-neutral and unassessable without declared target
  semantics; unknown receipts never execute the matcher. Invalid adapter methods
  and inputs have controlled type errors, and invalid target returns or known
  refund details have controlled value errors.
- Exported `Evidence`, `ToolResponse`, `ResponseStatus` and `TargetMatcher` from
  the package root. Added the standalone artifact-delivery application example
  and source-archive integration documentation.
- Preserved successive and duplicate effect records as separate graph witnesses,
  with identity edges and observation-specific verification/origin links.
  Conflicting later payloads or provenance cannot overwrite an earlier witness.
  Source-owned reserved fields remain available verbatim; attribution candidates
  must identify captured events.
- Made demonstration, fixture-experiment and explanation output paths preserve
  existing evidence. Run directories must be new or empty; explanation output
  must be a new file distinct from the input trace.
- Added `calibrate-interactions`, reproducible repeated physical refund sampling,
  same-draw uncertainty comparisons, bounded parallel execution, complete
  refusal/cost records and an independently implemented audit. The retained
  2,048-trial collection completed after the distribution-build checkpoint;
  its later research status is recorded above without changing released bytes.

The full frozen-source suite passed 1,480 tests and 240 subtests. Twenty
additional stable-publisher tests passed; final installed-wheel Windows Python
3.11.9 conformance passed 200 tests and 165 subtests. Independent Windows Python
3.12.14 wheel, source-archive and registry installations each passed 12 trace
round-trips and four artifact-adapter checks. All eight local release gates,
public artifact hash/size verification and the fresh registry installation are
complete. No GitHub Actions were used. These software checks do not establish
held-out model performance or attribution superiority.

## 0.1.0a2 — 14 October 2026

- Default decision-contrastive uncertainty now uses exact binomial intervals.
  Signed Shapley pair means use Hoeffding bounds; independent endpoint
  differences use two exact binomial marginals with a split failure allowance.
  Original bootstrap/normal modes remain explicit comparators.
- Added `compare-intervals`, with a pre-call protocol, complete same-draw
  retention, exact finite distribution calculations, width/power metrics and
  independent numerical/artifact audits. Original calibration data is preserved.
- Added an explicit on-reach positional game for normally terminated later
  decisions. The strict game remains the default, and incompatible operations,
  unknown evidence, provider failures and budget refusals remain explicit.
- Added `refund-interactions` to enumerate physical selection/retry interactions,
  idempotency and evidence/budget controls through actual payment readback.
- Interval rescoring now reconstructs Shapley pair vectors from replay evidence
  and validates stored coverage, points and endpoint diagnostics.
- Cached static record annotations while retaining validation of every value;
  added a working paper, reproducible evidence links and release preparation.

This is an engineering alpha. Sampling assumptions, individual-interval scope
and intervention games remain explicit. Synthetic validation does not establish
live-model calibration, cross-task generalization or attribution superiority.
GitHub Actions remains disabled; checks and builds run locally.

## 0.1.0a1

Initial Python alpha with portable evidence records, independent refund
verification, evidence graphs, local policy adapters and bounded replay
experiments. No registry publication is implied by the source version.
