# Consequa-X: An Evidence and Intervention Protocol for Consequential Agent Actions

Devrajsinh Jhala

Working manuscript, 13 October 2026. This draft reports completed preliminary
evidence and identifies experiments still required. It is not a submitted or
accepted paper. The framework is an alpha research implementation.

## Abstract

An agent's selected operation, returned tool response, reported assessment and
external effect can disagree. A refund can commit despite a lost acknowledgement;
a desired state can also be produced by another actor. Explaining such episodes
requires explicit outcome contracts, evidence and origin boundaries, and a
declared intervention experiment. We present Consequa-X, a Python framework that
records these distinctions, verifies temporal refund contracts from independent
readback, and executes isolated policy and decision replays while retaining
unknown evidence, invalid interventions, provider failures and exhausted budgets.
Its estimators adapt existing contrastive and permutation Shapley methods; the
candidate contribution is the evidence and intervention protocol and its
reproducibility infrastructure. An audited development study retained all 1,280
synthetic calibration trials. Several nominal 95% intervals substantially
undercovered analytically specified effects. A separate audited follow-up retained
384 new trials comparing interval methods on shared draws: conservative bounds
avoided homogeneous-sample certainty but substantially reduced weak-effect sign
detection at the declared budget. A small local
language-model pilot demonstrated auditable integration and assessment/effect
disagreement, rather than generalization or attribution superiority. Held-out
templates, matched strong baselines, interaction experiments and a final
statistical protocol remain necessary for stronger empirical claims.

## 1. Introduction

A consequential tool operation has several observable stages. The agent selects
an operation, the runtime dispatches one or more attempts, the tool returns a
response or times out, and the agent reports an assessment. An external service
may commit an effect before a response is lost. Repeating the operation can then
create a duplicate, unless its identity and idempotency semantics are preserved.
Conversely, a successful acknowledgement need not establish a complete effect.
These distinctions affect what an explanation can support.

Outcome and origin also differ. A refund visible in readback may satisfy a state
contract while remaining unlinked to the current agent. Evidence of a logical
operation's identity establishes an origin link; it does not establish that the
operation was necessary for the observed state. An intervention-based effect is
a third claim, concerning a specified alternative continuation and distribution
of outcomes.

Consequa-X makes these claims separately inspectable. Its current domain is an
isolated synthetic refund environment with finite balances, typed policy
decisions, temporal contracts, optional provenance and controlled execution or
observation faults. The implementation includes portable evidence records,
verification and explanation exports, a local Ollama policy adapter, replay
primitives and attribution experiments. Captured reported assessments are
observable outputs; they are not measurements of hidden reasoning or internal
belief.

The contributions supported at this stage are:

1. An explicit protocol connecting operation identity, attempts, responses,
   reported assessments, independent readback, verifier conclusions and origin.
2. Isolated replay infrastructure with declared intervention semantics, actual
   call accounting, complete failure/refusal receipts and separated evaluator
   truth.
3. Auditable development evidence exposing uncertainty failure in a specified
   binary replay adaptation, together with a separately frozen shared-draw
   comparison of conservative interval alternatives.

Whether this protocol improves attribution over equally informed modular
baselines remains an empirical question. Applying a verified target to an
existing replay estimator does not itself establish estimator novelty.

## 2. Related work and comparison boundary

