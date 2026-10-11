# Decision contrastive experiment

Provider: **scripted**; case: **unsafe_retry**. One factual capture; 2 planned continuations per reached factual decision. Continuation branches: 0 completed, 1 failed, 5 not started. Shared policy-call budget: 5 / 5 (3 factual, 2 continuation calls).

This is a scripted integration fixture. No language model was run.

Each changed branch resets the factual payment world, holds decisions before the tested index, and resamples that decision and its suffix with the same declared policy. All selected targets use the same collected branches. Held decisions cost no provider call; actual attempted fresh calls, including failures, consume the shared budget. Model phase seeds are reproducibility controls, not guarantees.

| Decision | Event | Target | Status | Factual bad | Changed bad rate | Signed effect | Percentile interval | Known | Unknown | Failed | Unstarted | Significant rescue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | refund_decision | action | refused | False | — | — | — | 0 | 0 | 1 | 1 | None |
| 0 | refund_decision | consequence | refused | True | — | — | — | 0 | 0 | 1 | 1 | None |
| 0 | refund_decision | action_linked_consequence | refused | True | — | — | — | 0 | 0 | 1 | 1 | None |
| 1 | response_decision_1 | action | refused | False | — | — | — | 0 | 0 | 0 | 2 | None |
| 1 | response_decision_1 | consequence | refused | True | — | — | — | 0 | 0 | 0 | 2 | None |
| 1 | response_decision_1 | action_linked_consequence | refused | True | — | — | — | 0 | 0 | 0 | 2 | None |
| 2 | response_decision_2 | action | refused | False | — | — | — | 0 | 0 | 0 | 2 | None |
| 2 | response_decision_2 | consequence | refused | True | — | — | — | 0 | 0 | 0 | 2 | None |
| 2 | response_decision_2 | action_linked_consequence | refused | True | — | — | — | 0 | 0 | 0 | 2 | None |

Bad means the selected target is false; unknown target values remain unknown. Signed effects are changed bad-outcome probability minus the single observed factual bad-outcome indicator. Negative effects mean the changed distribution reduces bad outcomes. These are distinct from context neutralization effects and are not responsibility shares.

Intervals use 200 pure-Python random bootstrap resamples, seed 0, confidence 0.95, and linearly interpolated percentiles. The random stream differs from the upstream NumPy implementation. Every planned continuation must be usable and at least two samples are required; unknowns, failures, and unstarted branches refuse the whole estimate. A locus is refused unless every tested decision for that target is usable. The latest decision with a negative point effect and strictly negative interval upper bound is a significant rescue. Intervals do not provide simultaneous coverage across decisions or targets.

The factual baseline is one observed indicator, not a separately estimated rate. The bootstrap resets its random seed at each position and makes no baseline draws; identical observed samples can produce degenerate intervals.

A degenerate interval does not establish zero population variance or certain rescue. The nominal locus rule does not prove unique causation, and requested seeds do not establish independent samples or equal hidden model state.

This independently written CAR-style binary adaptation adds contrastive decision localization; Shapley estimation and a matched baseline comparison remain research work. No attribution overlay is attached to these signed effects.

`traces/` contains completed factual and branch evidence only. `explanations/` is independently derived from each trace, while `evaluator_truth/` contains simulator labels that must not enter the policy or explainer. `results.json` preserves every reached request/reply, failures, the complete planned continuation seed schedule, per-target coverage, and loci. `trace-schema.json` describes each trace. `manifest.json` covers every other exported file; hashes detect changed bytes and do not establish authenticity.
