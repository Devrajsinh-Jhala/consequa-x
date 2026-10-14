# Changes

## 0.1.0a2 — 13 October 2026

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
