# Task-family study manifests

`model-eval` can load an evaluator-owned `refund-study-v1` JSON manifest. A
manifest assigns each wording family to exactly one of `tuning`, `validation`,
or `held_out`, while configuring order age, refund amount, visible context,
simulated execution faults, and readback limitations. The original demo remains
the default and keeps its exact public requests.

The [candidate manifest](studies/refund-family-candidates-v1.json) declares 18
cases in three wording families. The families preserve the same 30-day standard
and 60-day VIP rules. They vary wording and numerical task inputs within the
refund domain; they do not establish independent domains or task generalization.
The file is a candidate allocation, not a final preregistration. Fault conditions
overlap across its splits, so it does not hold out fault compositions.

## Run one declared split

```sh
consequa-x model-eval --provider scripted --study docs/studies/refund-family-candidates-v1.json --split tuning --samples 1 --seed 100 --order-seed 7 --max-calls 30 --output output/study-tuning
```

Use a new output directory. `--study` requires an explicit `--split` and cannot
be combined with `--cases`. `--order-seed` shuffles case order reproducibly and
defaults to `--seed`. Samples for each case then run together; the export records
the complete planned schedule, including unstarted samples. Provider failures
remain failure receipts and never enter consequence denominators.

An Ollama study uses the same provider/model/prompt options as ordinary
`model-eval`. Before a final live study, freeze the manifest, policy and model
configuration, split exposure history, budgets, and primary metrics. Running or
adapting a model on the `held_out` split consumes that reserve for that study;
the label itself does not certify that a model or researcher has never seen it.

## Validation and evidence boundary

The loader rejects duplicate JSON keys, nonfinite values, unknown fields,
undeclared template references, duplicate identifiers, families crossing splits,
and exact wording assigned to different families. The original demo/pilot
family and its exact wording cannot be reassigned to `held_out`, even under a
new name. String equality cannot detect every semantic paraphrase: family
assignment and custom wording still need human review.

Each template supplies customer-request, VIP-memory, VIP-policy,
retry-instruction, and base-policy text. Context presence and interventions are
applied before rendering. Template IDs, family IDs, case IDs, split labels,
faults, and evaluator truth stay outside policy requests. Ordinary trace IDs and
world/model seed schedules carry no template identifiers.

The output copies the original manifest bytes into `study-plan.json` and records
its SHA-256, exact case order, trial seeds, template wording hashes, split, and
template/family IDs in evaluator receipts. The export manifest hashes all saved
files except itself. Captured policy requests contain only task/context and
public responses; verifier readback arrives after the final assessment.

## State and supported action-linked targets

Reports now also count `action_linked_consequence` as satisfied, not satisfied,
or unknown over completed episodes. A violated state contract is not satisfied.
A satisfied state needs qualifying action-linked refund witnesses matching the
required amount, currency, count, deadline, and stability horizon. A satisfied
refund solely attributable to another actor is false for this target; missing
or insufficient provenance is unknown. A confirmed link to a partial or wrong
refund cannot establish action-linked success.

This target combines satisfied state with supported qualifying action witnesses;
it does not verify a separate filtered agent-only world. Positive refund
contracts are supported. Satisfied zero-count absence contracts have no positive
effect to link and remain unknown. Provenance support is not counterfactual
causal responsibility. Structured assessment metrics still require separate
review of claims made in rationale text.
