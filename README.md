# Consequa-X

Consequa-X explains consequential agent actions using captured history and independent outcome evidence. The version `1.0.0` candidate provides portable traces, explicit application verifiers, domain-specific target matching, and evidence graphs that preserve successive observations. Final release checks are in progress; the published PyPI checkpoint is `0.1.0a2`.

The GitHub repository is private; its source and research links require repository access. PyPI packages are public. GitHub Actions remains disabled, and validation runs locally.

The core can consume captured application actions without importing the simulator.
The [application guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/application-integration.md)
and [offline artifact example](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/examples/artifact_delivery.py)
show the complete integration. The [stable API contract](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/stable-api.md)
defines version 1 compatibility and the unchanged trace schema `0.1`.

Research adapters use an isolated payment simulator with scripted policies and an optional local Ollama adapter. They keep the tool response, the agent's reported assessment, the observed outcome, and effect origin separate. A timeout can coexist with a completed refund; another actor can satisfy the desired state after the agent's attempt fails.

The first [recorded local-model pilot](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/live-pilot-2026-10-10/README.md) completed six runs with Qwen3 4B. All refunds were independently verified as successful, while the model reported failure in every run; changing the retry instruction produced no observed effect in two replay pairs. This is a small integration result. Payments remain simulated, and neither fixture experiments nor the pilot establish a new attribution method or empirical superiority. See [the design](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/design.md) for exact semantics and [the research roadmap](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/research-roadmap.md) for the paper and release milestones.

## Research materials and contributions

- [Original research brief (PDF)](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/research/Consequa-X_Research_Brief.pdf)
- [Initial literature assessment](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/research/Consequa-X_Research_Assessment.md)
- [Demo results and evidence exports](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/demo/README.md)
- [Paired fixture experiment results](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/experiments/README.md)
- [Policy evaluation guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/policy-evaluation.md)
- [Scripted policy smoke results](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/policy-smoke/README.md)
- [Paired policy replay guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/policy-replay.md)
- [Scripted replay smoke results](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/replay-smoke/README.md)
- [First live-model pilot and audit](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/live-pilot-2026-10-10/README.md)
- [Exploratory prompt comparison and retry diagnostic](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/prompt-sensitivity-2026-10-10/README.md)
- [Proposed model study protocol](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/study-plan.md)
- [Candidate task-family splits and evidence targets](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/study-manifests.md)
- [Decision-prefix replay](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-replay.md)
- [Decision contrastive replay](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-contrastive.md)
- [Positional decision coalitions and Shapley replay](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-shapley.md)
- [Strong baseline reproduction plan](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/car-reproduction-plan.md)
- [Installed-package study and replay checks](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/study-foundation-2026-10-11/README.md)
- [Decision contrastive controls and seeded fixture](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/contrastive-foundation-2026-10-11/README.md)
- [Shapley controls, protective decision, and unavailable coalitions](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/shapley-foundation-2026-10-11/README.md)
- [Alpha validation report](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/build/README.md)

Collaborators with repository access can contribute to the framework and research. Read [CONTRIBUTING.md](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/CONTRIBUTING.md), then open an issue or pull request. The project uses the [MIT license](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/LICENSE). Useful next contributions include additional policy adapters, verified domains, stronger baseline comparisons, and held-out task templates.

## Install locally

With access to this private repository, use Python 3.11 or newer:

```sh
git clone https://github.com/Devrajsinh-Jhala/consequa-x.git
cd consequa-x
python -m venv .venv
```

Activate the environment in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```sh
source .venv/bin/activate
```

Then install the source and development tools:

```sh
python -m pip install -e ".[dev]"
consequa-x --version
```

The installed framework has no required runtime dependencies and needs no provider credentials. Use `python -m consequa_x` wherever these examples use `consequa-x`.

## Run the demo

```sh
consequa-x demo --output output/my-demo --seed 0
```

This writes 12 scenarios, including a timeout after commit, false success, partial refunds, delayed visibility, safe and unsafe retries, external-actor effects, and missing provenance. Open `output/my-demo/README.md` for the outcome table. Each run requires a new or empty output directory; choose another path when repeating a command.

