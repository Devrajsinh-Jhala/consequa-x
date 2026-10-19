"""Framework integrations: the shared tool-call capture and each optional SDK.

The SDK tests run only where the SDK is installed (the release checks install
openai-agents, langchain-core, claude-agent-sdk and opentelemetry in a separate
environment). They drive each SDK's own machinery offline: the Agents SDK's
``ScriptedModel`` in a real ``Runner`` loop, real LangChain tools with
callbacks, and the Claude Agent SDK's hook protocol through a scripted
transport. None of them calls a live model.
"""

import asyncio
import json
import threading

import pytest

from consequa_x import (
    ConsequaTypeError, Observation, OutcomeContract, RecordVerifier, TraceRecorder, explain,
)
from consequa_x.integrations import ToolCall, ToolCallCapture


STORE: dict[str, dict] = {}


def contract_for(call: ToolCall):
    if call.tool_name not in ("issue_refund", "mcp__billing__issue_refund"):
        return None
    order = call.arguments.get("order_id", "unknown")
    return OutcomeContract(contract_id=f"refund-{order}-{call.call_id or call.started_at_ms}",
                           predicate="record_present", expected={"order_id": order},
                           deadline_ms=call.started_at_ms + 60_000)


def recorder():
    return TraceRecorder("framework-run", actor="support-agent")


def test_capture_records_only_consequential_calls():
    rec = recorder()
    calls = ToolCallCapture(rec, contract_for=contract_for)
    assert calls.start("lookup_order", {"order_id": "o-1"}, framework="test") is None
    pending = calls.start("issue_refund", '{"order_id": "o-1"}', framework="test",
                          call_id="call_9", agent_name="Billing")
    assert pending.call.arguments == {"order_id": "o-1"}
    calls.finish(pending, "success", result="refunded")
    trace = rec.trace()
    assert [action.action_id for action in trace.actions] == ["call_9"]
    assert trace.responses[0].provider_request_id == "call_9"
    assert trace.responses[0].result == {"value": "refunded"}
    dispatch = next(event for event in trace.events if event.type.value == "action_dispatch")
    assert dispatch.data["framework"] == "test" and dispatch.data["agent"] == "Billing"
    unnamed = calls.start("issue_refund", "not json", framework="test")
    assert unnamed.capture.action_id == "issue_refund-1"
    assert unnamed.call.arguments == {"input": "not json"}
    with pytest.raises(ConsequaTypeError):
        ToolCallCapture(rec, contract_for="no")
    with pytest.raises(ConsequaTypeError):
        calls.finish("pending", "success")