**Counterfactual attribution.** CAR defines user-supplied trajectory outcome
scores, executed same-policy interventions, contrastive suffix replay and
permutation Shapley attribution. Consequa-X uses an independently written binary
adaptation of those ideas. Its world/evidence adapter, refusal rules and interval
choices require explicit comparison, rather than a claim to have introduced
verified-outcome replay. [Shah, CAR v1](https://arxiv.org/html/2606.08275v1).

PCCC estimates intervention-specific changes in final verified success under a
frozen continuation policy for reinforcement-learning credit. Its task differs
from post-hoc external-effect diagnosis, but its verified target and
intervention-validity treatment overlap with this work.
[Meng, PCCC v1](https://arxiv.org/html/2606.05263v1).

**Agent and infrastructure variables.** CausalLoss-Fin intervenes on decisions
and individually repairable infrastructure faults, with signed loss decomposition
and fault allocations. Its experiments evaluate deterministic programmatic
policies, limiting transfer to stochastic language policies. It nevertheless
occupies the broad combination of financial effects and joint decision/fault
attribution. A comparison must give each applicable method the same candidate
variables; an agent-only method cannot identify an omitted infrastructure
variable. [Sharma, CausalLoss-Fin v1](https://arxiv.org/html/2609.25960v1).

**Verification and operational semantics.** Verified Tool Calls already separates
responses from effects and uses read-only postcondition verification with unknown
results and verify-before-retry logic. Callability Is Not Operability evaluates
interface mechanisms and terminal claims under controlled operational ambiguity;
its verification effects vary by model. Outcome verification, three-valued
status and response/effect separation are therefore foundations and comparison
requirements, rather than unique contributions here.
[Mansoor, Phadke and Rana v1](https://arxiv.org/html/2608.02645v1),
[Wang v2](https://arxiv.org/html/2608.23628v2).

These are targeted primary-source checks, not a systematic review or independent
reproduction of their reported results. The
[source audit](source-audit.md) pins inspected versions. The wider
[research assessment](../output/research/Consequa-X_Research_Assessment.md)
identifies additional attribution and benchmark literature that must be refreshed
before submission.

## 3. Evidence protocol

### 3.1 Objects and trust

Let `H` denote the policy-visible history; `A` a logical operation with typed
parameters; `E` an execution attempt; `R` the response; `B` a timestamped reported
assessment; and `O` a readback observation. A contract `C` specifies parameters,
count, deadline and stability horizon. `Y(C,T)` is evaluator-only simulator truth.
`V(C,T)` is the verifier's evidence-supported conclusion: satisfied, violated or
unknown. Origin is recorded separately as confirmed, other actor or unknown.

The verifier receives portable traces and readback observations, rather than
injected fault labels or the simulator's gold event log. Source authority, query
scope, completeness and watermark declarations are trusted adapter inputs.
Schema validation and hashes check structure and changed bytes; they do not
authenticate a provider or certify a consistency guarantee.

The built-in refund contract uses integer currency minor units and a fixed
predicate interpreter. An eligible effect must match the payment, amount and
currency, commit in the declared time window and survive the stability interval.
An exact-count contract must also retain the specified count throughout that
interval. Insufficient horizon coverage or incomplete readback yields unknown;
absence in a stale snapshot is not a confirmed violation.

### 3.2 Targets and origin

The replay adapter exposes three distinct targets:

| Target | Positive meaning |
| --- | --- |
| Action | The declared initial refund action was selected. |
| Consequence | Independent readback supports the global state contract. |
| Action-linked consequence | The global contract is satisfied and qualifying witnesses support the declared operation linkage/count rule. |

An observed state violation remains false for the linked target. A satisfied
state with exclusively external qualifying effects is false for that target;
insufficient provenance can instead be unknown. The linked target combines
global state satisfaction and supported witnesses. It does not reconstruct an
agent-only filtered world. Its precise positive-witness/count rules are part of
the versioned target contract.

For a known binary target `Z`, define bad outcome `X = 1 - Z`. Unknown verification
does not acquire a numeric label. Returned acknowledgements and reported
assessments do not substitute for independent outcome evidence.

### 3.3 Worlds, receipts and budgets

Every replay branch starts an isolated payment world with the declared initial
state, world seed, template and contract. Factual decisions may be held; fresh
decisions pass through the same policy boundary. Reused held replies consume no
fresh calls. Every attempted provider call, including a protocol or provider
failure, consumes one unit of the shared call budget.

Exports retain the full planned schedule, reached requests/replies, completed
traces, unknown labels, errors, invalidity and unstarted slots. Unknown, failed or
unstarted branches are neither dropped nor redrawn. Simulator gold is exported
separately from evidence available to an explainer. Distinct model phase keys
support reproducibility and accounting; keys alone do not prove independence or
determinism of an arbitrary model server.

## 4. Declared replay estimands

### 4.1 Conditional suffix effects

At factual position `k`, prefix replay forces captured decisions before `k`,
resamples decision `k` and completes the suffix under the declared policy. A
branch can be shorter or longer than the factual trace within the attempt budget.
For factual bad label `x_f`, the conditional contrastive estimand is

```text
gamma_k = E[X under prefix-held, suffix-resampled replay at k] - x_f
gamma_hat_k = mean(X_changed_1, ..., X_changed_K) - x_f.
```

The factual term is one observed constant, not a separately estimated population
rate. Negative values indicate that replay reduces bad outcomes relative to
that observation. Because the suffix is resampled, an early irrelevant position
can exhibit an effect through a later stochastic decision. A latest-rescue rule
selects the latest position with a negative estimate and interval upper bound
strictly below zero, only when every planned position for that target is
estimable. This nominal selection rule has no simultaneous coverage guarantee
and does not establish a unique actual cause.

An estimate is refused when any planned target draw is unknown, failed or
unstarted. Available complete target estimates reuse the same recorded branches;
they do not issue extra policy calls.

### 4.2 Held-decision games and signed Shapley values

Let `N` be the set of reached factual decision positions. In the strict game,
coalition `S` requests that captured decisions at positions in `S` be forced;
other reached positions are sampled from the policy. A held decision must match
the reached typed stage and remain valid for the current public request. If an
earlier decision terminates before a requested held position, that draw is
invalid. A population game cannot be assigned numeric reference values merely
because a finite sample happened to avoid invalidity.

For a well-defined game, with all required outcome laws known,

```text
v(S) = E[X under the declared held-decision intervention S]
phi_i = sum over S subset of N without i:
        |S|! (n-|S|-1)! / n! * [v(S union {i}) - v(S)].
```

Positive contributions mean holding the factual decision increases bad outcomes;
negative contributions are protective. They are signed probability differences,
not percentage responsibility shares.
[Shapley's value](https://www.rand.org/pubs/papers/P295.html) is an existing
allocation rule.

The sampler evaluates a permutation and its reverse with fresh evaluations at
each coalition occurrence. Adjacent marginals share their encountered coalition
value, so each walk telescopes. The forward and reverse marginal vectors are
averaged into one pair vector; the estimate averages `P` pair vectors. Pairs,
rather than the two walks, are the sampling units. Repeated coalition occurrences
are not cached across pairs. Unknown, invalid, failed or unstarted path draws
refuse the entire affected target vector.

Empty and full coalitions are also sampled independently outside the walks. Their
full-minus-empty difference diagnoses endpoint agreement; its discrepancy from
the coefficient sum is descriptive. Contributions are not normalized to erase
that discrepancy. Endpoint availability cannot repair an undefined path game.

An optional **on-reach** game is under development. It applies a held decision
only when the branch reaches its factual position and records inactive held
positions after normal termination. This defines a different intervention game,
rather than silently repairing the strict game. Reached incompatible operations
remain invalid. Its implementation and the planned interacting refund mechanism
must be validated separately before results are inserted here.

### 4.3 Uncertainty methods and assumptions

The retained calibration probe used an empirical percentile bootstrap for
contrastive effects and normal pair-mean/endpoints intervals for Shapley replay.
These legacy methods are preserved as comparators. Their nominal confidence is
not an established coverage guarantee for the implemented sampling regime.

A separate interval study compares the same contrastive samples using bootstrap,
Wilson and equal-tailed Clopper-Pearson bounds. Under fully known independent,
identically distributed Bernoulli draws, a binomial interval `[L,U]` for the
changed bad probability gives `[L-x_f,U-x_f]` for the conditional contrastive
effect. Clopper-Pearson tail inversion is conservative under that model; Wilson
is approximate. [NIST's binomial interval definitions](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).

Signed pair values lie in `[-1,1]`. For independent pair vectors sampled from the
declared game, a two-sided Hoeffding bound has half-width

```text
h = 2 * sqrt(log(2/alpha) / (2*P)), with confidence 1-alpha.
```

The interval is clipped to the parameter domain `[-1,1]`. At `P=16` and confidence
.95 its half-width is approximately .6791, which can greatly reduce sign
detection. This is a transparent precision cost, not evidence of better effect
estimation. [Hoeffding's bounded-sum inequalities](https://doi.org/10.1080/01621459.1963.10500830).

For independently sampled binary endpoints, separate binomial bounds at
confidence `1-alpha/2` yield `[L_full-U_empty, U_full-L_empty]`. The union bound
requires valid marginal binomial sampling; it does not require between-arm
independence for its coverage argument. These individual bounds do not provide
simultaneous intervals over all players, targets or searched loci. They do not
resolve verifier error, dependent model continuations, selective availability
or template-level generalization. Alpha `0.1.0a2` selects Clopper-Pearson for
contrastive effects, Hoeffding for pair means and split-allowance exact binomial
endpoint differences as engineering defaults. Legacy methods remain explicit
options and frozen historical collection methods. The strict coalition game
retains its existing validity/refusal semantics.

## 5. Completed preliminary evidence

### 5.1 Synthetic replay calibration

The retained study froze source
`9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0` and its protocol before execution. Ten
declared cases used 128 repetitions each: 16 contrastive draws per position, 16
permutation/reverse pairs, one draw per coalition occurrence, 16 draws per
endpoint, 2,000 bootstrap resamples and confidence .95. Each method counted its
own factual recording within a 400-call cap; the deliberate budget control used
three. No language model was called.

All 1,280 trials were retained, with 289,709 actual synthetic policy calls.
The paired methods' 2,560 factual captures had no failures or disagreements.
Of 223,232 planned branches, 198,690 completed, 4,062 were invalid, 256 failed
at the intentional cap and 20,224 remained unstarted. Two independent auditors
checked saved statistics, seeded outcomes, receipts and the preselected detailed
traces. Their scripts and outputs remain with the
[retained findings](../output/calibration-probe-2026-10-11/FINDINGS.md).

Selected consequence results for the protective stop's position 1 are:

| Retry probability q | Contrastive coverage | Shapley coverage |
| --- | --- | --- |
| .1 | 100/128 (78.1%) | 107/128 (83.6%) |
| .5 | 122/128 (95.3%) | 121/128 (94.5%) |
| .9 | 103/128 (80.5%) | 103/128 (80.5%) |

Each displayed row has 128 available estimates and an analytic numerical
reference. These are illustrative rows; the retained summary reports every
case, target and position, bias/RMSE, width/degeneracy and scoring denominators.
State and linked targets reuse the same outcomes in these cases and are not
independent replications.

The three-position strict retry game has no numeric population Shapley reference
because fresh termination can leave a requested held position unreachable. Its
finite vectors were available in 0/128, 0/128 and 17/128 repetitions at
q=.1,.5,.9, respectively. Even the available vectors were excluded from numeric
reference coverage scoring. Missing provenance, lagged readback and call-cap
controls retained their distinct refusal boundaries.

### 5.2 Independent finite-distribution analysis

A separate enumerator uses exact rational probability weights for the declared
two-player independent Bernoulli idealization, with floating-point normal
quantiles and boundary classification. At 16 pairs, the protective stop normal
interval covers 83.7775% at q=.1 and .9, and 92.6377% at q=.5. The independent
endpoint normal interval covers 81.1401%, 92.3187% and 81.1401%, respectively.
These are finite-distribution calculations, rather than Monte Carlo proportions.
[Calculation and assumptions](../output/calibration-theory-2026-10-11/README.md).

For an interior Bernoulli probability `q`, a homogeneous sample forces an
empirical percentile bootstrap interval to a point. Thus coverage is at most
`1-q^K-(1-q)^K`; for `K=16`, q=.1 or .9, this is approximately 81.47%.
Other sample configurations can also miss. This mathematical explanation
motivated fresh comparison data; it does not retrospectively alter retained
intervals or establish an upstream CAR coverage result.

### 5.3 Local language-model integration

The first local Ollama pilot used one Qwen3 4B quantized model, one refund
template and six runs, making 13 policy calls. All six final assessments
contradicted independently satisfied action-linked readback. Neither of two
context-neutralization pairs changed action selection or consequence; those
small paired estimates are diagnostic, not evidence of an attribution advantage.
The full runtime/model identity and captures are retained in the
[pilot](../output/live-pilot-2026-10-10/README.md).

A subsequent exploratory prompt comparison used twelve one-attempt runs and two
separate retry-diagnostic episodes, with 28 calls. The revised prompt returned
unknown in all six controlled final status fields, while some rationales still
asserted success. Zero definite-status coverage left its conditional
contradiction rate undefined; it did not establish calibrated uncertainty or
accuracy improvement. The prompt adaptation followed the pilot and is not an
independent holdout. [Prompt follow-up](../output/prompt-sensitivity-2026-10-10/README.md).

### 5.4 Shared-draw interval follow-up

The separate study froze collection source
`0d8ec0baee84ca0d33f52739456d54d6f61a27ad` and retained 384 trials across 12
declared cases with 32 repetitions each, including q=0/1 controls. It recorded
66,048 planned branches and 87,054 actual scripted calls: 1,728 factual,
24,087 contrastive and 61,239 Shapley calls. Variants retained the same raw draws,
points, seeds, budgets and refusals, with zero additional policy calls.
[Retained findings and audit](../output/interval-comparison-2026-10-13/FINDINGS.md).

Every binomial success count was enumerated for sample counts 8,16,32,64 and
eleven predeclared probabilities. Minimum coverage on that finite grid was
7.72% for the limiting empirical percentile bootstrap, 85.15% for Wilson and
96.68% for Clopper-Pearson. Probability weights are exact rational values;
interval boundaries use floating-point arithmetic. The bootstrap grid is its
infinite-resample limit, distinct from the actual seeded 2,000-resample intervals
in the replay comparison. Neither the grid minimum nor a finite replay
proportion establishes coverage for dependent live-model continuations.

At the protective stop's timeout position for the consequence target:

| Retry probability q | Bootstrap covered | Clopper-Pearson covered | Normal pair interval covered | Hoeffding covered |
| --- | --- | --- | --- | --- |
| .1 | 26/32 | 31/32 | 23/32 | 32/32 |
| .5 | 31/32 | 32/32 | 32/32 | 32/32 |
| .9 | 31/32 | 32/32 | 29/32 | 32/32 |

The full summary retains every case and variant, including Clopper-Pearson
coverage of 30/32 in the retry-pivot q=.5 case. A finite observed proportion
can be below nominal coverage for a conservative method; 32 repetitions are
an integration comparison, not a high-precision empirical calibration proof.
State and linked targets sharing outcomes are not independent replications.

Wider pair bounds impose a substantial detection cost. At q=.1, mean width was
approximately .180 for normal versus 1.358 for Hoeffding; at q=.5, approximately
.344 versus 1.184. Hoeffding detected the negative reference sign in 0/32
repetitions at both weaker settings and 32/32 at q=.9. This is not uniformly
better attribution or improved point estimation.

The independent hardened audit rederived raw mechanisms, labels, seeds, call
accounting, legacy bootstrap/normal output and new bounds, and checked aggregate
inventories, variant loci and the manifest. It passed 3,283,523 assertions at
the initial derived-artifact inventory; twenty targeted corruptions were rejected
in separate smoke copies. An independent SciPy numerical check covered 1,290
binomial cases and 1,290 endpoint differences, with maximum absolute binomial
endpoint disagreement approximately 2.66e-14. SciPy was an audit dependency;
the framework still has no required runtime dependencies. These checks concern
the specified implementation and evidence, not authentic provider origin or
live-model independence.

## 6. Pending experiments and analysis

### 6.1 Further uncertainty and precision assessment

Budget effects, dependence, verifier error, multiplicity and template-level
generalization remain outside the completed interval study. A larger study must
predeclare precision targets and sampling units, retain availability/reference
eligibility alongside numeric results and evaluate effect detection together
with coverage. Standard conservative methods and finite-grid checks do not
constitute estimator novelty or a model-independent coverage guarantee.

### 6.2 Variable-length interaction study

The proposed on-reach refund mechanism has initial refund selection probability
`p`, timeout retry probability `q`, exactly-one-refund verification and two
attempts. Unsafe retry after a committed timeout can create a duplicate. Its
declared selection/retry interaction is `(1-p)(1-q)`; idempotency should remove
that interaction. Enumerate deterministic fresh choices through the actual
payment simulator and verifier before using an analytic reference to assess
the stochastic sampler. Retain strict-game results as a separate estimand.

**Pending insertion:** validated implementation revision, exact coalition
enumeration, repeated schedule, interaction estimates, uncertainty, inactive
position receipts, negative controls and independent audit.

### 6.3 Held-out model study and matched comparisons

Freeze templates, fault compositions, policy prompts/model identities,
interventions, trust assumptions, sample sizes, precision target, call budgets,
primary metrics and multiplicity handling before final generation. Split by
template family and fault composition, rather than seed alone. Keep pilot
templates and any tuning material out of the final held-out population. Measure
replay fidelity and report model-specific results before pooling.

The critical baseline is a faithful verifier-plus-CAR adaptation with the same
evidence, candidates, world resets, targets and budget. An applicable joint-fault
comparator must expose the same infrastructure variables. Response-only diagnosis,
recency and leave-one-out are descriptive baselines/ablations, not substitutes
for those comparisons. Publish an information/cost table for each method.

Predeclared analyses should include false outcome and origin claims, structured
assessment contradictions, separately audited rationale assertions, signed
effect error, interval coverage, factor recovery, unknown/refusal rates and
calls/tokens/latency. Use independent reference intervention experiments or
analytic mechanisms, not the tested method's own noisy samples as truth.
Template clusters are the relevant units for generalization uncertainty.

**Pending insertion:** achieved study population and failures, held-out results,
matched baseline deviations, preregistered analyses and all ablations. The
[study plan](../docs/study-plan.md) supplies the detailed protocol requirements.

## 7. Limitations and responsible interpretation

The present environment is synthetic and narrow. Its evidence authority and
watermarks are declared adapter inputs; production authentication, provider
consistency and real transactional guarantees are outside the current result.
Independent readback does not eliminate measurement error. Full-vector refusal
prevents unsupported numeric claims but can severely reduce availability.
Availability itself can depend on the intervention and must remain visible.

The retained calibration uses synthetic independent randomness, not validated
independence of live language-model outputs. The small local-model pilots cannot
estimate general performance, establish task-family transfer or demonstrate
method superiority. The new interval alternatives are standard methods with
explicit distributional assumptions and precision costs. Joint context/fault
attribution and multiple-domain evaluation remain incomplete.

All payments in the reported work are simulated. Model weights are identified
rather than redistributed. A reproducible engineering release is useful even
if an equally informed modular baseline performs as well; in that case the
paper's contribution must remain protocol/infrastructure and measured
limitations.

## 8. Artifact availability

Source, contribution instructions and retained research artifacts are in the
public MIT repository
[Devrajsinh-Jhala/consequa-x](https://github.com/Devrajsinh-Jhala/consequa-x).
The Python distribution is being prepared for a first registry alpha; a public
PyPI release and registry ownership are not established by this draft. The
[evidence ledger](evidence-ledger.md) maps manuscript claims to retained files
and distinguishes completed from pending evidence. Bibliographic records are
in [references.bib](references.bib).

Before submission, replace pending sections with audited final results, select
a suitable venue/format, refresh the related-work search and confirm author
affiliation, contributor credit, funding/conflict statements and artifact
version/archival identifier. None of those details is inferred here.
