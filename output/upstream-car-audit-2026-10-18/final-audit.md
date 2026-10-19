# Independent CAR artefact audit

Final audit: True; complete collection: True.
Observed engine files: 2048/2048. Planned paired groups:1024.

Paired semantic counts: `{"budget_control_discrepant_groups": 64, "draws_compared": 196608, "mismatched_draws": 64, "paired_groups": 1024, "same_actual_call_groups": 1024, "same_factual_trace_groups": 1024}`.
Group dispositions: `{"completed": 1024}`.

Every observed trial was checked against the frozen schedule, complete draw inventory, public readback semantics, actual-call budget, primary missingness gate and independently recomputed point estimate. Closed-form Bernoulli references were derived without replay or importing the collection implementation. Final summaries and pair comparisons were independently recomputed where present.

| Mechanism | Method | Variant | Position | Available/64 | Covered/scored | Mean width | Bias | RMSE |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| refund-p50-q50 | contrastive | upstream_bootstrap | 0 | 64/64 | 62/64 | 0.284692 | 0.0146484 | 0.0641862 |
| refund-p50-q50 | contrastive | upstream_bootstrap | 1 | 64/64 | 59/64 | 0.330627 | 0.00585938 | 0.0955236 |
| refund-p50-q50 | contrastive | upstream_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p50-q50 | contrastive | cx_bootstrap | 0 | 64/64 | 62/64 | 0.286133 | 0.0146484 | 0.0641862 |
| refund-p50-q50 | contrastive | cx_bootstrap | 1 | 64/64 | 60/64 | 0.328687 | 0.00585938 | 0.0955236 |
| refund-p50-q50 | contrastive | cx_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p50-q50 | contrastive | cx_clopper_pearson | 0 | 64/64 | 63/64 | 0.309489 | 0.0146484 | 0.0641862 |
| refund-p50-q50 | contrastive | cx_clopper_pearson | 1 | 64/64 | 62/64 | 0.356262 | 0.00585938 | 0.0955236 |
| refund-p50-q50 | contrastive | cx_clopper_pearson | 2 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| refund-p50-q50 | shapley | upstream_normal | 0 | 64/64 | 63/64 | 0.227086 | -0.00341797 | 0.0548268 |
| refund-p50-q50 | shapley | upstream_normal | 1 | 64/64 | 60/64 | 0.22546 | -0.012207 | 0.0562012 |
| refund-p50-q50 | shapley | upstream_normal | 2 | 64/64 | 61/64 | 0.220426 | -0.00170898 | 0.0547224 |
| refund-p50-q50 | shapley | cx_normal | 0 | 64/64 | 63/64 | 0.227086 | -0.00341797 | 0.0548268 |
| refund-p50-q50 | shapley | cx_normal | 1 | 64/64 | 60/64 | 0.22546 | -0.012207 | 0.0562012 |
| refund-p50-q50 | shapley | cx_normal | 2 | 64/64 | 61/64 | 0.220426 | -0.00170898 | 0.0547224 |
| refund-p50-q50 | shapley | cx_hoeffding | 0 | 64/64 | 64/64 | 0.960323 | -0.00341797 | 0.0548268 |
| refund-p50-q50 | shapley | cx_hoeffding | 1 | 64/64 | 64/64 | 0.960323 | -0.012207 | 0.0562012 |
| refund-p50-q50 | shapley | cx_hoeffding | 2 | 64/64 | 64/64 | 0.960323 | -0.00170898 | 0.0547224 |
| refund-p20-q80 | contrastive | upstream_bootstrap | 0 | 64/64 | 52/64 | 0.110352 | -0.00394531 | 0.0318443 |
| refund-p20-q80 | contrastive | upstream_bootstrap | 1 | 64/64 | 61/64 | 0.255432 | 0.0144531 | 0.0754867 |
| refund-p20-q80 | contrastive | upstream_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p20-q80 | contrastive | cx_bootstrap | 0 | 64/64 | 52/64 | 0.110364 | -0.00394531 | 0.0318443 |
| refund-p20-q80 | contrastive | cx_bootstrap | 1 | 64/64 | 57/64 | 0.255408 | 0.0144531 | 0.0754867 |
| refund-p20-q80 | contrastive | cx_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p20-q80 | contrastive | cx_clopper_pearson | 0 | 64/64 | 64/64 | 0.172989 | -0.00394531 | 0.0318443 |
| refund-p20-q80 | contrastive | cx_clopper_pearson | 1 | 64/64 | 63/64 | 0.283435 | 0.0144531 | 0.0754867 |
| refund-p20-q80 | contrastive | cx_clopper_pearson | 2 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| refund-p20-q80 | shapley | upstream_normal | 0 | 64/64 | 60/64 | 0.152716 | -0.00203125 | 0.0386246 |
| refund-p20-q80 | shapley | upstream_normal | 1 | 64/64 | 58/64 | 0.150743 | -0.00208008 | 0.0399792 |
| refund-p20-q80 | shapley | upstream_normal | 2 | 64/64 | 59/64 | 0.135544 | 0 | 0.0344991 |
| refund-p20-q80 | shapley | cx_normal | 0 | 64/64 | 60/64 | 0.152716 | -0.00203125 | 0.0386246 |
| refund-p20-q80 | shapley | cx_normal | 1 | 64/64 | 58/64 | 0.150743 | -0.00208008 | 0.0399792 |
| refund-p20-q80 | shapley | cx_normal | 2 | 64/64 | 59/64 | 0.135544 | 0 | 0.0344991 |
| refund-p20-q80 | shapley | cx_hoeffding | 0 | 64/64 | 64/64 | 0.960323 | -0.00203125 | 0.0386246 |
| refund-p20-q80 | shapley | cx_hoeffding | 1 | 64/64 | 64/64 | 0.960323 | -0.00208008 | 0.0399792 |
| refund-p20-q80 | shapley | cx_hoeffding | 2 | 64/64 | 64/64 | 0.960323 | 0 | 0.0344991 |
| refund-p80-q20 | contrastive | upstream_bootstrap | 0 | 64/64 | 59/64 | 0.315955 | -0.000136719 | 0.0945591 |
| refund-p80-q20 | contrastive | upstream_bootstrap | 1 | 64/64 | 58/64 | 0.271484 | 0.00996094 | 0.0713295 |
| refund-p80-q20 | contrastive | upstream_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p80-q20 | contrastive | cx_bootstrap | 0 | 64/64 | 60/64 | 0.319385 | -0.000136719 | 0.0945591 |
| refund-p80-q20 | contrastive | cx_bootstrap | 1 | 64/64 | 57/64 | 0.270532 | 0.00996094 | 0.0713295 |
| refund-p80-q20 | contrastive | cx_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p80-q20 | contrastive | cx_clopper_pearson | 0 | 64/64 | 61/64 | 0.342866 | -0.000136719 | 0.0945591 |
| refund-p80-q20 | contrastive | cx_clopper_pearson | 1 | 64/64 | 61/64 | 0.296761 | 0.00996094 | 0.0713295 |
| refund-p80-q20 | contrastive | cx_clopper_pearson | 2 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| refund-p80-q20 | shapley | upstream_normal | 0 | 64/64 | 61/64 | 0.215004 | -0.0115527 | 0.0546429 |
| refund-p80-q20 | shapley | upstream_normal | 1 | 64/64 | 64/64 | 0.212639 | 0.00485352 | 0.0493105 |
| refund-p80-q20 | shapley | upstream_normal | 2 | 64/64 | 61/64 | 0.224033 | -0.000488281 | 0.0528428 |
| refund-p80-q20 | shapley | cx_normal | 0 | 64/64 | 61/64 | 0.215004 | -0.0115527 | 0.0546429 |
| refund-p80-q20 | shapley | cx_normal | 1 | 64/64 | 64/64 | 0.212639 | 0.00485352 | 0.0493105 |
| refund-p80-q20 | shapley | cx_normal | 2 | 64/64 | 61/64 | 0.224033 | -0.000488281 | 0.0528428 |
| refund-p80-q20 | shapley | cx_hoeffding | 0 | 64/64 | 64/64 | 0.960323 | -0.0115527 | 0.0546429 |
| refund-p80-q20 | shapley | cx_hoeffding | 1 | 64/64 | 64/64 | 0.755308 | 0.00485352 | 0.0493105 |
| refund-p80-q20 | shapley | cx_hoeffding | 2 | 64/64 | 64/64 | 0.960323 | -0.000488281 | 0.0528428 |
| refund-p100-q100 | contrastive | upstream_bootstrap | 0 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | contrastive | upstream_bootstrap | 1 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | contrastive | upstream_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | contrastive | cx_bootstrap | 0 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | contrastive | cx_bootstrap | 1 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | contrastive | cx_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | contrastive | cx_clopper_pearson | 0 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| refund-p100-q100 | contrastive | cx_clopper_pearson | 1 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| refund-p100-q100 | contrastive | cx_clopper_pearson | 2 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| refund-p100-q100 | shapley | upstream_normal | 0 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | shapley | upstream_normal | 1 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | shapley | upstream_normal | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | shapley | cx_normal | 0 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | shapley | cx_normal | 1 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | shapley | cx_normal | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| refund-p100-q100 | shapley | cx_hoeffding | 0 | 64/64 | 64/64 | 0.960323 | 0 | 0 |
| refund-p100-q100 | shapley | cx_hoeffding | 1 | 64/64 | 64/64 | 0.960323 | 0 | 0 |
| refund-p100-q100 | shapley | cx_hoeffding | 2 | 64/64 | 64/64 | 0.960323 | 0 | 0 |
| idempotent-p50-q50 | contrastive | upstream_bootstrap | 0 | 64/64 | 57/64 | 0.331165 | -0.00244141 | 0.100429 |
| idempotent-p50-q50 | contrastive | upstream_bootstrap | 1 | 64/64 | 64/64 | 0 | 0 | 0 |
| idempotent-p50-q50 | contrastive | upstream_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| idempotent-p50-q50 | contrastive | cx_bootstrap | 0 | 64/64 | 57/64 | 0.333069 | -0.00244141 | 0.100429 |
| idempotent-p50-q50 | contrastive | cx_bootstrap | 1 | 64/64 | 64/64 | 0 | 0 | 0 |
| idempotent-p50-q50 | contrastive | cx_bootstrap | 2 | 64/64 | 64/64 | 0 | 0 | 0 |
| idempotent-p50-q50 | contrastive | cx_clopper_pearson | 0 | 64/64 | 60/64 | 0.355545 | -0.00244141 | 0.100429 |
| idempotent-p50-q50 | contrastive | cx_clopper_pearson | 1 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| idempotent-p50-q50 | contrastive | cx_clopper_pearson | 2 | 64/64 | 64/64 | 0.108881 | 0 | 0 |
| idempotent-p50-q50 | shapley | upstream_normal | 0 | 64/64 | 63/64 | 0.245805 | -0.00488281 | 0.0592412 |
| idempotent-p50-q50 | shapley | upstream_normal | 1 | 64/64 | 61/64 | 0.247392 | 0.00976562 | 0.0638287 |
| idempotent-p50-q50 | shapley | upstream_normal | 2 | 64/64 | 60/64 | 0.243765 | 0.000488281 | 0.0608924 |
| idempotent-p50-q50 | shapley | cx_normal | 0 | 64/64 | 63/64 | 0.245805 | -0.00488281 | 0.0592412 |
| idempotent-p50-q50 | shapley | cx_normal | 1 | 64/64 | 61/64 | 0.247392 | 0.00976562 | 0.0638287 |
| idempotent-p50-q50 | shapley | cx_normal | 2 | 64/64 | 60/64 | 0.243765 | 0.000488281 | 0.0608924 |
| idempotent-p50-q50 | shapley | cx_hoeffding | 0 | 64/64 | 64/64 | 0.943612 | -0.00488281 | 0.0592412 |
| idempotent-p50-q50 | shapley | cx_hoeffding | 1 | 64/64 | 64/64 | 0.960323 | 0.00976562 | 0.0638287 |
| idempotent-p50-q50 | shapley | cx_hoeffding | 2 | 64/64 | 64/64 | 0.960323 | 0.000488281 | 0.0608924 |
| unknown-provenance-p50-q50 | contrastive | upstream_bootstrap | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | upstream_bootstrap | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | upstream_bootstrap | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | cx_bootstrap | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | cx_bootstrap | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | cx_bootstrap | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | cx_clopper_pearson | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | cx_clopper_pearson | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | contrastive | cx_clopper_pearson | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | upstream_normal | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | upstream_normal | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | upstream_normal | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | cx_normal | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | cx_normal | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | cx_normal | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | cx_hoeffding | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | cx_hoeffding | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| unknown-provenance-p50-q50 | shapley | cx_hoeffding | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | upstream_bootstrap | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | upstream_bootstrap | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | upstream_bootstrap | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | cx_bootstrap | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | cx_bootstrap | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | cx_bootstrap | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | cx_clopper_pearson | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | cx_clopper_pearson | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | contrastive | cx_clopper_pearson | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | upstream_normal | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | upstream_normal | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | upstream_normal | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | cx_normal | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | cx_normal | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | cx_normal | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | cx_hoeffding | 0 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | cx_hoeffding | 1 | 0/64 | None/0 | undefined | undefined | undefined |
| lagged-readback-p50-q50 | shapley | cx_hoeffding | 2 | 0/64 | None/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | upstream_bootstrap | 0 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | upstream_bootstrap | 1 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | upstream_bootstrap | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | cx_bootstrap | 0 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | cx_bootstrap | 1 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | cx_bootstrap | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | cx_clopper_pearson | 0 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | cx_clopper_pearson | 1 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | contrastive | cx_clopper_pearson | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | upstream_normal | 0 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | upstream_normal | 1 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | upstream_normal | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | cx_normal | 0 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | cx_normal | 1 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | cx_normal | 2 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | cx_hoeffding | 0 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | cx_hoeffding | 1 | 0/64 | 0/0 | undefined | undefined | undefined |
| budget-p50-q50 | shapley | cx_hoeffding | 2 | 0/64 | 0/0 | undefined | undefined | undefined |

In-progress files are provisional until a terminal manifest or incomplete receipt exists.
Simulator/policy/transport compatibility and conditional calibration, not independent tasks or method superiority.
Coverage follows frozen exact floating comparisons; independently derived rational references agree within1e-12.
Intervals are read from recorded engine outputs; this audit independently computes points, coverage, error and widths.
Native CAR budget-control contrastive batches coalesce 31 or32 zero-spend refusal records under one failed canonical slot. The audit admits only the exact pinned gather/bridge shape; known/completed draws remain strict. Native failed/unstarted slot labels do not provide a one-to-one refused-attempt inventory, and these trials have no primary numeric estimates.
Counterfactual full event histories are not retained; their trace hashes cannot be regenerated without replay. This audit checks retained semantic evidence and file bindings.
