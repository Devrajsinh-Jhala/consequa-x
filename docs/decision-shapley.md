# Positional decision coalitions and Shapley replay

`decision-shapley` captures one factual policy trajectory and estimates signed
contributions of its decisions to a binary bad-outcome game. It is an
independently written CAR-style adaptation with conservative handling of
unavailable positional interventions. It uses the same verifier, provenance
targets, policy boundary, and isolated payment world as
[contrastive replay](decision-contrastive.md).

The pinned primary reference is the authors'
[Shapley implementation](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/shapley.py)
at `db90fa28b97164c35e7c524e4597b8cbdb3035af`, alongside the
[CAR paper](https://arxiv.org/abs/2606.08275). The reference holds factual actions
in a coalition, samples its complement, evaluates forward/reverse permutation
chains freshly, and averages their marginal vectors before normal intervals.
Its default is 64 pairs. This adapter defaults to 16 pairs and adds independent
endpoint diagnostics, strict missing-evidence refusal, positional validity
checks, and actual-call budgeting. No upstream source is vendored, and numerical
stream equivalence or method superiority is not claimed.

## Run a control

```sh
consequa-x decision-shapley --provider scripted --case clean --pairs 16 --samples 1 --endpoint-samples 16 --seed 100 --factual-seed 0 --max-calls 2000 --targets action,consequence,action_linked_consequence --output output/my-decision-shapley
```

`--samples` is the number of fresh draws **per occurrence of a coalition**.
`--pairs` counts permutation/reverse pairs; the two walks are not independent
observations. Defaults are one draw per coalition occurrence, 16 pairs, 16
draws for each independent endpoint, confidence 0.95, permutation seed 0, two
refund attempts, and 2,000 shared actual policy calls. This explicit command
also supports the existing local Ollama provider and prompt options; see
[policy evaluation](policy-evaluation.md). It does not install a model.

Before preparing a provider or creating files, the command checks settings and
the longest possible schedule. With at most `max_attempts + 1` factual players,
the bound is:

```text
branches <= 2 * endpoint_samples
            + 2 * pairs * (max_attempts + 2) * samples
```

The continuation range must fit `MAX_TRIAL_SEED` and exclude the factual policy
seed. The API instead uses the validated reached decision count. Every planned
branch has its own continuation seed; each reserves six separate model phase
keys. Requested seeds do not establish independent model output or equal hidden
state. Permutation shuffling uses a separate Python random stream.

## Coalition meaning and validity

A coalition is a subset of factual decision positions whose captured decisions
are forced. All other reached positions are resampled from the same declared
policy. The world seed, template, initial attempt budget, and outcome contract
stay fixed. The entire factual capture is validated before fresh policy calls,
including positions that a particular branch will not hold.

Unlike [prefix replay](decision-replay.md), a held decision may encounter changed
public inputs after earlier decisions were resampled. Its typed stage must
match the captured stage, and the held operation must be valid for the current
request and remaining attempts. The receipt records the current request,
original event and model key, original reply metadata, and `exact_request_match`.
The held decision includes its captured assessment and reported rationale;
these do not become verifier evidence or hidden-reasoning measurements.

New positions beyond the factual trace are resampled. Stopping before only
unheld factual positions is a valid completion. Stopping before a requested
held position, or reaching an incompatible held stage, makes that coalition
draw **invalid**. Its reached requests and replies are retained with an error,
but it has no completed replay episode or semantic outcome. It is not dropped,
replaced, or assigned a good/bad label.

This conservative rule changes the game from implementations that silently
ignore held positions after termination. It can make a variable-length refund
game unavailable. It remains the default `--coalition-game strict`.

The explicit `--coalition-game on_reach` option defines a different game. A
normally completed branch keeps its actual trajectory and verified outcome,
while later held positions are recorded as `inactive_held_indices`. No decision
or tool effect is added at an unreached position. Provider/budget failures and
reached but incompatible held decisions remain failures/invalid draws. The
method name and each receipt identify the chosen game; rescoring intervals
cannot convert one game into the other. See [refund interactions](refund-interactions.md)
for a physical selection/retry interaction and controls, separately from the
original mathematical payoff oracles. These checks do not establish model
behavior or joint context/fault attribution.

The primitive API is
`consequa_x.benchmark.decision_coalition.replay_decision_coalition(factual,
bounded_policy, held_indices=..., continuation_seed=..., template=...)`.
Held positions are unique integer indices; full hold can complete with zero
fresh calls even when the shared call counter is at its limit.

## Signed contributions and intervals

For a selected target, bad means target satisfaction is false. Unknown target
evidence stays unknown. The cooperative game and one walk's marginal are:

```text
v(S) = probability of bad outcome with factual decisions held at S
marginal(i, S) = v(S union {i}) - v(S)
```

Positive values mean holding the factual decision increases bad outcomes;
negative values mean it is protective. These are signed probability
differences, not normalized responsibility percentages. Their orientation is
different from the changed-minus-factual contrastive rescue effect.

Every pair samples a shuffled permutation and its reverse. Each walk freshly
evaluates the empty coalition and then the successive held sets, with all
requested draws at every step. Repeated coalitions across walks or pairs are
not cached. Adjacent walk marginals share their encountered coalition value so
the walk telescopes; each completed branch's allowed outcome is computed once
and reused across selected targets, requiring no extra policy calls.

The forward and reverse marginal vectors are averaged into one pair vector.
The point estimate is the mean over planned pair vectors. At least two pairs
are required. Alpha `0.1.0a2` defaults to a two-sided Hoeffding interval for
independent pair observations in `[-1,1]`. Its half-width before clipping is
`2 * sqrt(log(2/(1-confidence))/(2*pairs))`; endpoints are clipped to `[-1,1]`.
At confidence `.95` and 16 pairs, the half-width is about `.6791`. These bounds
retain uncertainty at constant samples and can need substantially more calls
to detect modest effects. They require a defined coalition game and independent
bounded pair vectors, assumptions that requested live-model seeds do not prove.

`--interval-method normal` preserves the approximate sample-variance comparator
(`ddof=1`, divided by pairs, with a normal quantile). It is not clipped, can
exceed the parameter range and can collapse at homogeneous samples. The
[same-draw comparison](../output/interval-comparison-2026-10-13/README.md) reports
coverage alongside width and reference-sign detection. Every interval conditions
on a captured factual trajectory/world and has no multiplicity correction.

Any unknown, invalid, failed, or unstarted **path** draw refuses the entire
affected target's contribution vector. Complete pair values remain visible in
receipts, but no partial-case coefficient estimate is emitted. Other targets
can still be known when provenance or readback prevents one target's estimate.

## Independent endpoints and actual budgets

Separate empty and full coalition draws run first, outside every permutation
walk, with disjoint continuation keys. Each endpoint uses at least two draws.
Their independently estimated difference is full-held bad rate minus
empty-held bad rate. The default `clopper_pearson_difference` interval assigns
half the failure allowance to each exact binomial marginal and subtracts their
opposing bounds. The union bound does not require independence between the two
marginals; each marginal still requires independent known binary draws.
`--endpoint-interval-method normal` retains the original independent
sample-variance approximation. A full-held world is deterministic under this
simulator; its repeated evaluations still do not substitute for fresh walk
endpoints.

The export also reports the sum of estimated coefficients and its discrepancy
from that independent difference. The discrepancy is descriptive, with no
interval or pass/fail threshold. A walk's telescoping identity alone cannot
validate the allocation. No coefficients are normalized to make the discrepancy
zero. Endpoint missingness refuses that diagnostic separately; otherwise
complete path coefficients can remain available. Conversely, endpoints can
be known when the path vector is refused.

Factual recording and fresh decisions share one actual-call budget. Held
decisions spend zero; attempted provider/protocol failures spend one call.
Full-held slots can complete at the counter limit until a needed fresh call is
refused. After a budget refusal, all remaining slots are unstarted. Estimation,
factual reconstruction, and target reuse make no policy calls. The export
records factual and continuation counts separately.

## Exports and API

`results.json` retains settings, exact factual byte hash, policy/model metadata,
permutations, the complete planned schedule, reached decision receipts, separate
coverage counts, estimates, and independent endpoint diagnostics. Completed
valid traces, evidence-only explanations, and evaluator-owned truth are saved
in separate folders. A bundled schema and manifest cover the exported files.
Hashes detect changed bytes and do not authenticate the source. No older
context-effect graph overlay is produced for these coefficients.

Factual failures preserve reached receipts without a fabricated trace or plan.
Completed factual captures that fail estimator preflight retain their original
evidence and a typed refusal; a validated coalition schedule is unavailable.
Exit status 2 reports factual/preflight failures, invalid coalitions, provider
failures, or budget exhaustion. Unknown-only evidence refusal is a valid result
and returns 0. Use a new or empty output directory to preserve previous runs.

The estimator API is
`consequa_x.benchmark.decision_shapley.shapley_decisions(factual,
bounded_policy, pairs=16, samples_per_eval=1, endpoint_samples=16, seed=100,
permutation_seed=0, confidence=.95, targets=("consequence",), template=...)`.
`calls` counts continuation calls only; the summary reports the shared counter
before and after the experiment. See [the remaining comparison plan](car-reproduction-plan.md)
for independent calibration, typed-domain extensions, and the frozen live study.

The repository includes [a reproducible seeded refund recipe](../examples/decision_shapley_fixture.py).
Run it with a fresh output directory after installing this source:

```sh
python -I examples/decision_shapley_fixture.py --mode protection --output output/my-protective-decision
python -I examples/decision_shapley_fixture.py --mode invalid --output output/my-unavailable-coalitions
```

The recipe saves settings and an analytic Bernoulli idealization before drawing
any policy decision. The protection case has a factual timeout stop, always
reaches both factual positions, and declares a protective final decision with
population shares `[0, -0.5]` for consequence targets. Finite fresh sampling can
assign noise to the irrelevant selection. The invalid case has a factual retry
and later stop; some held later positions become unreachable. Its unavailable
game has no declared population shares. Neither is a model-performance or
interval-calibration experiment.
