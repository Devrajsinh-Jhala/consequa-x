# Fixture replay experiment

40 paired replays per condition, initial seed 0. Each branch starts an isolated simulated world. All results use programmatic fixture policies, including the explicitly stochastic policy.

| Fixture | Target | Neutralized context | Original rate | Changed rate | Signed effect | Approx. 95% interval |
| --- | --- | --- | --- | --- | --- | --- |
| deterministic_retry_fixture | action | vip_policy | 1.000 | 0.000 | +1.000 | [+0.777, +1.000] |
| deterministic_retry_fixture | action | vip_memory | 1.000 | 0.000 | +1.000 | [+0.777, +1.000] |
| deterministic_retry_fixture | action | retry_instruction | 1.000 | 1.000 | +0.000 | [-0.112, +0.112] |
| deterministic_retry_fixture | action | distractor | 1.000 | 1.000 | +0.000 | [-0.112, +0.112] |
| deterministic_retry_fixture | consequence | vip_policy | 0.000 | 0.000 | +0.000 | [-0.112, +0.112] |
| deterministic_retry_fixture | consequence | vip_memory | 0.000 | 0.000 | +0.000 | [-0.112, +0.112] |
| deterministic_retry_fixture | consequence | retry_instruction | 0.000 | 1.000 | -1.000 | [-1.000, -0.777] |
| deterministic_retry_fixture | consequence | distractor | 0.000 | 0.000 | +0.000 | [-0.112, +0.112] |
| stochastic_retry_fixture | action | vip_policy | 0.825 | 0.000 | +0.825 | [+0.545, +0.921] |
| stochastic_retry_fixture | action | vip_memory | 0.825 | 0.000 | +0.825 | [+0.545, +0.921] |
| stochastic_retry_fixture | action | retry_instruction | 0.825 | 0.825 | +0.000 | [-0.264, +0.264] |
| stochastic_retry_fixture | action | distractor | 0.825 | 0.825 | +0.000 | [-0.264, +0.264] |
| stochastic_retry_fixture | consequence | vip_policy | 0.300 | 0.000 | +0.300 | [+0.056, +0.477] |
| stochastic_retry_fixture | consequence | vip_memory | 0.300 | 0.000 | +0.300 | [+0.056, +0.477] |
| stochastic_retry_fixture | consequence | retry_instruction | 0.300 | 0.825 | -0.525 | [-0.753, -0.180] |
| stochastic_retry_fixture | consequence | distractor | 0.300 | 0.300 | +0.000 | [-0.309, +0.309] |

The deterministic retry instruction changes initial action selection by 0, but changes exactly-once refund satisfaction by -1. Removing the instruction prevents a second committed refund. This validates that the two estimator targets can differ; it is not a new-method result.

Positive signed effects mean neutralization reduced the target probability; negative effects mean it increased that probability. These values are not shares of responsibility. Intervals subtract Bonferroni-adjusted marginal Wilson bounds; coverage is approximate and conservative. They describe this replay distribution, not generalization across tasks. Unknown pairs refuse an estimate.

Strong comparisons against verifier-plus-CAR, real stochastic LLM policies, and held-out task templates remain research work.
