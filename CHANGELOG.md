# Changes

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
the [six-page IEEE PDF](output/pdf/Consequa-X_IEEE_Paper.pdf) compiled and all
rendered pages passed visual review. The [QA receipt](output/pdf/qa.json) binds
it to [editable source](paper/consequa-x-ieee.tex) at manuscript revision
`01d0709ad98acf27c4e12c0899208c28417d46a9`. Actual venue selection, final human
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
