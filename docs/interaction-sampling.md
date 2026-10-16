# Repeated physical refund interaction sampling

This is a dedicated study of the physical refund Shapley sampler. It does
not change `CalibrationPlan`, historical calibration exports or the earlier
finite-mixture enumeration. No language model is called. The retained collection
completed on 15 October 2026 after source review, tests and freeze; the status
below was updated 16 October 2026.

## Retained collection

The [frozen protocol](../output/interaction-sampling-2026-10-15/protocol.json)
declares source `0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9` and the complete
2,048-trial schedule. All trials and 655,360 planned branch slots are retained:
536,150 completed, 37,423 invalid, 256 failed at the deliberate cap and 81,531
unstarted. The collection used 628,535 actual scripted policy calls, zero model
calls and zero extra comparison calls. The
[summary](../output/interaction-sampling-2026-10-15/summary.json) contains all
288 coefficient, 96 endpoint and 48 interaction rows. These counts do not make
refused estimates or undefined population games numerically assessable.

Collection used the separately retained
[installed checkpoint](../output/interaction-sampling-checkpoint-2026-10-15/checkpoint.json)
and four worker processes. The
[execution receipt](../output/interaction-sampling-2026-10-15-execution.json)
binds the completed export manifest. All 36 runtime payloads in the public
stable release match this study checkpoint; their packaging/documentation
artifacts retain distinct hashes and source identities. The
[independent saved-evidence audit](../output/interaction-sampling-audits-2026-10-15/independent.json)
passed on 16 October 2026: 44,698,925 assertions, all 2,048 trials and 655,360
branches, plus 4,210 preselected complete traces. The
[derived findings](../output/interaction-sampling-findings-2026-10-15/FINDINGS.md),
complete CSV tables and structured analysis remain outside the sealed export.
Their postprocessor rehashed all 52 sealed files before deriving the tables.

At `p=q=.5`, on-reach consequence selection/retry/dummy normal coverage was
122/128, 118/128 and 117/128, compared with 128/128 each for Hoeffding bounds.
Mean widths increased from approximately .220-.226 to .960; reference-sign
detection fell from 84/128 and 128/128 to 0/128 and 8/128 for the active players.
Independent endpoint normal/exact coverage was 113/128 versus 126/128, with
mean widths .292 versus .473 and sign detection 123/128 versus 30/128.
These are specified-case individual-interval results; the complete tables retain
all controls, both games, all targets and every refusal denominator. The pooled
interaction diagnostic remains a point without a confidence interval.

## Declared design

The default plan has 128 repetitions, 32 permutation/reverse pairs, one fresh
draw per coalition occurrence and 32 draws for each independent endpoint, at
confidence .95. All eight registered refund interaction mechanisms run under
both `strict` and `on_reach` games. This gives 2,048 trials, 320 planned branches
per trial and 655,360 planned branches overall.

Each trial records its own predeclared factual refund, retry and final stop,
then uses the production positional Shapley replay in isolated payment worlds.
This factual trajectory is a planted intervention, not natural selection or a
trajectory found by seed search. The policy reads public requests only. Outcomes
come from the existing independent readback/verifier/linked-target boundary.

The collection explicitly uses normal pair and endpoint intervals. The same
result is rescored with Hoeffding pair bounds and split-allowance exact-binomial
endpoint differences. No provider calls are made by rescoring; points, pair
vectors, branches, budgets and refusals stay the same. These variants are
comparisons of uncertainty, not new attribution estimators.

The strict game retains unreachable-held-position invalidity. The on-reach game
records normally unreached held positions as inactive and verifies the actually
completed trajectory. They are different population games. Available finite
strict vectors cannot create an otherwise undefined population reference.

## Seeds and caps

Trial seeds begin at 20,000,000 by default. Each trial reserves one factual seed
and all its continuation seeds; each seed reserves six model phase keys.
Permutation keys lie beyond the complete study's model-phase window. The plan
checks both reservations against supported ranges before any policy call.
This is disjoint from the earlier retained phase window ending around 72 million.
Seeded synthetic randomness models the declared Bernoulli law; requested keys do
not establish independence of arbitrary live models.

The nonbudget study cap is 1,000 actual calls per trial, including three factual
calls. A conservative upper bound at default settings is `3+3*320=963`, so this
cap permits all planned slots even at maximum reached length. It overrides the
finite-mixture export's smaller per-component cap without changing its mechanism
or historical data. The deliberate budget mechanism retains a four-call cap.
Held decisions consume zero fresh calls. Budget failures and every unstarted
slot remain in the record; no sample is replaced or redrawn.

Production full-held preflight reconstruction uses zero fresh policy calls and
is not an additional sampled endpoint. Both games and every interval variant
use the same per-trial declaration and cost accounting.

## Runner and artifacts

From an environment containing the reviewed package and the repository scripts:

```console
python scripts/run_interaction_sampling.py --source-revision FROZEN_COMMIT --output output/my-interaction-sampling
```

