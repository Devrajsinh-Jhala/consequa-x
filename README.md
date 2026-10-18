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

Use `python -m consequa_x` wherever a command below uses `consequa-x`.

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

Register the intended outcome before the action, capture what happened, read the
outcome back from a trusted read-only source, then verify and explain:

```python
from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Observation, OutcomeContract,
    Trace, explain, render_report, verify,
)

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

assert receipt.status.value == "satisfied"      # the refund really happened
assert receipt.origin.value == "confirmed"      # and this action produced it
assert explain(trace).assessment_alignment == "contradicted"  # the agent said failure
html = render_report(trace)                      # offline, minimal disclosure
```

The built-in `refund_processed` verifier checks payment, integer amount,
currency, exact count, commit deadline and a persistence window. Unavailable,
incomplete, wrongly scoped or stale readback produces `unknown`. Effect origin is
a separate conclusion: `confirmed`, `other_actor` or `unknown`.

Traces round-trip through a portable, versioned JSON schema (`0.1`):
`Trace.from_json(trace.to_json())` rejects unknown fields, broken identity links
and dependency cycles. `consequa_x.schema.get_trace_schema()` returns the bundled
JSON Schema.

## Capture a real agent's tool call

`TraceRecorder` records an action while your agent runs, and `RecordVerifier`
checks any outcome that leaves records behind (rows, orders, tickets, files):

```python
from consequa_x import OutcomeContract, RecordVerifier, TraceRecorder, explain

contract = OutcomeContract("refund-o-17", "record_present",
                           {"order_id": "o-17", "amount_minor": 5000, "currency": "INR"},
                           deadline_ms=200, stability_ms=50)
verifier = RecordVerifier(scope_fields=("order_id",))

rec = TraceRecorder("run-17", actor="support-agent")
rec.register("refund-o-17", "issue_refund", {"order_id": "o-17"}, contract=contract)
try:
    with rec.attempt(data={"tool": "issue_refund"}) as attempt:
        issue_refund("o-17", attempt_id=attempt.attempt_id)   # your tool
    rec.assessment("success")                                  # what the agent reported
except TimeoutError:
    rec.assessment("failure")
rec.verify(read_refunds_for("o-17"), verifier=verifier)       # your read-only readback
print(explain(rec.trace(), target_matcher=verifier.target_matcher()).diagnoses)
```

`capture_tool` decorates a synchronous tool so every call is recorded the same
way. The
[agent-loop example](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/examples/agent_loop_sqlite.py)
runs this end to end against a real SQLite database, offline, in three modes:
a timeout after the refund committed, a refund made by someone else, and a
readback too stale to decide.

## Bring your own domain

Supply a read-only `Verifier` for your predicate, and a `TargetMatcher` when the
agent's reported success or failure should be judged against that contract:

```python
receipt = verify(action, observation, verifier=MyVerifier())
explanation = explain(trace, target_matcher=MyTargetMatcher())
```

Your application owns source trust, scope, completeness, timing and provenance;
Consequa-X checks that receipts bind to the supplied contract and observation,
and keeps the evidence structured. The
[artifact-delivery example](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/examples/artifact_delivery.py)
implements both adapters with public APIs only, and the
[integration guide](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/application-integration.md)
describes the boundary in detail. The
[stable API](https://github.com/Devrajsinh-Jhala/consequa-x/blob/main/docs/stable-api.md)
page lists what version 1 guarantees.

## Command line

| Command | What it does |
| --- | --- |
| `consequa-x demo --output DIR` | Write the twelve synthetic refund scenarios: traces, explanations, schema and manifest |
| `consequa-x explain TRACE [--output FILE]` | Explain an existing trace without replay; prints JSON or writes a new file |
| `consequa-x report TRACE --output FILE` | Render a self-contained HTML report; add `--include-details` to embed the full capture |
| `consequa-x experiment …` and research commands | Paired replay, decision attribution and calibration studies (see Research) |

## What it does not do

- It does not watch or control a live agent; your application captures the records.
- It does not authenticate a readback source or prove that provider metadata is true.
- An evidence-graph link records provenance, not causal necessity.
- Default reports omit captured strings and identifiers, but keep times, counts
  and relationships. That is field omission, not anonymization.
- No accuracy advantage over other methods is claimed.

## Research

The repository also contains declared research interfaces, separate from the
stable core: isolated replay, contrastive and Shapley-style decision attribution,
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
