# Research and release roadmap

The current milestone is an installable representation and bounded policy replay prototype. Scripted fixtures establish that response, reported assessment and observed state can diverge, and that context can change a consequence while leaving the initial action unchanged. The policy integration prepares these experiments for an installed local model. It does not establish a novel attribution estimator or publishable empirical superiority.

The initial literature assessment is in `output/research/Consequa-X_Research_Assessment.md` (reviewed 4 October 2026). Before a submission, refresh paper versions and related work, particularly CausalLoss-Fin, CAR, PCCC, FinalityBench and ConsequenceBench.

## Completed foundation

- Versioned public records and portable JSON Schema.
- Deterministic refund environment, audited fault log, bounded funds and idempotency.
- Read-only, horizon-aware verification with independent origin status.
- Evidence graph and reported-assessment diagnosis.
- Recency heuristic and paired leave-one-out effect estimates.
- Separate demo trace, explanation and evaluator-truth exports.
- Offline deterministic and stochastic programmatic policy experiments.
- Visible-context policy interface, structured local Ollama adapter, and bounded evaluations.
- Bounded paired policy experiments with one factual branch per seed, cached action/consequence estimates, and explicit refusals for incomplete pairs.
- Scripted policy smoke exports, HTTP fixture tests, and a [first live Qwen3 4B pilot](../output/live-pilot-2026-10-10/README.md).
- Versioned opt-in prompt refinement with the original profile preserved, and assessment coverage/abstention metrics with explicit denominators.
- Proposed matched-baseline study protocol in [study-plan.md](study-plan.md).

## Next research milestone

1. Extend the recorded local pilot to actual stochastic LLM policies across several task templates and models. The adapter exposes declared task/context and public responses; independent readback follows the final assessment, and evaluator truth stays outside policy inputs. Measure replay fidelity rather than treating shared requested seeds as a determinism guarantee. Prompt changes informed by the pilot are exploratory adaptations and need independent held-out evaluation.
2. Specify context and fault intervention families and targets before running the study. Hold out templates and fault compositions, not just random seeds.
3. Compare with verifier-plus-CAR using identical evidence, origin information, candidate variables, snapshots and budget. Add a faithfully adapted joint-fault comparator where applicable.
4. Measure false consequence/origin claims and factor recovery against independent intervention estimates. Report abstention coverage and error together; report model-specific results and cost.
5. Expand domains only after a substantive gap remains in the strong baseline. An engineering framework can still be released if the methodological advantage does not emerge.

The current 40-sample fixture report, scripted policy smoke report, and scripted paired-policy examples validate plumbing. They cannot be used as real-model research results. The first live pilot completed six runs and 13 policy calls without provider errors; all six final assessments contradicted successful action-linked readback. The recency heuristic is explicitly noncausal, and leave-one-out is a baseline rather than a claimed new estimator. Current paired policy experiments change one visible context field at a time; joint context/fault analysis and the strong comparison methods remain unimplemented research milestones. See [policy-evaluation.md](policy-evaluation.md) and [policy-replay.md](policy-replay.md) for entry points. All payment effects remain simulated.

## Registry release

The first distribution target is Python/PyPI. The local distribution name is `consequa-x`; registry availability and account ownership are unverified. A TypeScript/npm adapter can later share the schema and conformance fixtures without duplicating the Python estimators.

The public source repository uses the MIT license and includes author metadata, contribution guides, and CI for Python 3.11/3.12 on Windows and Ubuntu. Before a registry release, confirm supported Python versions on clean hosts, document provider adapter trust assumptions, and verify release artifacts from a tagged revision. No PyPI/npm upload or package ownership claim is made by this alpha.

The selected workspace contains no existing Consequa runtime. Integration with that runtime requires the source repository and compatibility checks, rather than a rewrite based on the brief's assumed architecture.
