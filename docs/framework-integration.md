# Capturing agents built with a framework

Consequa-X has no framework dependency. In every framework the same five
records come from the same places:

| Record | Where it comes from | Recorder call |
| --- | --- | --- |
| Outcome contract | Your application, before the tool runs: what must hold, by when, how many times | `rec.register(...)` |
| Dispatch | The moment your code calls the tool | `rec.attempt()` / `capture_tool` |
| Tool response | What the tool returned, or the timeout or error it raised | recorded when the `attempt()` block exits |
| Agent's assessment | What the agent *claimed* afterwards: its final message or structured output | `rec.assessment("success" \| "failure" \| "partial" \| "unknown")` |
| Readback | A separate, read-only query of your system of record, after the contract horizon | `rec.verify(observation, verifier=...)` |

Rules that hold in every framework:

- Register the contract before dispatching. Declaring success after seeing the
  result would let the outcome define its own target.
- Record the agent's claim as it was stated. If it made no explicit claim, record
  `unknown`; never infer the claim from the tool response.
- Read back through a different path from the tool (a read-only connection or
  credential), after the deadline plus stability window, and declare the
  snapshot's scope, completeness and watermark honestly. Otherwise use
  `available=False` or `complete=False` and let the result stay `unknown`.
- Use one time base for the whole trace. `TraceRecorder.now()` returns the
  recorder's clock, for readback `observed_at_ms` and `as_of_ms`.
- To link an effect to its attempt, pass `attempt.attempt_id` (and the action ID)
  to the tool if the downstream system stores request metadata with the effect,
  as many payment and ticketing APIs do.

The snippets below are sketches of where the calls go. Check your framework
version's documentation for exact signatures. `rec`, `contract`, `verifier`,
`issue_refund_api` and `read_refunds` stand for your own objects; see
[the SQLite agent-loop example](../examples/agent_loop_sqlite.py) for a complete,
runnable version.

## A plain tool-calling loop

```python
rec = TraceRecorder(run_id, actor="support-agent")
rec.register("refund-o-17", "issue_refund", args, contract=contract)
try:
    with rec.attempt(data={"tool": "issue_refund"}) as attempt:
        attempt.result = issue_refund_api(**args, attempt_id=attempt.attempt_id)
except TimeoutError:
    pass                                      # the loop decides what to do next
rec.assessment(agent_final_claim)              # what the agent said, not what happened
rec.verify(read_refunds("o-17", observed_at_ms=rec.now()), verifier=verifier)
```

## Wrapping a framework's tool function

Most frameworks register an ordinary Python function as a tool. Record inside
that function, so the framework's retries and error handling are captured as
separate attempts:

```python
def issue_refund(order_id: str, amount_minor: int) -> dict:
    with rec.attempt(data={"tool": "issue_refund"}) as attempt:
        attempt.result = issue_refund_api(order_id, amount_minor,
                                          attempt_id=attempt.attempt_id)
        return attempt.result
```

Then register `issue_refund` the framework's way: for example with
`function_tool` in the OpenAI Agents SDK or the `tool` decorator in LangChain.
Register the outcome contract when your application starts the run, and record
the agent's assessment from the run's final output.

For an asynchronous tool, the same synchronous `with rec.attempt()` block can
surround the `await`. The Claude Agent SDK's in-process tools are asynchronous
functions, so the pattern is:

```python
async def issue_refund(args):
    with rec.attempt(data={"tool": "issue_refund"}) as attempt:
        attempt.result = await issue_refund_api_async(**args, attempt_id=attempt.attempt_id)
    return {"content": [{"type": "text", "text": "Refund requested."}]}
```

Framework callbacks and hooks (LangChain callback handlers, OpenAI Agents SDK
run hooks, Claude Agent SDK pre/post tool-use hooks) also see tool starts and
ends. Wrapping the tool function is preferred because it records exceptions
and timeouts exactly where they happen.

## MCP clients

`consequa_x.mcp_capture.call_mcp_tool` wraps a client session's tool call:

```python
from consequa_x.mcp_capture import call_mcp_tool

result = await call_mcp_tool(rec, session, "issue_refund",
                             {"order_id": "o-17", "attempt_hint": "include if stored"})
```

It works with any session exposing `await session.call_tool(name, arguments)`,
the shape of the MCP Python SDK's `ClientSession`, and records a result whose
`isError` is true as an error. Pass `classify=` to map an SDK-specific timeout
exception to `"timeout"`. Its tests use a stand-in session, not a live server.

## After the run

```python
trace = rec.trace()
explanation = explain(trace, target_matcher=verifier.target_matcher())
Path("report.html").write_text(render_report(trace), encoding="utf-8")
```

Keep `trace.to_json()` as the evidence record; the HTML report is a
presentation of it.
