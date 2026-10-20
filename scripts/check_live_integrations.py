"""Run each framework integration in a real agent loop with a real model.

The offline tests drive each SDK with scripted stand-ins. This check runs the
real thing once per framework: an agent asked to refund order o-17 calls an
``issue_refund`` tool that writes to a SQLite file. The tool's first call
commits the refund and then raises ``TimeoutError`` (a timeout after commit);
any later call commits again and succeeds. A ``lookup_order`` tool is not
consequential and must not be recorded.

What passes is the integration, not the model: the recorded attempts must match
the tool calls that actually ran (count, order, arguments and status), and no
non-consequential call may be recorded. The trace is then verified from a
read-only readback after the contract horizon and explained; whatever the model
chose to do (stop, retry, duplicate the refund) is reported as it happened.

Models: the OpenAI Agents SDK and LangChain runs use a local Ollama model through
its OpenAI-compatible endpoint (no API key); the Claude Agent SDK run uses the
local Claude Code login. Install the extras and ``langchain-openai`` first.

    python scripts/check_live_integrations.py --output live-run
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import sqlite3
import sys
import time

from consequa_x import (
    Observation, OutcomeContract, RecordVerifier, Trace, TraceRecorder, explain, poll_readback,
    render_report, retry_advice,
)
from consequa_x.integrations import ToolCall, ToolCallCapture

OLLAMA = "http://127.0.0.1:11434"
LOCAL_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
AGENT = "support-agent"
ORDER = "o-17"
PROMPT = ("Order o-17 arrived damaged and the customer paid INR 50. Look the order up, refund "
          "it, and tell the customer what happened.")
INSTRUCTIONS = ("You are a billing support agent. Use lookup_order to check an order and "
                "issue_refund to refund it. End your final answer with a line that is exactly "
                "'OUTCOME: success' if the refund went through, or 'OUTCOME: failure' if it did "
                "not.")
LOOKUP = "Order o-17: delivered damaged; paid INR 50; refundable."
DEADLINE_MS, STABILITY_MS = 60_000, 2_000
VERIFIER = RecordVerifier(scope_fields=("order_id",))


class Ledger:
    """The system the agent changes, and the ground truth of what its tool did."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls: list[dict] = []
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE refunds (effect_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, "
                "amount_minor INTEGER NOT NULL, committed_at_ms INTEGER NOT NULL, "
                "action_id TEXT, actor TEXT)")

    def refund(self, order_id: str) -> str:
        """Commit a refund; the first call then times out, as after a lost acknowledgement."""
        number = len(self.calls) + 1
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO refunds VALUES (?, ?, ?, ?, ?, ?)",
                               (f"rf-{number}", order_id, 5000, time.time_ns() // 1_000_000,
                                f"refund-{order_id}", AGENT))
        if number == 1:
            self.calls.append({"order_id": order_id, "status": "timeout"})
            raise TimeoutError("refund gateway timed out after the ledger committed")
        self.calls.append({"order_id": order_id, "status": "success"})
        return f"Refund rf-{number} for {order_id} accepted."

    def read(self, number: int) -> Observation:
        now = time.time_ns() // 1_000_000
        with closing(sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM refunds WHERE order_id = ? ORDER BY effect_id",
                              (ORDER,)).fetchall()
        return Observation(observation_id=f"readback-{number}", source="refunds.sqlite (read-only)",
                           observed_at_ms=now, as_of_ms=now, scope={"order_id": ORDER},
                           records=tuple(dict(row) for row in rows))


def contract_for(call: ToolCall) -> OutcomeContract | None:
    if not call.tool_name.endswith("issue_refund"):
        return None
    return OutcomeContract(contract_id=f"refund-{call.arguments.get('order_id')}",
                           predicate="record_present",
                           expected={"order_id": call.arguments.get("order_id"),
                                     "amount_minor": 5000},
                           deadline_ms=call.started_at_ms + DEADLINE_MS, exact_count=1,
                           stability_ms=STABILITY_MS)


