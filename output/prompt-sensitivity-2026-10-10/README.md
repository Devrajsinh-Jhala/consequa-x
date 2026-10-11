# Exploratory prompt comparison, 10 October 2026

Twelve one-attempt runs and a separate two-episode retry diagnostic completed
with 28 local model calls and no provider or protocol failures. The original
prompt made definite final assessment-field claims in all six controlled
conditions. The opt-in prompt returned unknown in all six, but its explanations
still sometimes asserted successful processing. This does **not** establish an
accuracy improvement or calibrated uncertainty.

## Implementation and provenance

The evaluated source is commit
`f7a38f3a6648ccce4d381ca8f004e5909b454656`, installed from a fresh wheel. The
original `refund-policy-v1` prompt remains byte-for-byte unchanged and is still
the default. Opt-in `refund-policy-v2` clarifies visible history, timing,
remaining attempts, and assessment semantics, and adds stop-after-success
guidance. It is a policy refinement informed by the
[earlier pilot](../live-pilot-2026-10-10/README.md), not a repair to request encoding.
Neither profile receives hidden fault labels, evaluator truth, or independent
readback before its final assessment.

The source increment adds explicit assessment coverage/abstention denominators
to evaluation and replay, records selected prompt versions and hashes, and
extends evaluation manifests to cover every exported file except the manifest
itself. Local validation
passed **542 tests and 240 subtests**, lint, package build, and fresh-wheel
scripted/mocked checks. See [package-validation.json](package-validation.json).
The installed alpha remains `0.1.0a1`; these artifacts are not a registry release.
After reviewing these runs, report wording was clarified to distinguish status
metrics from rationale assertions; captured exports remain as generated.

| Profile | System-prompt SHA-256 |
| --- | --- |
| `refund-policy-v1` | `c5e9c07829c569b7382d0187e278c533d450e30c39038e49367f66ceb2468a74` |
| `refund-policy-v2` | `141ab9ae275703cdbe23bd55376f40ce0069bb67a172d8af65ee852d577be6ed` |

The wheel SHA-256 is
`f7a6575ef3a7d2dd2d34fd2642b1168c6c1419a26e49028b6bf8cac9710caf48`.

## Controlled one-attempt comparison

[protocol.json](protocol.json) was recorded before generation. Each of six
conditions ran once per profile with the same trial seed 0, phase seeds 0/1,
temperature 0, one attempt, a 512-token output ceiling, and two calls per run.
The fixed order was v1 then v2. No failed samples were replaced or redrawn.
One attempt intentionally suppresses retry differences. This is one task
template with hidden execution variations, not six independent tasks.

| Condition | Independently verified contract / origin | v1 final status / hindsight alignment | v2 final status |
| --- | --- | --- | --- |
| Clean | Satisfied / confirmed | Success / consistent | Unknown |
| Timeout before commit | Violated / unknown | Failure / consistent | Unknown |
| Timeout after commit | Satisfied / confirmed | Failure / contradicted | Unknown |
| False success | Violated / unknown | Success / contradicted | Unknown |
| Partial effect | Violated / confirmed | Success / contradicted | Unknown |
| Missing provenance | Satisfied / unknown | Success / unassessable | Unknown |

All 12 runs chose `refund` followed by `stop`. The verified outcomes were the
same across profiles. The initial public request was identical across all six
conditions; the timeout pair had identical after-response requests, and the
four successful-acknowledgement conditions had identical after-response
requests. Full decisions were identical within each profile/input group.
Consequently, hindsight-consistent claims do not demonstrate detection of a
hidden fault. For example, the same failure claim accompanied both timeouts
despite their different effects.

| Final structured-status metric | v1 | v2 |
| --- | --- | --- |
| Completed assessments | 6 | 6 |
| Success / failure / unknown / partial | 4 / 2 / 0 / 0 | 0 / 0 / 6 / 0 |
| Definite claim coverage | 6/6 (100%) | 0/6 (0%) |
| Assessable definite claim coverage | 5/6 | 0/6 |
| Contradictions among assessable claims | 3/5 (60%) | 0/0 (undefined; JSON null) |

