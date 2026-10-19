# Consequa-X

**Evidence-aware explanation of consequential agent actions.**

When an agent calls a tool that changes something (a refund, a delivery, a
database write), the tool's response is only part of the story. A timeout can
hide a refund that went through. A "success" can hide one that never landed.
Another actor can produce the very outcome the agent was asked for.

Consequa-X keeps four things apart: the **tool response**, what the **agent
reported**, the outcome established by an **independent read-only readback**, and
**who produced the effect**. Missing, stale or incomplete evidence stays
`unknown` instead of being guessed.

- Website, live inspector and docs: <https://consequa-x.onrender.com>
- Package: <https://pypi.org/project/consequa-x/>
- Source and issues: <https://github.com/Devrajsinh-Jhala/consequa-x>

Python 3.11+ · MIT licensed · no required runtime dependencies · no model, API
key or network access needed for the core or the offline examples.

## Install

```sh
python -m pip install consequa-x
consequa-x --version
```

Use `python -m consequa_x` wherever a command below uses `consequa-x`. Optional
extras add framework integrations and OpenTelemetry: `consequa-x[openai-agents]`,
`consequa-x[langchain]`, `consequa-x[claude-agent-sdk]` and `consequa-x[otel]`.

## See it in a minute

```sh
consequa-x demo --output my-demo
consequa-x report my-demo/traces/episode_01.json --output my-report.html
```

`demo` writes twelve synthetic refund scenarios with simulated money: timeouts
before and after commit, false success, partial and duplicate effects, delayed
readback, retries, another actor and missing provenance. Episode 1 is a timeout
after commit: the tool timed out and the agent reported failure, but readback
shows the refund committed and linked to the agent's action. Open
`my-report.html` in any browser. It is one self-contained file with no scripts
or network requests.

Each run needs a new output directory, and a report never overwrites an existing
file. The demo's `evaluator_truth/` folder is simulator ground truth for
evaluation only; never pass it to an explainer.

## Use it in Python

Register each consequential action with its intended outcome before running it,
let the recorder capture what happens, read the outcome back from a trusted
read-only source, then verify and explain:

```python
from consequa_x import (
    Observation, OutcomeContract, RecordVerifier, TraceRecorder, explain, render_report,
)

verifier = RecordVerifier(scope_fields=("order_id",))
rec = TraceRecorder("run-17", actor="support-agent", time_base="relative_ms")
refund = rec.register(
    "refund-o-17", "issue_refund", {"order_id": "o-17"}, at_ms=0,
    contract=OutcomeContract(contract_id="refund-o-17", predicate="record_present",
                             expected={"order_id": "o-17", "amount_minor": 5000},
                             deadline_ms=200, stability_ms=50))

try:
    with refund.attempt(at_ms=5) as attempt:      # your tool call goes here
        attempt.at_ms = 30
        raise TimeoutError                        # ...and it timed out
except TimeoutError:
    refund.assessment("failure", at_ms=31)        # what the agent reported

# Captured independently, after the horizon, from a read-only replica of the orders table.
readback = Observation(
    observation_id="read-1", source="orders-replica", observed_at_ms=300, as_of_ms=300,
    scope={"order_id": "o-17"},
    records=({"effect_id": "rf-1", "order_id": "o-17", "amount_minor": 5000,
              "committed_at_ms": 20, "action_id": "refund-o-17",
              "attempt_id": "refund-o-17:attempt-1", "actor": "support-agent"},))
receipt = refund.verify(readback, verifier=verifier)

result = explain(rec.trace()).for_action("refund-o-17")
assert receipt.status.value == "satisfied"         # the refund really happened
assert receipt.origin.value == "confirmed"         # and this action produced it
assert result.assessment_alignment == "contradicted"   # the agent said failure
print(result.codes)  # ('ASSESSMENT_DIVERGENCE', 'ACKNOWLEDGEMENT_EFFECT_DIVERGENCE')
html = render_report(rec.trace())                  # offline, minimal disclosure
```

A run can register several actions; each `register` returns that action's
`ActionCapture`, and its attempts, assessments and verifications stay separate.
`capture_tool` decorates a tool (synchronous or `async def`) so every call is
recorded. `poll_readback` re-reads a lagging source until the outcome is known,
and `retry_advice` turns the receipt into a retry decision.

The built-in verifiers are `RecordVerifier` (rows, orders, tickets, files:
`record_present`) and `RefundVerifier` (`refund_processed`). Both check values,
count, commit deadline and persistence; unavailable, incomplete, wrongly scoped or
stale readback produces `unknown`. Effect origin is a separate conclusion:
`confirmed`, `other_actor` or `unknown`. Verifiers also record which effects match
the target and domain findings (excess, duplicate, mismatched, reversed or
removed effects); `explain` reads those receipts without any domain logic of its
own.

The [agent-loop example](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/examples/agent_loop_sqlite.py)
runs this end to end against a real SQLite database, offline, in three modes: a
timeout after the refund committed, a refund made by someone else, and a readback
too stale to decide. The
[framework guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/framework-integration.md)
shows where the calls go in OpenAI Agents SDK, LangChain, Claude Agent SDK and MCP
tool loops.

Traces round-trip through a portable, versioned JSON schema (`1.0`):
`Trace.from_json(trace.to_json())` rejects unknown fields, broken identity links
and dependency cycles, and every captured payload is read-only.

