# Native external benchmark workflow

Status: implemented research infrastructure; live development checks are still
in progress. There is no completed official autonomous score yet. This workflow
does not recruit humans or trigger GitHub Actions. It uses local inference only.
The earlier model-free state-transfer results remain separate.

The first prospective pilot is 12 externally authored airline task IDs, four
matched readback/controller conditions, one declared seed and 48 planned slots.
The corpus has been exposed to this project previously; this is not an unseen
holdout or a complete benchmark. See the
[controller design](native-controller-design-2026-10-21.md),
[analysis design](native-external-analysis-design-2026-10-21.md),
[independent protocol review](native-protocol-review-2026-10-21.md) and
[resource amendment](native-resource-amendment-2026-10-21.md).

The scientific runtime is the exact retained ConseqaX 2.1.1 wheel in a dedicated
Python 3.12 environment, alongside the pinned native tau2 source and dependency
versions. The product checkout's later release is not substituted. Native code,
task data, policy and tool schemas stay unchanged. The local provider's schema
normalization is disclosed and checked against its actual prompt rendering.

## Required order

1. Load the exact existing local model with a full 16K context per slot. Verify
   model bytes, manifest, server/runner binaries, actual q8 cache configuration,
   loopback endpoint and exact live prompt/token parity. The research server
   allocates two context-cache slots but sends one generation request at a time.
2. Run `transport-smoke` against task-independent fixtures. It must return an
   actual structured tool call and a tool-result follow-up. Progressive context
   receipts and failures survive; the shared development allowance is persistent.
3. Run `development` on excluded task 19 with `--arm native`, then excluded
   task 20 with `--arm G`. The shared native development ceiling is 64 completion
   invocations, initially at most 18 per trajectory. The initial 36-request
   allowance was amended before official collection after the local server
   stopped between sessions; the first 14 completed calls still count. All retries and pre-provider
   failures consume or remain explicitly accounted within that allowance. A
   native smoke must return native grading; reward one is not a readiness rule.
   The guarded smoke must exercise an actual package receipt.
4. Run `readiness` with `--transport-result`, `--native-episode`, and
   `--guarded-episode`. The receipt binds exact source bytes, full evidence
   inventories, installed runtime and the live runner lease. A boolean written
   by hand is insufficient.
5. Commit the tested execution source. Create a detached frozen checkout with
   the same source bytes; preserve LF line endings. Run `freeze` there, writing
   the prospective protocol and receipt into the publication checkout. Commit
   and publish that protocol before the first official generation. The protocol
   commit and execution-source commit are distinct immutable anchors.
6. Run `collect` from the frozen source, supplying the caller-pinned
   `--protocol-commit` and `--protocol`. The parent makes an exclusive claim,
   enforces hard subprocess deadlines, and preserves all 48 dispositions.
   There is no outcome-based replacement, retry, resume, or task exclusion.
   A source/runtime integrity failure stops the remaining slots explicitly.
7. Run `audit_native_external_benchmark.py` from the same frozen checkout in
   a fresh process. It verifies inventories and source identities before loading
   evaluator-only task information. With networking refused, it replays every
   actual read/write and regrades through the unchanged native evaluator.
8. Analyze the audited finite pilot and update the manuscript. Keep native task
   reward, narrow current-field predicates, unknown action origin, resource
   failures and unsupported free-form claims distinct. Report the two
   communication strata separately, including vacuous empty criteria. Do not
   turn four conditions into 48 independent tasks or assert conference readiness.

The collection CLI is
[run_native_external_benchmark.py](../scripts/run_native_external_benchmark.py).
Its `--help` lists required environment paths. The independent auditor is
[audit_native_external_benchmark.py](../scripts/audit_native_external_benchmark.py).
Scientific figure generation consumes only a passed, fully inventoried audit.

The latest 190 local tests check source, protocol, guard, supervision, arithmetic,
retention and synthetic native integration. They do not supply a live benchmark
result, external service validation or human validation. Original development
failures must remain available alongside any later successful readiness check.
