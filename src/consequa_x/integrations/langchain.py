"""Record LangChain tool runs with a callback handler.

Pass ``ConsequaCallbackHandler(calls)`` in a run's ``callbacks`` (or a tool's
``config``). Every tool run that ``contract_for`` makes consequential is
recorded through a :class:`~consequa_x.integrations.ToolCallCapture`: the tool
call ID when the run has one, the tool name and inputs, the dispatch, and the
response. A tool error that propagates is recorded as ``error`` (``timeout``
for ``TimeoutError``); an error the tool handled itself
(``handle_tool_error``) is recorded as ``error`` when the run returns a
``ToolMessage`` with error status, which is what LangChain returns for a tool
call. LangGraph agents run tools the same way.

Tested with ``langchain-core`` 1.6.12, offline and once with a live local model.
Install with
``pip install "consequa-x[langchain]"``.
"""

from __future__ import annotations

import threading
from typing import Any
from uuid import UUID

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError as error:  # pragma: no cover - exercised without the extra
    raise ImportError('This integration needs langchain-core: '
                      'pip install "consequa-x[langchain]"') from error

from ..errors import ConsequaTypeError
from . import PendingCall, ToolCallCapture, classify_exception

_FRAMEWORK = "langchain"


class ConsequaCallbackHandler(BaseCallbackHandler):
    """A LangChain callback handler that records consequential tool runs.

    Recording failures are raised rather than logged (``raise_error``), so a
    trace never silently misses a call, and the handler runs inline to keep
    the recorded order.
    """

    raise_error = True
    run_inline = True

    def __init__(self, calls: ToolCallCapture) -> None:
        super().__init__()
        if not isinstance(calls, ToolCallCapture):
            raise ConsequaTypeError("ConsequaCallbackHandler requires a ToolCallCapture")
        self.calls = calls
        self._pending: dict[UUID, PendingCall] = {}
        self._lock = threading.Lock()

    def on_tool_start(self, serialized: dict[str, Any] | None, input_str: str, *, run_id: UUID,
                      inputs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        name = kwargs.get("name") or (serialized or {}).get("name")
        metadata = kwargs.get("metadata") or {}
        pending = self.calls.start(
            name, inputs if isinstance(inputs, dict) else input_str, framework=_FRAMEWORK,
            call_id=kwargs.get("tool_call_id"),
            agent_name=metadata.get("lc_agent_name") or metadata.get("langgraph_node"))
        if pending is not None:
            with self._lock:
                self._pending[run_id] = pending

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        with self._lock:
            pending = self._pending.pop(run_id, None)
        if pending is None:
            return
        status = "error" if getattr(output, "status", None) == "error" else "success"
        content = getattr(output, "content", output)
        self.calls.finish(pending, status, result=content)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        with self._lock:
            pending = self._pending.pop(run_id, None)
        if pending is not None:
            self.calls.finish(pending, classify_exception(error), exception=type(error).__name__)


__all__ = ["ConsequaCallbackHandler"]
