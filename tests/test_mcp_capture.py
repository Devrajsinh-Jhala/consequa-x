"""call_mcp_tool records MCP-shaped tool calls without an MCP dependency."""

import asyncio
from types import SimpleNamespace

import pytest

from consequa_x import OutcomeContract, ResponseStatus, TraceRecorder
from consequa_x.mcp_capture import call_mcp_tool


class StandInSession:
    """Has the ClientSession.call_tool call shape; not the MCP SDK itself."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def recorder():
    ticks = iter(range(0, 1000, 5))
    rec = TraceRecorder("trace-1", actor="agent", clock=lambda: next(ticks))
    contract = OutcomeContract(contract_id="c1", predicate="record_present", expected={"order_id": "o-17"}, deadline_ms=100)
    rec.register("refund-1", "issue_refund", {"order_id": "o-17"}, contract=contract)
    return rec


@pytest.mark.parametrize("flag,status,result", [
    (False, ResponseStatus.SUCCESS, {"is_error": False}),
    (True, ResponseStatus.ERROR, {"is_error": True}),
    (None, ResponseStatus.SUCCESS, {}),
])
def test_returned_results_are_recorded_by_their_error_flag(flag, status, result):
    rec = recorder()
    session = StandInSession(SimpleNamespace(isError=flag, content=["not copied"]))
    returned = asyncio.run(call_mcp_tool(rec, session, "issue_refund", {"order_id": "o-17"}))
    assert returned is session.outcome
    assert session.calls == [("issue_refund", {"order_id": "o-17"})]
    rec.assessment("unknown")
    (response,) = rec.trace().responses
    assert (response.status, response.result) == (status, result)
    dispatch = rec.trace().events[1]
    assert dispatch.data["tool"] == "issue_refund" and dispatch.data["transport"] == "mcp"


def test_exceptions_are_recorded_and_reraised():
    class SdkTimeout(Exception):
        pass

    rec = recorder()
    with pytest.raises(TimeoutError):
        asyncio.run(call_mcp_tool(rec, StandInSession(TimeoutError()), "issue_refund"))
    with pytest.raises(SdkTimeout):
        asyncio.run(call_mcp_tool(rec, StandInSession(SdkTimeout()), "issue_refund",
                                  classify=lambda error: "timeout"))
    rec.assessment("failure")
    statuses = [response.status for response in rec.trace().responses]
    assert statuses == [ResponseStatus.TIMEOUT, ResponseStatus.TIMEOUT]


def test_inputs_are_checked():
    with pytest.raises(TypeError, match="TraceRecorder"):
        asyncio.run(call_mcp_tool(object(), StandInSession(None), "tool"))
    with pytest.raises(TypeError, match="call_tool"):
        asyncio.run(call_mcp_tool(recorder(), object(), "tool"))
    with pytest.raises(ValueError, match="tool name"):
        asyncio.run(call_mcp_tool(recorder(), StandInSession(None), " "))