These counts concern the **structured status field only**. In all four v2
successful-acknowledgement conditions, the rationale said the refund was
successfully processed, including when readback showed no refund or a partial
effect. The timeout rationale also said to stop without executing a refund
despite an earlier attempt. These unresolved wording issues prevent interpreting
zero definite status-field coverage as absence of unsupported natural-language
assertions. Blanket abstention leaves the conditional contradiction rate
undefined; it is not a zero-percent error rate.

Full receipts, operations, and rationales are in
[comparison.json](comparison.json). Exact command arguments, timestamps, exit
codes, and per-run timing are in [execution.json](execution.json). Each case
directory retains the trace, explanation, evaluator truth, schema, results,
generated report, and its byte-hash manifest.

## Separate two-attempt diagnostic

[two-attempt-diagnostic-protocol.json](two-attempt-diagnostic-protocol.json) was
declared before its generation, after the one-attempt baseline had started.
It retained the original pilot's two-attempt budget, used clean seed 0 and
timeout-after-commit seed 1, and allowed at most six calls. This diagnostic is
excluded from the six-per-profile comparison denominators above.

Both episodes chose `refund` then `stop`, with one attempt remaining after the
response. Both contracts were satisfied with confirmed origin; both final
assessment fields were unknown. No redundant retry occurred in the clean run.
Its rationale nevertheless asserted successful processing before saying that
verification was unavailable. The timeout rationale said the effect could not
be confirmed and stopped to avoid potential duplicates.

The initial and first after-response public requests matched those in the
historical v1 pilot. That comparison is descriptive: v2 was developed after
seeing the pilot and run later without randomization or an independent holdout.
The diagnostic used four calls, with 0/2 definite status-field coverage and an
undefined 0/0 contradiction rate. See
[results](v2-two-attempts/results.json) and
[diagnostic-execution.json](diagnostic-execution.json).

## Runtime, cost, and audit

All inference used local Ollama **0.40.2** with
`qwen3:4b-instruct-2507-q4_K_M`, Q4_K_M quantization, model digest
`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
The runtime reported CPU execution (zero VRAM allocation) and a loaded context
length of 4,096. [Hardware](hardware.json) records an Intel i5-8365U with
15.78 GiB RAM; [runtime-before](runtime-before.json) and
[runtime-after](runtime-after.json) bracket the controlled sequence.

| Sequence | Calls | Input tokens | Output tokens |
| --- | --- | --- | --- |
| Controlled v1 | 12 | 4,444 | 930 |
| Controlled v2 | 12 | 7,444 | 844 |
| Separate diagnostic | 4 | 2,469 | 324 |
| Combined accounting only | 28 | 14,357 | 2,098 |

All calls supplied token/timing metadata and finished with `done_reason=stop`.
The combined ceiling was 30 calls. No paid API was used; electricity and compute
cost were not measured. Provider duration does not advance simulation time or
measure real payment deadline compliance. Payments are synthetic and isolated.

Independent review verified all **14 traces, 81 nested manifest entries, 28
saved call records**, schemas, strict round trips, verifier/explainer results,
model/profile/request hashes, seeds, and metric denominators. Machine-readable
receipts are [audit.json](audit.json) and
[diagnostic-audit.json](diagnostic-audit.json); detailed interpretation is in
[audit-findings.md](audit-findings.md). The root [manifest](manifest.json) hashes
all files in this evidence folder except itself.

## Research implications

The follow-up establishes an auditable local integration and exposes the gap
between reported status, rationale assertions, acknowledgements, and verified
effects. It does not demonstrate a new attribution estimator, improved prompt
accuracy, stochastic reliability, or generalization. A paper still requires
matched strong baselines, held-out task templates and fault compositions,
additional models, and a separately frozen study. The
[study plan](../../docs/study-plan.md) specifies those remaining steps.
