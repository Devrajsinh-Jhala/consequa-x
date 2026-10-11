# Decision contrastive replay

`decision-experiment` captures one complete policy episode, then tests every
decision boundary with fresh continuations. Each branch starts a fresh simulated
payment world with the factual world seed and contract. It holds the captured
decisions before a tested position, then resamples that decision and its suffix
with the same declared policy. A changed trajectory can end earlier or later than
the factual trajectory, within the original attempt budget.

This independently written CAR-style binary adaptation builds on the
[decision-prefix primitive](decision-replay.md). The reference is the authors'
[contrastive implementation at revision
db90fa28b97164c35e7c524e4597b8cbdb3035af](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/contrastive.py),
read alongside the [CAR paper](https://arxiv.org/abs/2606.08275). This implementation
does not reproduce the upstream numerical random stream. The separate
[Shapley estimator](decision-shapley.md) allocates a held-decision coalition game;
these suffix effects are not its shares. The [comparison plan](car-reproduction-plan.md) describes the
remaining work. No method superiority or attribution novelty follows from these
integration fixtures.

## Run an offline example

```powershell
consequa-x decision-experiment --provider scripted --case unsafe_retry `
  --samples 16 --seed 100 --factual-seed 0 --max-calls 400 `
  --targets action,consequence,action_linked_consequence `
  --output output/decision-contrastive-example
```

Scripted runs validate integration and produce inspectable receipts without
calling a language model. The command supports the same installed Ollama model,
prompt-profile, and sampling options as `model-experiment`; see
[policy evaluation](policy-evaluation.md). It never downloads a model. The
default template is `refund-demo-v1`; `--template` selects another registered
refund template. Defaults are 16 samples per reached factual decision, factual
seed 0, continuation seed 100, two refund attempts, and 400 total policy calls.

`--max-calls` is one shared budget for the factual capture and all continuations.
An actual attempted fresh call consumes one unit, including provider/protocol
failures. Reused held decisions consume zero calls. Estimation and bootstrapping
make no policy calls. The export reports factual, continuation, and total calls
separately.

The command validates target names, settings, and a conservative maximum
continuation seed schedule before provider preparation or file creation. Its
bound is `seed + (max_attempts + 1) * samples - 1 <= MAX_TRIAL_SEED`, using the
maximum possible number of captured decision positions. This range must also
exclude the factual seed, ensuring fresh model phase keys. This conservative
guard can reject a schedule that would fit a shorter factual trajectory. Seeds
are controls for reproducibility; they do not guarantee identical model output
or statistically independent samples.

## Read the signed effects

For a selected binary target, **bad** is the negation of target satisfaction.
The target can be initial action selection, verified consequence satisfaction,
or supported action-linked consequence satisfaction. Unknown evidence remains
unknown and never becomes a good outcome. A failed branch has no target label.

At each decision position the signed effect is:

```text
mean(changed bad-outcome indicators) - observed factual bad-outcome indicator
```

The factual baseline is one observed trajectory, not an independently estimated
success rate. For example, if the factual contract failed and 4 of 16 changed
branches also failed, the effect is `4/16 - 1 = -0.75`. Negative effects mean
resampling reduced bad outcomes. Positive effects mean it increased bad outcomes.
These signs differ from the context neutralization estimator, and values are not
responsibility shares. Every selected target reuses the same completed branches
without additional policy calls.

Intervals use a percentile bootstrap of the changed binary samples, conditional
on the single factual label and world. Defaults are confidence 0.95, 2,000
bootstrap resamples, and bootstrap seed 0. The implementation uses
`random.Random` (MT19937), resets the bootstrap seed at each estimate, holds the
factual baseline constant without random draws, and linearly interpolates sorted
bootstrap quantiles. The upstream implementation uses NumPy random draws, so
equal seeds do not imply equal numerical intervals.

A significant rescue requires a negative point effect **and** an interval upper
bound strictly below zero. For each target, the locus is the latest factual
decision position satisfying that rule. Every position must be estimable before
a locus can be identified or declared absent; otherwise the whole target's locus
is refused. There is no multiplicity adjustment across positions or targets.
The selected locus is a nominal statistical rule, not proof of unique causation.

Identical observed samples can yield zero-width intervals. The export marks
`interval_degenerate` explicitly. Such intervals do not establish zero population
variance or certain rescue. Requested seeds do not establish independence or
equal hidden model state. A single-template result does not establish task
generalization.

## Refusals and failure receipts

An estimate requires at least two samples and every planned sample to have a
known target. Unknown target values, failed branches, and unstarted branches
have separate counts and refuse the whole affected estimate. Samples are never
dropped or redrawn. An action estimate may still be available when consequence
readback is unknown; each target has its own coverage.

If the factual capture fails, the output preserves its reached requests,
available replies, call counts, and error. No factual trace or outcome is
fabricated, no estimator runs, and the decision-specific schedule is unavailable.
Continuation failures similarly retain reached decision receipts without a
fabricated trace or outcome. The full schedule records branches not started
after budget exhaustion.

If a factual capture completes but its policy identity or captured boundaries
fail estimator preflight, the original factual trace, independent explanation,
evaluator record, and exact hash are preserved. `estimator_availability` records
the refusal and typed validation error. No continuation is drawn or redrawn,
and there is no fabricated estimate or decision-specific schedule. Recorded
position counts and conservative planning bounds are labeled
`source: unvalidated_capture`; these bounds are not a validated replay plan.

Exit code 2 signals factual failure, continuation failure, or budget exhaustion.
A completed factual capture that fails estimator preflight also returns 2.
A fully completed run that refuses estimates solely because evidence is unknown
returns 0: the refusal is a valid result. Invalid inputs return 2 before output
creation. The output folder must be new or empty so prior evidence is preserved.

## Export layout

| File or folder | Contents |
| --- | --- |
| `results.json` | Settings, policy/model metadata, exact factual trace hash, complete planned continuation schedule, all reached requests/replies, per-target coverage, estimates, loci, and separate call totals |
| `traces/` | The completed factual trace and completed continuation traces |
| `explanations/` | A separate evidence-only explanation derived independently from each completed trace |
| `evaluator_truth/` | Simulator configuration and injected records, separate from policy/explainer evidence |
| `trace-schema.json` | Schema for each exported trace |
| `README.md` | Run-specific interpretation, coverage, and statistical limits |
| `manifest.json` | SHA-256 hashes for every other exported file |

Manifest hashes detect changed bytes; they do not establish authenticity. Keep
evaluator truth and run-level labels out of the policy and explainer. These
signed effects are exported separately, with no overlay through the older
`EffectEstimate` graph representation.

The Python API is
`consequa_x.benchmark.decision_contrastive.contrastive_decisions`. It accepts a
completed policy episode and a `BudgetedPolicy`, so callers can share one budget
across factual recording and continuations, or account for those stages
separately. Its `calls` field counts continuation calls only; the result summary
records shared-budget calls before and after the experiment.
