# Retained synthetic attribution calibration findings

The production replay paths recovered the declared mechanism means while retaining missing and invalid evidence. The main limitation is uncertainty: several nominal 95% intervals cover the known effect far less often. This is an exploratory conditional simulation result; the current defaults do not support a calibrated coverage claim.

The frozen source is `9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0`. An isolated installed wheel ran all ten predeclared cases with 128 repetitions each, 16 contrastive draws per position, 16 Shapley pairs, one draw per coalition occurrence, 16 endpoint draws, 2,000 bootstrap resamples and confidence .95. Each independent method had a shared cap of 400 actual policy calls including its own factual capture; the budget control used three. No language model was called.

All 1,280 planned trials are retained. There were **289,709 actual synthetic policy calls**: 5,888 factual, 79,910 contrastive and 203,911 Shapley. The 2,560 paired factual captures had no failures or disagreements. Of 223,232 planned branches, 198,690 completed, 4,062 were invalid held-tail replays, 256 failed at the intentional call cap and 20,224 remained unstarted. These categories were not converted into bad outcomes or silently dropped.

## Consequence interval coverage

Every row below has 128 available estimates and an independent numerical reference. State and linked targets reuse the same outcomes in these cases and are not pooled as separate replications. The full summary includes each target, position, bias, RMSE, Monte Carlo standard errors, zero-width counts and Wilson uncertainty.

| Mechanism | Position | Contrastive coverage | Shapley coverage | Contrastive bias / RMSE | Shapley bias / RMSE |
| --- | --- | --- | --- | --- | --- |
| Protective stop, q=0.1 | 0 | 107/128 (83.6%) | 126/128 (98.4%) | -0.0028 / 0.0720 | +0.0037 / 0.0515 |
| Protective stop, q=0.1 | 1 | 100/128 (78.1%) | 107/128 (83.6%) | -0.0033 / 0.0703 | +0.0011 / 0.0527 |
| Protective stop, q=0.5 | 0 | 126/128 (98.4%) | 121/128 (94.5%) | -0.0146 / 0.1154 | +0.0039 / 0.0906 |
| Protective stop, q=0.5 | 1 | 122/128 (95.3%) | 121/128 (94.5%) | -0.0229 / 0.1254 | -0.0010 / 0.0873 |
| Protective stop, q=0.9 | 0 | 99/128 (77.3%) | 124/128 (96.9%) | +0.0048 / 0.0722 | -0.0024 / 0.0570 |
| Protective stop, q=0.9 | 1 | 103/128 (80.5%) | 103/128 (80.5%) | -0.0050 / 0.0767 | +0.0040 / 0.0586 |

Position 0 is a genuine zero-value player in the Shapley game. It is not a contrastive null because resampling its suffix also resamples the timeout decision. Shapley false nonzero flags for this player were 2/128 at q=.1, 7/128 at q=.5 and 4/128 at q=.9.

| Retry-pivot q | Position 0 contrastive coverage | Position 1 contrastive coverage | Exact latest-population-rescue match |
| --- | --- | --- | --- |
| 0.1 | 104/128 (81.2%) | 93/128 (72.7%) | 128/128 (100.0%) |
| 0.5 | 125/128 (97.7%) | 125/128 (97.7%) | 127/128 (99.2%) |
| 0.9 | 103/128 (80.5%) | 100/128 (78.1%) | 10/128 (7.8%) |

The retry terminal position 2 is a true contrastive null: all 128 estimates were zero with zero-width intervals at each q. At q=.9 the latest population negative position is 1, but the nominal rule chose 1 ten times, 0 five times, and no rescue 113 times. This describes limited detection at the declared sample count, not a proof of unique causation or a model error.

The three-position retry Shapley game has no numerical population reference because a fresh stop can leave a held terminal position unreachable. Path estimates were available in 0/128, 0/128 and 17/128 repetitions for q=.1,.5,.9. The 17 available vectors remain ineligible for numerical error/coverage scoring. All independent endpoints were available, with coverage 102/128, 117/128 and 100/128; endpoint truth does not repair an undefined positional game.

## Refusal controls

| Control | Contrastive / Shapley availability per position | Interpretation |
| --- | --- | --- |
| Idempotent stop | 128/128 for all targets | Every effect and contribution zero; all reference intervals covered. |
| Missing provenance | 128/128 action and state; 0/128 linked | Supported state does not establish qualifying origin. Duplicate violations still retain known false linked labels. |
| Lagged readback | 128/128 action; 0/128 state and linked | The readback watermark does not cover the horizon. |
| Three-call budget | 0/128 for all targets | Two factual calls and one fresh call per method; failed and unstarted receipts retained. |

Availability and coverage remain distinct. Refusals do not count as truth-covered intervals; unavailable truth has no coverage denominator. Contributions are not adjusted to force agreement with independent endpoints.

## Independent checks and next study

`audits/` contains two independent saved-evidence auditors and their receipts. The statistics auditor recomputes every bootstrap interval, pair vector, normal interval, endpoint and scoring denominator. The evidence auditor checks every phase-seeded continuation coin, outcome label, held-tail validity and call receipt, plus the preselected full traces, schemas, verifications and explanations. Neither uses the production analytic reference or analyzer as its numerical oracle.

The separate [finite interval enumeration](../calibration-theory-2026-10-11/README.md) predicts weak coverage under independent Bernoulli assumptions without using these outcomes. Homogeneous bootstrap samples alone limit population coverage to at most 81.47% at q=.1/.9 with 16 draws. A finite observed proportion can exceed this bound through sampling variation.

The [next interval comparison](../../docs/interval-followup-plan.md) will retain these methods as comparators and use new declared draws. It will compare binomial intervals for the constant-baseline contrastive estimator and separately assess signed pair uncertainty. This probe changes no intervals after inspecting results. It establishes neither live-model accuracy, held-out task performance, domain interaction recovery nor method superiority.

## Reproduction and integrity

```sh
consequa-x calibrate-attribution --replicates 128 --source-revision 9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0 --output output/my-calibration-probe
```

Use the frozen revision and a fresh directory. `protocol.json` was written before any policy call. `execution.json` records the installed-wheel digest, source-module hashes and elapsed time (6,684 seconds). Compact receipts for every repetition are compressed JSONL; full public evidence for replicate 0 was selected in advance and its simulator gold is separate.

`export-manifest.json` preserves the exporter's original byte index. `manifest.json` also covers the execution receipt, audits and this analysis. Hashes establish changed-byte detection, not provider authenticity. GitHub Actions has been disabled at the maintainer's request; subsequent checks and publishing use local validation.
