# Consequa-X: first offline demo

This demo uses transparent programmatic policies and local simulated money. The refund target is INR 5,000 (500,000 paise), exactly once, by the declared deadline.

| Scenario | Agent reported | Verified outcome | Effect origin | Matching effects |
| --- | --- | --- | --- | --- |
| clean | success | satisfied | confirmed | 1 |
| timeout_after_commit | failure | satisfied | confirmed | 1 |
| timeout_before_commit | failure | violated | unknown | 0 |
| false_success | success | violated | unknown | 0 |
| partial_effect | success | violated | confirmed | 0 |
| delayed_visibility | success | unknown | unknown | unknown |
| delayed_reconciled | success | satisfied | confirmed | 1 |
| unsafe_retry | success | violated | confirmed | 2 |
| safe_retry | success | satisfied | confirmed | 1 |
| external_actor | failure | satisfied | other_actor | 1 |
| missing_provenance | success | satisfied | unknown | 1 |
| synthetic_compensation | success | violated | confirmed | 0 |

The timeout-after-commit case diagnoses **BELIEF / RESPONSE DIVERGENCE**. The unsafe retry produces two partial refunds within the payment's original INR 10,000 balance. The safe retry reuses a key and produces one effect.

The external-actor case satisfies the desired state while the agent's attempt failed. Its graph contains no provider-origin link from the agent's dispatch to the other actor's effect. Missing provenance yields unknown origin.

Delayed readback stays unknown until its watermark covers the horizon. Synthetic compensation tests temporal contracts; it is not a claim about real-provider refund reversibility.

`traces/` and `explanations/` contain portable evidence records. `evaluator_truth/` holds injection labels and simulator truth and must not be passed to an explainer. The manifest checks file integrity, not authenticity.
