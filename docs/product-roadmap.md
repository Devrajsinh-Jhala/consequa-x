# Product roadmap

Agreed 18 October 2026, after publishing 1.1.1. This page tracks package
features for users of Consequa-X; the research agenda stays in the
[research roadmap](research-roadmap.md). Update the status column as work lands.

## Decision

1. **1.2 before the launch video: additive only.** Nothing in the 1.x API or
   trace schema `0.1` changes, so the paper's description of the version-1 core
   and schema `0.1`, the retained research evidence and the website demo all stay
   valid. 1.2 makes first use easy: capture as an agent acts, check any
   record-shaped outcome without custom code, and show it on a real agent loop.
2. **2.0 after launch feedback and after the paper is settled.** Breaking changes
   are bets about how people use the package; make them once, with a migration
   guide and a `migrate` command for schema `0.1` traces. The paper must name
   the version it describes before 2.0 lands.

Doing everything as a breaking 2.0 before launch was considered and rejected:
it is months of work, it would contradict the paper mid-review, and it would
fix design choices before any user feedback.

## How work proceeds

- Features are built one at a time on the `release-1.2` branch. Each feature is
  one reviewed commit with its own tests and docs, pushed to GitHub when done.
- `main` stays at the released 1.1.1 state until 1.2 is complete; then
  `release-1.2` is merged, the version is bumped and release checks run.
- Nothing is published to PyPI without the maintainer's explicit approval.
- Paper and study work (`paper/`, `output/`) continues independently on `main`.
  1.2 does not change any runtime behavior those materials describe.

Status: `planned`, `in progress`, `done` (on `release-1.2`), `released`.

## 1.2: launch features (additive)

| ID | Feature | What it gives a user | Status |
| --- | --- | --- | --- |
| B1 | `TraceRecorder` capture helper | Record an action as it happens (contract, context, dispatch, response, the agent's report, readback, verification) and get a validated `Trace`, without hand-linking events or positional constructors. | done |
| B3 | `RecordVerifier` and `RecordTargetMatcher` | A built-in `record_present` check for any record-shaped outcome (rows, orders, tickets, files): field values, exact or minimum count, commit deadline, persistence window, origin from configurable fields. Same evidence discipline as the refund verifier: unavailable, incomplete, out-of-scope, stale or malformed readback stays `unknown`. | done |
| B2 | `capture_tool` wrapper | A decorator/context manager that records dispatch, response status and timing around any tool function, including timeouts and errors. | done |
| X1 | Real agent-loop example | `examples/agent_loop_sqlite.py`: a stdlib-only tool-calling loop writing to a real SQLite file, read back through a separate read-only connection. Modes `timeout_after_commit`, `other_actor` and `stale_readback`; each writes a trace and an offline report. This is the launch-video demo. | planned |
| X2 | Framework integration guide | Where each capture call goes in OpenAI Agents SDK, LangChain, Claude Agent SDK and MCP tool loops; prose and pseudo-code, no dependencies. | planned |
| C4 | MCP tool-call wrapper | A thin, optional wrapper around an MCP client's tool calls that uses the recorder; no MCP dependency in the core. | planned |

Planned 1.2 API sketch (names may still change during review):

```python
from consequa_x import OutcomeContract, RecordVerifier, TraceRecorder, explain

contract = OutcomeContract("refund-contract", "record_present",
                           {"order_id": "o-17", "amount_minor": 5000, "currency": "INR"},
                           deadline_ms=200, stability_ms=50)
verifier = RecordVerifier(scope_fields=("order_id",))

rec = TraceRecorder("run-17", actor="support-agent")
rec.register("refund-1", "issue_refund", {"order_id": "o-17"}, contract=contract)
attempt = rec.dispatch()
rec.response(attempt, "timeout")
rec.assessment("failure")
rec.verify(readback, verifier=verifier)      # readback: an Observation from a read-only source
explanation = explain(rec.trace(), target_matcher=verifier.target_matcher())
```

Release engineering for 1.2: README section for the recorder, changelog,
website "How it works" and demo updated to the recorder and SQLite example,
one Linux and macOS run (GitHub Actions is free for this public repository but
currently disabled; enabling it is the maintainer's decision), version 1.2.0,
installed-artifact checks, then publication on approval.

## 2.0: candidates after launch (breaking)

| ID | Change | Why |
| --- | --- | --- |
| A1 | Several actions, contracts and verifications per trace | Real agent runs take several consequential actions; today a trace holds one. |
| A2 | Keyword-only record constructors | Seven positional arguments are easy to misorder. |
| A3 | Refund logic as a domain plugin; diagnoses from verifier-supplied facts | `explain()` has refund-only branches. |
| A4 | Structured diagnoses (code, evidence references) | Replace the joined diagnosis string. |
| A5 | Schema `1.0` with absolute timestamps and a time base, plus `consequa-x migrate` | Real systems log wall-clock time. |
| A6 | Several agent assessments per action | Agents can report before and after a retry. |
| A7 | Research interfaces moved to a separate package or extra | Keep the user-facing core small. |
| A8 | Typed exceptions | Precise error handling for callers. |
| A9 | Deeply immutable captured payloads | Evidence cannot be mutated after capture. |

Other candidates, additive or 2.0-dependent:

| ID | Feature |
| --- | --- |
| B4 | Verifier composition (all-of / any-of) and several readbacks per verification |
| B5 | Readback scheduler: re-check until the watermark covers the contract horizon |
| B6 | Retry guard: check readback before retrying a timed-out action. Moves from explanation to control; wording must stay careful. |
| B7 | Async recorder, verifiers and wrapper |
| B8 | `consequa-x summarize`: divergence and unknown counts across many traces |
| C1–C3 | Optional OpenAI Agents SDK, LangChain and Claude Agent SDK integrations as extras |
| C5 | OpenTelemetry export/import using the GenAI conventions |
| D1 | Reports for several actions (needs A1) |
| D2 | Compare two traces |
| D3 | Markdown and JSON summary output |
| D4 | `consequa-x verify` from a JSON/YAML contract and a readback file |
| D5 | `consequa-x validate` and `migrate` |
| D6 | Configurable report redaction rules |
| D7 | JSONL trace store |

Not planned: a hosted service or live monitoring product, a TypeScript port,
or new research interfaces in the core package.
