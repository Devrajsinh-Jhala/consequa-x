"""Optional integrations with agent frameworks.

Each integration records a framework's tool calls through one shared
:class:`ToolCallCapture`, which needs no framework:

- ``consequa_x.integrations.openai_agents``: ``consequential_tool``, a
  ``function_tool`` that records each call (``pip install "consequa-x[openai-agents]"``);
- ``consequa_x.integrations.langchain``: ``ConsequaCallbackHandler`` for tool
  runs (``pip install "consequa-x[langchain]"``);
- ``consequa_x.integrations.claude_agent_sdk``: ``consequa_hooks`` for the
  ``PreToolUse``, ``PostToolUse`` and ``PostToolUseFailure`` hooks
  (``pip install "consequa-x[claude-agent-sdk]"``).

The application decides which calls are consequential: ``contract_for``
returns an outcome contract for a call, or ``None`` to leave it unrecorded.
What a framework reports about a call is a tool response, never verification;
readback is still captured by the application and verified through the
action's ``ActionCapture``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
from typing import Any, Callable

from ..capture import ActionCapture, TraceRecorder, _result_payload
from ..errors import ConsequaTypeError, RecorderError
from ..models import OutcomeContract, ResponseStatus, _json_copy


@dataclass(frozen=True)
class ToolCall:
    """A framework tool call, offered to ``contract_for`` before it runs.

    ``started_at_ms`` uses the recorder's clock and time base, so a contract
    deadline can be set relative to it. ``call_id`` is the identifier the
    framework or model gave the call, when there is one.
    """

    tool_name: str
    arguments: dict[str, Any]
    call_id: str | None
    started_at_ms: int
    framework: str
    agent_name: str | None = None


@dataclass(frozen=True)
class PendingCall:
    """A dispatched attempt waiting for its response."""

    capture: ActionCapture
    attempt_id: str
    call: ToolCall


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {"input": value}
    try:
        copied = _json_copy(value, "arguments")
    except (TypeError, ValueError):
        return {}
    return copied if type(copied) is dict else {"input": copied}


class ToolCallCapture:
    """Record framework tool calls as actions, attempts and responses.

    ``contract_for(call)`` returns the outcome contract of a consequential
    call, or ``None`` to skip it. Each recorded call becomes an action whose ID
    is ``action_id_for(call)`` when given, otherwise the call's ``call_id``, or
    ``<tool>-<n>``. A call whose action ID is already registered is recorded as
    another attempt of that action, so a retry can be grouped with the call it
    retries. Calls may arrive from several threads; recording is serialized.
    """

    def __init__(self, recorder: TraceRecorder, *,
                 contract_for: Callable[[ToolCall], OutcomeContract | None],
                 action_id_for: Callable[[ToolCall], str] | None = None) -> None:
        if not isinstance(recorder, TraceRecorder):
            raise ConsequaTypeError("ToolCallCapture requires a TraceRecorder")
        if not callable(contract_for):
            raise ConsequaTypeError("contract_for must be callable")
        if action_id_for is not None and not callable(action_id_for):
            raise ConsequaTypeError("action_id_for must be callable")
        self.recorder = recorder
        self._contract_for = contract_for
        self._action_id_for = action_id_for
        self._lock = threading.RLock()
        self._captures: dict[str, ActionCapture] = {}
        self._counts: dict[str, int] = {}

    @property
    def captures(self) -> tuple[ActionCapture, ...]:
        """The actions recorded through this capture, in first-call order."""
        with self._lock:
            return tuple(self._captures.values())

    def start(self, tool_name: str, arguments: Any, *, framework: str,
              call_id: str | None = None, agent_name: str | None = None) -> PendingCall | None:
        """Register (or reuse) the call's action and dispatch one attempt.

        Returns ``None`` when ``contract_for`` leaves the call unrecorded.
        """
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise RecorderError("tool_name must be a nonempty string")
        with self._lock:
            call = ToolCall(tool_name=tool_name, arguments=_arguments(arguments),
                            call_id=call_id if isinstance(call_id, str) and call_id else None,
                            started_at_ms=self.recorder.now(), framework=framework,
                            agent_name=agent_name if isinstance(agent_name, str) else None)
            contract = self._contract_for(call)
            if contract is None:
                return None
            if not isinstance(contract, OutcomeContract):
                raise ConsequaTypeError("contract_for must return an OutcomeContract or None")
            if self._action_id_for is not None:
                action_id = self._action_id_for(call)
            elif call.call_id is not None:
                action_id = call.call_id
            else:
                self._counts[tool_name] = self._counts.get(tool_name, 0) + 1
                action_id = f"{tool_name}-{self._counts[tool_name]}"
            capture = self._captures.get(action_id)
            if capture is None:
                registered = {item.action_id for item in self.recorder.actions}
                if action_id in registered:
                    capture = self.recorder.capture_for(action_id)
                else:
                    capture = self.recorder.register(action_id, tool_name, call.arguments,
                                                     contract=contract,
                                                     at_ms=call.started_at_ms)
                self._captures[action_id] = capture
            data = {"tool": tool_name, "framework": framework}
            if call.call_id is not None:
                data["call_id"] = call.call_id
            if call.agent_name is not None:
                data["agent"] = call.agent_name
            attempt = capture.dispatch(at_ms=call.started_at_ms, data=data)
            return PendingCall(capture, attempt, call)

    def finish(self, pending: PendingCall, status: str | ResponseStatus, *,
               result: Any = None, exception: str | None = None) -> None:
        """Record what the framework returned for a dispatched attempt."""
        if not isinstance(pending, PendingCall):
            raise ConsequaTypeError("finish requires the PendingCall that start returned")
        payload = {} if result is None else _result_payload(result)
        if exception is not None:
            payload = {**payload, "exception": exception}
        with self._lock:
            pending.capture.response(pending.attempt_id, status,
                                     provider_request_id=pending.call.call_id, result=payload)


def classify_exception(error: BaseException) -> ResponseStatus:
    """``timeout`` for ``TimeoutError`` (including asyncio's), ``error`` otherwise."""
    return ResponseStatus.TIMEOUT if isinstance(error, TimeoutError) else ResponseStatus.ERROR


__all__ = ["PendingCall", "ToolCall", "ToolCallCapture", "classify_exception"]
