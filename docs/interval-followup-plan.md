# Separate interval follow-up

This follow-up is separate from the frozen percentile-bootstrap and normal-pair
calibration probe. The [fresh comparison](../output/interval-comparison-2026-10-13/README.md)
has completed; the original probe remains unchanged.

## Contrastive binary target

The factual bad label is a fixed observed constant. With fully known independent
Bernoulli changed outcomes, infer the changed bad probability and subtract that
constant from both interval endpoints. Compare the existing percentile bootstrap
with Wilson score and equal-tailed Clopper–Pearson intervals at confidence .95.
The point estimate and intervention definition stay fixed.

For an interior probability `q`, homogeneous samples force the empirical
bootstrap to a point at zero or one and miss `q`. Their probability is
`q^K + (1-q)^K`, giving the coverage ceiling
`1 - q^K - (1-q)^K`. At `K=16`, `q=.1` or `.9`, this is about 81.47%.
This derivation is independent of recorded simulation outcomes.

Wilson avoids this collapse but is approximate. Equal-tailed Clopper–Pearson
is conservative under the independent binomial model. Their definitions and
limits are documented by [NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)
and [statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.stats.proportion.proportion_confint.html).
Binomial coverage guarantees do not apply automatically to dependent model
continuations or incomplete evidence.

## Freeze before execution

First enumerate every binomial success count, with its exact probability, for
sample counts `8,16,32,64` and probabilities
`0,.01,.05,.1,.25,.5,.75,.9,.95,.99,1`. Report inclusive coverage, expected width,
boundary widths and probability mass checks for each interval method. The
enumeration evaluates interval mathematics without new payment replays.

Then freeze a fresh integration schedule against actual refund-world evidence.
Compare all intervals on the same branch outcomes, including protective stops,
retry pivots, idempotency, missing provenance, stale readback and exhausted
budgets. Record new seed keys that do not overlap the original probe. The
integration repetition count and call limits must be declared in that future
protocol before calls; this plan does not execute or select a later sample.

Preserve refusals for every unknown, failed or unstarted planned draw. Pin the
probability endpoints to zero at zero successes and one at all successes to
prevent numerical rounding from inventing a rescue. Keep the latest nominal
rescue rule: negative effect, strictly negative upper bound, and every factual
position estimable. Its individual intervals remain unadjusted for testing
multiple positions.

## Report and decide

Report covered/available intervals, available/planned eligible trials, and the
separate covered/planned eligible composite. Include explicit numerators,
denominators, Monte Carlo uncertainty, interval widths, homogeneous samples,
refusal reasons and exact locus counts. Never use unavailable truth as zero.

The Shapley paired-contribution law is different from a single Bernoulli mean.
Its signed dummy coefficient cannot receive an ordinary binomial interval.
Analyze its pair distribution and small-pair uncertainty in a separately
specified comparison. Independent binary endpoint differences also need their
own interval definition when both endpoint distributions vary.

Choose a revised default only after the mathematical checks and fresh
integration results are reviewed. Preserve the original interval method as an
explicit comparator. Live-model inference and held-out task claims require
additional studies beyond this synthetic interval comparison.

## Implemented comparison protocol (13 October 2026)

The `compare-intervals` command implements the finite grid above, then collects
one fresh dataset through the production refund replayers. It compares
percentile bootstrap, Wilson and Clopper–Pearson on the same contrastive draws.
The Shapley comparison retains normal intervals and adds Hoeffding bounds on
independent averaged forward/reverse pairs in `[-1,1]`. Its endpoint alternative
uses two Clopper–Pearson marginals, each assigned half the failure allowance,
and subtracts their opposing bounds. This union bound does not require
independence between endpoint blocks; each binomial marginal requires
independent binary samples. The original
[Hoeffding paper](https://doi.org/10.1080/01621459.1963.10500830)
supports the bounded-mean concentration calculation.

The fresh run declares 32 repetitions for each of the original ten cases and
two additional protective cases at `q=0` and `q=1`: 384 planned trials. Within
each trial use `K=16`, `P=16`, `S=1`, `E=16`, 2,000 finite seeded bootstrap
resamples and confidence `.95`. Each method has its own 400-call allowance
including factual capture; the budget control retains its three-call limit.
The first world/continuation key is `2_000_000`. Inference keys are reserved
beyond the complete model-phase key window. No old samples are reused, and
no new replay is run merely to compare intervals.

The protocols are written before calls, with the frozen source commit recorded
by the caller. All compact raw receipts and interval variants are retained;
full public traces and separate evaluator truth are selected at replicate zero
in advance. The repetition count validates integration and gives descriptive
Monte Carlo estimates; it cannot establish nominal coverage empirically.
Exact binomial enumeration and independent numerical checks support the
conditional mathematical claims instead.

Every eligible row reports covered/available and covered/planned, availability,
width, bias/RMSE, null flags and detection of the reference sign. A zero or
undefined reference has no sign-detection denominator. Unknown or incomplete
evidence and population-undefined retry games keep the previous refusal and
eligibility rules. Individual intervals have no multiplicity correction.

Run the comparison with the Python environment used for local tests:

```powershell
$sourceCommit = git rev-parse HEAD
consequa-x compare-intervals --replicates 32 --seed 2000000 --source-revision $sourceCommit --output output/interval-comparison-2026-10-13
```

`scripts/audit_interval_comparison.py` uses SciPy only as an independent audit
dependency, alongside the frozen standard-library raw-draw auditor. It checks
the new binomial endpoints against beta quantiles with direct upper tails and
rederives the same-draw bounds and aggregate metrics. The framework still has
no runtime dependency on SciPy. `scripts/plot_interval_comparison.py` exports a
research figure using Matplotlib in a separate plotting environment. Versions,
audit results and artifacts must be retained with the run. SciPy's
[binomial documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html)
describes its exact reference interval.
