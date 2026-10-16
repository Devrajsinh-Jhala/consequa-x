# Consequa-X

Consequa-X explains consequential agent actions from captured history and
independent outcome evidence. It keeps the tool response, the agent's reported
assessment, the observed outcome, and effect origin separate. A timeout can
coexist with a completed effect; another actor can satisfy the requested state.

Version 1 provides a stable evidence core: portable typed traces, explicit
application verifiers, domain-specific target matching, and evidence graphs that
preserve successive observations. Research replay adapters have separately
declared interfaces and assumptions.

The GitHub repository is private. Repository, issue and research links require
access; the Python distributions on PyPI are public. The source distribution
includes application examples, Markdown documentation, tests and study scripts
so package users can work without GitHub access. Large retained research
datasets and the original research PDF remain repository materials.

## Install

Use Python 3.11 or newer:

```sh
python -m pip install consequa-x
consequa-x --version
```

The examples below use the version 1 API. The framework has no required runtime
dependencies. Importing the core and running offline examples require no model,
API key, payment provider or network call. Use `python -m consequa_x` wherever an
example uses `consequa-x`.

Current validation covers Windows with Python 3.11 and 3.12; the declared
Python 3.11+ range and pure-Python wheel are not test results on every platform.
Release receipts identify the exact source, artifacts and checks. GitHub Actions
remains disabled; release validation runs locally.

## Capture, verify and explain

The core accepts application records without importing the refund simulator.
This minimal synthetic capture illustrates the built-in refund predicate:

```python
from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Observation, OutcomeContract,
    Trace, explain, verify,
)
from consequa_x.schema import get_trace_schema, validate_trace

expected = {"payment_id": "p1", "amount_minor": 1000, "currency": "INR"}
contract = OutcomeContract("contract-1", "refund_processed", expected,
                           deadline_ms=50, stability_ms=20)
action = Action("refund-1", "trace-1", "agent", "refund", expected, 0, contract)

# In an application, capture this independently from a trusted read-only source.
observation = Observation(
    "readback-1", "independent-ledger", 100, 100, {"payment_id": "p1"},
    ({**expected, "effect_id": "effect-1", "committed_at_ms": 25,
      "status": "processed", "action_id": "refund-1", "actor": "agent"},),
)
receipt = verify(action, observation)
trace = Trace("trace-1", action, (), (),
              AgentAssessment(AssessmentStatus.FAILURE, 10),
              (observation,), (receipt,))
restored = Trace.from_json(trace.to_json())
assert validate_trace(restored.to_json()) == trace
assert receipt.status.value == "satisfied"
assert receipt.origin.value == "confirmed"
assert explain(restored).assessment_alignment == "contradicted"
schema = get_trace_schema()  # Bundled portable trace schema 0.1.
```

Register the intended contract before the action. In a full capture, retain
dispatch/response events, attempts and the agent's reported assessment, then
obtain separate readback. The built-in verifier checks payment, integer amount,
currency, exact count, commit deadline and persistence horizon. Incomplete,
unavailable, stale or malformed readback produces `unknown` when the predicate
cannot be established. Origin is a separate `confirmed`, `other_actor` or
`unknown` conclusion.

The wire schema remains `0.1`; software version and wire version are separate.
Decoding rejects unsupported versions, unknown fields, invalid identity links
and dependency cycles. Validation checks structure and declarations; it does
not authenticate the source or establish that its records are truthful.

## Integrate another application

Supply `verify(action, observation, verifier=application_verifier)`. Its
`verify` method returns a `VerificationResult` bound to the supplied contract,
observation identity, source and watermark. The application owns source trust,
scope, completeness, predicate semantics, time bounds and provenance.

For another predicate, `explain(trace)` stays domain-neutral and leaves reported
assessment alignment unassessable. Supply
`explain(trace, target_matcher=application_target_matcher)` when the reported
assessment concerns satisfaction of that contract. Its
`matching_effect_ids(action, verification)` method returns a tuple of unique
attributable effect IDs after checking requested payload, deadline and
persistence. A propagated action ID alone does not qualify an unrelated effect.
The matcher is never executed for an `unknown` receipt.

The source archive contains a complete second domain in
`examples/artifact_delivery.py`: capture an artifact-delivery timeout, hash the
bytes independently read back, verify an exactly-one delivery contract, round-trip
the trace, and explain the discrepancy using only the public API. Download and
extract the version 1 source archive, then run the example:

```sh
python -m pip download --no-deps --no-binary=:all: consequa-x==1.0.0
python -m tarfile -e consequa_x-1.0.0.tar.gz unpacked
cd unpacked/consequa_x-1.0.0
python -m pip install .
python examples/artifact_delivery.py
```

The example performs no delivery or model call. Its fixture's persistence
witness is a declared source responsibility; current existence alone would not
prove historical stability. The packaged `docs/application-integration.md`,
`docs/stable-api.md`, and `docs/graph-witnesses.md` describe the adapter boundary,
version 1 compatibility and graph migration in detail.

Repeated effect IDs retain an identity node and separate observation witnesses.
Changed payload, actor or status in a later readback cannot overwrite an earlier
witness or inherit its origin edge. Graph edges distinguish declared dependency,
captured order, provider provenance and estimated intervention effects. A
provenance edge does not prove counterfactual necessity.

## Run offline demonstrations

