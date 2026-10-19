# Product roadmap

Agreed 18 October 2026, after publishing 1.1.1. This page tracks package
features for users of Consequa-X; the research agenda stays in the
[research roadmap](research-roadmap.md). Update the status column as work lands.

## Decision

1. **1.2 before the launch video: additive only.** Released 19 October 2026.
2. **2.0 now, and the package leads the paper.** Revised 19 October 2026 by the
   maintainer: the breaking 2.0 is built next, and the paper will be reshaped
   around it instead of 2.0 waiting for the paper. Research code (benchmark,
   replay, attribution, policies) is ported to the 2.0 data model, not split
   into a separate package. The design is in [design-2.0.md](design-2.0.md).

The earlier plan (2.0 only after launch feedback and the paper) is superseded.
Breaking changes are still made once, with a `migrate` command for every
schema `0.1` trace.

## How work proceeds

- 2.0 is built on the `release-2.0` branch in the order given in the design.
  Each step is reviewed commits with the full suite passing, pushed when done.
- `main` stays at the released 1.2.0 state until 2.0 is complete. Merging
  `release-2.0` into `main` waits until no frozen study is running there,
  because study runners hash `src/consequa_x/**/*.py`.
- Nothing is published to PyPI without the maintainer's explicit approval.
- Retained study receipts under `output/` keep their recorded 1.x revisions.

Status: `planned`, `in progress`, `done` (on its release branch), `released`.

## 1.2: launch features (additive)

| ID | Feature | What it gives a user | Status |
| --- | --- | --- | --- |
| B1 | `TraceRecorder` capture helper | Record an action as it happens (contract, context, dispatch, response, the agent's report, readback, verification) and get a validated `Trace`, without hand-linking events or positional constructors. | released |
| B3 | `RecordVerifier` and `RecordTargetMatcher` | A built-in `record_present` check for any record-shaped outcome (rows, orders, tickets, files): field values, exact or minimum count, commit deadline, persistence window, origin from configurable fields. Same evidence discipline as the refund verifier: unavailable, incomplete, out-of-scope, stale or malformed readback stays `unknown`. | released |
| B2 | `capture_tool` wrapper | A decorator/context manager that records dispatch, response status and timing around any tool function, including timeouts and errors. | released |
| X1 | Real agent-loop example | `examples/agent_loop_sqlite.py`: a stdlib-only tool-calling loop writing to a real SQLite file, read back through a separate read-only connection. Modes `timeout_after_commit`, `other_actor` and `stale_readback`; each writes a trace and an offline report. This is the launch-video demo. | released |
| X2 | Framework integration guide | Where each capture call goes in OpenAI Agents SDK, LangChain, Claude Agent SDK and MCP tool loops; prose and pseudo-code, no dependencies. | released |
| C4 | MCP tool-call wrapper | A thin, optional wrapper around an MCP client's tool calls that uses the recorder; no MCP dependency in the core. | released |

The 1.2 API as built (the [SQLite example](../examples/agent_loop_sqlite.py)
is a complete, runnable version):

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

Released as 1.2.0 on 19 October 2026; see the
[release record](../output/release-1.2.0-2026-10-19/README.md). Linux was
checked in a local QEMU guest instead of GitHub Actions; macOS is still untested.

Release engineering for 1.2: README section for the recorder, changelog,
website "How it works" and demo updated to the recorder and SQLite example,
one Linux and macOS run (GitHub Actions is free for this public repository but
currently disabled; enabling it is the maintainer's decision), version 1.2.0,
installed-artifact checks, then publication on approval.

## 2.0: breaking changes

| ID | Change | Why | Status |
| --- | --- | --- | --- |
| A1 | Several actions, contracts and verifications per trace | Real agent runs take several consequential actions; today a trace holds one. | done |
| A2 | Keyword-only record constructors | Seven positional arguments are easy to misorder. | done |
| A3 | Refund logic as a domain plugin; diagnoses from verifier-supplied facts | `explain()` has refund-only branches. | done |
| A4 | Structured diagnoses (code, evidence references) | Replace the joined diagnosis string. | done |
| A5 | Schema `1.0` with absolute timestamps and a time base, plus `consequa-x migrate` | Real systems log wall-clock time. | done |
| A6 | Several agent assessments per action | Agents can report before and after a retry. | done |
| A7 | Research interfaces moved to a separate package or extra | Keep the user-facing core small. | done (as `consequa_x.research`; research is ported) |
| A8 | Typed exceptions | Precise error handling for callers. | done |
| A9 | Deeply immutable captured payloads | Evidence cannot be mutated after capture. | done |

Also planned for 2.0, in the order given in the design (C1–C3 and C5 may move to 2.1):

| ID | Feature |
| --- | --- |
| B4 | Verifier composition (all-of / any-of) and several readbacks per verification. Deferred past 2.0.0: an outcome with several required effects can be several actions with their own contracts; an all-of/any-of contract format needs its own design. |
| B5 | Readback scheduler: re-check until the watermark covers the contract horizon (done on `release-2.0`) |
| B6 | Retry guard: check readback before retrying a timed-out action. Moves from explanation to control; wording must stay careful. (done on `release-2.0`) |
| B7 | Async recorder, verifiers and wrapper (done on `release-2.0`) |
| B8 | `consequa-x summarize`: divergence and unknown counts across many traces (done on `release-2.0`) |
| C1–C3 | Optional OpenAI Agents SDK, LangChain and Claude Agent SDK integrations as extras. Deferred to 2.1: they need the SDKs installed and tested; the framework guide shows where the calls go. |
| C5 | OpenTelemetry export/import using the GenAI conventions. Deferred to 2.1. |
| D1 | Reports for several actions (needs A1) (done on `release-2.0`) |
| D2 | Compare two traces (done on `release-2.0`) |
| D3 | Markdown and JSON summary output (done on `release-2.0`) |
| D4 | `consequa-x verify` from a JSON/YAML contract and a readback file (done on `release-2.0`) |
| D5 | `consequa-x validate` and `migrate` (done on `release-2.0`) |
| D6 | Configurable report redaction rules (done on `release-2.0`) |
| D7 | JSONL trace store (done on `release-2.0`) |

Not planned: a hosted service or live monitoring product, a TypeScript port,
or new research interfaces in the core package.
