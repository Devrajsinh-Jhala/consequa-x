# Study plan

Status: proposed research protocol with implemented evaluation and paired-replay
entry points, 10 October 2026. A [first live pilot](../output/live-pilot-2026-10-10/README.md)
and an [exploratory prompt follow-up](../output/prompt-sensitivity-2026-10-10/README.md)
have completed; this document specifies the stronger research study still needed.
Scripted fixtures, mocked Ollama tests, and the small local-model pilot establish
integration behavior, without demonstrating method superiority or generalization.
The follow-up found that structured unknown assessments can coexist with definite
rationale claims. A final study must assess those claims separately; field-level
abstention alone does not establish calibrated uncertainty or improved accuracy.

## Research question and scope

With the same visible trajectory, verification evidence, origin metadata,
candidate variables, replay access, and compute budget, can an evidence-aware
consequence attribution protocol reduce unsupported explanations of stochastic
LLM actions under ambiguous execution and imperfect observation?

The useful distinction is among action selection, returned response, reported
assessment, external effect, and evidence-supported origin. Simply applying
replay to a verified target is not a new estimator. CAR already accepts a
user-defined outcome score and reruns affected continuations. [CAR, version 1](https://arxiv.org/html/2606.08275v1).
PCCC also studies credit for final verified success under specified
interventions and a continuation policy. [PCCC](https://arxiv.org/html/2606.05263).

CausalLoss-Fin jointly intervenes on decisions and infrastructure faults in a
financial environment. Its reported policies are deterministic procedures,
which limits transfer of its findings to stochastic LLM policies. It is a
required comparison rather than evidence that this project's broad claim is
unoccupied. [CausalLoss-Fin, version 1](https://arxiv.org/html/2609.25960v1).

The candidate contribution is a reproducible evidence and intervention
protocol, a benchmark extension that tests it, and any advantage actually
demonstrated against strong modular baselines. The framework can be useful
even if the last advantage does not appear. The
[initial literature assessment](../output/research/Consequa-X_Research_Assessment.md)
records the wider related-work audit; refresh it before submission.

The implemented [policy evaluation](policy-evaluation.md) and
[paired policy replay](policy-replay.md) provide a structured local-model
boundary, isolated simulated worlds, a global call budget, paired visible
context interventions, and separate action/consequence estimates. One factual
branch per seed is reused across candidates, and both targets reuse the same
recorded branches. Provider failures, unstarted branches, and unknown
verification remain explicit; a candidate/target estimate is refused unless
all planned target pairs are known. The cached estimator is the existing
leave-one-out baseline. [Task-family manifests](study-manifests.md) now support
declared split isolation, and [decision-prefix replay](decision-replay.md)
preserves factual prefixes for separately seeded continuations. Current support
still lacks joint context/fault attribution and faithful implementations of the
required strong comparison methods; see the [CAR reproduction plan](car-reproduction-plan.md).

## Hypotheses to preregister

| Hypothesis | Required evidence |
| --- | --- |
| Separating outcome and origin reduces false agent-success claims under interference or missing provenance. | Error and abstention comparisons at matched evidence and coverage. |
| Upstream context can affect consequences without changing the initial selected action. | Context interventions that change retries, parameters, or routes, with initial action-selection rates measured separately. |
| Explicit unknown conclusions avoid unsupported outcome and attribution claims under incomplete visibility. | Risk-versus-coverage curves; unknowns are retained in denominators. |
| Joint context and fault analysis improves factor recovery in composed-fault cases. | Held-out interaction cases, a joint-fault comparator, and independent reference interventions. |

The current runner varies initial selection and retry behavior. It does not yet
provide a general policy-selected parameter, tool, route, or multi-domain
action space. Those extensions should be implemented and validated before
claiming broad long-horizon or multi-domain coverage.

## Freeze the pilot protocol

The first local Ollama pilot verified data capture and observed model misreadings
of assessments, response timing, and remaining attempts. The default v1 prompt
is preserved. Opt-in v2 clarifies those fields and refines continuation guidance;
it is an exploratory adaptation informed by that pilot. Measure replay fidelity
and choose an attainable study budget. Keep all pilot templates and seeds out
of the final held-out set.
Do not use pilot rates as final evidence or select the primary metric after
seeing which one favors Consequa-X.

Before the final study, freeze:

- The policy prompt, response schema, interventions, outcome contracts, fault
  distribution, readback trust assumptions, and failure handling.
- The model configurations, independent task templates, split assignments,
  episode count, candidate factors, replay repetitions, and call limits.
- Primary metrics, uncertainty calculations, model-specific analyses, minimum
  detectable effect or precision target, and the comparison decision rule.
- Baseline implementations, deviations from published methods, cost accounting,
  and the treatment of invalid interventions or insufficient evidence.

Choose sample sizes from the desired precision or pilot variance, not from a
convenient round number. Two samples per case are a smoke test. Repeated seeds
on one template do not establish generalization to other tasks.

## Dataset and split design

Cross several independent wording and task templates with policy-relevant
context, execution faults, readback limitations, and provenance conditions.
Include clean controls and irrelevant context. Include paired observations
that are indistinguishable to the policy but correspond to different hidden
commit states; correct behavior may require uncertainty.

At minimum, retain these separate strata:

| Stratum | What it tests |
| --- | --- |
| Reliable execution | Ordinary selection and reported-assessment calibration. |
| Timeout before/after commit | Ambiguous acknowledgements and retry effects. |
| False success or partial effect | Response/effect disagreement. |
| Safe/unsafe retry | Action identity, idempotency, and duplicate consequences. |
| Delayed or incomplete readback | Outcome abstention and later reconciliation. |
| Other actor or absent provenance | Outcome/origin separation. |
| Compensation and composed faults | Temporal contracts and factor interactions. |

Split by template families and fault compositions, not only by seed. Keep
model configurations and paraphrase families visible in the release metadata.
Report model-specific results before pooling. A single small local model is
an integration demonstration and a limited study population, not evidence
about all language agents.

Fault labels and gold records belong only to the evaluator. Ensure that prompt
text, file names exposed to policies, trace identities, and context values
cannot encode the label. Randomize case order where it can affect server state
or model caching, and record that order.

## Baselines and fairness

The required attribution baselines are:

1. **Verifier plus CAR:** the same supported outcome target, verifier receipts,
   origin information, candidate variables, resettable world, and replay budget
   as Consequa-X. Adapt or reproduce CAR faithfully and report deviations.
2. **Joint-fault comparator:** include agent and infrastructure variables in
   the same declared intervention space, informed by CausalLoss-Fin. Avoid
   comparing against an agent-only baseline incapable of naming a fault.

Add response-only diagnosis, recency, and the current leave-one-out estimator
as descriptive weak baselines and ablations. The scripted refund policy tests
the harness; it is not a methodological comparator. A human or LLM trace judge
must receive the same allowed evidence, and its own token or annotation cost
must be accounted for.

For each comparison, publish an input-and-budget table: visible trace fields,
verifier availability, provenance availability, candidate interventions,
world-reset access, policy model, generation settings, number of calls,
prompt/output tokens, and wall time. Distinguish available privileged oracle
information from normal method inputs. Simulator truth can score methods but
must not enrich one method's input unless the experiment is explicitly an
oracle condition.

Hold the continuation policy fixed within a paired intervention. Reset the
world for every branch. Reuse factual samples only under a declared estimator
and include their calls in the budget. The current paired-policy command shares
one factual branch per seed across candidates and all selected targets, counts attempted
policy calls including errors, and makes no additional provider calls during
estimation. Its budget is a policy-call limit; preflight inspections, token cost,
and wall time require separate accounting. Seeds improve pairing but do not
prove identical LLM randomness across divergent histories; measure replay
fidelity. Record branch order because an exhausted budget can leave different
candidates with different coverage.

## Targets, reference effects, and metrics

Predeclare each target. At minimum, keep selected initial action, verified
contract satisfaction, and action-linked contract satisfaction separate.
State satisfaction by another actor is not the current agent's success. The
current paired-policy `consequence` target measures state-contract satisfaction,
with origin reported separately. The opt-in `action_linked_consequence` target
additionally requires supported qualifying action-linked refund witnesses.
State violation is false, exclusively external satisfied state is false, and
missing or insufficient provenance is unknown. It combines global state
satisfaction with qualifying linked evidence rather than verifying a filtered
agent-only world. Its positive-witness/count semantics and unknown treatment
must be frozen before the final comparison; see [study-manifests.md](study-manifests.md).
Reported assessment is an observable response, not a measured internal belief.

For known simulator states, evaluate supported conclusions against gold
effects and temporal eligibility. For attribution, use a separate, sufficiently
large reference intervention experiment or analytic planted mechanisms. Do not
score against the same noisy replays used by the tested method. A single
injected fault name is not automatically the only cause when several factors
interact.

| Metric family | Required reporting |
| --- | --- |
| Outcome accuracy | False satisfied/violated claims, unknown rate, coverage, and error among decided cases. |
| Origin accuracy | False agent-origin and other-actor claims, unknown rate, and supported-link coverage. |
| Reported assessment | Contradiction and unassessable rates, stratified by linked outcome and response type. |
| Attribution | Signed effect error, interval coverage, factor ranking/recovery, false distractor attribution, and refusals. |
| Interaction handling | Recovery of joint sufficient sets or allocation error against the declared reference. |
| Reproducibility/cost | Replay agreement, calls, tokens, wall time, failure rate, and budget exhaustion. |

Every rate needs its denominator. Report provider failures and missing episodes
beside completed episodes; never recode network errors as semantic violations.
Report refusal and unknown coverage alongside accuracy so a method cannot win
by abstaining on everything. Do not silently discard unknown replay pairs.

Use intervals and tests compatible with the sampling unit and dependence.
Repeated seeds within a template are not independent templates; use template
clusters or a justified hierarchical analysis. The current conservative
Wilson-difference intervals are individual-estimate uncertainty, not
simultaneous coverage over all tested factors. Predeclare any multiplicity
correction and distinguish exploratory analyses from confirmatory results.

## Required ablations

Compare the full protocol with independent readback removed, provenance
removed, the outcome/origin separation removed, retries disabled, idempotency
changed, and joint-fault variables omitted. Keep other inputs and budgets
fixed. Include clean negative controls and label-invariance checks.

Show at least one case in which consequence attribution is more than a
rescaling of action-selection attribution. The unsafe retry fixture is a
candidate mechanism; an actual LLM must exhibit measurable sensitivity to the
visible retry context before it supports the paper's empirical claim.

## Reproducibility and release record

Save a machine-readable study configuration, repository commit, package
versions, exact model tag and weight digest, Ollama version, hardware and
quantization details, generation settings, prompt/response captures, seed
schedule, simulation snapshots, verifications, evaluator-only gold, and
failures. Record simulated deadlines separately from inference latency.
Current adapter receipts include public-request, system-prompt, and full-request
hashes plus declared local-model inspection metadata. These support integrity
and identity checks but do not replace the source revision, complete study
record, or trust in the local server. The adapter rejects declared remote
routing before generation; it does not authenticate the server's execution
location. Keep startup inspection failures separate from completed study runs.

The evaluation command returns a nonzero exit status when a provider/protocol
sample fails or the call budget is exhausted. Verified contract violations are
valid outcomes and do not make an otherwise completed evaluation an execution
failure. Analysis scripts must use the recorded status and denominators rather
than equating the command's exit status with refund success.

Release the supported traces and evidence independently of gold labels so
third parties can repeat the scoring boundary. A file hash manifest establishes
integrity, not provider authenticity. Document source trust and watermark
assumptions. Use synthetic customer data and check model redistribution terms
before including weights in a release.

The result is ready for a research manuscript only after the frozen study has
run on held-out cases, the strong baselines have completed at matched budgets,
and the reported uncertainty and limitations match the evidence. If the modular
baseline performs equally well, publish the engineering framework and protocol
without claiming an improved attribution method.
