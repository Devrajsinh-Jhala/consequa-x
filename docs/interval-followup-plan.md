# Separate interval follow-up

This is a proposed next study, separate from the frozen percentile-bootstrap
and normal-pair calibration probe. It changes no retained estimate or interval.

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
