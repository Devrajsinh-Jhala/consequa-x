# Research and release roadmap

The current milestone is an installable representation and replay prototype. It establishes that response, reported assessment and observed state can diverge, and that context can change a consequence while leaving the initial action unchanged. It does not establish a novel attribution estimator or publishable empirical superiority.

The initial literature assessment is in `output/research/Consequa-X_Research_Assessment.md` (reviewed 4 October 2026). Before a submission, refresh paper versions and related work, particularly CausalLoss-Fin, CAR, PCCC, FinalityBench and ConsequenceBench.

## Completed foundation

- Versioned public records and portable JSON Schema.
- Deterministic refund environment, audited fault log, bounded funds and idempotency.
- Read-only, horizon-aware verification with independent origin status.
- Evidence graph and reported-assessment diagnosis.
- Recency heuristic and paired leave-one-out effect estimates.
- Separate demo trace, explanation and evaluator-truth exports.
- Offline deterministic and stochastic programmatic policy experiments.

## Next research milestone

1. Add a policy adapter that exposes only supported observations, without accessing evaluator truth. Evaluate actual stochastic LLM policies across several task templates.
2. Specify context and fault intervention families and targets before running the study. Hold out templates and fault compositions, not just random seeds.
3. Compare with verifier-plus-CAR using identical evidence, origin information, candidate variables, snapshots and budget. Add a faithfully adapted joint-fault comparator where applicable.
4. Measure false consequence/origin claims and factor recovery against independent intervention estimates. Report abstention coverage and error together; report model-specific results and cost.
5. Expand domains only after a substantive gap remains in the strong baseline. An engineering framework can still be released if the methodological advantage does not emerge.

The current 40-sample fixture report validates plumbing. It cannot be used as a real-model research result. The recency heuristic is explicitly noncausal, and leave-one-out is a baseline rather than a claimed new estimator.

## Registry release

The first distribution target is Python/PyPI. The local distribution name is `consequa-x`; registry availability and account ownership are unverified. A TypeScript/npm adapter can later share the schema and conformance fixtures without duplicating the Python estimators.

The public source repository uses the MIT license and includes author metadata, contribution guides, and CI for Python 3.11/3.12 on Windows and Ubuntu. Before a registry release, confirm supported Python versions on clean hosts, document provider adapter trust assumptions, and verify release artifacts from a tagged revision. No PyPI/npm upload or package ownership claim is made by this alpha.

The selected workspace contains no existing Consequa runtime. Integration with that runtime requires the source repository and compatibility checks, rather than a rewrite based on the brief's assumed architecture.
