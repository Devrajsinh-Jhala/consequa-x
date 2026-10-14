# Same-draw interval comparison

384 predeclared synthetic trials, 32 repetitions per case. No language model was called. All variants reuse the same real refund-world evidence; interval comparisons spent zero additional policy calls.

## Consequence coverage at the timeout position

| Mechanism | Bootstrap | Wilson | Exact binomial | Normal Shapley | Hoeffding Shapley |
| --- | --- | --- | --- | --- | --- |
| protective-stop-q10 | 26/32 | 29/32 | 31/32 | 23/32 | 32/32 |
| protective-stop-q50 | 31/32 | 28/32 | 32/32 | 32/32 | 32/32 |
| protective-stop-q90 | 31/32 | 29/32 | 32/32 | 29/32 | 32/32 |
| retry-pivot-q10 | 28/32 | 31/32 | 32/32 | unavailable | unavailable |
| retry-pivot-q50 | 30/32 | 28/32 | 30/32 | unavailable | unavailable |
| retry-pivot-q90 | 29/32 | 30/32 | 32/32 | unavailable | unavailable |
| idempotent-stop-q50 | 32/32 | 32/32 | 32/32 | 32/32 | 32/32 |
| unknown-provenance-stop-q50 | 32/32 | 30/32 | 32/32 | 30/32 | 32/32 |
| lagged-readback-stop-q50 | unavailable | unavailable | unavailable | unavailable | unavailable |
| budget-stop-q50 | unavailable | unavailable | unavailable | unavailable | unavailable |
| protective-stop-q0 | 32/32 | 32/32 | 32/32 | 32/32 | 32/32 |
| protective-stop-q100 | 32/32 | 32/32 | 32/32 | 32/32 | 32/32 |

Coverage denominators include available eligible intervals only. Availability and covered/planned eligible composites remain separate in `summary.json`. The state and linked targets share evidence and are not pooled as independent observations.

## Finite distribution calculation

The predeclared grid uses n=8,16,32,64 and eleven probabilities including zero and one. Minimum coverage over that grid: percentile_bootstrap_limit 7.72%, wilson 85.15%, clopper_pearson 96.68%. The bootstrap entry is its infinite-resample limit; actual seeded bootstrap intervals are separately measured above. Exact probability weights do not make a finite observed coverage proportion a population guarantee.

## Width, refusals and interpretation

Exact binomial and Hoeffding options retain uncertainty at homogeneous samples and can be much wider than bootstrap/normal intervals. Every row retains mean interval width, point bias/RMSE, zero-width frequency and explicit refusal counts. No point, draw, locus rule or budget was changed. Different interval bounds can change nominal locus selections; all such selections are retained.

The strict three-position retry game can be population-undefined. Available vectors there remain ineligible for numerical scoring. Unknown readback/provenance and budget failures remain refusals under every method. Conservative bounds do not repair undefined interventions or missing evidence.

Binomial bounds require independent known binary draws; Hoeffding requires independent bounded pair observations from a defined game. Requested seeds do not establish these assumptions for live models. Intervals remain individual, with no multiplicity correction across decisions or targets.

Raw public traces and explanations for replicate 0 are under `raw/evidence/`; simulator gold is separate. All planned raw draws and numerical variants are compressed JSONL. Both protocols were saved before policy calls. Byte manifests detect changes, not authenticity.
