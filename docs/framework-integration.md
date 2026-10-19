# Capturing agents built with a framework

The core package has no framework dependency. Version 2.1 adds optional,
tested integrations for the OpenAI Agents SDK, LangChain and the Claude Agent
SDK (below), and [OpenTelemetry export and import](opentelemetry.md). In every
framework the same records come from the same places:

| Record | Where it comes from | Recorder call |
| --- | --- | --- |
| Outcome contract | Your application, before the tool runs: what must hold, by when, how many times | `capture = rec.register(...)` |
| Dispatch | The moment your code calls the tool | `capture.attempt()` / `capture_tool(capture)` / `capture.acall(...)` |
| Tool response | What the tool returned, or the timeout or error it raised | recorded when the attempt ends |
| Agent's assessment | What the agent *claimed* afterwards: its final message or structured output | `capture.assessment("success" \| "failure" \| "partial" \| "unknown")` |
| Readback | A separate, read-only query of your system of record, after the contract horizon | `capture.verify(observation, verifier=...)` or `poll_readback(...)` |

`rec.register` returns an `ActionCapture` for that action. A run that takes
several consequential actions registers each one and records through each
handle; their attempts, assessments and receipts never mix. While a run has a
single action, the same calls also work on the recorder itself.

Rules that hold in every framework:

- Register the contract before dispatching. Declaring success after seeing the
  result would let the outcome define its own target.
- Record the agent's claim as it was stated. If it made no explicit claim, record
  `unknown` or nothing; never infer the claim from the tool response. An agent
  may report more than once (before and after a retry); record each report.
- Read back through a different path from the tool (a read-only connection or
  credential), after the deadline plus stability window, and declare the
  snapshot's scope, completeness and watermark honestly. Otherwise use
  `available=False` or `complete=False` and let the result stay `unknown`.
  `poll_readback` waits for the horizon and re-reads a lagging replica for you.
- Use one time base for the whole trace. The recorder defaults to wall-clock
  `unix_ms`; `TraceRecorder.now()` returns its clock, for readback
  `observed_at_ms` and `as_of_ms`.
- To link an effect to its attempt, pass `attempt.attempt_id` (and the action ID)
  to the tool if the downstream system stores request metadata with the effect,
  as many payment and ticketing APIs do.
- Before retrying a timed-out action, ask `retry_advice(receipt)`: a retry after
  a hidden success duplicates the effect.

## Ready-made integrations

Each integration is an optional extra and records through one shared
`ToolCallCapture`. Your application decides which calls are consequential:
`contract_for(call)` returns the call's outcome contract, or `None` to leave it
unrecorded. `call` is a `ToolCall` with the tool name, parsed arguments, the
framework's call ID and `started_at_ms` in the recorder's clock:

```python
from consequa_x import OutcomeContract, TraceRecorder
from consequa_x.integrations import ToolCallCapture


def contract_for(call):
    if call.tool_name != "issue_refund":
        return None
    return OutcomeContract(contract_id=f"refund-{call.call_id}", predicate="record_present",
                           expected={"order_id": call.arguments["order_id"]},
                           deadline_ms=call.started_at_ms + 30_000, stability_ms=5_000)


rec = TraceRecorder(run_id, actor="support-agent")
calls = ToolCallCapture(rec, contract_for=contract_for)
```

Each recorded call becomes an action named by the framework's call ID (or
`<tool>-<n>`), with one attempt per call. Pass `action_id_for=` to group a
retry with the call it retries: a call whose action ID is already registered
becomes another attempt of that action. After the run, `calls.captures` lists
the recorded actions; record the agent's claim and verify readback through
them as usual.

| Framework | Install | Hook it up |
| --- | --- | --- |
| OpenAI Agents SDK | `pip install "consequa-x[openai-agents]"` | `@consequential_tool(calls=calls)` in place of `@function_tool` |
| LangChain (and LangGraph) | `pip install "consequa-x[langchain]"` | `config={"callbacks": [ConsequaCallbackHandler(calls)]}` |
| Claude Agent SDK | `pip install "consequa-x[claude-agent-sdk]"` | `ClaudeAgentOptions(hooks=consequa_hooks(calls))` |

```python
# OpenAI Agents SDK
from consequa_x.integrations.openai_agents import consequential_tool

@consequential_tool(calls=calls, timeout=10)      # other options go to function_tool
async def issue_refund(order_id: str) -> str:
    ...

# LangChain
from consequa_x.integrations.langchain import ConsequaCallbackHandler

agent.invoke({"messages": [...]}, config={"callbacks": [ConsequaCallbackHandler(calls)]})

# Claude Agent SDK
from claude_agent_sdk import ClaudeAgentOptions
from consequa_x.integrations.claude_agent_sdk import consequa_hooks

options = ClaudeAgentOptions(hooks=consequa_hooks(calls, matcher="mcp__billing__.*"))
```