## Bring your own domain

Write a read-only `Verifier` for your predicate. It returns a
`VerificationResult` with the state, origin and the effects it saw; to let the
agent's report be judged, it also records `target_effect_ids` (this action's
effects that match the full target):

```python
receipt = verify(action, observation, verifier=MyVerifier())
```

Your application owns source trust, scope, completeness, timing and provenance;
Consequa-X checks that receipts bind to the supplied action, contract and
observation, and keeps the evidence structured. The
[artifact-delivery example](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/examples/artifact_delivery.py)
implements a verifier with public APIs only, and the
[integration guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/application-integration.md)
describes the boundary in detail. The
[stable API](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/stable-api.md)
page lists what version 2 guarantees.

An outcome with several required effects (a refund *and* a closed ticket, or a
refund *or* store credit) is one contract: `all_of(...)` or `any_of(...)` over
part contracts, checked by `CompositeVerifier` with one readback per source.
Unknown parts keep the whole outcome unknown unless another part already
settles it.

## Agent frameworks and OpenTelemetry

Optional integrations record an agent framework's tool calls through the same
recorder. Your `contract_for(call)` decides which calls are consequential:

```python
from consequa_x.integrations import ToolCallCapture
calls = ToolCallCapture(rec, contract_for=contract_for)

# OpenAI Agents SDK: use in place of @function_tool
from consequa_x.integrations.openai_agents import consequential_tool
# LangChain: config={"callbacks": [ConsequaCallbackHandler(calls)]}
from consequa_x.integrations.langchain import ConsequaCallbackHandler
# Claude Agent SDK: ClaudeAgentOptions(hooks=consequa_hooks(calls))
from consequa_x.integrations.claude_agent_sdk import consequa_hooks
```

`consequa_x.otel` writes traces as OTLP/JSON with `execute_tool` spans named as
the OpenTelemetry GenAI conventions describe, emits them through
`opentelemetry-api`, and turns tool spans from other instrumentation into
recorded actions. See the
[framework guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/framework-integration.md)
and the
[OpenTelemetry guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/opentelemetry.md).

## Upgrading from 1.x

Version 2.0 changes the trace schema to `1.0` (several actions per trace, a
declared time base, keyword-only and read-only records) and moves domain
interpretation into verifiers. Convert saved 1.x traces with
`consequa-x migrate OLD.json --output NEW.json` or `migrate_trace()`. The
[migration guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/migrating-to-2.0.md)
lists every change and its replacement.

## Command line

| Command | What it does |
| --- | --- |
| `consequa-x demo --output DIR` | Write the twelve synthetic refund scenarios: traces, explanations, schema and manifest |
| `consequa-x explain TRACE [--output FILE]` | Explain an existing trace without replay; prints JSON or writes a new file |
| `consequa-x report TRACE --output FILE` | Render a self-contained HTML report; `--include-details` embeds the full capture, `--redact KEY` blanks named keys in it |
| `consequa-x summarize PATH... [--format markdown]` | Count outcomes, alignment and divergences across trace files, folders and `.jsonl` stores |
| `consequa-x compare A B` | Compare two traces action by action |
| `consequa-x verify TRACE --readback OBS --output NEW` | Verify captured readback with built-in verifiers; repeat `--readback` for an `all_of`/`any_of` contract |
| `consequa-x otel-export TRACE --output FILE` / `consequa-x otel-import FILE --output-dir DIR` | Write a trace as OpenTelemetry OTLP/JSON spans; restore traces exported with `--include-payloads` |
| `consequa-x validate TRACE...` / `consequa-x migrate OLD --output NEW` | Check traces; convert schema `0.1` traces |
| `consequa-x experiment …` and research commands | Paired replay, decision attribution and calibration studies (see Research) |

## What it does not do

- It does not watch or control a live agent; your application captures the records.
  `retry_advice` is advice derived from captured evidence, not a guarantee.
- It does not authenticate a readback source or prove that provider metadata is true.
- An evidence-graph link records provenance, not causal necessity.
- Default reports omit captured strings and identifiers, but keep times, counts
  and relationships. That is field omission, not anonymization.
- No accuracy advantage over other methods is claimed.

## Research

The repository also contains declared research interfaces, imported from
`consequa_x.research`: isolated replay, contrastive and Shapley-style decision attribution,
calibration studies, an optional local Ollama adapter, and the retained evidence
for each study. Results so far are synthetic or exploratory local-model studies
and are reported with their denominators and limits. Start with the
[research roadmap](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/research-roadmap.md)
and the [paper notes](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/paper/README.md).

## Platforms

The package is pure Python. Released wheels have been install-tested on Windows
with Python 3.11 and 3.12 and on one Alpine Linux virtual machine with Python
3.14. macOS has not been tested yet. See the
[release notes](https://consequa-x.onrender.com/changelog.html) for exact
environments.

## Contributing and support

- Questions and bugs: [GitHub issues](https://github.com/Devrajsinh-Jhala/consequa-x/issues/new/choose).
  Use synthetic data only; never post real traces, customer data or credentials.
- Security: report vulnerabilities privately as described in
  [SECURITY.md](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/SECURITY.md).
- Development: see [CONTRIBUTING.md](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/CONTRIBUTING.md).

```sh
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests scripts
```

## License

MIT, copyright Devrajsinh Jhala. The website's self-hosted fonts keep their SIL
Open Font License.
