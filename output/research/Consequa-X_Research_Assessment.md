# Consequa-X: initial research assessment

Reviewed 4 October 2026. Intended outcome: a research paper and a reusable framework distributed through PyPI and/or npm.

Source brief: [Consequa-X Research Brief](../../docs/research/Consequa-X_Research_Brief.pdf), all 20 pages. This assessment treats the document's implementation directives as proposed project content. At the time of this initial assessment, no framework implementation, experiments, registry publication, or external writes had been performed. The subsequent alpha build is documented in the repository README.

## Assessment

The problem is worth investigating: an agent's selected action, returned tool response, reported outcome assessment, and actual external effect can disagree. However, the brief's central combination is not yet an established novel research contribution. The closest work already supplies much of it.

The strongest candidate direction is **evidence-aware attribution of stochastic LLM behaviour to action-linked external consequences under ambiguous execution, imperfect observation, and incomplete provenance**. This is our research judgment, not a claim that the literature gap has been proved unoccupied. Recent work directly occupies the broad connection between agent decisions, infrastructure faults, and executed financial effects, so the original paper pitch needs narrowing.

The framework can be useful even if its first version uses existing attribution estimators. A paper must distinguish the contribution of its protocol, benchmark, and engineering from any demonstrated improvement in attribution methodology.

## What the brief proposes

The proposal connects upstream context to a decision, execution attempt, response, reported belief, external effect, and independent verification. It suggests a Causal Consequence Graph, counterfactual replay, a fault-injected benchmark, and TypeScript runtime adapters paired with Python research tooling.

Its refund example is a good representation test: a refund commits, the acknowledgement is lost, the agent reports failure, and readback finds the refund. That example alone does not establish a new causal attribution method.

Preserve the brief's distinction between safe decision replay with mocked reads and complete counterfactual execution in isolated simulated worlds. Those modes support different claims and should be explicit in the public API.

## Literature audit

The nine research references R3-R11 resolve to papers with matching titles and corresponding author names. The two documentation references also resolve. Publication status should be tracked per paper rather than grouping all 2026 work as unpublished preprints.

