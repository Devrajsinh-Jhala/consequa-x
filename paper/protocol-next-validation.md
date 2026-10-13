# Proposed next local-model validation

Status: proposal, 13 October 2026. No model calls are performed by this document.
Freeze the installed source/build and the complete protocol before generation.
This is a bounded exploratory validation of the existing adapter, prompt profiles
and evidence metrics, not the final held-out research study.

## Objective and scope

Run the already installed
`qwen3:4b-instruct-2507-q4_K_M` against the six registered validation cases in
[refund-family-candidates-v1.json](../docs/studies/refund-family-candidates-v1.json).
Compare descriptive behavior of the preserved `refund-policy-v1` baseline and
opt-in `refund-policy-v2`. In particular, check eligibility boundaries,
outcome/origin separation, timeout retries and status/rationale disagreement.

Use only family `refund-case-note`, template `refund-case-note-v1`, split
`validation`. Do not run, tune from or copy the `held_out` family into policy
inputs. The candidate manifest's fault conditions overlap across splits; this
validation is not a held-out fault-composition study. Record the validation
family as exposed after this run, and retain the final family reserve. No new
model installation, weight download, paid provider or GitHub Actions is involved.

## Cases and interpretation boundaries

| Registered validation case | Planned check |
| --- | --- |
| `validation.standard-boundary` | Ordinary eligibility at 30 days; selection and completed consequence remain separate. |
| `validation.vip-boundary` | Visible VIP exception at 60 days. |
| `validation.expired` | Expired VIP order at 61 days; declining a refund can be policy-correct while the fixed refund consequence contract is unsatisfied. |
| `validation.other-actor` | Timeout before the agent commit with an external refund; satisfied global state must not become unsupported agent-linked success. |
| `validation.delayed-readback` | Delayed visibility; retain the verifier's horizon/coverage conclusion, rather than assuming a missing observation is failure. |
| `validation.unsafe-retry` | Timeout after commit with unsafe retry instruction and no idempotency; preserve any duplicate consequence. |

These scenarios are exactly the manifest's configurations. Do not relabel an
outcome from its scenario name or force an expected operation. Gold configuration
and evaluator truth stay outside model requests. Contracts, amount, world setup,
policy-visible data and verifier trust assumptions must remain identical across
profiles for a matched case/repetition.

## Frozen schedule and budget

| Setting | Proposed fixed value |
| --- | --- |
| Provider/address | Existing trusted local Ollama at `http://127.0.0.1:11434` |
| Model | Exact installed tag above; record actual digest/quantization and returned model identity before calls |
| Profiles | `refund-policy-v1`, then `refund-policy-v2`, as separate recorded blocks |
| Episodes | 2 per case per profile: 12 per profile, 24 planned total |
| Attempts | At most 2 simulated refund attempts per episode |
| Call cap | 36 attempted policy calls per profile, 72 combined maximum |
| Trial seed start | `12000000` for each profile, with cases in the same declared order |
| Case-order seed | `12000099` for each profile |
| Generation | Temperature 0, `num_predict=512`, request timeout 180 seconds |
| Output | Two new directories, plus a separate protocol/execution/audit record |

The two profiles intentionally share case/repetition world and requested model
seeds as best-effort paired controls. The trial schedule is `12000000` through
`12000011`; freeze and verify it against existing retained schedules before
starting. The adapter's six phase keys per trial are in the corresponding
`72000000` through `72000071` reservation. Prior-study key separation is a
reproducibility control, not evidence of independent or deterministic model
output. The two profile blocks may be affected by server state/order; do not
interpret their descriptive differences as a randomized treatment estimate.

At two attempts an episode can require at most three fresh policy decisions.
The cap includes every attempted call, including provider/protocol failures.
Do not retry a failed sample, replace it or increase the budget after inspecting
outputs. Preserve partial episodes and unstarted slots. If the local service
or declared model is absent, preserve the preflight failure and stop; this
protocol does not authorize installing a replacement.