| Export | Purpose |
| --- | --- |
| `traces/` | Captured events, responses, assessments, observations, and verification records |
| `explanations/` | Diagnoses and evidence graphs produced from those traces |
| `evaluator_truth/` | Simulator truth, injection labels, and scenario configuration for evaluation only |
| `trace-schema.json` | Portable JSON Schema for trace structure |
| `manifest.json` | SHA-256 hashes of episode artifacts for integrity checks |

Keep evaluator truth outside explainer and policy inputs. Manifest hashes detect file changes; they do not authenticate evidence sources. The simulator uses local synthetic funds, including synthetic compensation for temporal-contract tests.

Explain a saved trace without replaying a policy or executing a provider call:

```sh
consequa-x explain output/my-demo/traces/episode_01.json --output output/my-explanation.json
```

## Evaluate a policy

Run the policy interface without installing a model:

```sh
consequa-x model-eval --provider scripted --samples 2 --max-calls 100 --output output/my-policy-smoke
```

The policy chooses whether to refund, retry, or stop, then reports its assessment before independent verification. Each trial starts a fresh simulated world. Reports include completed, failed, and unstarted samples; provider/protocol errors stay separate from verified consequence violations and unknown readback. Use a fresh output directory for each run.

Once you have installed Ollama and a local model, replace `YOUR_INSTALLED_MODEL` with its name:

```sh
consequa-x model-eval --provider ollama --model YOUR_INSTALLED_MODEL --cases clean,timeout_after_commit --samples 1 --max-calls 6 --output output/my-local-model
```

The adapter checks installed models and declared local routing before generation, uses structured decisions, and records model identity and request hashes. It performs no model installation or download. See [the evaluation guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/policy-evaluation.md) for setup, limits, API examples, and trust assumptions. The [study protocol](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/study-plan.md) defines the stronger comparisons and held-out tasks still needed for a research paper.

The original `refund-policy-v1` prompt remains the default. Select the opt-in `--prompt-version refund-policy-v2` to clarify assessment, timing, and attempt-budget semantics and add stop-after-success guidance. This is a pilot-informed policy refinement; comparison results are exploratory. Both evaluation and replay record the chosen version and its exact prompt hash. Reports also expose assessment abstention, claim coverage, and contradictions with explicit denominators. These metrics score the structured status, while rationale text requires separate review. The [follow-up pilot](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/prompt-sensitivity-2026-10-10/README.md) found unknown status fields alongside affirmative rationale claims, so it does not establish an accuracy gain. Hindsight alignment with verified state does not establish what a policy could know from an ambiguous response.

## Use the Python API

For study preparation, `model-eval --study docs/studies/refund-family-candidates-v1.json --split tuning`
selects a validated candidate wording family and records the planned order and
exact manifest hash. The original pilot family is excluded from the held-out
reserve. This assignment is not a claim of held-out model performance.
`model-experiment --targets action,consequence,action_linked_consequence` adds
qualifying action-linked outcomes without additional replay calls. The
[decision replay API](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-replay.md) holds factual prefixes for future
baseline implementations. [Decision contrastive replay](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-contrastive.md)
now estimates suffix effects against one recorded factual outcome.
[Positional Shapley replay](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-shapley.md) adds fresh coalition walks,
paired contribution estimates, and independent endpoint diagnostics. Strict
unreachable-position refusal can make variable-length games unavailable;
calibration and the final matched comparison remain research milestones.

```python
from consequa_x import Trace, explain, verify
from consequa_x.benchmark.runner import run_scenario
from consequa_x.schema import get_trace_schema, validate_trace

episode = run_scenario(seed=0)  # Default: timeout after the refund commits.
trace = episode.trace

receipt = verify(trace.action, trace.observations[-1])
print(receipt.status.value)  # satisfied
print(receipt.origin.value)  # confirmed
print(explain(trace).diagnosis)  # BELIEF / RESPONSE DIVERGENCE

encoded = trace.to_json()
restored = Trace.from_json(encoded)
assert validate_trace(encoded) == restored
schema = get_trace_schema()  # Bundled trace schema v0.1.
```