The runner also accepts `--repeats`, `--pairs`, `--samples`, `--endpoint-samples`,
`--confidence`, `--seed`, `--max-calls`, repeated `--mechanism` and repeated
`--game`. Use a new or empty output directory. Source revision is caller-supplied
provenance; the exporter does not inspect Git or certify that the caller used
that source. The installed source/build identity must be verified separately.

The installed package also exposes `consequa-x calibrate-interactions` with the
same numerical defaults and required `--source-revision`. The standalone runner
adds a separate timing/environment receipt. Both support `--workers 1..8`;
the retained protocol records the worker count, bounded in-flight queue and
declared-order result collation. Each process uses the same assigned trial seed
and budget, with no retries or replacement draws. Serial/parallel conformance
checks compare exact raw rows, evidence, evaluator truth and summary values.

Before the first policy call, `protocol.json` saves the complete trial schedule,
settings, mechanism declarations, analytic population references, interval
methods, retention rules and assumptions. The export contains:

| Artifact | Purpose |
| --- | --- |
| `trials/<mechanism>__<game>.jsonl.gz` | Every planned trial and slot, permutations, raw pair values, labels, compact measurement metadata, reached decision/call receipts and both interval variants |
| `evidence/<mechanism>__<game>.json.gz` | Preselected replicate-zero factual and every attempted branch: full public traces, explanations and receipts |
| `evaluator_truth/<mechanism>__<game>.json.gz` | Separately retained replicate-zero simulator configurations and committed/attempt records |
| `summary.json` | Complete branch inventories and coefficient/endpoint/interaction metric rows |
| `trace-schema.json` | Schema for the retained public traces |
| `manifest.json` | Completed artifact inventory with canonical paths, byte sizes and SHA-256 hashes |

Unexpected execution/export exceptions preserve the protocol and earlier raw
rows without a completion manifest. Do not rerun into that directory or silently
continue with replacement draws. The runner saves a timing/environment receipt
outside the completed artifact as `<output-name>-execution.json`. Audits and
derived findings should also stay outside the sealed export inventory. The
independent auditor requires the exact declared export files; hashes detect
changed bytes, not provider authenticity.

## Metrics and eligibility

Every coefficient and independent endpoint row reports planned, available and
refused estimates; population-reference-eligible trials; and eligible available
estimates. Numeric bias/RMSE and coverage use only the independently defined,
eligible reference. Refusals remain in planned denominators. An undefined strict
game has no coefficient coverage denominator even if a sampled vector is finite.
The four-call control retains an ideal population law while refusing incomplete
finite estimates.

Report interval coverage together with width, degeneracy, reference sign
detection and false nonzero flags for reference-zero players. Coverage rates have
explicit numerators/denominators and nominal Wilson uncertainty; a zero
denominator produces null, not zero error. Signed shares are probability
differences, not responsibility percentages. There is no multiplicity adjustment
over players, targets or mechanisms. State and linked targets often reuse the
same outcomes and are not independent replications.

A separate interaction diagnostic pools existing occurrences of masks 0,1,2,3
and computes `v(3)-v(1)-v(2)+v(0)`. It refuses if any required planned arm draw is
missing/unknown/invalid, or an arm has no sampled occurrence. It makes no extra
policy calls and has no confidence interval. Its bias/RMSE are descriptive;
this diagnostic does not create a newly calibrated interaction estimator.

## Independent audit

The auditor imports no Consequa-X estimator, scorer, analytic reference or
simulator. It independently reconstructs the complete seed/permutation schedule,
each fresh seeded choice, held/inactive/unreachable position, budget boundary,
measurement labels, pair vectors, normal and Hoeffding bounds, exact binomial
endpoint differences and every summary row. It uses fixed mechanism laws and
rational arithmetic for population references. Replicate-zero checks additionally
cover saved schemas, readback/gold projection, logical identities, request
response prefixes, evidence references, explanations and dependency structure.
`jsonschema` is an existing audit-only development dependency, not a framework
runtime requirement.

```console
python scripts/audit_interaction_sampling.py output/my-interaction-sampling --expected-source FROZEN_COMMIT --output output/my-interaction-sampling-audit.json
```

The audit output must be new and outside the sealed study. Corruption tests alter
raw schedules, labels, operations, costs, pairs, intervals, references,
inventories and aggregates, refreshing checksums where appropriate, to establish
that the audit checks semantics in addition to unchanged-byte detection.

## Evidence limits and reproduction gate

Passing integration tests or a small smoke run does not establish coverage,
power, live-model interaction recovery, held-out task generalization, joint
context/fault attribution or superiority over a matched strong baseline. Run
any new retained schedule only after source review, required local checks and
source freeze, and give it a distinct output location and declared identity.
The completed collection above retains the default seed window beginning at
20,000,000. Choose a separate seed window for engineering smoke checks, such as
30,000,000; do not overwrite or extend the sealed study. Package publication and
GitHub Actions are separate from this runner; it does not invoke either.
