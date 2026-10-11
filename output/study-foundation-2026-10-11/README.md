# Study-family and decision-replay installation checks

These exports validate the installed Python alpha (`0.1.0a1`) at source commit
`0c0413b8f6d3ec976962cd443d751385c528ecc7`. All policy decisions are scripted and
all payments are simulated. No Ollama generation or paid API calls were made.
This is contributor evidence for the new interfaces, not a live model study or
a completed CAR comparison.

## Retained examples

| Example | Completed episodes/branches | New policy calls | Purpose |
| --- | ---: | ---: | --- |
| [Tuning split](tuning/README.md) | 6 | 12 | Manifest loading, shuffled order, exact manifest bytes, and separate evaluator receipts. |
| [Three-target replay](three-target-replay/README.md) | 4 | 6 | One cached branch collection supplies action, state, and supported action-linked estimates. |
| [Decision-prefix replay](decision-prefix.json) | 2 of 3 | 4 | Held decisions, suffix resampling, and a shared budget that fails the third branch. |

The prefix example records a separate three-call factual episode. Its branches
hold 3, 1, and 0 decisions and spend 0, 2, and 2 new calls, respectively. The
third branch attempts another decision after the shared four-call budget is
exhausted; its receipt has no completed trace or invented outcome. Both completed
branches preserve the scripted unsafe retry and violate the exactly-once refund
contract. Resampling this deterministic policy does not imply rescue.

In the tuning example, state verification finds three satisfied and three
violated contracts. The supported action-linked target finds two satisfied,
three not satisfied, and one unknown: missing provenance does not become agent
success merely because the state is satisfied.

The paired example removes `vip_policy` under `refund-support-note-v1`, with two
seeds per condition. Each selected target has factual rate 1, changed rate 0,
and signed effect 1. The approximate intervals include zero. These are fixture
checks of wiring and call reuse, not adequately sampled research claims.

## Reproduce the examples

Install this revision in an isolated environment. Use fresh output directories:

```sh
python -I -m consequa_x model-eval --provider scripted --study docs/studies/refund-family-candidates-v1.json --split tuning --samples 1 --seed 100 --order-seed 7 --max-calls 30 --output output/my-study-tuning
python -I -m consequa_x model-experiment --provider scripted --case clean --candidates vip_policy --samples 2 --seed 200 --targets action,consequence,action_linked_consequence --template refund-support-note-v1 --max-calls 12 --output output/my-three-target-replay
```

[protocol.json](protocol.json) records the settings declared before export;
[execution.json](execution.json) records command status and timing. The Python
[decision replay guide](../../docs/decision-replay.md) explains the prefix API
and factual-recording cost. Captured decisions and receipts for this example
are in [decision-prefix.json](decision-prefix.json).

## Validation and integrity

[package-validation.json](package-validation.json) records a wheel and source
distribution built from the declared revision, then checked in a fresh virtual
environment without project runtime dependencies. Its separate temporary
checks cover all 18 candidate cases across the three splits, four additional
replay branches, and 82 artifact hashes. They verify schemas, strict decoding,
recomputed verifier/explainer results, evaluator-label isolation, exact study
manifest bytes in exports and the source distribution, and prefix/provider
failure handling. The temporary check exports are summarized in that receipt;
they are separate from the examples retained here. The default trace also
matches the previous installed wheel exactly.

[source-validation.json](source-validation.json) records 776 passing tests and
240 passing subtests, followed by 71 focused checks for the final additive
branch-receipt field. Independent review compared 36 complete default episodes
against the preceding revision. The packaging-only fix adds the candidate JSON
to source distributions. CI additionally runs the candidate split, three-target
replay, installed prefix API, and source-manifest inclusion on Windows and
Ubuntu with Python 3.11 and 3.12.

[audit.json](audit.json) independently checks the retained example files,
their hashes, schemas, recomputed outcomes, and call accounting. Each CLI
example has its own manifest; [manifest.json](manifest.json) covers every file
in this folder except itself, using exact byte hashes. Hashes detect changes;
they do not authenticate evidence or model execution.

## Research scope

The [candidate manifest](../../docs/studies/refund-family-candidates-v1.json)
contains 18 cases in three wording families with six cases per split. The
original demo/pilot family is excluded from the held-out reserve. Loader checks
prevent families crossing splits and exact wording being reassigned under new
family names. They cannot certify semantic independence or historical exposure.
Fault conditions overlap across splits. The package checks used a deterministic
scripted policy even for the candidate `held_out` allocation; no language model
was evaluated on it.

Supported action-linked evidence is not counterfactual causal responsibility.
Prefix replay is a foundation for decision-level methods, not an attribution
estimator. Implementing and validating the contrastive/Shapley comparators and
freezing a live study remain in the [CAR reproduction plan](../../docs/car-reproduction-plan.md)
and [study protocol](../../docs/study-plan.md). Earlier live-pilot exports remain
separate. Nothing has been published to PyPI or npm.
