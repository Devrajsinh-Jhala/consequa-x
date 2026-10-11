# Paired policy replay

`model-experiment` tests whether a declared change in visible context changes a
policy's initial action selection or the independently verified consequence.
Every branch uses a fresh simulated payment world and the same outcome contract.
It uses the existing paired leave-one-out estimator; this is a prepared research
entry point, not a new attribution method.

Examples include scripted policies, HTTP fixtures, and a recorded
[first local-model pilot](../output/live-pilot-2026-10-10/README.md).
That pilot observed no action or consequence change from removing the retry
instruction in two Qwen3 4B pairs. It is an integration measurement, not a
generalization result. Payment operations remain simulated.

## Run the offline experiment

From an environment with Consequa-X installed:

```console
consequa-x model-experiment --provider scripted --case unsafe_retry --candidates vip_policy,vip_memory,retry_instruction,distractor --samples 20 --seed 0 --max-calls 400 --max-attempts 2 --output output/model-experiment
```

These are the defaults. Use a new or empty output directory for each run. The
command keeps the factual and changed branches, their evidence, evaluator truth,
failure receipts, pair counts, and estimates in a report with an integrity
manifest. Evaluator material must stay outside policy and explainer inputs.

`--targets action,consequence,action_linked_consequence` adds the supported
action-linked target using the same collected branches and no extra policy
calls. It requires qualifying linked refund witnesses; another actor's satisfied
state is false, and insufficient provenance remains unknown. The default keeps
the original two targets. `--template refund-support-note-v1` selects a curated
wording variant without changing context intervention semantics. See
[study-manifests.md](study-manifests.md) for the target's precise limits.

[Decision-prefix replay](decision-replay.md) is a separate Python primitive for
holding recorded decisions and resampling continuations. It does not replace
the context leave-one-out estimator or implement CAR's attribution algorithms.

`results.json` records the run settings, summary, attempted branch receipts,
interventions, planned seed schedule, and `estimated` or `refused` results.
Completed branches have globally unique paths such as
`traces/branch_0000.json`, `explanations/branch_0000.json`, and
`evaluator_truth/branch_0000.json`; the trial seed alone cannot identify a file
because paired branches reuse it. The export also includes `trace-schema.json`
and `README.md`. The manifest covers these reports and evidence files, excluding
the manifest itself.

`--samples` is the number of paired trial seeds per condition. It requires at
least two; a small count checks the integration and is not a justified research
sample size. `--case` chooses one of the existing demo cases. `--candidates`
lists unique visible context fields, in the desired order, separated by commas.
The command supports neutralization; the Python API also supports typed
replacement.

For one case, `model-eval` records ordinary policy episodes. `model-experiment`
adds declared context changes, matched seeds, and cached comparisons between
the factual and changed outcomes. See [policy-evaluation.md](policy-evaluation.md)
for the common policy interface, response validation, and local-server trust
boundary.

## Use an already installed local model

Once an appropriate local service and model are available:

```console
consequa-x model-experiment --provider ollama --model YOUR_INSTALLED_MODEL --case unsafe_retry --candidates vip_policy,vip_memory,retry_instruction,distractor --samples 20 --seed 0 --max-calls 400 --max-attempts 2 --output output/ollama-replay
```

Replace `YOUR_INSTALLED_MODEL` with its installed name. Provider options match
`model-eval`: `--base-url`, `--temperature`, `--timeout`, `--num-predict`, and
`--prompt-version`. The default prompt remains `refund-policy-v1`; the opt-in
`refund-policy-v2` is a pilot-informed policy refinement. Keep the selected
profile fixed across factual and changed branches.
The command checks installed-model metadata and rejects declared remote routing
before generation. It does not install Ollama, pull weights, or select a model.
Loopback access and server-declared metadata require trust in the local server;
they do not authenticate its execution location.

The policy receives the ordinary task, intervened visible context, and public
tool responses. It receives neither the case name nor injected fault labels,
simulator truth, independent readback, or a verifier verdict before it finishes
acting. Its reported assessment is captured before verification.

## Declare the intervention

Each candidate changes one context field before dependent decisions are rerun.
The other context fields, fault configuration, available operations, attempt
limit, simulated starting state, and consequence contract stay fixed.

| Context field | Neutralization | API replacement |
| --- | --- | --- |
| `customer_request` | Remove the visible request. | Boolean: present or absent canonical request. |
| `vip_memory` | Remove the visible VIP memory. | Boolean: present or absent canonical VIP memory. |
| `vip_policy` | Remove the retrieved VIP exception. | Boolean: present or absent canonical exception. |
| `retry_instruction` | Remove the visible retry instruction. | Boolean: present or absent canonical retry instruction. |
| `distractor` | Replace its text with an empty string. | A string containing the replacement text. |

The four Boolean context fields are rendered as their declared canonical text
or an empty string. Replacing `vip_policy` with an arbitrary policy paragraph is
therefore not supported by this API. Changing arbitrary history records,
execution faults, model prompts, refund parameters, or several factors jointly
requires a separately defined experiment.

A candidate that is already absent may have no effect. That is a legitimate
control, not evidence that the factor is generally irrelevant. The scripted
policy checks canonical context presence and age limits; it does not model how
a language model interprets arbitrary wording.

## Pair the branches and bound the calls

The trial seeds are `seed` through `seed + samples - 1`. Each seed has one
factual branch and one changed branch per candidate. The factual branch is
reused across candidates, and both estimator targets use the same completed
branch data. Estimating the second target never makes additional policy calls.
Execution order is fixed: all factual seeds first, then all seeds for the first
candidate, then each subsequent candidate in the supplied order. This order is
part of the run record and affects which conditions remain covered when the
budget runs out.

