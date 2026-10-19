"""Record Claude Agent SDK tool use with hooks.

``consequa_hooks(calls)`` returns hook matchers for ``PreToolUse``,
``PostToolUse`` and ``PostToolUseFailure``; pass them as
``ClaudeAgentOptions(hooks=...)`` (merge them with any hooks you already use).
Every tool use that ``contract_for`` makes consequential is recorded through a
:class:`~consequa_x.integrations.ToolCallCapture`: the ``tool_use_id``, tool
name and input, the dispatch at ``PreToolUse`` and the response at
``PostToolUse`` (``success``) or ``PostToolUseFailure`` (``timeout`` when the
reported error names a timeout, otherwise ``error``). The hooks only observe:
they return an empty result and never block or change a tool call.

Tested with ``claude-agent-sdk`` 0.2.168 through its hook callback protocol,
and once in a live session with Claude Haiku. Install with
``pip install "consequa-x[claude-agent-sdk]"``.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

try:
    from claude_agent_sdk import HookMatcher
except ImportError as error:  # pragma: no cover - exercised without the extra
    raise ImportError('This integration needs claude-agent-sdk: '
                      'pip install "consequa-x[claude-agent-sdk]"') from error

from ..errors import ConsequaTypeError
from ..models import ResponseStatus
from . import PendingCall, ToolCallCapture

_FRAMEWORK = "claude-agent-sdk"


def _failure_status(error: Any) -> ResponseStatus:
    text = str(error or "").lower()
    timed_out = "timed out" in text or "timeout" in text
    return ResponseStatus.TIMEOUT if timed_out else ResponseStatus.ERROR


def consequa_hooks(calls: ToolCallCapture, *, matcher: str | None = None,
                   classify: Callable[[dict[str, Any]], str | ResponseStatus] | None = None,
                   ) -> dict[str, list[HookMatcher]]:
    """Hook matchers that record consequential tool use through ``calls``.

    ``matcher`` limits the hooks to tool names, as in the SDK (for example
    ``"mcp__billing__.*"``); ``contract_for`` still decides which calls are
    recorded. ``classify(failure_input)`` can map a ``PostToolUseFailure``
    input to a response status instead of the default reading of its error.
    """
    if not isinstance(calls, ToolCallCapture):
        raise ConsequaTypeError("consequa_hooks requires a ToolCallCapture")
    pending: dict[str, PendingCall] = {}
    lock = threading.Lock()

    def take(data: dict[str, Any], tool_use_id: str | None) -> PendingCall | None:
        key = data.get("tool_use_id") or tool_use_id
        with lock:
            return pending.pop(key, None) if key else None

    async def before(data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        key = data.get("tool_use_id") or tool_use_id
        call = calls.start(data.get("tool_name"), data.get("tool_input") or {},
                           framework=_FRAMEWORK, call_id=key,
                           agent_name=data.get("agent_type"))
        if call is not None and key:
            with lock:
                pending[key] = call
        return {}

    async def after(data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        call = take(data, tool_use_id)
        if call is not None:
            calls.finish(call, "success", result=data.get("tool_response"))
        return {}

    async def failed(data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        call = take(data, tool_use_id)
        if call is not None:
            status = classify(data) if classify else _failure_status(data.get("error"))
            calls.finish(call, status,
                         result={"is_interrupt": data.get("is_interrupt") is True})
        return {}

    return {
        "PreToolUse": [HookMatcher(matcher=matcher, hooks=[before])],
        "PostToolUse": [HookMatcher(matcher=matcher, hooks=[after])],
        "PostToolUseFailure": [HookMatcher(matcher=matcher, hooks=[failed])],
    }


__all__ = ["consequa_hooks"]
