"""Record OpenAI Agents SDK function-tool calls.

``consequential_tool`` is a drop-in for the SDK's ``function_tool`` decorator.
The tool it returns behaves as before for the model, and every call that
``contract_for`` makes consequential is recorded through a
:class:`~consequa_x.integrations.ToolCallCapture`: the call's ID, tool name and
arguments, the dispatch, and the response the agent saw.

An exception is recorded as ``error`` (``timeout`` for ``TimeoutError``) before
it is turned into the model-visible message by ``failure_error_function``, the
SDK's default unless another one is passed; with ``None`` it propagates. When
the SDK cancels the call at the tool's ``timeout``, the attempt is recorded as
``timeout``; any other cancellation is recorded as ``error``. A timeout says
nothing about whether the effect happened: verify readback afterwards.

Tested with ``openai-agents`` 0.24.0. Install with
``pip install "consequa-x[openai-agents]"``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import time
from typing import Any, Callable

try:
    from agents import FunctionTool, default_tool_error_function, function_tool
except ImportError as error:  # pragma: no cover - exercised without the extra
    raise ImportError('This integration needs openai-agents: '
                      'pip install "consequa-x[openai-agents]"') from error

from ..errors import ConsequaTypeError
from . import ToolCallCapture, classify_exception

_FRAMEWORK = "openai-agents"
_DEFAULT = object()


def consequential_tool(func: Callable[..., Any] | None = None, *, calls: ToolCallCapture,
                       failure_error_function: Any = _DEFAULT,
                       **function_tool_options: Any) -> Any:
    """``function_tool`` that records consequential calls through ``calls``.

    Use it as ``@consequential_tool(calls=calls)`` or call it with the function.
    Other keyword arguments (``name_override``, ``timeout``, ...) go to
    ``function_tool`` unchanged.
    """
    if not isinstance(calls, ToolCallCapture):
        raise ConsequaTypeError("consequential_tool requires calls=ToolCallCapture(...)")
    formatter = default_tool_error_function if failure_error_function is _DEFAULT \
        else failure_error_function

    def build(target: Callable[..., Any]) -> FunctionTool:
        tool = function_tool(target, failure_error_function=None, **function_tool_options)
        return observe(tool, calls, formatter)

    return build if func is None else build(func)


def observe(tool: FunctionTool, calls: ToolCallCapture, formatter: Any) -> FunctionTool:
    """Wrap a ``FunctionTool`` built with ``failure_error_function=None``.

    Exceptions must reach this wrapper to be recorded as errors, so the tool
    itself must not convert them; ``formatter`` converts them afterwards (or,
    when ``None``, they propagate).
    """
    if not isinstance(tool, FunctionTool):
        raise ConsequaTypeError("observe requires an agents FunctionTool")
    inner = tool.on_invoke_tool

    async def invoke(context: Any, arguments: str) -> Any:
        agent = getattr(getattr(context, "agent", None), "name", None)
        pending = calls.start(tool.name, arguments, framework=_FRAMEWORK,
                              call_id=getattr(context, "tool_call_id", None), agent_name=agent)
        started = time.monotonic()
        try:
            value = await inner(context, arguments)
        except asyncio.CancelledError:
            if pending is not None:
                limit = tool.timeout_seconds
                timed_out = limit is not None and time.monotonic() - started >= limit * 0.9
                calls.finish(pending, "timeout" if timed_out else "error",
                             exception="CancelledError")
            raise
        except Exception as error:
            if pending is not None:
                calls.finish(pending, classify_exception(error), exception=type(error).__name__)
            if formatter is None:
                raise
            message = formatter(context, error)
            return await message if inspect.isawaitable(message) else message
        if pending is not None:
            calls.finish(pending, "success", result=value)
        return value

    return dataclasses.replace(tool, on_invoke_tool=invoke)


__all__ = ["consequential_tool", "observe"]