What each one records as the tool response:

- **OpenAI Agents SDK.** The tool behaves as a `function_tool` for the model. An
  exception is recorded as `error` (`timeout` for `TimeoutError`) and then turned
  into the usual model-visible message by `failure_error_function` (the SDK's
  default unless you pass another; with `None` it propagates). When the SDK
  cancels the call at the tool's `timeout`, the attempt is recorded as `timeout`.
- **LangChain.** An exception the tool raises is recorded as `error` (`timeout`
  for `TimeoutError`). An error the tool handles itself (`handle_tool_error`) is
  recorded as `error` when the run returns a `ToolMessage` with error status,
  which LangChain does for tool calls. The handler raises recording failures
  instead of logging them, so a trace never silently misses a call.
- **Claude Agent SDK.** `PreToolUse` records the dispatch, `PostToolUse` a
  success and `PostToolUseFailure` a failure: `timeout` when the reported error
  names a timeout, otherwise `error` (pass `classify=` to decide yourself). The
  hooks only observe; they never block or change a tool call. Merge them with
  any hooks you already use.

None of this establishes an outcome. A timeout says nothing about whether the
refund happened; readback does.

Tested with openai-agents 0.24.0, langchain-core 1.6.12 and claude-agent-sdk
0.2.168. The tests drive each SDK offline: the Agents SDK's `ScriptedModel` in a
real `Runner` loop, real LangChain tools with callbacks, and the Claude Agent
SDK's hook protocol through a scripted transport. No live model was called.

## Doing it by hand

The snippets below show where the calls go without an integration. Check your
framework version's documentation for exact signatures. `rec`, `contract`,
`verifier`, `issue_refund_api` and `read_refunds` stand for your own objects;
see [the SQLite agent-loop example](../examples/agent_loop_sqlite.py) for a
complete, runnable version.

### A plain tool-calling loop

```python
rec = TraceRecorder(run_id, actor="support-agent")
refund = rec.register("refund-o-17", "issue_refund", args, contract=contract)
try:
    with refund.attempt(data={"tool": "issue_refund"}) as attempt:
        attempt.result = issue_refund_api(**args, attempt_id=attempt.attempt_id)
except TimeoutError:
    pass                                       # the loop decides what to do next
refund.assessment(agent_final_claim)            # what the agent said, not what happened
receipt = poll_readback(refund, lambda n: read_refunds("o-17", read_number=n),
                        until_ms=rec.now() + 60_000, interval_ms=2_000, verifier=verifier)
if retry_advice(receipt).advice is RetryAdvice.RETRY_PERMITTED:
    ...                                         # retry with an idempotency key
```

### Wrapping a framework's tool function

Most frameworks register an ordinary Python function as a tool. Record inside
that function, so the framework's retries and error handling are captured as
separate attempts:

```python
@capture_tool(refund)                 # works for def and async def tools
def issue_refund(order_id: str, amount_minor: int) -> dict:
    return issue_refund_api(order_id, amount_minor)
```

Then register `issue_refund` the framework's way: for example with
`function_tool` in the OpenAI Agents SDK or the `tool` decorator in LangChain.
Register the outcome contract when your application starts the run (or when the
agent decides to act), and record the agent's assessment from the run's final
output.

The Claude Agent SDK's in-process tools are asynchronous functions:

```python
async def issue_refund(args):
    await refund.acall(issue_refund_api_async, **args)
    return {"content": [{"type": "text", "text": "Refund requested."}]}
```

`acall` records the awaited call as one attempt; use `refund.attempt()` around an
`await` when you need the attempt ID inside the call. Async verifiers go through
`refund.averify(...)`, and `apoll_readback` polls with `asyncio.sleep`.

Wrapping the tool function yourself records exceptions and timeouts exactly
where they happen; the integrations above do the same through each framework's
own extension point.

## MCP clients

`consequa_x.mcp_capture.call_mcp_tool` wraps a client session's tool call:

```python
from consequa_x.mcp_capture import call_mcp_tool

result = await call_mcp_tool(refund, session, "issue_refund",
                             {"order_id": "o-17", "attempt_hint": "include if stored"})
```

It works with any session exposing `await session.call_tool(name, arguments)`,
the shape of the MCP Python SDK's `ClientSession`, and records a result whose
`isError` is true as an error. Pass `classify=` to map an SDK-specific timeout
exception to `"timeout"`. Its tests use a stand-in session, not a live server.

## After the run

```python
trace = rec.trace()
for action in explain(trace).actions:
    print(action.action_id, action.assessment_alignment, action.codes)
Path("report.html").write_text(render_report(trace), encoding="utf-8")
TraceStore("traces.jsonl").append(trace)        # then: consequa-x summarize traces.jsonl
```

Keep `trace.to_json()` (or the store) as the evidence record; the HTML report is
a presentation of it.