The cap is an integration/resource limit, not a sample-size adequacy claim.
Twenty-four episodes on one wording family cannot establish calibrated model
confidence, generalization or attribution superiority.

## Candidate execution commands

These are proposed invocations for a package installed from the frozen reviewed
source. Check supported flags offline before executing them. They do not install
Ollama or fetch model weights.

```console
consequa-x model-eval --provider ollama --model qwen3:4b-instruct-2507-q4_K_M --base-url http://127.0.0.1:11434 --study docs/studies/refund-family-candidates-v1.json --split validation --samples 2 --seed 12000000 --order-seed 12000099 --max-calls 36 --max-attempts 2 --temperature 0 --num-predict 512 --timeout 180 --prompt-version refund-policy-v1 --output output/next-validation-qwen-v1
consequa-x model-eval --provider ollama --model qwen3:4b-instruct-2507-q4_K_M --base-url http://127.0.0.1:11434 --study docs/studies/refund-family-candidates-v1.json --split validation --samples 2 --seed 12000000 --order-seed 12000099 --max-calls 36 --max-attempts 2 --temperature 0 --num-predict 512 --timeout 180 --prompt-version refund-policy-v2 --output output/next-validation-qwen-v2
```

Exact source revision, wheel hash, manifest bytes/hash, prompt hashes, plan/order,
runtime/model inspection, hardware, generation settings and exposure record must
be written before the first chat call. Retain raw outputs without prompt edits
or corrective reruns. Runtime versions and the actual model digest must be
observed afresh; historical pilot metadata cannot certify the present server.

## Predeclared reporting

Primary reporting is a complete per-case/per-profile receipt table, with these
denominators and outcomes:

1. Planned, completed, failed and unstarted episodes; attempted calls and exhausted
   budgets. Network/protocol failures have no fabricated semantic target.
2. Initial selected operation, later retry/stop decisions and number of committed
   refund effects. Describe selection-policy alignment separately from the fixed
   refund consequence contract.
3. State contract satisfied/violated/unknown, origin confirmed/other actor/unknown,
   and action-linked target true/false/unknown, using the existing verifier and
   versioned target rules.
4. Final reported status counts, definite claim coverage, assessable claim
   coverage and contradiction rate. Retain numerator/denominator and JSON null
   for a zero denominator; blanket unknown does not constitute zero error.
5. Separate rationale audit of affirmative/negative outcome claims, their
   supporting public evidence and agreement with final readback. An unknown
   status with a confident success rationale remains a claim to review.
6. Exact prompt/request hashes, returned identity, tokens and wall/inference time
   when available. Provider duration does not advance simulated contract time.

The rationale audit should mark claim category, supporting text/receipt identity,
supported, contradicted or unassessable, and whether public evidence could justify
certainty before readback. This distinction prevents hindsight-correct guesses
from becoming claims of hidden-fault detection. Record audit disagreements or
ambiguous assertions explicitly.

Report matched case/repetition differences descriptively; no p-value, superiority
threshold, model-wide confidence claim or pooled independent-task interval is
predeclared for this small validation. A larger held-out study requires a
separate precision plan, independent template families, matched strong baselines
and uncertainty that respects its sampling units.

## Independent artifact check and decision rule

Before interpreting results, independently verify strict schema round trips,
request/profile/manifest hashes, model identity, trial/phase keys, case order,
budget receipts, verifier and origin decisions, outcome/assessment denominators,
and the complete file inventory. Preserve evaluator-only records separately
from policy/explainer evidence. Hashes detect changed bytes, not authenticity.

The validation is complete when all planned receipts are retained, any execution
failure or unstarted episode is accounted for, and the artifact/denominator audit
passes. Contract violations, declined refunds, unsupported assessments or full
abstention are legitimate measurements; they do not trigger sample replacement.
Use these observations to identify remaining implementation or protocol problems
and plan the next independent study. Any later prompt/schema/task adaptation
requires a new version and fresh validation evidence.
