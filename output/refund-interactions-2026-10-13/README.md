# Refund interaction enumeration

This artifact enumerates four deterministic fresh-choice components, all eight held masks, and both explicitly named games. It is not a set of live stochastic samples.

The factual refund, retry and final stop are planted. All targets come from actual payment readback; evaluator records are stored separately.

| Case | Game | Consequence shares | Interaction |
| --- | --- | --- | --- |
| refund-p50-q50 | strict | None | None |
| refund-p50-q50 | on_reach | [-0.125, 0.375, 0.0] | 0.25 |
| refund-p20-q80 | strict | None | None |
| refund-p20-q80 | on_reach | [-0.08000000000000002, 0.12000000000000004, 0.0] | 0.16000000000000003 |
| refund-p80-q20 | strict | None | None |
| refund-p80-q20 | on_reach | [-0.07999999999999999, 0.7200000000000002, 0.0] | 0.16000000000000003 |
| refund-p100-q100 | strict | [0.0, 0.0, 0.0] | 0.0 |
| refund-p100-q100 | on_reach | [0.0, 0.0, 0.0] | 0.0 |
| idempotent-p50-q50 | strict | None | None |
| idempotent-p50-q50 | on_reach | [-0.5, 0.0, 0.0] | 0.0 |
| unknown-provenance-p50-q50 | strict | None | None |
| unknown-provenance-p50-q50 | on_reach | [-0.125, 0.375, 0.0] | 0.25 |
| lagged-readback-p50-q50 | strict | None | None |
| lagged-readback-p50-q50 | on_reach | None | None |
| budget-p50-q50 | strict | None | None |
| budget-p50-q50 | on_reach | None | None |

Actual synthetic policy calls: 718.

A positive invalid, unknown, failed or unstarted mixture weight refuses the numerical vector. Budget controls retain the reference law while refusing incomplete enumerations. Zero-weight components remain in the evidence but do not affect that law.

Run the independent auditor in `scripts/audit_refund_interactions.py` against this directory. Permutation-sampler accuracy, live-model studies, context/fault attribution and cross-domain recovery require separate experiments.
