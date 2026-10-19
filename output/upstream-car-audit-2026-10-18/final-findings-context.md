# Final independent CAR audit context

The read-only stdlib audit completed successfully. It checked every one of 2,048 compressed engine files, all 1,024 semantic group bindings, all 393,216 planned engine receipt slots (196,608 paired positions), 38 frozen local source blobs and 36 pinned upstream source files. All reported per-condition summary values were independently reproduced from raw retained records.

Factual traces and total successful fresh scripted policy calls agree in all 1,024 paired groups. The primary gate admits 640 paired groups and withholds 384 for both engines. All eligible paired point estimates agree exactly. The 64 discrepant canonical slots are confined to the 64 native budget-control contrastive groups documented in `protocol-deviation.md`; no non-budget pair discrepancy was found.

| Engine | Known receipts | Unknown | Failed | Unstarted |
| --- | ---: | ---: | ---: | ---: |
| upstream_car | 142999 | 29101 | 128 | 24380 |
| consequa_x | 142999 | 29101 | 88 | 24420 |

The table counts retained canonical slots. Native budget contrastive refusal attempts are coalesced; their actual invocation inventory is separately disclosed in the deviation note. All invalid counts are zero.

| Method | Engine | Factual fresh calls | Continuation fresh calls | Total fresh calls | Recorded native bridge worlds | Recorded native tool dispatches | CX completed worlds | CX preflights |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| contrastive | consequa_x | 1536 | 64211 | 65747 | n/a | n/a | 43048 | 512 |
| contrastive | upstream_car | 1536 | 64211 | 65747 | 216998 | 249211 | n/a | n/a |
| shapley | consequa_x | 1536 | 142383 | 143919 | n/a | n/a | 129052 | 512 |
| shapley | upstream_car | 1536 | 142383 | 143919 | 628674 | 719093 | n/a | n/a |

Fresh policy calls are independently counted from successful retained decisions; they are scripted policy invocations, with zero live model calls. Native deterministic bridge counters include prefix reconstruction, probes and closing evidence worlds; they are recorded resource counters, not fresh policy calls and not an additional count to be added to every completed canonical draw. Full bridge event histories were not retained, so their aggregate world/tool counts cannot be independently replayed by this read-only audit. CX completed-world counts are independently counted from known/unknown draw receipts; preflight counts are separately recorded.

Summed per-trial elapsed values include four-worker contention and adapter work. They do not measure serial runtime or intrinsic estimator speed. The collector reports 3,246.742094400004s collection wall and 3,253.227094599999s runner-entry wall, excluding final summary serialization.

For the prespecified p=q=0.5 refund condition, each coordinate has 64 planned and 64 available replicates:

| Method / interval | Coverage at positions 0, 1, 2 | Mean widths at positions 0, 1, 2 |
| --- | --- | --- |
| contrastive / upstream_bootstrap | 62/64, 59/64, 64/64 | 0.284692, 0.330627, 0.000000 |
| contrastive / cx_bootstrap | 62/64, 60/64, 64/64 | 0.286133, 0.328687, 0.000000 |
| contrastive / cx_clopper_pearson | 63/64, 62/64, 64/64 | 0.309489, 0.356262, 0.108881 |
| shapley / upstream_normal | 63/64, 60/64, 61/64 | 0.227086, 0.225460, 0.220426 |
| shapley / cx_normal | 63/64, 60/64, 61/64 | 0.227086, 0.225460, 0.220426 |
| shapley / cx_hoeffding | 64/64, 64/64, 64/64 | 0.960323, 0.960323, 0.960323 |

The table is a disclosed example condition, not a selected pooled superiority claim. All conditions, including every unavailable replicate and coordinate, remain in `final-audit.md` and `final-audit.json`. Intervals are engine outputs: the audit independently recomputes point estimates, exact-reference comparisons, coverage, bias, RMSE and widths. It does not reimplement each interval algorithm. At 64 replications, empirical coverage is descriptive and imprecise; coordinates share draws and should not be pooled as independent samples.

This scripted simulator/adapter comparison supports compatibility and conditional calibration claims. It does not establish independent task generalization, live model causal accuracy, autonomous benchmark success, human-validated semantics or method superiority.