With `k` candidates and `n` seeds, the plan contains `n * (k + 1)` branches.
Each branch may make one selection call and up to `max_attempts` calls after
returned tool responses. `--max-calls` is one global limit over the experiment,
including attempted calls that fail at the provider or response-validation
boundary. It is a policy-call budget, not a token budget or a count of simulated
refund attempts. Provider preflight inspections are separate from generation
calls.

The runner starts a fresh world for every branch and reruns the decisions that
depend on the changed context. Each trial reserves six model phase seeds:
`trial_seed * 6 + phase`, where phase zero is selection and later phases follow
the responses. Corresponding factual and changed phases request the same seed;
adjacent trials use disjoint phase keys. The full schedule must fit the
runner's supported seed range.

This controls requested seeds, not hidden model runtime state. Divergent
prompts, model or server versions, hardware, and generation behavior can defeat
exact replay. The policy should be stateless over its request and seed. Record
replay fidelity before treating paired model runs as reproducible samples.

## Interpret the two targets

| Target | Measurement |
| --- | --- |
| `action` | Whether the initial policy decision selected the refund. Later retries are separate decisions. |
| `consequence` | Whether the unchanged state contract was independently verified as satisfied. Unknown verification remains unknown. |

The consequence target remains defined when a changed context causes the policy
to stop. It is not conditioned on the policy choosing the original action.
State satisfaction and effect origin are separate: a refund by another actor
can satisfy the contract without becoming the current agent's success. This
experiment's `consequence` estimate concerns state satisfaction; it is not an
action-linked-success estimate.

For each candidate and target, the signed effect is:

```text
effect = factual target rate - intervened target rate
```

A positive value means the context change reduced the target rate. A negative
value means the change increased it. These effects are not normalized shares
of responsibility and do not prove that one event caused one observed trace.

In the scripted `unsafe_retry` control, removing the retry instruction leaves
initial selection unchanged while preventing a second committed refund. The
fixed exactly-once contract can then become satisfied. This illustrates why
action and consequence targets can differ; it is not a language-model finding
or evidence of superiority over another attribution method.

## Keep incomplete pairs visible

The result records every candidate/target as `estimated` or `refused`, with the
planned seeds and counts of known, unknown, failed, and unstarted pairs. Pair
categories are mutually exclusive: a failed branch takes precedence over an
unstarted branch, then an unknown consequence, then a known pair.

- A provider or protocol error fails the branch; it never becomes a negative
  action or consequence outcome.
- Reaching the global call limit can fail a branch already in progress and
  leave later branches unstarted. The partial report retains this distinction.
- Completed episodes with unknown verification still support an action target
  if both initial decisions are known. They cannot support a complete
  consequence-target estimate.
- Any non-known planned pair refuses that candidate/target's entire estimate.
  The runner does not redraw a failed trial, drop unknown pairs, or calculate a
  complete-case rate. Other candidates or targets can remain estimable if all
  of their planned pairs are known.

Failed branches have receipts without completed traces or verifier results.
Receipts do not preserve a partial episode or raw provider envelope. Inspect
pair coverage, branch failures, and branches not started beside the estimated
effects. A refusal is a reported result of insufficient evidence, not an effect
of zero.

The command returns exit status `2` if a branch fails or the call budget is
exhausted. Unknown-only refusals return `0` because unknown verification is a
valid measurement. A verified violation is also a valid outcome. Read the
reported status and denominators; exit status alone cannot establish either
contract success or available attribution evidence.

When a completed factual trace and at least one estimate are available, the
export includes `attribution-explanation.json`, an evidence explanation with
the available action and consequence estimates added as influence edges.
`results.json` links the representative factual trace and this optional file.
These edges describe the declared replay distribution, not counterfactual
necessity in that representative execution. A run with no usable estimate or
factual trace has no attribution overlay.

## Uncertainty and research limits

Complete pairs are passed from the cache to the existing `leave_one_out`
estimator. Its intervals subtract Bonferroni-adjusted marginal Wilson bounds
for an approximate conservative 95% interval on each rate difference. They do
not model within-pair covariance, offer an exact finite-sample guarantee, or
provide simultaneous coverage across all candidates and both targets. Shared
factual samples also make estimates dependent on one another.

These intervals describe the declared seed experiment on one case. Repeating
seeds on a single template does not establish performance across tasks, and
requested model seeds do not establish independent random samples. Predeclare
the sampling unit, required precision, baseline methods, failure treatment,
and multiplicity handling before a confirmatory study.

Strong comparisons against verifier-plus-CAR, an applicable joint-fault
comparator, actual stochastic language policies, and held-out task families
remain work in [study-plan.md](study-plan.md). This entry point supports
single-context interventions; it does not yet implement the joint-fault study
or reproduce those comparison methods.

## Python entry point

```python
from consequa_x.attribution import Intervention
from consequa_x.benchmark.policy_experiment import experiment_policy
from consequa_x.benchmark.runner import demo_scenarios
from consequa_x.policies import ScriptedRefundPolicy

config = next(case for case in demo_scenarios() if case.name == "unsafe_retry")
experiment = experiment_policy(
    ScriptedRefundPolicy(),
    config,
    [Intervention("retry_instruction"), Intervention("distractor", "replace", "")],
    samples=20,
    seed=0,
    max_calls=400,
    max_attempts=2,
)

print(experiment.summary())
for result in experiment.results:
    print(result.event_id, result.target, result.status, result.estimate)
```

The result retains attempted branch records and explicit pair coverage. Save
the source revision, provider configuration, exact model identity and digest,
prompt and response captures, seed schedule, branch order, verifications,
evaluator-only truth, and failure receipts with a formal run. Manifest hashes
check file integrity; they authenticate neither model execution nor readback
evidence.