| Brief reference | Verified source and research implication |
| --- | --- |
| R1: Agents SDK tracing | [Official tracing documentation](https://openai.github.io/openai-agents-python/tracing/). Reusable instrumentation; tracing itself is not the contribution. |
| R2: OpenInference | [Semantic conventions](https://arize-ai.github.io/openinference/spec/). Use an adapter and preserve original span identities. |
| R3: Qian et al., agentic attribution | [The Why Behind the Action](https://arxiv.org/abs/2601.15075). Historical trajectory and evidence attribution already exist; explaining why a tool was selected is insufficient novelty. |
| R4: Shah, CAR | [Causal Agent Replay](https://arxiv.org/abs/2606.08275). Repeated interventions, uncertainty, and arbitrary trajectory outcome scoring substantially overlap with the proposed effect estimator. |
| R5: Chen et al., long-horizon attribution | [Long-Horizon Agent Trajectory Attribution](https://arxiv.org/abs/2608.06909). Existing benchmark and fine-grained attribution framework should inform long-range evaluation. |
| R6: Zhang et al., Who&When | [ICML 2025 / PMLR record](https://proceedings.mlr.press/v267/zhang25cq.html). Failure agent/step localization is established prior work. |
| R7: Liu et al., Who&When Pro | [Who&When Pro](https://arxiv.org/abs/2607.09996). Richer failure attribution evaluation exists; outcome information can also encourage shortcuts. |
| R8: Barke et al., AgentRx | [AgentRx](https://arxiv.org/abs/2602.02475). ArXiv metadata reports acceptance to EMNLP Findings 2026; v2 was revised 31 August. It is closer to constraint-based failure diagnosis than ordinary trace summarization. |
| R9: Mansoor, Phadke, Rana | [Verified Tool Calls](https://arxiv.org/abs/2608.02645). Read-only postcondition verification, response/effect separation, and verification before retry already exist. |
| R10: Zihao Wang | [Callability Is Not Operability](https://arxiv.org/abs/2608.23628). Matched interface experiments already include false outcome claims, response loss, partial completion, and authoritative-state verification. |
| R11: Zexun Wang | [CAVA](https://arxiv.org/abs/2607.13716). Canonical action identity, approval binding, and receipts are foundations, not novel components here. |

R10 and R11 are by different people: Zihao Wang and Zexun Wang. Their shared abbreviation in the brief obscures that distinction. The inspected R9-R11 arXiv records do not establish a peer-reviewed venue.

### Closest overlaps needing explicit treatment

The most direct omitted paper is **CausalLoss-Fin**, submitted 22 September 2026. It jointly intervenes on decisions and infrastructure faults and attributes executed financial loss. Its attribution experiments use deterministic programmatic policies rather than LLM agents. Its infrastructure faults affect what the policy observes; this is a possible scope distinction from faults that directly alter tool commits. Extending to stochastic LLM context attribution and fallible verification is a candidate contribution, not sufficient novelty by itself. Its comparator is explicitly CAR-shaped, not a reproduction of CAR. [CausalLoss-Fin](https://arxiv.org/html/2609.25960v1).

Its underlying **FinalityBench** already supplies hidden canonical events, separately faulted financial-system views, and effect-level grading. Its indistinguishable task pairs are especially useful for testing when an explanation must abstain. Evaluate reuse before building a financial benchmark from scratch. [FinalityBench](https://arxiv.org/abs/2609.04706).

CAR's outcome function is already general. Its paper defines a user-supplied score over trajectories, and its code exposes an asynchronous outcome interface. Consequently, changing the target from action choice to a verified outcome does not by itself introduce a new estimator. The inspected implementation lacks native branch-specific world snapshots and dedicated belief/effect records; these are concrete adapter opportunities. [CAR method](https://arxiv.org/html/2606.08275v1), [audited outcome interface](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/outcome/functions.py#L27-L40).

The verification literature is closer than the brief implies. Verified Tool Calls already separates response and effect; Callability Is Not Operability also measures incorrect terminal assessments. In the latter, verification benefit varies by model, so improved calibration must remain a hypothesis rather than an architectural guarantee. [Verified Tool Calls method](https://arxiv.org/html/2608.02645v1), [Callability v2](https://arxiv.org/html/2608.23628v2).

Add the omitted **Policy-Conditioned Counterfactual Credit** paper. It already estimates changes in final verified success under specified interventions and a frozen continuation policy, with intervention-validity gating. Its purpose is reinforcement-learning credit, whereas our proposed purpose is post-hoc external-effect diagnosis; nevertheless, verified-target counterfactual credit is occupied territory. [PCCC / CVT-RL](https://arxiv.org/html/2606.05263).

Add **ConsequenceBench** before naming or building ConseqBench. Its development preview contains consequential worlds, independent readback, retries, delayed visibility, partial effects, and causal/invariance variants. It is not established as a qualified benchmark by its own release statement. The inspected material does not supply the proposed upstream post-hoc trajectory attribution, but benchmark infrastructure and naming overlap are substantial. Consider extending compatible worlds and use a distinctive dataset name. [Repository](https://github.com/yuvin-labs/consequencebench), [lifecycle protocol](https://github.com/yuvin-labs/consequencebench/blob/main/docs/CONSEQUENCE_LIFECYCLE_PROTOCOL.md).

Also include **CausalFlow**, which intervenes on execution steps and propagates affected descendants to evaluate counterfactual repairs. This strengthens the need to distinguish real simulated re-execution from predicted counterfactual outcomes. [CausalFlow](https://arxiv.org/html/2605.25338v1). **AXIS** provides earlier simulator-based explanations of multi-agent behaviour, though its agent setting differs from consequential LLM tool operations. [AXIS](https://arxiv.org/abs/2505.17801).

**REFLECT** already feeds intervention-supported outcome verification into silent-failure attribution. [REFLECT](https://arxiv.org/abs/2606.09071). **LongRCA Bench** is an additional recent source for evaluation beyond synthetic faults; its September revision supplies human-labeled long-horizon failures. [LongRCA Bench](https://arxiv.org/abs/2608.15242).

**EffectWitness** is a relevant engineering comparison, not evidence of a mature research benchmark. Its pre-alpha fixtures separate client observations from durable synthetic effects and test response loss and reconciliation. [EffectWitness](https://github.com/tiramitree/effect-witness).

These checks are a targeted literature audit, not a systematic review or independent reproduction of published results.

## Sharpen the research claim

Working research question:

> With the same trace, verification evidence, provenance, candidate causal variables, replay access, and compute budget, can an evidence-aware consequence attribution protocol reduce false causal explanations for stochastic LLM agents compared with existing replay and joint-fault attribution methods?

There are three possible contributions, which must be evaluated separately:

1. A protocol that separates factual outcomes, effect origin, agent assessments, and experimental influence estimates, including insufficient-evidence results.
2. A benchmark extension that tests upstream responsibility for effects under retries, interference, and imperfect observation.
3. An attribution improvement over modular verifier-plus-CAR and an appropriately adapted joint-fault method. Claim this only if experiments demonstrate it.

A graph joining existing components is useful infrastructure, but does not establish the third contribution.

### Avoid a trivial consequence target

Our derivation: if action selection is A, execution success is an independent binary Z, and the target consequence is Y = A * Z, then an upstream intervention has effect:

`effect_on_Y = P(Z = 1) * effect_on_A`

Under these assumptions, consequence attribution rescales action attribution and preserves its ranking. Reliable atomic tools are not sufficient to ensure this equivalence if parameters or later actions can still differ.

The pilot must therefore include cases where upstream context changes arguments, retries, idempotency, or alternative routes. A strong example is identical initial refund selection, followed by different retry behaviour after response loss. An upstream retry instruction can cause a second partial refund even though action-selection attribution is unchanged. The payment simulator must permit both refunds within its balance constraints; do not invent a provider that accepts unlimited duplicate full refunds.

## Repair the formal model

Use separate objects for:

| Object | Meaning |
| --- | --- |
| H | Externally available trajectory and context |
| A | Intended action with typed parameters |
| E | An execution attempt belonging to a logical operation |
| S | External world state, with faults and other actors represented |
| R | Returned response or absence of acknowledgement |
| B | Timestamped agent-reported outcome assessment |
| O | Readback observation, its source, and freshness |
| Y(C,T) | Simulator-ground-truth consequence for contract C and horizon T |
| V(C,T) | Verifier conclusion from observations and evidence |

In controlled experiments, Y is the outcome target and V is a fallible measurement. In deployed systems, report V and its evidentiary limits; do not silently equate it with inaccessible world truth.

A contract should specify whether it asks for existence, correct parameters, exactly one effect, completion by a deadline, or persistence through a stability interval. An initially satisfied contract can later cease to hold. Preserve that observation history rather than mixing reversal, timeout, and truth values in one enum.

For a valid intervention I_i, estimate the difference between expected outcomes under the original and intervened continuation, with initial world state and the designated context fixed. Specify the continuation policy, intervention family, horizon, and distribution of agent/environment randomness. A signed effect estimate is not a percentage share of responsibility and need not sum to one.

Removing evidence just before the final decision while retaining its downstream summaries measures local context sensitivity. To estimate its total trajectory effect, intervene where it originally entered and recompute affected descendants. These are different estimands. CAR and PCCC should inform this specification, rather than be reintroduced under new terminology.

### Evidence and origin

Postcondition satisfaction, provider-confirmed origin, and counterfactual influence are distinct claims. A second actor can make the requested state true even when the agent's attempt failed. Caller-provided operation identifiers help correlate effects; identical argument hashes alone cannot distinguish retries from separate legitimate requests. [AWS idempotency guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).

Preserve a logical operation ID, attempt ID, provider request/effect ID, and entity ID separately. A semantic fingerprint describes equivalent action content; it is not a unique operation identity. [CAVA method](https://arxiv.org/html/2607.13716v1).

Graph edges should state whether they encode temporal order, declared dependency, provider-origin evidence, or an experimentally estimated effect. A temporal arrow must not become a causal claim merely by appearing in the same graph.

### Reported assessments

Capture B before revealing verifier evidence. Prefer structured success/failure/partial/unknown assessments with the evidence the agent cites. This measures reported assessment, not hidden mental belief. Generated explanations can omit influential context. [Turpin et al.](https://arxiv.org/abs/2305.04388).

A timeout is ambiguous evidence; it does not necessarily mean the tool lied or the mutation was non-atomic. If verification is unknown, a failure claim may be unsupported but is not demonstrably contradicted. Score unsupported certainty separately from claims contradicted by adequate evidence.

## First experiment

Begin with one refunds environment and several task templates, not a dashboard or a 6,000-run study. Use deterministic policies to validate mechanics, then stochastic LLM policies to test attribution.

| Case family | What it tests |
| --- | --- |
| Clean success; failure before commit | Correct control diagnosis |
| Timeout after commit; false success | Response/effect disagreement |
| Lost response followed by retry, with and without a stable key | Different consequences despite the same initial action |
| Wrong amount or wrong payment | Parameter-specific consequence attribution |
| Agent fails; another actor produces the same desired state | False responsibility claims |
| Delayed readback; stale observation | Unknown and freshness handling |
| Later compensation or reversal where the domain permits it | Time-bounded contracts |
| Ignored, redundant, interacting, and distant upstream factors | Genuine intervention effects rather than planted-label shortcuts |

Start with approximately 300-500 factual diagnostic runs as a development pilot, then budget a smaller causal-replay subset separately. These are planning values, not a statistical adequacy guarantee. Reject incompatible fault/task combinations instead of blindly crossing all factors.

Required comparators:

1. Trace-only LLM explanation: quantifies the benefit of additional evidence.
2. LLM explanation with the same readback and provenance: tests whether a schema alone explains the benefit.
3. Action-targeted leave-one-out with matched replay budget.
4. CAR with the same verifier, isolated snapshots, target contracts, and evidence: the crucial modular baseline.
5. A faithful CausalLoss-style joint decision/fault comparator where applicable, with adaptations and unavailable features documented.
6. Consequa-X under the same conditions.
7. Simulator oracle as an evaluation ceiling, with gold records unavailable to explainers.

Match candidate variable scope as well as information. If only Consequa-X can intervene on an infrastructure fault, improved infrastructure attribution may simply reflect a missing variable in the comparator. Report restricted agent-only results separately from comparisons in which every applicable method can name and intervene on the same faults.

Keep actor observations, explainer evidence, and evaluator-only truth in separate stores. A planted policy snippet is only a candidate cause: an LLM may ignore it. Gold factor effects require independent intervention estimates or fully specified deterministic mechanisms. Hold out templates and fault compositions, not only random seeds.

Primary metrics should measure false causal claims, incorrect effect-origin attribution, and consequence-specific factor recovery against independent effect estimates. Evaluate unknown/abstention error together with coverage so a method cannot win by always refusing. Report outcome accuracy, multi-label failure diagnosis, reported-assessment accuracy, cost, and latency separately.

Twenty replays per condition are a debugging starting point. For two independent Bernoulli arms near probability 0.5, 20 samples per arm give an approximate normal 95% margin of about 0.31 for their difference. This is an illustrative calculation, not the chosen final interval estimator. Choose sample counts using pilot variance and desired precision; aggregate uncertainty by task/template clusters and report per-model effects.

Budget factual runs and replay runs separately. Under a naive design with ten candidates, 20 fresh original and 20 intervened samples per candidate, 6,000 factual runs imply about 2.406 million total trajectories. Reusing one 20-sample original arm per factual run lowers that illustrative total to 1.326 million, before coalition methods, additional models, or multi-step calls. Branch pairing and caching must preserve the declared estimand and world isolation.

Proceed to multiple domains after establishing a measurable gap in the equal-evidence modular baseline. If Consequa-X only beats trace-only methods, narrow the paper to an evidence protocol/benchmark contribution rather than claiming a superior causal estimator.

## Publishable framework boundary

Recommendation: implement the research engine in Python first and distribute it through **PyPI**, where users install it with pip. Add a small TypeScript/npm runtime adapter when connecting existing Consequa components. Registry publication is a later deliverable, not completed work in this assessment.

| Layer | Proposed responsibility |
| --- | --- |
| Shared specification | Versioned JSON Schema, semantic definitions, and cross-language conformance fixtures |
| Python package | Graph construction, typed interventions, replay adapters, attribution estimates, uncertainty, explanation records |
| TypeScript package | Runtime action/attempt registration, contracts, response/assessment capture, read-only verification adapters, JSONL export |
| Benchmark tooling | Simulators, isolated snapshots, hidden gold logs, fault plans, experiments, evaluation |

Keep benchmark dependencies optional. Users should be able to ingest a trace and evidence without installing a simulator or an LLM provider. Do not initially duplicate the estimators in both languages.

The public interfaces should cover `record_action`, `record_attempt`, `observe`, `verify`, `build_graph`, and `explain`, plus an optional replay protocol. Replay adapters must declare decision-only versus complete-world capability and snapshot isolation. Explanations should expose separate attribution targets and explicit insufficient-evidence results. Provider-specific verifiers belong behind adapters.

Package names such as `consequa-x` and a scoped npm name are tentative; availability and ownership have not been checked. The selected workspace contains no existing Consequa runtime code to assess, so compatibility with that repository remains unverified.

Before release, require documented semantics, a license, installable distributions, conformance fixtures, an offline demo, reproducible evaluation configurations, and clean-environment install tests. Python's official packaging guide covers project metadata, distributions, and TestPyPI validation. [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/). For npm, official trusted publishing supports automated provenance under documented conditions. This package build provenance is separate from runtime action provenance. [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/).

## Milestones and decision gates

1. **Research specification:** finish the overlap matrix, formal estimands, outcome horizons, baseline contracts, hidden-gold boundaries, and replay budget. Pin cited paper/code versions.
2. **Representation prototype:** demonstrate committed refund plus lost acknowledgement, reported failure, and independent readback; also demonstrate another actor satisfying the postcondition without agent-origin evidence.
3. **Causal pilot:** show whether a retry/parameter/context factor changes consequences beyond action selection, and compare against verifier-plus-CAR with equal information and compute.
4. **Research and library release:** expand only justified cases/domains, freeze the benchmark, run ablations and reproducibility checks, and prepare the paper and installable package from the same versioned artifacts.

The first milestone is complete only when the proposed claim and comparison are precise. The second establishes engineering correctness. The third determines whether a methodological paper is justified. The fourth requires actual results; the brief's example attribution scores and confidence intervals are illustrations, not empirical findings.

One concrete brief correction before implementation: the Razorpay example labels INR 5,000 but passes `amount: 5000`. Razorpay amounts use currency subunits, so that raw value represents INR 50; INR 5,000 requires `500000` paise. Store currency and units explicitly. Its refund documentation also describes the `X-Refund-Idempotency` header and stable-key retry semantics. [Official refund documentation source](https://github.com/razorpay/markdown-docs/blob/master/api/refunds/normal-refunds-idempotent.md).

The next deliverable should be a precise proposal and pilot protocol built around these decision gates, followed by the smallest reusable implementation. Publication novelty remains to be demonstrated by that work.
