# Repeated physical refund sampling: derived findings

Frozen source `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`; package `1.0.0`. Retained 2,048/2,048 trials, 655,360 planned branches and 628,535 actual scripted calls. Interval comparison made zero additional calls. No model was called.

The independent audit passed 44,698,925 assertions and checked 4,210 complete preselected traces. Its receipt matches the sealed manifest `3ee00dfb6ac66db219bc25b1248a1645b8f86deeecae6c9c46a8419cc1235af4`; this postprocessor rehashed all 52 sealed files.

The CSV files and analysis.json retain every mechanism/game/target/position/variant row. Availability.csv counts whole coefficient vectors once, rather than counting three players or two interval variants as independent trials. Undefined references and zero-denominator rates remain undefined.

## Every case and game: branch retention

Completed counts executed branches, including known violations and unknown target evidence.

| Case | Game | Completed | Invalid | Failed | Unstarted | Calls | Inactive-held branches |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| refund-p50-q50 | strict | 34828 | 6132 | 0 | 0 | 42415 | 0 |
| refund-p50-q50 | on_reach | 40960 | 0 | 0 | 0 | 42526 | 6182 |
| refund-p20-q80 | strict | 33741 | 7219 | 0 | 0 | 36627 | 0 |
| refund-p20-q80 | on_reach | 40960 | 0 | 0 | 0 | 36688 | 7212 |
| refund-p80-q20 | strict | 35402 | 5558 | 0 | 0 | 45797 | 0 |
| refund-p80-q20 | on_reach | 40960 | 0 | 0 | 0 | 45817 | 5492 |
| refund-p100-q100 | strict | 40960 | 0 | 0 | 0 | 61824 | 0 |
| refund-p100-q100 | on_reach | 40960 | 0 | 0 | 0 | 61824 | 0 |
| idempotent-p50-q50 | strict | 34781 | 6179 | 0 | 0 | 42203 | 0 |
| idempotent-p50-q50 | on_reach | 40960 | 0 | 0 | 0 | 42378 | 6123 |
| unknown-provenance-p50-q50 | strict | 34818 | 6142 | 0 | 0 | 42241 | 0 |
| unknown-provenance-p50-q50 | on_reach | 40960 | 0 | 0 | 0 | 42429 | 6187 |
| lagged-readback-p50-q50 | strict | 34767 | 6193 | 0 | 0 | 42318 | 0 |
| lagged-readback-p50-q50 | on_reach | 40960 | 0 | 0 | 0 | 42424 | 6196 |
| budget-p50-q50 | strict | 64 | 0 | 128 | 40768 | 512 | 0 |
| budget-p50-q50 | on_reach | 69 | 0 | 128 | 40763 | 512 | 0 |

## On-reach consequence coefficients

All registered cases are shown. Coverage and sign/false-nonzero columns are explicit k/n; nominal rate intervals are retained in the complete tables. Width and sign detection must accompany coverage. A zero sign denominator is not evidence of zero error.

