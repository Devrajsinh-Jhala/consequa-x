# Decision coalitions and Shapley: offline validation

The Python alpha (`0.1.0a1`) at source revision
`ee1a4062fb6b6b111fb2990cd51b649b403d38ce` now supports positional held-decision
coalitions, fresh antithetic Shapley walks, and independent endpoint diagnostics.
These retained examples use scripted or seeded synthetic policies with simulated
payments. No model calls, replacement draws, or registry releases were made.

## Retained examples

| Example | Completed branches | Invalid / failed / unstarted | Actual calls including factual | Result |
| --- | ---: | ---: | ---: | --- |
| [Scripted control](scripted-control/README.md) | 16 | 0 / 0 / 0 | 18 | All six coefficients and all three endpoint differences are zero. |
| [Budget limit](budget-limit/README.md) | 0 | 0 / 1 / 15 | 3 | The first empty-endpoint draw fails partway; every vector and endpoint diagnostic is refused. |
| [Protective timeout stop](protective-stop/results.json) | 112 | 0 / 0 / 0 | 143 | The timeout stop has a negative consequence contribution; independent totals differ because fresh samples are retained. |
| [Unavailable coalitions](invalid-coalitions/results.json) | 19 | 1 / 0 / 0 | 29 | One requested held position is unreachable; all nine path coefficients are refused, while separate endpoint estimates remain available. |

Every example retains one complete factual trace. Across these examples there
are **151 completed valid traces** and **193 actual scripted/synthetic policy
calls**. Held decisions spend zero fresh calls. Invalid or failed branches have
reached receipts without a fabricated completed trace or semantic outcome.
Every requested target reuses each collected branch without extra calls.

## Protective decision and sampling noise

The [public recipe](../../examples/decision_shapley_fixture.py) selects an eligible
refund and uses a seeded fair coin after an ambiguous timeout. One refund has
already committed; a non-idempotent retry commits a duplicate. Stopping preserves
exactly one refund. Factual world seed 0 and policy seed 3 produce two positions:
selection followed by a timeout stop. Both positions are reached in every
requested coalition; a fresh retry can extend the branch with a new stop.

The [analytic reference](protective-stop/fixture-truth.json), written before
sampling and kept out of policy/estimator inputs, idealizes the retry coin as
Bernoulli(0.5). The population consequence shares are `[0, -0.5]`: holding the
selection is irrelevant, while holding the factual stop is protective. Finite
fresh draws need not assign exactly zero to an irrelevant player.

The predeclared eight pairs, two draws per encountered coalition, and eight
draws per independent endpoint produced:

| Position | Role | Consequence contribution | Nominal 95% normal interval |
| --- | --- | ---: | --- |
| 0 | Initial selection | -0.125 | [-0.285387, 0.035387] |
| 1 | Timeout stop | -0.5 | [-0.707059, -0.292941] |

Action-linked consequence results match these state results because the fixture
has qualifying agent provenance. Initial-action contributions are both zero.
The consequence coefficient sum is **-0.625**, while the independent full-minus-
empty endpoint difference is **-0.375**, giving a descriptive discrepancy of
**-0.25**. These numbers are preserved without normalization. Walks telescope
against their own fresh endpoint values; that identity cannot guarantee
agreement with a separately sampled diagnostic. This finite example establishes
neither calibrated coverage nor population certainty.

## Unavailable positional game

The second recipe mode fixes factual policy seed 0, producing a retry and then
a later post-success stop. Resampling the earlier retry can stop before the
requested held position 2. One of the 20 planned draws does so. Its coalition
is invalid under this adapter's declared conservative rule. It is retained
without a target label or redraw, and the complete path vector is refused for
every target. Independent endpoint estimates remain separate; the state and
linked endpoint difference is 0.5, with the unbounded nominal normal interval
`[-0.479982, 1.479982]` from only two endpoint draws.

This restriction can make variable-length refund attribution unavailable. A
fixed-length AND oracle in the tests and [independent math audit](math-validation.json)
checks shared-credit allocation separately. It does not demonstrate interacting
refund decisions or language-model performance.

## Reproduce and inspect

Install the declared source in a fresh environment and use new output folders:

```sh
python -I -m consequa_x decision-shapley --provider scripted --case clean --pairs 2 --samples 1 --endpoint-samples 2 --seed 100 --factual-seed 0 --targets action,consequence,action_linked_consequence --max-calls 30 --output output/my-shapley-control
python -I -m consequa_x decision-shapley --provider scripted --case clean --pairs 2 --samples 1 --endpoint-samples 2 --seed 100 --factual-seed 0 --targets action,consequence,action_linked_consequence --max-calls 3 --output output/my-shapley-budget
python -I examples/decision_shapley_fixture.py --mode protection --source-commit ee1a4062fb6b6b111fb2990cd51b649b403d38ce --output output/my-protective-stop
python -I examples/decision_shapley_fixture.py --mode invalid --source-commit ee1a4062fb6b6b111fb2990cd51b649b403d38ce --output output/my-invalid-coalitions
```

The budget command deliberately returns status 2. The standalone recipe returns
0 when it successfully writes evidence, including its invalid-coalition mode;
inspect `summary` and estimate statuses to interpret that mode. The CLI returns
2 when its own run contains invalid coalitions. The recipe records its exact
byte hash, settings, and analytic reference before policy calls. A supplied
source SHA is a caller declaration, not package authentication.

[protocol.json](protocol.json) and [execution.json](execution.json) retain the
original plan, timing, and expected statuses. CLI runs retain separate
explanations and simulator truth; recipe runs retain raw traces and analytic
truth, with explanations independently recomputable. Nested manifests cover
their exports; [manifest.json](manifest.json) covers every file here except
itself. Hashes detect changed bytes and do not establish authenticity.

## Checks and limits

[source-validation.json](source-validation.json) records **1,020 passing tests
and 240 passing subtests**, plus focused coalition, estimator, and command
checks. The [fresh-package audit](package-validation.json) passed nine temporary
executions and 128 completed trace checks, independently recomputing pair
vectors, normal intervals, endpoint differences/discrepancies, refusal coverage,
and call receipts. Those temporary traces are separate from these retained
examples. All 12 ordinary default traces exactly match the preceding wheel.
Wheel and source archives, documentation, the public recipe, MIT license,
type marker, and installed commands were checked.

[math-validation.json](math-validation.json) records 14 independent mathematical
and boundary checks, including signed interaction/protective oracles, pair-unit
variance, fresh seeds, and an extreme-confidence numeric edge. The independent
[retained-byte audit](audit.json) checks these saved examples without inference
or replacing draws.

This is a CAR-style adaptation with declared differences: conservative
unreachable-position refusal, strict whole-vector evidence coverage, actual-call
budgets, minimum two pairs/endpoints, Python streams, 16-pair default, and
independent endpoint diagnostics. Intervals condition on one factual world,
have no multiplicity adjustment, and can be fragile or degenerate. Requested
seeds do not establish independence. Descriptive discrepancy is not a calibrated
test, and signed contributions are not responsibility percentages. See the
[method guide](../../docs/decision-shapley.md) and [comparison plan](../../docs/car-reproduction-plan.md)
for calibration, typed-domain extensions, and the frozen live study still needed.
