# Changes

## 1.0.0 - 15 October 2026

Runtime source is frozen at `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`.
Release-specific artifact and publication checks are recorded in release receipts.

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
  2,048-trial run is in progress and its audit is pending as of 15 October 2026.

The full frozen-source suite passed 1,480 tests and 240 subtests. Twenty
additional stable-publisher tests passed; Windows Python 3.11 source conformance
passed 200 tests and 165 subtests. Final wheel/sdist and installed-artifact
results must be recorded separately. No GitHub Actions were used. These software
checks do not establish held-out model performance or attribution superiority.

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