| Case | Player | Variant | Reference | Available/planned | Coverage k/n | Mean width | Sign k/n | False nonzero k/n | Bias | RMSE |
| --- | ---: | --- | ---: | ---: | --- | ---: | --- | --- | ---: | ---: |
| refund-p50-q50 | 0 | normal | -0.125 | 128/128 | 122/128 | 0.22617 | 84/128 | undefined (0/0) | -0.0062256 | 0.055844 |
| refund-p50-q50 | 1 | normal | 0.375 | 128/128 | 118/128 | 0.22551 | 128/128 | undefined (0/0) | -0.0026855 | 0.061111 |
| refund-p50-q50 | 2 | normal | 0 | 128/128 | 117/128 | 0.21956 | undefined (0/0) | 11/128 | 0.0047607 | 0.054914 |
| refund-p50-q50 | 0 | hoeffding_exact_endpoints | -0.125 | 128/128 | 128/128 | 0.96032 | 0/128 | undefined (0/0) | -0.0062256 | 0.055844 |
| refund-p50-q50 | 1 | hoeffding_exact_endpoints | 0.375 | 128/128 | 128/128 | 0.96011 | 8/128 | undefined (0/0) | -0.0026855 | 0.061111 |
| refund-p50-q50 | 2 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | 0.0047607 | 0.054914 |
| refund-p20-q80 | 0 | normal | -0.08 | 128/128 | 118/128 | 0.15329 | 67/128 | undefined (0/0) | 0.0028516 | 0.037917 |
| refund-p20-q80 | 1 | normal | 0.12 | 128/128 | 124/128 | 0.15352 | 123/128 | undefined (0/0) | -0.0013477 | 0.037259 |
| refund-p20-q80 | 2 | normal | 0 | 128/128 | 119/128 | 0.13313 | undefined (0/0) | 9/128 | -0.00012207 | 0.036199 |
| refund-p20-q80 | 0 | hoeffding_exact_endpoints | -0.08 | 128/128 | 128/128 | 0.96032 | 0/128 | undefined (0/0) | 0.0028516 | 0.037917 |
| refund-p20-q80 | 1 | hoeffding_exact_endpoints | 0.12 | 128/128 | 128/128 | 0.96032 | 0/128 | undefined (0/0) | -0.0013477 | 0.037259 |
| refund-p20-q80 | 2 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | -0.00012207 | 0.036199 |
| refund-p80-q20 | 0 | normal | -0.08 | 128/128 | 120/128 | 0.21561 | 45/128 | undefined (0/0) | -0.003252 | 0.051337 |
| refund-p80-q20 | 1 | normal | 0.72 | 128/128 | 123/128 | 0.2176 | 128/128 | undefined (0/0) | -0.012969 | 0.053313 |
| refund-p80-q20 | 2 | normal | 0 | 128/128 | 117/128 | 0.22788 | undefined (0/0) | 11/128 | 0.0053711 | 0.060263 |
| refund-p80-q20 | 0 | hoeffding_exact_endpoints | -0.08 | 128/128 | 128/128 | 0.96032 | 0/128 | undefined (0/0) | -0.003252 | 0.051337 |
| refund-p80-q20 | 1 | hoeffding_exact_endpoints | 0.72 | 128/128 | 128/128 | 0.77313 | 128/128 | undefined (0/0) | -0.012969 | 0.053313 |
| refund-p80-q20 | 2 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | 0.0053711 | 0.060263 |
| refund-p100-q100 | 0 | normal | -0 | 128/128 | 128/128 | 0 | undefined (0/0) | 0/128 | 0 | 0 |
| refund-p100-q100 | 1 | normal | 0 | 128/128 | 128/128 | 0 | undefined (0/0) | 0/128 | 0 | 0 |
| refund-p100-q100 | 2 | normal | 0 | 128/128 | 128/128 | 0 | undefined (0/0) | 0/128 | 0 | 0 |
| refund-p100-q100 | 0 | hoeffding_exact_endpoints | -0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | 0 | 0 |
| refund-p100-q100 | 1 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | 0 | 0 |
| refund-p100-q100 | 2 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | 0 | 0 |
| idempotent-p50-q50 | 0 | normal | -0.5 | 128/128 | 121/128 | 0.2477 | 128/128 | undefined (0/0) | 0.0013428 | 0.057393 |
| idempotent-p50-q50 | 1 | normal | 0 | 128/128 | 123/128 | 0.24412 | undefined (0/0) | 5/128 | 0.0054932 | 0.062301 |
| idempotent-p50-q50 | 2 | normal | 0 | 128/128 | 114/128 | 0.24352 | undefined (0/0) | 14/128 | -0.0067139 | 0.069535 |
| idempotent-p50-q50 | 0 | hoeffding_exact_endpoints | -0.5 | 128/128 | 128/128 | 0.94618 | 81/128 | undefined (0/0) | 0.0013428 | 0.057393 |
| idempotent-p50-q50 | 1 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | 0.0054932 | 0.062301 |
| idempotent-p50-q50 | 2 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | -0.0067139 | 0.069535 |
| unknown-provenance-p50-q50 | 0 | normal | -0.125 | 128/128 | 118/128 | 0.23041 | 76/128 | undefined (0/0) | 0.0042725 | 0.060279 |
| unknown-provenance-p50-q50 | 1 | normal | 0.375 | 128/128 | 120/128 | 0.22768 | 128/128 | undefined (0/0) | 0.00085449 | 0.059802 |
| unknown-provenance-p50-q50 | 2 | normal | 0 | 128/128 | 115/128 | 0.22347 | undefined (0/0) | 13/128 | -0.0032959 | 0.061033 |
| unknown-provenance-p50-q50 | 0 | hoeffding_exact_endpoints | -0.125 | 128/128 | 128/128 | 0.96032 | 0/128 | undefined (0/0) | 0.0042725 | 0.060279 |
| unknown-provenance-p50-q50 | 1 | hoeffding_exact_endpoints | 0.375 | 128/128 | 128/128 | 0.96032 | 7/128 | undefined (0/0) | 0.00085449 | 0.059802 |
| unknown-provenance-p50-q50 | 2 | hoeffding_exact_endpoints | 0 | 128/128 | 128/128 | 0.96032 | undefined (0/0) | 0/128 | -0.0032959 | 0.061033 |
| lagged-readback-p50-q50 | 0 | normal | undefined | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| lagged-readback-p50-q50 | 1 | normal | undefined | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| lagged-readback-p50-q50 | 2 | normal | undefined | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| lagged-readback-p50-q50 | 0 | hoeffding_exact_endpoints | undefined | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| lagged-readback-p50-q50 | 1 | hoeffding_exact_endpoints | undefined | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| lagged-readback-p50-q50 | 2 | hoeffding_exact_endpoints | undefined | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| budget-p50-q50 | 0 | normal | -0.125 | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| budget-p50-q50 | 1 | normal | 0.375 | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| budget-p50-q50 | 2 | normal | 0 | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| budget-p50-q50 | 0 | hoeffding_exact_endpoints | -0.125 | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| budget-p50-q50 | 1 | hoeffding_exact_endpoints | 0.375 | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |
| budget-p50-q50 | 2 | hoeffding_exact_endpoints | 0 | 0/128 | undefined (0/0) | undefined | undefined (0/0) | undefined (0/0) | undefined | undefined |

## Interpretation limits

- Synthetic planted-factual refund study; no model calls or held-out model generalization
- Games/targets/players/variants share data; rows are not independent replications
- Coverage conditions on available estimates and defined population references; refusals stay explicit
- Rate uncertainty is nominal Wilson, with no multiplicity adjustment
- Interactions are point-only pooled diagnostics; no interval or sign claim
- Pairing compares interval variants on identical retained draws; count changes are descriptive, not a paired significance test
- Hashes and an audit receipt detect changed bytes; they do not authenticate external providers