`verify(action, observation)` is read-only. The built-in `refund_processed` contract checks the payment, amount, currency, count, deadline, and optional stability interval. Stale, incomplete, unavailable, or malformed readback produces `unknown` rather than a final success/failure claim. Origin is reported independently as `confirmed`, `other_actor`, or `unknown`.

`explain(trace, estimates=())` uses the latest captured verification. It records reported-assessment alignment and graph edges with explicit meanings. A reported assessment is not a measurement of hidden reasoning; an origin link is not proof of counterfactual necessity. Supplied replay estimates add estimated-influence edges. Recency remains a labeled heuristic.

Trace decoding rejects unsupported versions, unknown fields, invalid references, and dependency cycles. The portable JSON Schema covers record structure; `validate_trace` also checks relationships between records. These checks trust source and watermark declarations and do not authenticate a provider. See [the design](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/design.md) before writing an adapter.

## Run paired replay experiments

Replay the policy interface under declared context changes:

```sh
consequa-x model-experiment --provider scripted --case unsafe_retry --samples 20 --max-calls 400 --output output/my-policy-replay
```

Each factual seed runs once and is reused across candidate comparisons and all selected targets. The call limit applies to the whole experiment. Failed or unstarted branches and unknown consequences remain explicit; an estimate requires every planned target pair to be usable. The export includes branch evidence, signed effects, pair coverage, and an optional factual explanation with estimated-influence edges. See [the replay guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/policy-replay.md) for the Python API and prepared Ollama entry point.

The committed [scripted replay example](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/replay-smoke/README.md) uses two seeds per condition to check the integration. It is not a model result or an adequate sample size for a research claim.

Test recorded decision boundaries using one factual capture and fresh suffixes:

```sh
consequa-x decision-experiment --provider scripted --case unsafe_retry --samples 16 --seed 100 --factual-seed 0 --max-calls 400 --output output/my-decision-replay
```

This independently written CAR-style binary adaptation estimates changed-minus-factual
bad-outcome probability and reports the latest nominal rescue position. Its shared
call budget includes the factual recording. Unknowns, failures, and unstarted
samples refuse affected estimates; incomplete decision coverage refuses the final
locus. The default exact binomial intervals retain uncertainty at homogeneous
samples and condition on one observed factual episode. Legacy bootstrap and
Wilson options remain explicit comparators. See [the decision guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-contrastive.md)
for signs, reference version, implementation deviations, and statistical limits.

Allocate signed contributions with fresh held-decision coalition walks:

```sh
consequa-x decision-shapley --provider scripted --case clean --pairs 16 --samples 1 --endpoint-samples 16 --seed 100 --max-calls 2000 --output output/my-decision-shapley
```

One permutation and its reverse form one observation. Separate endpoint draws
check the total scale without normalizing the shares. Unknown or unavailable
path evidence refuses the affected target vector. See the
[Shapley guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/decision-shapley.md) for intervention validity, signs,
budgets, and conditional interval limits. Defaults use Hoeffding bounds for
pair means and two exact binomial marginals for endpoint differences. They can
be wide at small budgets; normal intervals remain an explicit comparator.

The default strict game refuses unreachable held positions. The separate
`--coalition-game on_reach` option records normally unreached held positions as
inactive and uses the actual completed trajectory. Reached incompatible
decisions still invalidate a draw. See the
[refund interaction guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/refund-interactions.md) for exact physical
enumeration and the distinction between the two games.

Probe both decision estimators against declared analytic refund mechanisms:

```sh
consequa-x calibrate-attribution --replicates 32 --output output/my-calibration
```

This offline experiment reports error, interval coverage, false nonzero flags,
locus recovery and refusals with explicit denominators. It saves its protocol
before execution, every planned draw in compressed JSONL, and full evidence
for a preselected repetition. See [the calibration design](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/attribution-calibration.md)
for analytic references, budget controls and interpretation limits.

