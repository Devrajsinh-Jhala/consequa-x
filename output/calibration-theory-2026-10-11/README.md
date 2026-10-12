# Finite interval analysis for the two-player refund game

This independent calculation enumerates every possible count combination for
the current binary positional Shapley normal interval and independent endpoint
interval. It uses exact rational probability weights and moments; normal
quantiles and interval boundary classification use floating-point arithmetic.
No model, payment replay, production scorer or random draws are used.

The reference implementation is source
`9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0`. The factual timeout stop is planted;
fresh continuation retries are ideal independent Bernoulli draws with
probability q. Readback and provenance are complete. All two-player coalitions
are valid. There are 16 permutation/reverse pairs, one fresh draw per coalition
occurrence, 16 samples per endpoint and nominal 95% normal intervals, with
sample variance using 15 degrees of freedom.

| q | Protective stop coefficient coverage | Zero-value selection false nonzero flag | Independent endpoint coverage | Contrastive bootstrap coverage upper bound |
| --- | --- | --- | --- | --- |
| .1 | 83.7775% | 3.0759% | 81.1401% | 81.4698% |
| .5 | 92.6377% | 7.3623% | 92.3187% | 99.9969% |
| .9 | 83.7775% | 3.0759% | 81.1401% | 81.4698% |

Coverage in the first and third columns is a finite-distribution calculation,
not a Monte Carlo proportion. The last column is only an upper bound: all-zero
or all-one Bernoulli samples force an incorrect constant empirical-bootstrap
interval for interior q. Its probability is `q^16 + (1-q)^16`. Other samples
can miss as well. A finite observed coverage proportion can exceed that
population bound through sampling variation.

For three fresh independent Bernoulli coins A, B and C, one averaged
forward/reverse pair has selection contribution `(B-A)/2` and stop contribution
`-(B+C)/2`. Their supports are `[-.5,0,.5]` and `[-1,-.5,0]`. The enumerator
checks all 153 multinomial count cells for each marginal and all 17 binomial
endpoint counts. Every probability mass is exactly one; means, variances,
expected sample variances and cross-coefficient covariance agree with
independent analytic moment identities.

The known action-selection control has deterministic zero effects and
contributions, interval `[0,0]`, coverage one and no false nonzero flag. This
control does not validate uncertainty for stochastic consequences.

Reproduce the calculation with the standard library:

```sh
python output/calibration-theory-2026-10-11/enumeration.py --output output/my-finite-interval-results.json
```

`results.json` retains the rational weights, moment checks, boundary-distance
checks and settings. `manifest.json` identifies the retained bytes. The result
concerns this declared Consequa-X adaptation under its stated independent
Bernoulli assumptions. It is not a numerical reproduction of upstream CAR,
evidence of seed independence, model accuracy, domain interaction recovery or
publication readiness. Unknown evidence, invalid three-position games and
budget failures lie outside this enumeration.

The [repeated simulation probe](../calibration-probe-2026-10-11/FINDINGS.md)
checks actual replay integration separately. A revised interval method should
be assessed using the [separate follow-up plan](../../docs/interval-followup-plan.md).
