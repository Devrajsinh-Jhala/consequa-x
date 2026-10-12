# Synthetic attribution calibration probe

This experiment repeats the production contrastive and positional Shapley
estimators against analytic refund mechanisms. It measures estimation error,
interval coverage, false nonzero flags, locus recovery, availability and actual
policy calls. It runs entirely offline. It is a conditional simulation probe,
not evidence of language-model accuracy or task generalization.

The design follows the separation of mechanisms, estimands, methods and
performance measures in [Morris, White and Crowther (2019)](https://doi.org/10.1002/sim.8086).
All repetitions and seed ranges are declared before execution. No failed or
unknown draw is replaced, and no trial is selected for a favorable outcome.

```sh
consequa-x calibrate-attribution --replicates 32 --output output/my-calibration
```

For an integration smoke check, explicitly reduce the settings:

```sh
consequa-x calibrate-attribution --replicates 2 --samples 2 --pairs 2 --endpoint-samples 2 --bootstrap-samples 20 --output output/my-calibration-smoke
```

The Python API separates planning, execution and scoring:

```python
from consequa_x.benchmark.calibration import (
    CalibrationPlan, calibration_protocol, run_calibration,
)

plan = CalibrationPlan(repeats=32)
protocol = calibration_protocol(plan)  # save this before execution
result = run_calibration(plan)
summary = result.summary()
```

`--mechanisms` selects comma-separated registered cases, including
`budget-stop-q50`. `--max-calls` is a separate shared limit for each method;
the budget control always uses its declared cap of three. An intentional
control refusal is a study result and the calibration command returns success
when its planned execution and exports complete. An export failure or invalid
plan returns an error. Existing nonempty output directories are rejected.
`--source-revision` records a caller-supplied source identifier in the protocol;
the exporter does not inspect Git or certify that identifier.

## Mechanisms and independent truth

The first refund commits but returns a timeout. A second refund is permitted.
The synthetic policy always selects the refund, retries an ambiguous timeout
with declared probability `q`, and stops after the second response. An exact,
reserved factual timeout phase key forces the predeclared factual stop or
retry. This intervention is visible in stable policy metadata. Continuation
keys are disjoint from that reserved key. The policy receives ordinary public
requests, not fault labels, independent readback or evaluator truth.

The outcome labels come from the ordinary payment world and verification
adapter. The numerical reference is specified separately from episodes and
does not use the estimator's replay sample.

| Stratum | Factual decisions | Consequence reference |
| --- | --- | --- |
| Protective stop, `q=.1,.5,.9` | select, stop | Contrastive `[q,q]`; Shapley `[0,-q]`; endpoint gap `-q`. |
| Retry pivot, `q=.1,.5,.9` | select, retry, stop | Contrastive `[q-1,q-1,0]`; latest population rescue `1`; endpoint gap `1-q`. |
| Idempotent stop, `q=.5` | select, stop | All effects and contributions zero. |
| Missing provenance, `q=.5` | select, stop | State reference unchanged; linked reference unavailable. |
| Lagged readback, `q=.5` | select, stop | State and linked reference unavailable; action remains known. |
| Budget control, `q=.5` | select, stop | Protective-stop reference, but only three calls per method including capture. |

Initial action selection succeeds in every completed valid branch, so action
effects and contributions are zero. State and linked targets share outcome
draws when provenance is present; they are reported separately and never
pooled as independent observations.

The retry factual has three positions. A coalition holding the terminal stop
while resampling the preceding timeout may stop before that held position.
Such a branch is invalid. The population positional game is incomplete for
`q<1`, so it has no numerical Shapley reference. A finite run can happen to
avoid invalid draws and produce estimates; this does not create a population
truth. Those estimates remain available but ineligible for error or coverage
scoring. Independent empty/full endpoints still have known references.

For `P` permutation/reverse pairs and `S` fresh draws per coalition occurrence,
the retry game's idealized probability of complete path availability is
`[(2/3)q^S + (1/3)q^(2S)]^P`. Conditional on the declared permutations it is
`q^(S * sum(abs(rank(1)-rank(2))))`. These probabilities concern invalid held
positions, independently of whether the selected target is known.

## Budgets, retention and scoring

Each method makes its own factual capture under its own shared call limit.
The paired captures use the same declared world and factual policy keys.
Fresh continuation keys differ across methods and repetitions. Actual capture
and continuation calls both count. The budget-control cap of three allows
two factual calls and only the first fresh selection; its next required call
fails and the remaining planned branches stay unstarted.

The CLI saves the protocol before any policy call, compact receipts for every
planned branch, all estimator outputs, and separate analytic reference labels.
Representative full traces and decisions are chosen by replicate number in
advance. Compact records retain branch statuses, outcome labels, seeds, call
counts and failure details; full traces are not retained for every repetition.
The hash manifest checks bytes, not authenticity.

For each mechanism, method, target and position, report the planned repetitions,
available estimates, refusals, reference eligibility, and scored denominator.
Bias and RMSE use available estimates with a defined reference. Coverage is
inclusive containment of that reference among available eligible intervals.
`covered / planned eligible trials` is a separate availability-and-coverage
composite. Refused estimates never count as successful coverage.

Zero-width intervals and false nonzero flags on zero-reference positions are
reported explicitly. A false nonzero flag means an interval excludes zero in
either direction. Contrastive locus recovery scores the exact latest
population-negative position, separately from availability; a nominal rescue
rule does not establish unique causation.

Proportion uncertainty uses 95% Wilson intervals following the
[NIST formula](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
A zero denominator produces unavailable metrics. Bias Monte Carlo standard
error uses the sample variance of errors divided by the scored count. Refusal
reasons keep unknown evidence, invalid replay, execution failure and unstarted
budget slots separate. Endpoint diagnostics retain their own availability and
reference eligibility; contributions are never adjusted to match an endpoint.

## Interpretation

The defaults use 16 contrastive draws per position, 16 Shapley pairs, one draw
per coalition evaluation, 16 endpoint draws, 2,000 bootstrap resamples and
nominal 95% intervals. The default 32 repetitions are exploratory; a larger
retained probe must declare its count before running. Wilson intervals that
overlap .95 do not prove calibrated coverage. Requested deterministic seeds
also do not prove independent sampling.

For the valid protective game, the independent Bernoulli idealization gives
coefficient variance `q(1-q)/(2SP)`, coefficient covariance
`-q(1-q)/(4SP)`, and endpoint-gap variance `q(1-q)/E`. The sum-minus-endpoint
discrepancy has mean zero and variance `q(1-q)[1/(2SP)+1/E]`. These are sampling
reference formulas, not identities that finite recorded runs must satisfy.

This probe can reveal weaknesses of the current intervals. It does not modify
them after inspecting results. Interval redesign, interaction mechanisms,
matched local-model comparisons and held-out task studies remain subsequent
research work.

The [retained 128-repetition run](../output/calibration-probe-2026-10-11/FINDINGS.md)
and [independent finite calculation](../output/calibration-theory-2026-10-11/README.md)
are available. Their undercoverage findings motivate the
[separately planned interval comparison](interval-followup-plan.md).