def test_retries_group_under_one_action_and_threads_are_serialized():
    rec = recorder()
    calls = ToolCallCapture(rec, contract_for=contract_for,
                            action_id_for=lambda call: f"refund-{call.arguments['order_id']}")
    first = calls.start("issue_refund", {"order_id": "o-2"}, framework="test", call_id="c1")
    calls.finish(first, "timeout", exception="TimeoutError")
    second = calls.start("issue_refund", {"order_id": "o-2"}, framework="test", call_id="c2")
    calls.finish(second, "success")
    trace = rec.trace()
    assert [action.action_id for action in trace.actions] == ["refund-o-2"]
    assert [item.status.value for item in trace.responses] == ["timeout", "success"]

    many = ToolCallCapture(recorder(), contract_for=contract_for)

    def work(index):
        pending = many.start("issue_refund", {"order_id": f"o-{index}"}, framework="test",
                             call_id=f"t{index}")
        many.finish(pending, "success")

    threads = [threading.Thread(target=work, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(many.recorder.trace().responses) == 20


def readback(capture, *records):
    """A complete readback taken at the contract horizon."""
    at = capture.action.contract.horizon_ms
    return Observation(observation_id=f"orders-{at}", source="orders-db", observed_at_ms=at,
                       as_of_ms=at, scope={"order_id": "o-1"}, records=records)


# OpenAI Agents SDK ------------------------------------------------------------------


def test_openai_agents_runner_records_success_error_and_timeout(monkeypatch):
    pytest.importorskip("agents")
    monkeypatch.setenv("OPENAI_AGENTS_DISABLE_TRACING", "1")
    from agents import Agent, Runner, function_tool
    from agents.testing import ScriptedModel, assistant_message, function_call
    from consequa_x.integrations.openai_agents import consequential_tool

    rec = recorder()
    calls = ToolCallCapture(rec, contract_for=contract_for)

    @consequential_tool(calls=calls, timeout=0.2)
    async def issue_refund(order_id: str) -> str:
        """Refund an order."""
        if order_id == "o-boom":
            raise PermissionError("not allowed")
        STORE[order_id] = {"effect_id": f"e-{order_id}", "order_id": order_id,
                           "committed_at_ms": rec.now(), "action_id": f"call-{order_id}",
                           "actor": "support-agent"}
        if order_id == "o-1":
            await asyncio.sleep(1)  # commits, then times out
        return f"refunded {order_id}"

    @function_tool
    def lookup_order(order_id: str) -> str:
        """Look up an order."""
        return "open"

    model = ScriptedModel([
        [function_call("lookup_order", {"order_id": "o-1"}, call_id="call-lookup")],
        [function_call("issue_refund", {"order_id": "o-1"}, call_id="call-o-1"),
         function_call("issue_refund", {"order_id": "o-boom"}, call_id="call-o-boom"),
         function_call("issue_refund", {"order_id": "o-2"}, call_id="call-o-2")],
        [assistant_message("The refund for o-1 failed.")],
    ])
    agent = Agent(name="Billing", instructions="Refund orders.", tools=[issue_refund,
                                                                        lookup_order],
                  model=model)
    result = asyncio.run(Runner.run(agent, "Refund o-1", hooks=None))
    assert result.final_output == "The refund for o-1 failed."
    outputs = [item.output for item in result.new_items if hasattr(item, "output")]
    assert "timed out" in outputs[1] and "error occurred" in outputs[2]
    trace = rec.trace()
    assert [action.action_id for action in trace.actions] == ["call-o-1", "call-o-boom",
                                                              "call-o-2"]
    statuses = {item.action_id: item.status.value for item in trace.responses}
    assert statuses == {"call-o-1": "timeout", "call-o-boom": "error", "call-o-2": "success"}
    assert trace.responses_for("call-o-boom")[0].result == {"exception": "PermissionError"}
    dispatch = next(event for event in trace.events if event.type.value == "action_dispatch")
    assert dispatch.data["agent"] == "Billing" and dispatch.data["framework"] == "openai-agents"

    capture = calls.captures[0]
    capture.assessment("failure")
    receipt = capture.verify(readback(capture, STORE["o-1"]),
                             verifier=RecordVerifier(scope_fields=("order_id",)))
    assert receipt.status.value == "satisfied" and receipt.origin.value == "confirmed"
    judged = explain(rec.trace()).for_action("call-o-1")
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in judged.codes
    assert judged.assessment_alignment == "contradicted"


def test_openai_agents_failure_function_none_propagates(monkeypatch):
    pytest.importorskip("agents")
    from agents.tool_context import ToolContext
    from consequa_x.integrations.openai_agents import consequential_tool

    rec = recorder()
    calls = ToolCallCapture(rec, contract_for=contract_for)

    @consequential_tool(calls=calls, failure_error_function=None)
    def issue_refund(order_id: str) -> str:
        """Refund an order."""
        raise TimeoutError("gateway")

    context = ToolContext(context=None, tool_name="issue_refund", tool_call_id="call-x",
                          tool_arguments='{"order_id": "o-1"}')
    with pytest.raises(Exception):
        asyncio.run(issue_refund.on_invoke_tool(context, '{"order_id": "o-1"}'))
    assert rec.trace().responses[0].status.value == "timeout"


# LangChain --------------------------------------------------------------------------


def test_langchain_callbacks_record_tool_runs():
    pytest.importorskip("langchain_core")
    from langchain_core.tools import ToolException, tool
    from consequa_x.integrations.langchain import ConsequaCallbackHandler

    rec = recorder()
    handler = ConsequaCallbackHandler(ToolCallCapture(rec, contract_for=contract_for))

    @tool
    def issue_refund(order_id: str) -> str:
        """Refund an order."""
        if order_id == "o-boom":
            raise ValueError("bad order")
        if order_id == "o-slow":
            raise TimeoutError("gateway")
        if order_id == "o-handled":
            raise ToolException("declined")
        return f"refunded {order_id}"

    issue_refund.handle_tool_error = True

    @tool
    def lookup_order(order_id: str) -> str:
        """Look up an order."""
        return "open"

    config = {"callbacks": [handler]}

    def call(name, order, call_id):
        return {"name": name, "args": {"order_id": order}, "id": call_id, "type": "tool_call"}

    message = issue_refund.invoke(call("issue_refund", "o-1", "lc-1"), config=config)
    assert message.content == "refunded o-1"
    lookup_order.invoke(call("lookup_order", "o-1", "lc-2"), config=config)
    for order, call_id, error in (("o-boom", "lc-3", ValueError), ("o-slow", "lc-4",
                                                                    TimeoutError)):
        with pytest.raises(error):
            issue_refund.invoke(call("issue_refund", order, call_id), config=config)
    handled = issue_refund.invoke(call("issue_refund", "o-handled", "lc-5"), config=config)
    assert handled.status == "error"
    asyncio.run(issue_refund.ainvoke(call("issue_refund", "o-2", "lc-6"), config=config))
    trace = rec.trace()
    assert [action.action_id for action in trace.actions] == ["lc-1", "lc-3", "lc-4", "lc-5",
                                                              "lc-6"]
    assert [item.status.value for item in trace.responses] == [
        "success", "error", "timeout", "error", "success"]
    assert trace.responses[0].result == {"value": "refunded o-1"}
    assert trace.actions[0].arguments == {"order_id": "o-1"}


# Claude Agent SDK -------------------------------------------------------------------


class ScriptedCLI:
    """Plays the CLI side of the SDK's control protocol for a scripted tool session."""

    def __init__(self, hook_events):
        self.hook_events = hook_events
        self.outgoing: asyncio.Queue = asyncio.Queue()
        self.responses: dict[str, asyncio.Future] = {}
        self.callbacks: dict[str, list[str]] = {}
        self.replies = []

    async def connect(self):
        pass

    def is_ready(self):
        return True

    async def end_input(self):
        pass

    async def close(self):
        await self.outgoing.put(None)

    async def write(self, data):
        message = json.loads(data)
        if message["type"] == "control_request" and message["request"]["subtype"] == "initialize":
            for event, matchers in (message["request"]["hooks"] or {}).items():
                self.callbacks[event] = [item for matcher in matchers
                                         for item in matcher["hookCallbackIds"]]
            await self.outgoing.put({"type": "control_response", "response": {
                "subtype": "success", "request_id": message["request_id"], "response": {}}})
        elif message["type"] == "control_response":
            response = message["response"]
            self.replies.append(response.get("response"))
            self.responses[response["request_id"]].set_result(response)
        elif message["type"] == "user":
            asyncio.get_running_loop().create_task(self.play())

    async def play(self):
        for index, (event, payload) in enumerate(self.hook_events):
            for callback in self.callbacks.get(event, []):
                request_id = f"cli-{index}-{callback}"
                self.responses[request_id] = asyncio.get_running_loop().create_future()
                await self.outgoing.put({"type": "control_request", "request_id": request_id,
                                         "request": {"subtype": "hook_callback",
                                                     "callback_id": callback,
                                                     "input": {"hook_event_name": event,
                                                               "session_id": "s-1",
                                                               "transcript_path": "",
                                                               "cwd": ".", **payload},
                                                     "tool_use_id": payload["tool_use_id"]}})
                await self.responses[request_id]
        await self.outgoing.put({"type": "result", "subtype": "success", "duration_ms": 5,
                                 "duration_api_ms": 0, "is_error": False, "num_turns": 1,
                                 "session_id": "s-1", "result": "done"})
        await self.outgoing.put(None)  # the CLI exits after its result

    async def read_messages(self):
        while True:
            item = await self.outgoing.get()
            if item is None:
                return
            yield item


def test_claude_agent_sdk_hooks_record_tool_use_through_the_sdk_protocol():
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    from consequa_x.integrations.claude_agent_sdk import consequa_hooks

    rec = recorder()
    calls = ToolCallCapture(rec, contract_for=contract_for)
    refund = "mcp__billing__issue_refund"
    events = [
        ("PreToolUse", {"tool_name": "Read", "tool_input": {"path": "x"},
                        "tool_use_id": "tu-0"}),
        ("PostToolUse", {"tool_name": "Read", "tool_input": {"path": "x"},
                         "tool_response": "text", "tool_use_id": "tu-0"}),
        ("PreToolUse", {"tool_name": refund, "tool_input": {"order_id": "o-1"},
                        "tool_use_id": "tu-1"}),
        ("PostToolUseFailure", {"tool_name": refund, "tool_input": {"order_id": "o-1"},
                                "tool_use_id": "tu-1", "error": "MCP tool call timed out"}),
        ("PreToolUse", {"tool_name": refund, "tool_input": {"order_id": "o-2"},
                        "tool_use_id": "tu-2"}),
        ("PostToolUse", {"tool_name": refund, "tool_input": {"order_id": "o-2"},
                         "tool_response": {"refund_id": "r-2"}, "tool_use_id": "tu-2"}),
        ("PreToolUse", {"tool_name": refund, "tool_input": {"order_id": "o-3"},
                        "tool_use_id": "tu-3"}),
        ("PostToolUseFailure", {"tool_name": refund, "tool_input": {"order_id": "o-3"},
                                "tool_use_id": "tu-3", "error": "Permission denied"}),
    ]
    cli = ScriptedCLI(events)

    async def run():
        options = ClaudeAgentOptions(hooks=consequa_hooks(calls))
        return [message async for message in query(prompt="Refund o-1", options=options,
                                                   transport=cli)]

    messages = asyncio.run(asyncio.wait_for(run(), timeout=30))
    assert isinstance(messages[-1], ResultMessage)
    assert all(reply == {} for reply in cli.replies) and len(cli.replies) == len(events)
    trace = rec.trace()
    assert [action.action_id for action in trace.actions] == ["tu-1", "tu-2", "tu-3"]
    assert [item.status.value for item in trace.responses] == ["timeout", "success", "error"]
    assert trace.responses[1].result == {"refund_id": "r-2"}
    assert trace.actions[0].name == refund