```sh
consequa-x demo --output output/my-demo --seed 0
consequa-x explain output/my-demo/traces/episode_01.json --output output/my-explanation.json
consequa-x experiment --output output/my-experiments --samples 40 --seed 0
```

The demo exports twelve refund scenarios, including timeout after commit,
false success, partial effects, delayed visibility, retries, other actors and
missing provenance. Open `output/my-demo/README.md` for its outcome table.
Every run requires a new or empty output directory. Explanation output must be
a new file and cannot replace its source trace. Choose a different path when
repeating a command.

| Export | Purpose |
| --- | --- |
| `traces/` | Captured events, responses, assessments, observations and receipts |
| `explanations/` | Diagnoses and evidence graphs |
| `evaluator_truth/` | Synthetic world state and fault labels for evaluation only |
| `trace-schema.json` | Portable JSON Schema |
| `manifest.json` | Artifact identities and hashes |

Keep evaluator truth outside policy and explainer inputs. Hashes detect changed
bytes; they do not authenticate evidence sources. All payment effects in the
research adapters use synthetic funds in isolated worlds.

## Research interfaces

Modules under `consequa_x.benchmark`, study commands and exact policy prompts
remain declared research interfaces. Their protocols pin source revisions and
assumptions separately from the stable evidence core.

```sh
consequa-x model-eval --provider scripted --samples 2 --max-calls 100 --output output/my-policy-smoke
consequa-x decision-experiment --provider scripted --case unsafe_retry --samples 16 --seed 100 --factual-seed 0 --max-calls 400 --output output/my-decision-replay
consequa-x decision-shapley --provider scripted --case clean --pairs 16 --samples 1 --endpoint-samples 16 --seed 100 --max-calls 2000 --output output/my-shapley-replay
```

Replay uses fresh isolated worlds, explicit targets and call budgets. Unknown
outcomes, failures, invalid coalitions and unstarted branches remain visible;
affected estimates are refused. Contrastive defaults use exact binomial
intervals. Shapley pair means use Hoeffding bounds, with separate exact-binomial
endpoint differences. These intervals can be wide at small budgets; their
sampling assumptions and individual-interval scope remain explicit. Legacy
bootstrap/normal modes remain named comparison options.

The default `strict` game refuses unreachable held positions. The separate
`--coalition-game on_reach` game treats normally unreached held positions as
inactive and uses the actual completed outcome. Reached incompatible decisions
still invalidate a draw. The games have different population targets.

`refund-interactions` enumerates physical selection/retry games.
`calibrate-interactions` repeatedly samples them and rescores the same saved
draws under normal versus conservative uncertainty methods. Both require
`--source-revision`; see packaged `docs/refund-interactions.md` and
`docs/interaction-sampling.md` before running a retained study. The full default
sampling plan has 2,048 trials and 655,360 planned branches; it is not a quick demo.
A sampling implementation or smoke test does not establish a completed,
independently audited calibration result.

An optional Ollama adapter uses an already installed local model and server:

```sh
consequa-x model-eval --provider ollama --model YOUR_INSTALLED_MODEL --cases clean,timeout_after_commit --samples 1 --max-calls 6 --output output/my-local-model
```

This command does not install or download a model. The original
`refund-policy-v1` profile remains the default; `--prompt-version refund-policy-v2`
selects an exploratory refinement. Study exports record model identity, prompt
hashes, requested seeds, ordering, failures and actual cost. A requested seed is
not proof of model determinism or independent sampling.

The retained evidence includes an audited 384-trial synthetic interval comparison
and a 24-episode local Qwen3 validation using 59 model calls. The latter compares
two existing prompt profiles on exposed validation cases. The revised profile
abstained in every structured status, so its conditional contradiction rate is
undefined; some rationales still contained positive processing claims. Structured
abstention, assessable-claim errors and rationale assertions must be scored
separately. These results establish neither improved accuracy nor held-out
superiority.

The paper is a protocol/software contribution with synthetic and exploratory
local-model evidence. It does not claim a new attribution estimator, calibrated
live-model confidence, broad domain generalization or superiority over a matched
strong baseline. The IEEE draft and retained data remain private repository
materials; no submission or acceptance is claimed. Joint context/fault methods,
matched live baselines and held-out template/fault-composition studies remain
future research. No npm package is published.

## Develop and contribute

From the extracted source archive or an authorized repository checkout:

```sh
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests scripts
python -m build
```

Builds write the wheel and source archive to `dist/`. `requirements-dev.lock`
records the Python 3.12 development dependencies; it is not a compatibility
result for other interpreters. Release-specific validation, artifact hashes,
registry verification and study status belong in release receipts.

Private repository collaborators can use the
[contribution guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/CONTRIBUTING.md),
[release checklist](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/release-readiness.md),
[research roadmap](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/research-roadmap.md),
and [evidence ledger](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/paper/evidence-ledger.md).
The contribution guide and Markdown documentation are also in the source archive;
retained datasets and the paper are not bundled into the Python wheel.

The [next-release launch plan](docs/launch-readiness.md) prioritizes an offline
visual report, minimal disclosure by default, public onboarding/support and
additional platform validation. These are proposed additions; the published
package remains version 1.0.0.

Consequa-X is licensed under the **MIT License**, included with the distributions.
Copyright and author metadata identify Devrajsinh Jhala. Source privacy does not
change the permissions granted for the publicly distributed code.
