# Manuscript claims and evidence

This ledger is a review aid for [manuscript.md](manuscript.md), drafted
13 October 2026, updated 16 October 2026. A completed implementation or integration check is not evidence
of held-out empirical superiority. Retained studies keep their frozen revisions
and methods even when the current framework changes.

| Claim or result | Evidence | Status and scope |
| --- | --- | --- |
| Portable logical-operation/attempt/effect records, verifier outcome/origin separation and isolated replay | [Design](../docs/design.md), [build contract](../docs/build-contract.md), production code and tests | Implemented protocol; source authority and watermark declarations remain trusted inputs. |
| Reusable read-only verifier and qualified target-matcher boundary | [Application integration](../docs/application-integration.md), offline artifact-delivery example and application integration tests | Explicit adapters have receipt identity/source/watermark checks. Domain semantics, authentication and read-only behavior remain application responsibilities; the example is not a production-domain evaluation. |
| Successive effect records retain their own provenance witnesses | [Witness specification](../docs/graph-witnesses.md), graph identity and repeated-observation tests | Shared effect identities do not authenticate or merge conflicting source records. Origin edges belong to the supporting observation witness. Historical research graphs remain unchanged. |
| Conditional suffix replay relative to a fixed factual binary label | [Contrastive specification](../docs/decision-contrastive.md) and production replay receipts | Implemented CAR-style adaptation, not a new estimator or population-original-arm contrast. |
| Signed positional coalition sampler and separate endpoints | [Shapley specification](../docs/decision-shapley.md) and production tests/receipts | Implemented strict game; finite numeric availability does not make an invalid population game reference-eligible. |
| All 1,280 synthetic calibration trials retained; 289,709 actual synthetic calls | [Findings](../output/calibration-probe-2026-10-11/FINDINGS.md), protocol, compact receipts and audits in the same folder | Completed development study at source `9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0`; no language-model calls. |
| Several nominal 95% legacy intervals undercover the known conditional effects | [Full calibration summary](../output/calibration-probe-2026-10-11/summary.json) and independently recomputed audits | Completed synthetic evidence for the specified cases and assumptions; not an upstream CAR reproduction or broad live-model result. |
| Finite-distribution normal coverage and homogeneous bootstrap ceiling | [Independent enumeration](../output/calibration-theory-2026-10-11/README.md) and `results.json` | Completed idealized Bernoulli calculation, exact probability weights with floating-point interval classification. |
| Six local pilot runs, 13 calls, six contradicted final assessments | [Live pilot](../output/live-pilot-2026-10-10/README.md), protocol, raw captures and artifact audit | Completed narrow integration evidence; one model/template, no superiority or generalization claim. |
| Revised status fields abstain while some rationales still assert success | [Exploratory prompt comparison](../output/prompt-sensitivity-2026-10-10/README.md), comparison and audits | Completed twelve-run comparison plus separate two-episode diagnostic; developed after pilot, no independent holdout. |
| Alternative intervals compared on 384 new trials, 66,048 planned branches and 87,054 actual scripted calls, with zero extra comparison calls | [Retained findings](../output/interval-comparison-2026-10-13/FINDINGS.md), `summary.json`, numerical/saved-evidence audits and negative checks in the same folder | Completed separate development study at collection source `0d8ec0baee84ca0d33f52739456d54d6f61a27ad`; same points/draws/refusals across variants. Thirty-two repetitions per case do not establish broad empirical calibration. |
| Finite-grid minimum coverage 7.72% bootstrap limit, 85.15% Wilson and 96.68% Clopper-Pearson; wider Hoeffding bounds lose weak-effect sign detection | [Interval comparison](../output/interval-comparison-2026-10-13/FINDINGS.md), enumerated theory and retained summaries | Completed specified independent synthetic/binomial evidence. Bootstrap limit differs from finite resampling; individual bounds do not resolve dependence, multiplicity or unavailable games. |
| Alpha `0.1.0a2` conservative defaults | [Engineering decision](../output/interval-comparison-2026-10-13/FINDINGS.md), [build receipt](../output/release-alpha-2026-10-14/checks.json) and [publication receipt](../output/release-alpha-2026-10-14/publication.json) | Clopper-Pearson contrastive, Hoeffding pair means and exact-marginal endpoint differences; strict game remains unchanged. Published on PyPI with both download hashes and an isolated registry installation verified on 14 October 2026. |
| Stable `1.0.0` public wheel and source distribution | [Publication receipt](../output/release-1.0.0-2026-10-15/publication.json), [inventory recheck](../output/release-1.0.0-2026-10-15/inventory-recheck.json) and [registry installation](../output/release-1.0.0-2026-10-15/registry-install.json) | Both public artifact hashes and isolated registry installation verified 15 October 2026. Build source `85ce6c316838c995782aadc8c10770acc708339b`; all 36 runtime files match frozen runtime/study source `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`. The public source distribution includes documentation, examples, tests and auditors, while private research outputs are excluded. Software stability does not establish research superiority. |
| Explicit on-reach game and interacting refund decisions | [Retained physical enumeration](../output/refund-interactions-2026-10-13/README.md) and [independent audit](../output/refund-interaction-audits-2026-10-13/independent.json) | Completed at source `2c4adfeb2a364a8116d6edbccbbdac64b413fc9c`: 512 planned branches, eight cases and 718 scripted calls; on-reach state/linked shares `[-.125,.375,0]` and interaction .25 at p=q=.5. Strict game remains distinct and undefined at interior probabilities. |
| Idempotency removes the planted refund selection/retry interaction | [Enumeration controls](../output/refund-interactions-2026-10-13/summary.json) | On-reach consequence shares become `[-.5,0,0]`, interaction zero. Lagged/budget controls retain refusals. This is a programmatic mixture, not a live-model effect. |
| Closed-form on-reach refund reference | Analytic-reference subsection of [the manuscript](manuscript.md), physical payment/policy source, [mechanism specification](../docs/refund-interactions.md), [standalone mathematical check](verify_analytic_references.py) and [SHA-bound receipt](analytic-reference-check.json) | Unsafe exactly-one state target: `v(empty)=1-p(1-q)`, `v(s)=q`, `v(r)=v(sr)=1`; final stop dummy. Therefore `phi_s=-(1-p)(1-q)/2`, `phi_r=(1+p)(1-q)/2`, endpoint `p(1-q)`, interaction `(1-p)(1-q)`. Idempotency and action-selection shares are `[-(1-p),0,0]`. Exact-rational enumeration checked 100 probability/control cases without framework imports, simulator/model calls or saved study inputs. These are ideal mechanism references; finite budgets and unknown evidence retain separate eligibility/refusal rules. |
| Actual permutation sampler works with the refund interaction adapter | Final source tests using two controls, P=32, S=1, E=32 | Engineering regression only: eighteen numeric coefficients within .3 of reference. This tolerance is not empirical calibration; the separately frozen retained study below evaluates repeated sampling. |
| Actual physical permutation sampler retained 2,048 fresh trials, 655,360 branches and 628,535 scripted calls | [Precollection protocol](../output/interaction-sampling-2026-10-15/protocol.json), [all summary rows](../output/interaction-sampling-2026-10-15/summary.json), [execution receipt](../output/interaction-sampling-2026-10-15-execution.json) and [installed checkpoint](../output/interaction-sampling-checkpoint-2026-10-15/checkpoint.json) | Eight declared mechanisms, two separate games, 128 repetitions each, P=32/S=1/E=32, source `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`. All 655,360 planned slots remain: 536,150 completed, 37,423 invalid, 256 failed and 81,531 unstarted. There were zero language-model calls or additional interval-comparison calls. |
| Standalone audit recomputed the retained physical-sampling evidence and summary | [Independent receipt](../output/interaction-sampling-audits-2026-10-15/independent.json), [derived findings](../output/interaction-sampling-findings-2026-10-15/FINDINGS.md) and [complete analysis](../output/interaction-sampling-findings-2026-10-15/analysis.json) | Passed 44,698,925 assertions across 2,048 trials, 655,360 branches, 4,210 full traces and 628,535 actual scripted calls, with zero generation calls. Receipt source is `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9`; original 52-file manifest SHA-256 is `3ee00dfb6ac66db219bc25b1248a1645b8f86deeecae6c9c46a8419cc1235af4`. Auditor imports no framework implementation. Derived CSV/JSON and their manifest remain outside the unchanged original collection. Computational independence does not establish independent human verification or source authenticity. |
| Shared-draw physical-sampling intervals expose a precision/detection tradeoff and distinct refusal boundaries | Repeated-sampling subsection and all-eight-case table in [the manuscript](manuscript.md), with [all target/position/game/variant rows](../output/interaction-sampling-2026-10-15/summary.json) | On-reach global-consequence retry at p=q=.5: normal coverage 118/128, mean width .226, sign detection 128/128; Hoeffding coverage 128/128, width .960, sign detection 8/128. At p=.2,q=.8, the on-reach global-consequence endpoint normal coverage is 92/128 versus exact-marginal 128/128, with widths .114/.319. In the on-reach game, all lagged-consequence coefficients are unknown; all budget coefficient vectors unavailable despite a defined ideal reference; missing provenance refuses linked consequence while global consequence remains assessable. Nondeterministic strict coefficient games remain undefined. A finite numeric strict interaction and a finite numeric strict linked endpoint without provenance remain reference-ineligible. Interaction diagnostics have no interval, coverage or calibrated sign result. Finite rates include Wilson uncertainty; variants/reused targets are not independent replications. |
| Capped validation completed 24/24 episodes and 59 local model calls, with no failed/unstarted episodes | [Frozen validation](../output/local-validation-2026-10-14/README.md), protocol, execution and saved-data audit | Completed exploratory integration at source `2c4adfeb2a364a8116d6edbccbbdac64b413fc9c` and retained candidate wheel, distinct from the final release. Audit passed 2,227 assertions and seven corrupted-copy checks. Validation family is now exposed; held-out reserve not generated. |
| v1 has six structured contradictions among ten assessable claims; v2 has no definite statuses | [All-case findings](../output/local-validation-2026-10-14/FINDINGS.md) and [audit rows](../output/local-validation-2026-10-14/audit.json) | v1 claim coverage 12/12, two unassessable claims; v2 coverage 0/12, contradiction rate 0/0 undefined. Fixed profile order, overlapping fault conditions and two repetitions per case prevent generalization or calibrated-uncertainty claims. |
| Some v2 rationales retain positive processing language despite unknown statuses | [Retained rationale annotations](../output/local-validation-2026-10-14/rationale-audit.json) | Seven of twelve final rationales have affirmative processing clauses; five also hedge verification. These labels arose in an unblinded annotation pass within the AI-assisted development workflow; no independent human verification or inter-rater reliability is established. The historical artifact's label “single unblinded manual annotation” does not establish independent human annotation. Labels are descriptive, not ground-truth language classification. A literal second committed attempt can be true while the exactly-one task contract is violated. |
| Better false-claim or factor-recovery performance than verifier-plus-CAR/joint-fault methods | [Study plan](../docs/study-plan.md), [CAR reproduction plan](../docs/car-reproduction-plan.md) | Unestablished. Needs faithful matched baselines, held-out families, independent reference effects and cost reporting. |
| Python distribution available publicly on PyPI | [Public stable version](https://pypi.org/project/consequa-x/1.0.0/), [publication receipt](../output/release-1.0.0-2026-10-15/publication.json) and [registry installation](../output/release-1.0.0-2026-10-15/registry-install.json) | Public stable package publication and isolated registry installation verified 15 October 2026. This does not establish public access to the complete research archive. |
| Private research repository with public MIT package | Maintainer's 15 October 2026 visibility decision and explicit public-PyPI instruction | Source history and retained studies are access-controlled. Do not describe the repository or full raw-evidence archive as publicly accessible. Public immutable research archiving and reviewer access remain unresolved. |
| Existing PyPI account `devraj0502` | [Official public profile](https://pypi.org/user/devraj0502/), maintainer confirmation and successful alpha2 publication receipt | Identity/display-name check completed 13 October 2026; working upload and registry artifact verification completed 14 October 2026. Credentials are excluded from artifacts. |

## Numeric insertion rules

1. Insert final values from an audited structured output tied to a frozen source
   and study protocol. Retain the exact numerator, denominator and unavailable
   count for every rate.
2. Keep availability, reference eligibility and interval coverage separate.
   Undefined references and unknown outcomes do not supply a coverage denominator.
3. Do not pool state and linked targets that reuse the same outcomes as independent
   samples, or treat repeated seeds on one template as independent task families.
4. Label finite-distribution theory, finite bootstrap output, exploratory replay
   simulation and held-out model studies separately.
5. Keep historical legacy intervals unchanged. New intervals computed on shared
   fresh evidence are a separately declared study, with their own source revision.
6. Update the manuscript's abstract and conclusions only when the new evidence
   justifies a change; standard uncertainty alternatives do not create estimator
   novelty.

## Reproducing the analytic reference check

From the repository root, use Python's standard library only:

```console
python paper/verify_analytic_references.py --output paper/analytic-reference-check-fresh.json
```

The output must be a new file. The retained receipt binds its script SHA-256 and
lists every case: the exact grid `0, 1/5, 1/2, 4/5, 1` for both `p` and `q`,
both idempotency settings, and action/consequence targets. This yields 100
control cases, 800 coalition values, 3,200 weighted Boolean components and 600
permutation orders. Every comparison uses exact fractions. The script imports
no framework code, reads no retained study files, makes no model/network calls
and does not execute the simulator. It independently checks the mathematical
four-component law and six-order allocation against the printed closed forms;
it is not an independent execution audit or a sampling-calibration experiment.
Assumptions and limits are included in the receipt. Repeated targets and control
settings are not independent empirical replications.

## Submission requirements still open

The protocol/software manuscript is complete within its stated claims; a
confirmatory superiority paper is a separate research objective. That larger
study still needs a precision/sample-size justification, held-out template and
fault-composition populations, replay-fidelity assessment, matched strong
comparisons, joint-fault scope, ablations and final analysis. Generic IEEE
conference formatting is selected, with no specific venue yet. Before submission,
confirm author/contributor credit, any affiliation, conflict/funding disclosures,
venue-specific requirements, and a reviewer-access or immutable-archive plan.
