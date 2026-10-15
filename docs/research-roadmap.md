# Research and release roadmap

Updated 15 October 2026 after public release verification. The stable evidence
core is complete and [version 1.0.0 is public on PyPI](https://pypi.org/project/consequa-x/1.0.0/).
Runtime source remains frozen at `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`;
build source is `85ce6c316838c995782aadc8c10770acc708339b`. The current milestone
is completing the retained physical-interaction study and scoped IEEE
protocol/software paper. The research contribution does not depend on claiming
a new estimator or empirical superiority.

The initial literature assessment is in `output/research/Consequa-X_Research_Assessment.md` (reviewed 4 October 2026). Before a submission, refresh paper versions and related work, particularly CausalLoss-Fin, CAR, PCCC, FinalityBench and ConsequenceBench.

## Completed foundation

- Versioned public records and portable JSON Schema.
- Explicit custom verification and target matching, a domain-neutral explanation
  path, and a complete non-refund artifact-delivery example using the public API.
- Successive effect witnesses that preserve historical payload, state and origin,
  controlled adapter/domain errors, preserved CLI output and a documented
  stable-core/schema compatibility boundary.
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
- Audited [prompt-sensitivity follow-up](../output/prompt-sensitivity-2026-10-10/README.md): 12 controlled one-attempt runs and a separate two-episode retry diagnostic. The opt-in profile abstained in the structured field while still making affirmative rationale claims; no accuracy improvement was established.
- Proposed matched-baseline study protocol in [study-plan.md](study-plan.md).
- Validated evaluator-owned task-family manifests with explicit split and order metadata; an 18-case candidate allocation is available in [study-manifests.md](study-manifests.md).
- A supported action-linked refund target distinct from state satisfaction, plus [decision-prefix replay](decision-replay.md) with factual boundary checks and separate continuation seeds.
- Independent CAR-style [decision contrastive replay](decision-contrastive.md) with one observed factual baseline, explicit bootstrap limits, and complete-coverage locus/refusal receipts.
- Conservative [positional coalition and Shapley replay](decision-shapley.md), with fresh antithetic walks, signed pair estimates, independent endpoint diagnostics, and unavailable-coalition refusal.
- An offline [attribution calibration probe](attribution-calibration.md) with predeclared synthetic mechanisms, separate analytic references, repeated error/coverage scoring, and complete refusal denominators.
- An audited [1,280-trial calibration run](../output/calibration-probe-2026-10-11/FINDINGS.md), [finite interval enumeration](../output/calibration-theory-2026-10-11/README.md), and fresh [384-trial same-draw comparison](../output/interval-comparison-2026-10-13/FINDINGS.md). Conservative interval defaults retain uncertainty at constant observations, with width and detection tradeoffs explicit.
- Separate strict and [on-reach positional games](decision-shapley.md), plus [physical refund selection/retry interactions](refund-interactions.md), idempotency and evidence/budget controls. Exact component enumeration establishes the declared physical game; repeated permutation-sampler calibration remains separate.
- Repeated [physical-interaction sampling](interaction-sampling.md), bounded
  serial/parallel collection, same-draw uncertainty comparisons and an independent
  semantic auditor. Implementation/conformance checks are complete; the retained
  2,048-trial study is running and has no completed audit or result claim yet.
- A [working manuscript and evidence ledger](../paper/README.md), with completed preliminary evidence and pending held-out, matched-baseline and joint-fault experiments identified.
- A [24-episode local Qwen3 validation](../output/local-validation-2026-10-14/FINDINGS.md)
  comparing both existing prompt profiles across six validation cases with
  59 actual model calls. Structured abstention, assessable-claim contradictions
  and manual rationale clauses are reported separately; the held-out reserve
  remains untouched.
- [Reviewed alpha 2 distributions](../output/release-alpha-2026-10-14/README.md),
  bound to the final source revision, with local tests, strict metadata checks,
  independent archive inspection, fresh wheel/sdist installations and verified
  public PyPI publication. The repository has since become private.
- A full frozen-source suite of 1,480 passing tests plus 240 subtests, 20
  additional stable-publisher checks, and final installed-wheel Windows Python
  3.11.9 conformance of 200 tests plus 165 subtests.
- [Stable 1.0.0 release checks](../output/release-1.0.0-2026-10-15/checks.json),
  independent wheel/sdist installations, public metadata/download hash and size
  verification, and a [fresh registry installation](../output/release-1.0.0-2026-10-15/registry-install.json)
  with 12 trace round-trips and four artifact-adapter checks. PR #8 merged as
  `708d064`; GitHub remains private and Actions stayed disabled.

## Current completion gates

Complete the retained interaction run, independently audit every declared trial
and denominator, and integrate the achieved results into the IEEE manuscript.
Finalize its discussion and primary references and compile/render the paper.
The software release gates are complete; [publication](../output/release-1.0.0-2026-10-15/publication.json)
and installation receipts preserve the achieved result. [Completion scope](completion-plan.md)
tracks the remaining study, audit and paper gates. The 2,048-trial study is still
running, and no completed sampling result is claimed yet.

## Research after this protocol/software paper

1. Extend the recorded local pilot to actual stochastic LLM policies across several task templates and models. The adapter exposes declared task/context and public responses; independent readback follows the final assessment, and evaluator truth stays outside policy inputs. Measure replay fidelity rather than treating shared requested seeds as a determinism guarantee. Prompt changes informed by the pilot are exploratory adaptations and need independent held-out evaluation.
2. Specify context and fault intervention families and targets before running the study. Hold out templates and fault compositions, not just random seeds.
3. Extend synthetic sampler calibration to live-model and new-domain settings,
   then compare the [CAR adaptations](car-reproduction-plan.md) with identical
   evidence, origin information, intervention units, snapshots and budget.
   Conservative intervals do not establish live-model coverage or resolve
   undefined strict games. Report unavailable coalitions and sampling assumptions,
   and add a faithfully adapted joint context/fault comparator.
4. Measure false consequence/origin claims and factor recovery against independent intervention estimates. Report abstention coverage and error together; audit rationale assertions separately from structured status and report model-specific results and cost.
5. Expand domains only after a substantive gap remains in the strong baseline. An engineering framework can still be released if the methodological advantage does not emerge.

The current 40-sample fixture report, scripted policy smoke report, and scripted paired-policy examples validate plumbing. They cannot be used as real-model research results. The first live pilot completed six runs and 13 policy calls without provider errors; all six final assessments contradicted successful action-linked readback. The recency heuristic is explicitly noncausal, and leave-one-out is a baseline rather than a claimed new estimator. Current paired policy experiments change one visible context field at a time; joint context/fault analysis and the strong comparison methods remain unimplemented research milestones. See [policy-evaluation.md](policy-evaluation.md) and [policy-replay.md](policy-replay.md) for entry points. All payment effects remain simulated.

## Registry release

The Python distribution is `consequa-x`; stable `1.0.0` and the earlier alpha
`0.1.0a2` are publicly published with distinct verified artifacts and registry
installations. Public stable publication was explicitly authorized while GitHub
stays private. The final stable wheel and source archive retain their reviewed
bytes; their dated build-time checklist predates the publication receipts. An
optional TypeScript/npm adapter can later share the schema and conformance
fixtures; no npm package is claimed.

The private repository and public distributions use the MIT license. Source
archives include application examples and Markdown documentation; retained
datasets and the IEEE manuscript remain private repository materials. GitHub
Actions stays disabled at the maintainer's request. Final installations cover
Windows Python 3.11.9 and 3.12.14, with their exact checks retained. No Linux/macOS
or every-newer-interpreter test result is implied. See
[release readiness](release-readiness.md) for the completed gates and receipts.

The selected workspace contains no existing Consequa runtime. Integration with that runtime requires the source repository and compatibility checks, rather than a rewrite based on the brief's assumed architecture.