The [retained 1,280-trial probe](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/calibration-probe-2026-10-11/FINDINGS.md)
and [independent finite interval analysis](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/calibration-theory-2026-10-11/README.md)
show weak coverage for several original nominal 95% intervals. The
[384-trial same-draw comparison](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/interval-comparison-2026-10-13/README.md)
and [follow-up protocol](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/interval-followup-plan.md) compare revised bounds
on fresh data, including width and detection strength. The original probe and
its methods remain available; synthetic checks do not establish live-model
coverage or superiority.

```sh
consequa-x compare-intervals --replicates 32 --seed 2000000 --output output/my-interval-comparison
```

A [working research paper](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/paper/manuscript.md) links the completed evidence and
the held-out studies still required. [Release readiness](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/release-readiness.md)
records completed publication checks and the remaining stable-release checks.

The [24-episode local validation](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/local-validation-2026-10-14/FINDINGS.md)
compares both existing prompt profiles on six validation cases using the same
local Qwen3 4B model. Structured abstention and explanation claims are scored
separately; the study does not establish improved accuracy or held-out superiority.

Run the original deterministic and stochastic fixture comparison:

```sh
consequa-x experiment --output output/my-experiments --samples 40 --seed 0
```

The command requires at least 20 samples per condition. It writes `results.json` and a report comparing action selection and verified consequence under deterministic and stochastic programmatic policies. Both branches of each pair start in fresh simulated worlds with aligned random draws.

The unsafe retry fixture illustrates why the targets differ: neutralizing the retry instruction leaves initial action selection unchanged, but prevents a second refund and restores exactly-once satisfaction.

For a custom fixture experiment:

```python
from consequa_x import Intervention, explain, leave_one_out
from consequa_x.benchmark.runner import (
    RefundContext, RefundReplayRunner, ScenarioConfig, run_scenario,
)

config = ScenarioConfig(
    context=RefundContext(retry_instruction=True),
    use_idempotency=False,
)
estimates = leave_one_out(
    RefundReplayRunner(config),
    (Intervention("retry_instruction"), Intervention("distractor")),
    target="consequence",
    samples=40,
    seed=0,
)
print(estimates[0].effect)  # -1.0: removing retry improves this target.
explanation = explain(run_scenario(config, seed=0).trace, estimates)
```

An estimate is the original rate minus the intervened rate, with an approximate conservative 95% interval. It is a signed experimental effect, not a normalized responsibility share. Unknown consequence pairs refuse an estimate. Results describe the declared replay distribution; they do not demonstrate generalization across tasks or LLMs. A custom replay runner must reset its world, preserve the outcome contract, and supply independently verified outcomes. The current fixture runner supports neutralization or typed replacement of declared context fields.

## Development and local distribution

```sh
python -m pytest
python -m ruff check src tests
python -m build
```

The build writes a wheel and source distribution to `dist/`. To install the current version `1.0.0` candidate wheel in another environment:

```sh
python -m pip install dist/consequa_x-1.0.0-py3-none-any.whl
```

`requirements-dev.lock` captures the Python 3.12 development environment.
The [stable core API](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/stable-api.md)
and trace schema have explicit compatibility rules; benchmark modules and study
commands remain declared research interfaces. Release receipts identify the
exact interpreters, platforms and installations checked.

The [Python alpha is published on PyPI](https://pypi.org/project/consequa-x/0.1.0a2/),
with both public artifact hashes and a fresh registry installation verified.
Install that exact checkpoint with `python -m pip install consequa-x==0.1.0a2`.
The current [completion work](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/completion-plan.md)
tracks final stable-release validation and a scoped IEEE protocol/software paper.
A later npm adapter can share the trace schema and conformance fixtures. The
package is not published on npm.

The [reviewed alpha 2 artifacts and checks](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/release-alpha-2026-10-14/README.md)
retain the wheel, source distribution and final build revision. Installation
checks cover Windows Python 3.12.14. GitHub Actions stays disabled at the
maintainer's request; this release uses local checks. The
[publication receipt](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/output/release-alpha-2026-10-14/publication.json)
records the completed PyPI upload and registry installation.
