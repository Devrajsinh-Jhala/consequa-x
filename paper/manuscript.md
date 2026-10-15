# Consequa-X: An Evidence and Intervention Protocol for Consequential Agent Actions

Devrajsinh Jhala

Complete protocol and software manuscript, updated 15 October 2026. This readable
source follows the [generic IEEE conference version](consequa-x-ieee.tex). No
specific conference, acceptance, institutional affiliation or funding is asserted.
The contribution and empirical claims are limited to the declared artifact and
settings. Broader comparative research is future work.

## Abstract

An agent's selected operation, tool response, reported assessment and external
effect can disagree. A refund may commit before an acknowledgement is lost,
and another actor may satisfy the requested state. Consequa-X records these
distinctions in portable evidence traces, verifies temporal contracts from
independent readback and executes isolated intervention replays with explicit
unknown, invalid and budget-exhausted outcomes. The contribution is a software
and evidence protocol; its contrastive and permutation Shapley estimators adapt
existing methods. Audited synthetic studies retain 1,280 original calibration
trials and 384 fresh shared-draw comparisons. Several original nominal 95%
intervals undercovered specified effects. Conservative alternatives retain
uncertainty at homogeneous samples but have substantial precision and
detection costs. Physical refund enumeration shows different initial-action
and consequence interactions under an explicit on-reach positional game.
A separate 24-episode local-model validation found six contradicted status
claims among ten assessable claims for one prompt, while another abstained in
every structured status but retained affirmative language in some rationales.
The reusable core supports explicit application verifiers and separates
successive effect witnesses in its evidence graph. These results establish
auditable implementation behavior and measured limitations in the declared
settings; they do not establish a new estimator or broad attribution superiority.

**Index terms:**
agent systems, outcome verification, evidence provenance, counterfactual replay,
software artifacts, uncertainty

## 1. Introduction

A consequential tool operation has distinct stages: selection, dispatch,
execution, response, reported assessment and external observation. A service
can commit an effect before its acknowledgement is lost. Retrying can create
another effect unless the logical operation's identity and idempotency semantics
are retained. Conversely, a successful response can coexist with an incomplete
or incorrect effect. Explaining such runs requires more than reading the last
tool response or the agent's prose.

State satisfaction and effect origin also differ. An external refund may
satisfy the requested balance or count while remaining unlinked to this agent.
A source-supported origin link is a provenance claim; it does not establish
counterfactual necessity. A replay effect is a separate claim about a declared
intervention, continuation policy and outcome distribution.

Consequa-X makes these distinctions inspectable. Its core contains typed
records, schema validation, application verification and evidence-only
explanation. Its research adapters provide isolated refund worlds, public-only
policy inputs, a local Ollama adapter and bounded replay experiments. Reported
assessments are captured outputs, not measurements of hidden reasoning.

This paper contributes (1) a reproducible protocol linking operation identity,
attempts, responses, assessments, independent readback, conclusions and origin;
(2) replay infrastructure with declared games, actual-call accounting and
complete refusal records; and (3) audited evidence exposing uncertainty and
reporting limits in specified synthetic and exploratory local-model settings.
It presents a protocol/software artifact rather than a superiority comparison.

## 2. Related Work

