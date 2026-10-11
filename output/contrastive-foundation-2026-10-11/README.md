# Decision contrastive replay: offline validation

The installed Python alpha (`0.1.0a1`) at source revision
`2a17931536701bfb24e0cdc2c2c032cd613b7da1` now tests recorded decision boundaries
with fresh policy continuations. These retained examples use scripted or seeded
synthetic policies and simulated payments. No language model was run, no draws
were replaced, and no PyPI/npm release was made.

## Retained examples

| Example | Completed continuations | Failed / unstarted | Total policy calls | Result |
| --- | ---: | ---: | ---: | --- |
| [Scripted control](scripted-control/README.md) | 6 | 0 / 0 | 15 | All nine target/position effects are zero; no rescue locus. |
| [Budget limit](budget-limit/README.md) | 0 | 1 / 5 | 5 | A partial continuation fails; all estimates and loci are refused. |
| [Seeded retry fixture](planted-retry/results.json) | 48 | 0 / 0 | 84 | The nominal state and action-linked loci identify the middle retry decision. |

Each example captures one three-decision factual episode. The call totals
include the factual recording: 3 + 12 for the control, 3 + 2 for the budget
failure, and 3 + 81 for the seeded fixture. Held decisions spend zero fresh
calls. The budget failure's final refused decision also spends zero; it retains
no completed branch trace or invented outcome. Across these examples there are
57 completed traces, including three factual traces, and 104 actual scripted or
synthetic policy calls.

## Independent mechanism reference

[reproduce_fixture.py](reproduce_fixture.py) defines a visible-input synthetic
policy that selects the eligible refund and uses a seeded fair coin to retry an
ambiguous timeout. The simulated first refund commits before that timeout.
Without idempotency, retrying commits a duplicate; stopping preserves exactly
one refund. Policy metadata and configuration remain fixed across branches.

The [fixture reference](planted-retry/fixture-truth.json) was saved before policy
sampling and is not an estimator or policy input. Its analytic Bernoulli
idealization has changed bad-outcome probabilities 0.5, 0.5, and 1 at positions
0, 1, and 2 for the state and action-linked targets. Resampling the early selection
also resamples the later retry, so it can improve the outcome. Resampling only
the terminal stop cannot undo a duplicate already committed. The intended latest
population rescue is therefore position 1. Initial selection stays true and has
zero effect at every position.

The fixed 16-seed samples at each position produced:

| Position | Role | Changed state bad rate | Signed effect | Nominal 95% bootstrap interval |
| --- | --- | ---: | ---: | --- |
| 0 | Initial selection and suffix | 6/16 | -0.625 | [-0.875, -0.375] |
| 1 | Retry/stop and suffix | 11/16 | -0.3125 | [-0.5625, -0.125] |
| 2 | Terminal stop | 16/16 | 0 | [0, 0] |

The action-linked estimates match these state estimates because the fixture's
effects have complete qualifying agent provenance. Initial-action effects are
zero. Position 1 is the latest nominal negative rescue, even though the early
position has the larger observed effect. This demonstrates the localization
rule on one declared mechanism; it establishes neither statistical calibration
nor language-model performance.

## Reproduce without inference

Install the declared source revision in a fresh environment, then use new output
directories:

```sh
python -I -m consequa_x decision-experiment --provider scripted --case unsafe_retry --samples 2 --seed 100 --factual-seed 0 --targets action,consequence,action_linked_consequence --max-calls 30 --bootstrap-samples 200 --output output/my-contrastive-control
python -I -m consequa_x decision-experiment --provider scripted --case unsafe_retry --samples 2 --seed 100 --factual-seed 0 --targets action,consequence,action_linked_consequence --max-calls 5 --bootstrap-samples 200 --output output/my-contrastive-budget
python -I output/contrastive-foundation-2026-10-11/reproduce_fixture.py --output output/my-planted-retry --source-commit 2a17931536701bfb24e0cdc2c2c032cd613b7da1
```

The second command deliberately returns exit status 2 for budget exhaustion.
The fixture recipe records settings, its own byte hash, and analytic reference
before drawing any decisions. Its source-commit argument is caller-declared;
it does not authenticate the installed package. [protocol.json](protocol.json)
and [execution.json](execution.json) preserve the original command plan,
statuses, and timing. The fixture saves raw traces; explanations can be
recomputed using the installed framework. The CLI examples also retain their
explanations and separate simulator truth.

## Checks and limits

[source-validation.json](source-validation.json) records **866 passing tests and
240 passing subtests**, plus independent core and CLI checks. The fresh-wheel
[package audit](package-validation.json) verifies builds, manifests, 14
completed temporary export traces, recomputed verification/explanation results,
budget and unknown-provenance refusals, and exact compatibility for all 12
ordinary default traces against the previous installed wheel. Those temporary
checks are separate from the retained examples. [audit.json](audit.json) checks
the retained evidence without policy execution or redraws. Nested manifests
cover each export; [manifest.json](manifest.json) covers every file here except
itself. Hashes detect changes and do not authenticate evidence.

This is an independently written CAR-style binary adaptation. It uses one
observed factual label, changed-minus-factual bad probability, Python bootstrap
draws with linear percentile interpolation, and a latest negative-rescue rule.
Python random draws, minimum two samples, actual-call budgets, strict missing
outcome refusals, and incomplete-locus refusal are explicit differences from
the pinned upstream implementation. See [the method guide](../../docs/decision-contrastive.md)
for exact settings and reference links.

Intervals condition on one factual episode and world, have no multiplicity
adjustment, and can collapse for homogeneous samples. The fixed pseudorandom
seed schedule is not proof of independent sampling. A nominal rescue locus is
not proof of unique causation. This one mechanism does not measure interval
coverage or generalization. Positional coalitions, antithetic Shapley allocation,
a matched baseline comparison, and the frozen live study remain in the
[research plan](../../docs/car-reproduction-plan.md).
