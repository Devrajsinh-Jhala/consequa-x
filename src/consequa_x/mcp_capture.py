"""Record MCP tool calls without depending on an MCP SDK.

``call_mcp_tool`` wraps any client session that exposes
``await session.call_tool(name, arguments)``, the call shape of the MCP Python
SDK's ``ClientSession``. The package's tests use a stand-in session with that
shape, not a live MCP server or the SDK itself.

Only the call's outcome class is kept with the response: whether the server
flagged a tool error. Tool content is not copied into the trace. To let readback
link an effect to this call, pass the action and attempt identifiers to the
server in the tool arguments, if the server stores them with the effect.
"""

from __future__ import annotations

from typing import Any, Callable

from .errors import ConsequaTypeError, ValidationError
from .capture import ActionCapture, TraceRecorder
from .models import ResponseStatus


async def call_mcp_tool(recorder: TraceRecorder | ActionCapture, session: Any, name: str,
                        arguments: dict[str, Any] | None = None, *,
                        attempt_id: str | None = None,
                        classify: Callable[[Exception], str | ResponseStatus] | None = None,
                        ) -> Any:
    """Await one MCP tool call as a recorded attempt and return the server's result.

    Pass the ``ActionCapture`` of the action this call performs, or the recorder
    while it has exactly one registered action.

    A result whose ``isError`` is true is recorded as ``error``; any other
    returned result as ``success``. ``TimeoutError`` is recorded as ``timeout``
    and other exceptions as ``error`` unless ``classify`` maps them (for
    example, an SDK-specific timeout error); the exception is re-raised. As with
    any tool response, none of this establishes whether the effect happened.
    """
    if not isinstance(recorder, (TraceRecorder, ActionCapture)):
        raise ConsequaTypeError("call_mcp_tool requires a TraceRecorder or an ActionCapture")
    call_tool = getattr(session, "call_tool", None)
    if not callable(call_tool):
        raise ConsequaTypeError("session must provide an awaitable call_tool(name, arguments)")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name must be a nonempty tool name")
    with recorder.attempt(attempt_id=attempt_id, data={"tool": name, "transport": "mcp"},
                          classify=classify) as attempt:
        result = await call_tool(name, dict(arguments or {}))
        flagged = getattr(result, "isError", None)
        if flagged is True:
            attempt.status = "error"
        attempt.result = {"is_error": flagged} if isinstance(flagged, bool) else {}
    return result