def capture() -> tuple[TraceRecorder, ToolCallCapture]:
    recorder = TraceRecorder("live-run", actor=AGENT)
    # Retries of the same refund are attempts of one action.
    calls = ToolCallCapture(recorder, contract_for=contract_for,
                            action_id_for=lambda call: f"refund-{call.arguments.get('order_id')}")
    return recorder, calls


def outcome(text: str) -> str:
    match = re.search(r"OUTCOME:\s*(success|failure)", text or "", re.IGNORECASE)
    return match.group(1).lower() if match else "unknown"


# The three frameworks ----------------------------------------------------------------


def run_openai_agents(ledger: Ledger, calls: ToolCallCapture) -> str:
    from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool
    from agents import set_tracing_disabled
    from openai import AsyncOpenAI

    from consequa_x.integrations.openai_agents import consequential_tool

    set_tracing_disabled(True)

    @consequential_tool(calls=calls)
    def issue_refund(order_id: str) -> str:
        """Refund a paid order in full."""
        return ledger.refund(order_id)

    @function_tool
    def lookup_order(order_id: str) -> str:
        """Look up an order's delivery and payment status."""
        return LOOKUP

    model = OpenAIChatCompletionsModel(
        model=LOCAL_MODEL, openai_client=AsyncOpenAI(base_url=f"{OLLAMA}/v1", api_key="ollama"))
    agent = Agent(name="Billing", instructions=INSTRUCTIONS, tools=[lookup_order, issue_refund],
                  model=model)
    result = asyncio.run(Runner.run(agent, PROMPT, max_turns=8))
    return str(result.final_output)


def run_langchain(ledger: Ledger, calls: ToolCallCapture) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    from consequa_x.integrations.langchain import ConsequaCallbackHandler

    @tool
    def issue_refund(order_id: str) -> str:
        """Refund a paid order in full."""
        return ledger.refund(order_id)

    @tool
    def lookup_order(order_id: str) -> str:
        """Look up an order's delivery and payment status."""
        return LOOKUP

    tools = {item.name: item for item in (issue_refund, lookup_order)}
    llm = ChatOpenAI(model=LOCAL_MODEL, base_url=f"{OLLAMA}/v1", api_key="ollama",
                     temperature=0).bind_tools(list(tools.values()))
    config = {"callbacks": [ConsequaCallbackHandler(calls)]}
    messages = [SystemMessage(INSTRUCTIONS), HumanMessage(PROMPT)]
    for _ in range(8):
        reply = llm.invoke(messages)
        messages.append(reply)
        if not reply.tool_calls:
            return str(reply.content)
        for call in reply.tool_calls:
            try:
                messages.append(tools[call["name"]].invoke(call, config=config))
            except Exception as error:  # what LangGraph's ToolNode does by default
                messages.append(ToolMessage(content=f"Error: {type(error).__name__}: {error}",
                                            tool_call_id=call["id"], status="error"))
    return ""


def run_claude_agent_sdk(ledger: Ledger, calls: ToolCallCapture, workdir: Path) -> str:
    from claude_agent_sdk import (
        AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, create_sdk_mcp_server,
        query, tool,
    )

    from mcp.types import ToolAnnotations

    from consequa_x.integrations.claude_agent_sdk import consequa_hooks

    # The refund is not caught here: its first call must time out through the SDK,
    # because that timeout is what the check records.
    @tool("issue_refund", "Refund a paid order in full.", {"order_id": str},
          annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                      idempotentHint=False, openWorldHint=False))
    async def issue_refund(args):
        return {"content": [{"type": "text", "text": ledger.refund(args["order_id"])}]}

    @tool("lookup_order", "Look up an order's delivery and payment status.", {"order_id": str},
          annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=False))
    async def lookup_order(args):
        return {"content": [{"type": "text", "text": LOOKUP}]}

    server = create_sdk_mcp_server(name="billing", version="1.0.0",
                                   tools=[issue_refund, lookup_order])
    options = ClaudeAgentOptions(
        mcp_servers={"billing": server}, system_prompt=INSTRUCTIONS, model="haiku",
        allowed_tools=["mcp__billing__issue_refund", "mcp__billing__lookup_order"],
        tools=[], hooks=consequa_hooks(calls), max_turns=8, cwd=str(workdir))

    async def run():
        texts, final = [], ""
        async for message in query(prompt=PROMPT, options=options):
            if isinstance(message, AssistantMessage):
                texts += [block.text for block in message.content if isinstance(block, TextBlock)]
            elif isinstance(message, ResultMessage):
                final = message.result or ""
        return final or "\n".join(texts)

    return asyncio.run(run())


