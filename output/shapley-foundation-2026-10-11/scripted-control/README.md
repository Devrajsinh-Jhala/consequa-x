# Decision Shapley experiment

Provider: **scripted**; case: **clean**. 2 planned antithetic pairs, 1 draws per coalition evaluation. Branches: 16 completed, 0 invalid, 0 failed, 0 not started. Actual calls: 18 / 30, including 2 factual calls.

Scripted integration example; no language model was run.

A coalition holds its recorded decisions at compatible positional stages and resamples other decisions. Changed public inputs are allowed. A requested held position that is not reached invalidates that branch; only completed valid branches have outcome labels. Every evaluation is fresh, including repeated coalitions. All requested targets reuse each branch without additional calls.

| Decision | Target | Status | Signed contribution | Normal interval | Known pairs |
| --- | --- | --- | --- | --- | --- |
| 0 | action | estimated | 0.0 | (0.0, 0.0) | 2 / 2 |
| 1 | action | estimated | 0.0 | (0.0, 0.0) | 2 / 2 |
| 0 | consequence | estimated | 0.0 | (0.0, 0.0) | 2 / 2 |
| 1 | consequence | estimated | 0.0 | (0.0, 0.0) | 2 / 2 |
| 0 | action_linked_consequence | estimated | 0.0 | (0.0, 0.0) | 2 / 2 |
| 1 | action_linked_consequence | estimated | 0.0 | (0.0, 0.0) | 2 / 2 |

Positive contributions mean holding a factual decision increases bad-outcome probability; negative contributions mean it is protective. Values are not normalized responsibility shares. Normal approximation intervals use the averaged forward/reverse vector as one unit, sample variance, and the planned pair count. Incomplete target path coverage refuses its whole vector; unknown, invalid, failed, and unstarted draws remain separate, with no redraws.

Independent empty/full endpoint samples lie outside the permutation walks. The discrepancy is coefficient sum minus that independently sampled endpoint difference, not a forced efficiency identity or a statistical pass/fail test. Endpoint refusal is separate from coefficient refusal.

These conditional intervals have no multiplicity adjustment or calibrated coverage guarantee. Homogeneous samples can collapse intervals; a small pair count and requested seeds do not establish certainty or independence. Strict unreachable-position refusal makes some variable-length refund games unavailable. A fixed-length mathematical interaction oracle is a different mechanism from this refund adapter. The implementation is independently written and declares its differences from the pinned CAR reference.

Evaluator truth stays separate from policy/explainer inputs. Manifests detect changed bytes, not authenticity. No context-effect graph overlay is produced.