Causal Agent Replay (CAR) performs same-policy interventions on recorded
decisions, evaluates user-specified outcomes and uses contrastive suffix and
permutation Shapley attribution [Shah, CAR v1](https://arxiv.org/html/2606.08275v1). Consequa-X implements an independent
binary adaptation with its own typed-world, evidence and refusal boundaries.
Applying a verified outcome to replay is therefore not an estimator novelty
claim. Policy-Conditioned Counterfactual Credit studies changes in final
verified success under specified interventions and a continuation
policy [Meng, PCCC v1](https://arxiv.org/html/2606.05263v1); its learning objective differs from post-hoc external-effect
diagnosis, but verified targets and valid interventions are shared concerns.

CausalLoss-Fin jointly intervenes on agent decisions and repairable
infrastructure messages [Sharma, CausalLoss-Fin v1](https://arxiv.org/html/2609.25960v1). Its deterministic programmatic
evaluation limits transfer to stochastic language policies, but it already
occupies the broad combination of financial effects and joint decision/fault
attribution. A future comparison must expose applicable variables to every
method rather than charge omitted infrastructure effects to decisions.

Verified Tool Calls distinguishes acknowledgements from independently checked
effects and uses unknown postcondition conclusions [Mansoor, Phadke and Rana v1](https://arxiv.org/html/2608.02645v1).
Callability Is Not Operability studies controlled interface ambiguity and
terminal agent claims [Wang v2](https://arxiv.org/html/2608.23628v2). Three-valued verification and
response/effect separation are foundations and comparison requirements here.
These targeted primary-source checks do not constitute a systematic review or
an independent reproduction of those papers' empirical results.

## 3. Evidence Protocol and Core Interfaces

### Objects, contracts and trust

Let $H$ be visible history, $A$ a logical action, $E$ an execution attempt,
$R$ its response, $B$ a timestamped reported assessment and $O$ an independent
readback observation. A contract $C$ declares payload, count, deadline and
stability horizon. The verifier conclusion $V(C,O)$ is satisfied, violated or
unknown. Origin is separately confirmed, other actor or unknown. Evaluator-only
simulator truth never becomes a policy or explainer input.

The built-in refund predicate uses integer currency minor units. An eligible
effect matches payment, amount and currency, commits in the declared time
window and persists through the horizon. Exact-count contracts also constrain
the count during the stability interval. A stale watermark or inadequate scope
and completeness yields unknown rather than a confident absence claim.
Source authority, scope, completeness and watermark declarations remain trusted
adapter inputs. Schemas and hashes validate structure and changed bytes, not
source authenticity or real transactional guarantees.

### Reusable application boundary

Applications can supply an explicit read-only verifier through
`verify(action, observation, verifier=...)`. The wrapper checks receipt
type, contract identity, observation identity, source, watermark and timing.
Domain predicate semantics, authentication and read-only adapter behavior are
the application's responsibility. There is no evaluation of arbitrary predicate
strings. An offline artifact-delivery example constructs captured records and
checks independently read-back content digests without importing the refund
simulator or executing writes.

`explain(trace)` reads a captured verification and performs no replay.
Refund target matching is built in; other predicates receive a neutral
explanation unless a trusted domain matcher explicitly qualifies attributable
effects against payload and temporal rules. Matchers can return only unique
IDs within the receipt's attributable IDs. Unknown receipts are not interpreted
as target matches. A qualified provenance link still is not a causal effect.

### Successive witnesses and graph meanings

Repeated readbacks can disagree about the same effect identifier. The graph
therefore retains observation-specific witnesses and an identity-only shared
effect node. Dispatch-to-effect edges attach to the witness supplying origin
metadata; verification edges use witnesses in that receipt's own observations.
A later conflicting actor, corrected payload or reversal cannot overwrite an
earlier witness and inherit its unqualified origin link. Shared identifiers do
not authenticate or reconcile the records. Estimated-influence edges require
captured event identifiers and an explicitly supplied intervention estimate.

## 4. Replay Targets, Games and Uncertainty

### Targets and conditional suffix effects

The refund adapter exposes three targets: initial action selection, global
state-contract satisfaction and action-linked consequence. A known global
violation is false for the linked target. Satisfied state with exclusively
external qualifying effects is false for that target; insufficient provenance
can instead yield unknown. The linked target combines global satisfaction and
qualifying operation-linked witnesses rather than reconstructing an agent-only
world. Unknown observations do not acquire numeric labels.

For known binary target $Z$, set bad outcome $X=1-Z$. Prefix replay holds
factual decisions before position $k$ and resamples the suffix. With one
observed factual bad label $x_f$, the conditional estimand is
$$
\gamma_k = \mathbb{E}[X\mid \text{prefix held, suffix resampled at }k]-x_f.
$$
The factual term is one observed constant, not a population rate estimate.
Negative values indicate rescue relative to that observation. An earlier
irrelevant position can have a nonzero suffix effect through a later stochastic
choice. A latest nominal rescue is selected only when every planned position
is estimable and its interval supports a negative effect. This selection has
no simultaneous coverage guarantee and does not establish a unique cause.

### Held-decision coalition games

Let $N$ be reached factual positions. Coalition $S$ requests holding captured
decisions at positions in $S$; other decisions are sampled. Reached held
decisions must match the typed public stage. In the **strict** game, an
earlier termination leaving a requested held position unreachable invalidates
the draw. Finite samples avoiding invalidity do not define the population game.

The separate **on-reach** game treats requested positions beyond a normal
termination as inactive and uses the actual completed episode. Reached
incompatible operations remain invalid; provider failures and exhausted budgets
are not normal inactivity. This is an explicit alternative game, not a repair
of retained strict results.

For a defined game $v(S)=\mathbb{E}[X\mid S]$, signed Shapley values allocate
the held-decision effect [Shapley, RAND P-295](https://www.rand.org/pubs/papers/P295.html):
$$
\phi_i = \sum_{S\subseteq N\setminus\{i\}}
\frac{|S|!(|N|-|S|-1)!}{|N|!}\,[v(S\cup\{i\})-v(S)].
$$
Fresh forward/reverse permutation walks form one paired contribution vector.
Independent empty/full draws diagnose the endpoint scale. Values are signed
allocations under the declared game, not normalized responsibility shares.
Positive values mean holding the factual decision increases bad outcomes;
negative values mean it is protective.

### Intervals and refusals

Contrastive defaults use exact binomial Clopper–Pearson bounds translated by
$-x_f$ [NIST binomial intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm). Signed pair observations lie in $[-1,1]$; the default
Hoeffding half-width for $P$ independent pairs and failure allowance $\alpha$
is [Hoeffding, 1963](https://doi.org/10.1080/01621459.1963.10500830)
$$
h=\sqrt{\frac{2\log(2/\alpha)}{P}}.
$$
This is the half-width before clipping the interval to $[-1,1]$.
Endpoint differences use two exact binomial marginals with a split failure
allowance. Each marginal has confidence $1-\alpha/2$; the difference interval
is $[L_f-U_e,U_f-L_e]$. The union bound requires valid marginal bounds, not
independence between the two arms. Bootstrap and normal intervals remain
explicit legacy comparators.
These are standard conditional methods with sampling assumptions and precision
costs, not distribution-free guarantees for dependent model continuations.

Each replay starts a fresh declared world. Held replies consume no fresh calls;
every attempted fresh call, including a provider/protocol failure, consumes
budget. Every planned branch remains recorded. Unknown, invalid, failed and
unstarted branches are not dropped or redrawn; affected estimates are refused.
Targets and interval variants reuse captured evidence without extra policy calls.

## 5. Audited Evaluation

### Original calibration and finite analysis

The original development study retained 1,280 trials across ten specified
mechanisms, with 128 repetitions. Of 223,232 planned branches, 198,690
completed, 4,062 were invalid, 256 failed at the deliberate cap and 20,224
were unstarted. Independent auditors checked raw evidence, seeded outcomes,
statistics and accounting. Table 1 reports a preselected
protective-stop consequence position with 128 available, reference-eligible
estimates in each row.

**Table 1. Original nominal 95% coverage at the protective stop.**

| Retry $q$ | Contrastive covered | Shapley covered |
| --- | --- | --- |
| 0.1 | 100/128 | 107/128 |
| 0.5 | 122/128 | 121/128 |
| 0.9 | 103/128 | 103/128 |

Separate finite-distribution calculations yielded protective-stop normal pair
coverage of 83.7775% at $q=0.1,0.9$ and 92.6377% at $q=0.5$ for 16 pairs.
For interior Bernoulli $q$, homogeneous draws force an empirical percentile
bootstrap interval to a point, giving coverage ceiling
$1-q^K-(1-q)^K$. At $K=16$ and $q=0.1,0.9$, this is about 81.47%.
These findings concern the specified adaptation; they do not establish
coverage of upstream CAR implementations.

### Shared-draw conservative comparison

A separately frozen follow-up retained 384 trials across twelve cases,
66,048 planned branches and 87,054 actual scripted calls. Variants reused
the same points, draws, seeds and refusals. Exact probability weights over
sample counts 8,16,32,64 and eleven probabilities yielded minimum grid
coverage 7.72% for the limiting empirical percentile bootstrap, 85.15% for
Wilson and 96.68% for Clopper–Pearson. The bootstrap grid is its
infinite-resample limit, distinct from the replay's finite seeded bootstrap.

**Table 2. Fresh shared-draw coverage: 32 trials per row.**

| $q$ | Bootstrap | Exact binomial | Normal | Hoeffding |
| --- | --- | --- | --- | --- |
| 0.1 | 26/32 | 31/32 | 23/32 | 32/32 |
| 0.5 | 31/32 | 32/32 | 32/32 | 32/32 |
| 0.9 | 31/32 | 32/32 | 29/32 | 32/32 |

Table 2 is the protective-stop timeout position, not every
case. The full summary includes exact-binomial coverage 30/32 for a retry-pivot
case. Finite observed coverage can fall below nominal despite a conservative
population method. At $q=0.1$, mean normal versus Hoeffding width was about
0.180 versus 1.358; at $q=0.5$, 0.344 versus 1.184. Hoeffding detected the
negative reference sign in 0/32 trials at both weaker settings, and 32/32 at
$q=0.9$. Wider intervals therefore impose a substantial detection cost.

The hardened independent audit passed 3,283,523 assertions at its recorded
derived-artifact inventory; twenty targeted corruptions were rejected. A
separate SciPy numerical audit covered 1,290 binomial cases and 1,290 endpoint
differences, with maximum binomial endpoint disagreement approximately
$2.66\times10^{-14}$. SciPy was an audit dependency, not a framework runtime
dependency. Finite grids and synthetic replays do not establish live-model
sampling independence or simultaneous attribution coverage.

### Physical interactions and variable length

An independent physical enumeration covered four deterministic fresh-choice
components, eight held masks, two games and eight cases, retaining 512 planned
branches and 718 actual scripted calls. Outcomes came from ordinary payment
readback rather than injected payoff values. With selection and timeout retry
probabilities $p=q=0.5$, unsafe retry and exactly-one verification, on-reach
consequence shares were $[-0.125,0.375,0]$, with selection/retry interaction
0.25. Action-selection shares were $[-0.5,0,0]$. Idempotency changed consequence
shares to $[-0.5,0,0]$ and removed the interaction. This is a declared
programmatic mixture, not observed model interaction recovery.

The strict population game remained undefined at interior probabilities;
missing provenance, lag and small budgets retained their distinct limits.
The independent audit passed 27,277 checks; twenty-nine semantic corruptions
were rejected. The original export manifest and data remain preserved alongside
the derived canonical inventory. Two sampler integration controls exercised
32 pairs and 32 endpoint draws, with eighteen coefficients within a broad
0.3 regression tolerance. That tolerance alone is not a calibration result.

### Exploratory local-model validation

A frozen installed Qwen3 4B checkpoint completed six validation cases,
two repetitions and two unchanged prompt profiles, using 59 actual calls
within a 72-call cap. No episode failed or remained unstarted. Model identity,
prompt/payload hashes, public traces and the exact source checkpoint are retained.
The original and revised profiles induced different action sequences; this
is not a pure reporting experiment or an attribution-method comparison.

**Table 3. Local-model validation with explicit claim denominators.**

| Quantity | Original v1 | Revised v2 |
| --- | --- | --- |
| Completed/planned episodes | 12/12 | 12/12 |
| Actual calls/profile cap | 36/36 | 23/36 |
| Definite final status claims | 12/12 | 0/12 |
| Contradictions/assessable claims | 6/10 | 0/0 |
| State satisfied/violated/unknown | 6/4/2 | 7/3/2 |
| Linked satisfied/false/unknown | 6/4/2 | 5/5/2 |

The revised profile's conditional contradiction rate is undefined, not zero
error. In the other-actor case, revised-profile readback satisfied state while
origin was external and action linkage false. In the expired-request case,
the original profile correctly described ineligibility but issued a refund;
its failure assessment contradicted achieved effect. Effect satisfaction and
eligibility-policy correctness are distinct targets.

A separate single unblinded manual reading annotated affirmative processing
clauses in 10/12 original and 7/12 revised final rationales. Five of those
seven revised rationales also hedged independent verification. A statement
that a second attempt committed can be literally true while two effects
violate an exactly-one task. These annotations are descriptive, without an
inter-rater reliability result; unknown structured fields do not ensure prose
abstention. The saved auditor passed 2,227 assertions and rejected seven
corrupted smoke copies without additional generation. Fixed profile order,
tiny sample size, shared fault conditions and an exposed validation family
limit interpretation. The held-out reserve was not generated.

## 6. Discussion and Limitations

The evidence protocol supports different, inspectable claims about responses,
state, origin and intervention effects. Its refusal rules prevent unsupported
numerical outputs but can sharply reduce availability. Availability can depend
on interventions and must remain visible beside numerical results. Conservative
intervals do not make undefined games numeric, resolve missing evidence, or
remove the need to assess the actual sampling law.

The environment is synthetic and narrow. The artifact-delivery example validates
an integration interface, not a second production-domain experiment. Declared
source authority and watermarks are not authenticated transactional guarantees.
The model experiments use one local model and exposed development/validation
families; they do not estimate broad model performance or held-out transfer.
State and linked targets sharing outcomes are not independent replications.
Claims about hidden reasoning cannot be inferred from reported assessments.

Future superiority research requires faithful modular baselines with matched
evidence, target definitions, candidate variables, snapshots and actual budgets.
Joint context/fault attribution must expose infrastructure variables. Independent
template and fault-composition families, predeclared precision, replay-fidelity
checks and cluster-aware uncertainty are needed for generalization claims.
Those comparisons are future work, not completed evidence of this paper.

## 7. Conclusion and Artifact Availability

Consequa-X provides a reusable evidence core and auditable replay adapters for
separating reported assessments, external outcomes, origin and intervention
effects. The retained studies expose uncertainty failure, precision costs,
variable-length game restrictions and prose/structured-status disagreement.
The useful result is a reproducible protocol/software artifact with measured
limits, without claiming a new estimator or general method superiority.

Stable version 1.0.0 is publicly available under MIT on
[PyPI](https://pypi.org/project/consequa-x/1.0.0/). Its wheel and source
distribution were independently downloaded and hash-checked, and an isolated
registry installation was verified on October 15, 2026. The wheel contains the runtime, schemas and typing
marker; the source distribution also includes documentation, offline examples,
tests and audit scripts. Private research outputs and model weights are excluded.
The maintainer-controlled
[repository](https://github.com/Devrajsinh-Jhala/consequa-x) is private. Git
history, retained protocols, raw evidence and evaluator-only truth are retained
there for authorized collaborators; this paper does not assert unrestricted
access to that research archive.
Each historical study retains its own source revision and manifest; later
engineering fixes do not silently replace earlier data. A public immutable
research archive and review-access arrangements have not been established.
Framework imports and offline examples require no model credentials or required
runtime dependencies. All reported payments are simulated; model weights are
identified rather than redistributed.

## Acknowledgment

Generative AI assistance was used for software development, research-source
inspection and manuscript drafting. The empirical records and audit scripts
are retained for review. Human authors are responsible for checking the final
manuscript, code, references and submission requirements. No institutional
affiliation, funding or venue acceptance is asserted here.

## Evidence and reproducibility links

The [evidence ledger](evidence-ledger.md) maps claims to retained artifacts and
frozen source revisions. The [source audit](source-audit.md) records the focused
primary-source inspection and access limits. Bibliographic metadata is retained
in [references.bib](references.bib). These files are available within the
maintainer-controlled repository; links do not imply public research-archive access.

- [Original calibration](../output/calibration-probe-2026-10-11/FINDINGS.md) and
  [finite analysis](../output/calibration-theory-2026-10-11/README.md).
- [Shared-draw interval comparison](../output/interval-comparison-2026-10-13/FINDINGS.md).
- [Physical refund enumeration](../output/refund-interactions-2026-10-13/README.md)
  and [independent audit](../output/refund-interaction-audits-2026-10-13/independent.json).
- [Local-model validation](../output/local-validation-2026-10-14/FINDINGS.md) and
  [frozen proposal](protocol-next-validation.md).
- [Application integration](../docs/application-integration.md) and
  [graph witnesses](../docs/graph-witnesses.md).
- [Broader study plan](../docs/study-plan.md) and
  [CAR reproduction plan](../docs/car-reproduction-plan.md).