# One framework run -------------------------------------------------------------------


def check(framework: str, output: Path) -> dict:
    folder = output / framework
    folder.mkdir(parents=True)
    ledger = Ledger(folder / "refunds.sqlite")
    recorder, calls = capture()
    started = time.monotonic()
    error = None
    try:
        if framework == "openai-agents":
            final = run_openai_agents(ledger, calls)
        elif framework == "langchain":
            final = run_langchain(ledger, calls)
        else:
            final = run_claude_agent_sdk(ledger, calls, folder)
    except Exception as failure:  # the run itself failed; still report what was captured
        final, error = "", f"{type(failure).__name__}: {failure}"
    seconds = round(time.monotonic() - started, 1)
    actions = calls.captures
    recorded = [{"order_id": item.action.arguments.get("order_id"), "status": response.status.value}
                for item in actions for response in recorder.trace().responses_for(item.action_id)] \
        if actions else []
    result = {"framework": framework, "seconds": seconds, "run_error": error,
              "tool_calls_that_ran": ledger.calls, "recorded_attempts": recorded,
              "recorded_actions": [item.action_id for item in actions],
              "final_answer_tail": (final or "")[-300:]}
    result["recording_matches_reality"] = recorded == ledger.calls and bool(ledger.calls)
    if not actions:
        result["passed"] = False
        return result
    capture_handle = actions[0]
    capture_handle.assessment(outcome(final), rationale="Parsed from the agent's final answer")
    receipt = poll_readback(capture_handle, ledger.read,
                            until_ms=capture_handle.action.contract.horizon_ms + 30_000,
                            interval_ms=2_000, verifier=VERIFIER)
    trace = recorder.trace()
    assert Trace.from_json(trace.to_json()) == trace
    judged = explain(trace).for_action(capture_handle.action_id)
    (folder / "trace.json").write_text(trace.to_json(indent=2), encoding="utf-8")
    (folder / "report.html").write_text(render_report(trace), encoding="utf-8")
    result.update({
        "agent_reported": outcome(final), "state": receipt.status.value,
        "origin": receipt.origin.value, "alignment": judged.assessment_alignment,
        "diagnoses": list(judged.codes), "retry_advice": retry_advice(receipt).advice.value,
        "refund_rows": len(ledger.read(99).records),
    })
    result["passed"] = result["recording_matches_reality"] and error is None
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True, help="A new folder")
    parser.add_argument("--framework", action="append",
                        choices=("openai-agents", "langchain", "claude-agent-sdk"))
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    frameworks = args.framework or ["openai-agents", "langchain", "claude-agent-sdk"]
    runs = [check(name, args.output) for name in frameworks]
    packages = ("consequa-x", "openai-agents", "openai", "langchain-core", "langchain-openai",
                "claude-agent-sdk")
    receipt = {
        "passed": all(item["passed"] for item in runs), "python": platform.python_version(),
        "platform": platform.platform(), "local_model": LOCAL_MODEL,
        "claude_model_alias": "haiku",
        "versions": {name: metadata.version(name) for name in packages},
        "runs": runs,
    }
    (args.output / "live-integrations.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({item["framework"]: {key: item.get(key) for key in (
        "passed", "tool_calls_that_ran", "recorded_attempts", "state", "alignment",
        "diagnoses", "run_error", "seconds")} for item in runs}, indent=1))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
