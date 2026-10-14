# Synthetic attribution calibration probe

384 predeclared trials across 12 mechanisms; 32 repetitions each. No language model was called.

`protocol.json` was saved before policy calls. `summary.json` reports availability, reference eligibility, error and interval coverage with explicit denominators. All planned draws and refusal receipts are in compressed JSONL files under `trials/`. Full public traces, explanations and decision receipts for replicate 0 are in `evidence/`; its gold records stay separately in `evaluator_truth/`. Python's standard `gzip` module can read these files.

The policy has a declared fixed factual timeout intervention and stochastic fresh continuations. Analytic references describe its ideal Bernoulli law, not the observed replay sample. The three-position retry game has undefined population Shapley values when some held positions are unreachable. Available finite estimates there are not scored against fabricated truth.

Missing provenance, stale readback and the three-call budget control are intentional refusal strata. Refusals remain in planned denominators. State and linked targets reuse outcomes and are not independent replications. This exploratory synthetic probe does not establish calibrated coverage, model accuracy, interaction recovery or method superiority.

The file manifest detects changed bytes, not authenticity. The detailed design and metric definitions are in `docs/attribution-calibration.md`.
