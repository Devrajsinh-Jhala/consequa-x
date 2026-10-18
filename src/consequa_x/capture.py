"""Record one consequential action as it happens and build a validated trace.

A recorder arranges records that the application supplies. It never reads a
source or decides an outcome, and it runs a tool only when the application hands
it the function through ``call`` or ``capture_tool``; the application calls it at
each step, and ``trace()`` returns an ordinary :class:`~consequa_x.models.Trace`
validated exactly like a hand-built one. Events are linked the way the
package's own fixtures link them: decision, intent, dispatch, response, then
the agent's reported assessment. Readback still comes from an independent
read-only source that the application captures as an ``Observation``.
"""

from __future__ import annotations

from contextlib import contextmanager
import functools
import inspect
import time
from typing import Any, Callable, Iterator

from .models import _json_copy
from .models import (
    Action,
    AgentAssessment,
    AssessmentStatus,
    Event,
    EventType,
    Observation,
    OutcomeContract,
    ResponseStatus,
    ToolResponse,
    Trace,
    VerificationResult,
)
from .verification import Verifier, verify as _verify


_CONTEXT_TYPES = {
    EventType.USER_INPUT,
    EventType.SYSTEM_INSTRUCTION,
    EventType.RETRIEVAL,
    EventType.MEMORY_READ,
}
_RESERVED_DISPATCH_KEYS = {"action_id", "attempt_id"}


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _default_status(error: Exception) -> str:
    # asyncio, socket and concurrent.futures timeouts are TimeoutError since 3.11.
    return "timeout" if isinstance(error, TimeoutError) else "error"


def _result_payload(value: Any) -> dict[str, Any]:
    """Keep a JSON object as is, wrap other JSON values, and name anything else."""
    try:
        copied = _json_copy(value, "result")
    except (TypeError, ValueError):
        return {"type": type(value).__name__}
    return copied if type(copied) is dict else {"value": copied}


class Attempt:
    """One in-flight tool attempt inside ``TraceRecorder.attempt``.

    Set ``result`` to keep a JSON payload with the response, ``status`` to
    report an error the tool returned without raising,
    ``provider_request_id`` when the provider supplies one, and ``at_ms`` to
    give the response an explicit time instead of the recorder's clock.
    """

    def __init__(self, attempt_id: str) -> None:
        self.attempt_id = attempt_id
        self.status: str | ResponseStatus | None = None
        self.result: dict[str, Any] = {}
        self.provider_request_id: str | None = None
        self.at_ms: int | None = None
        self.response: ToolResponse | None = None


class TraceRecorder:
    """Capture the history of one registered action, step by step.

    Each method takes an optional ``at_ms``: an explicit nonnegative integer
    time in milliseconds. Without it, the recorder asks its ``clock``, which
    defaults to milliseconds elapsed since the recorder was created. Pass a
    clock or explicit times when traces must be reproducible.

    Typical order: optional ``context`` and ``decision`` events, ``register``
    (the outcome contract is declared before the action), ``dispatch`` for each
    attempt, ``response`` for each returned or timed-out attempt, the agent's
    ``assessment``, then ``verify`` with a captured readback. Recording a
    response or a success assessment establishes nothing about the outcome.
    """

    def __init__(self, trace_id: str, *, actor: str,
                 clock: Callable[[], int] | None = None) -> None:
        self.trace_id = _identifier(trace_id, "trace_id")
        self.actor = _identifier(actor, "actor")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable and return integer milliseconds")
        start = time.monotonic_ns()
        self._clock = clock or (lambda: (time.monotonic_ns() - start) // 1_000_000)
        self._events: list[Event] = []
        self._event_ids: set[str] = set()
        self._counters: dict[str, int] = {}
        self._responses: list[ToolResponse] = []
        self._observations: list[Observation] = []
        self._verifications: list[VerificationResult] = []
        self._action: Action | None = None
        self._assessment: AgentAssessment | None = None
        self._intent_id: str | None = None
        self._last_decision_id: str | None = None
        self._dispatch_event_ids: dict[str, str] = {}
        self._response_event_ids: list[str] = []

    @property
    def action(self) -> Action | None:
        """The registered action, or ``None`` before ``register``."""
        return self._action

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def now(self) -> int:
        """Current time in this trace's time base, for readback observations.

        Every time in one trace (contract deadline, events, readback
        ``observed_at_ms`` and ``as_of_ms``) must use the same time base.
        """
        return self._time(None)

    def _time(self, at_ms: int | None) -> int:
        value = self._clock() if at_ms is None else at_ms
        if type(value) is not int or value < 0:
            raise ValueError("times must be nonnegative integer milliseconds")
        return value

    def _new_event_id(self, prefix: str, event_id: str | None) -> str:
        if event_id is None:
            while True:
                self._counters[prefix] = self._counters.get(prefix, 0) + 1
                event_id = f"{prefix}-{self._counters[prefix]}"
                if event_id not in self._event_ids:
                    break
        _identifier(event_id, "event_id")
        if event_id in self._event_ids:
            raise ValueError(f"event_id is already recorded: {event_id!r}")
        return event_id

    def _add_event(self, event: Event) -> str:
        self._events.append(event)
        self._event_ids.add(event.id)
        return event.id

    def _require_action(self) -> Action:
        if self._action is None:
            raise ValueError("register the action and its outcome contract first")
        return self._action

    def context(self, kind: str | EventType, data: dict[str, Any] | None = None, *,
                at_ms: int | None = None, event_id: str | None = None) -> str:
        """Record context the agent saw: user input, instruction, retrieval or memory."""
        event_type = EventType(kind)
        if event_type not in _CONTEXT_TYPES:
            raise ValueError("context kind must be user_input, system_instruction, "
                             "retrieval or memory_read")
        identifier = self._new_event_id("context", event_id)
        return self._add_event(Event(identifier, self.trace_id, event_type, self._time(at_ms),
                                     None, (), dict(data or {})))

    def decision(self, data: dict[str, Any] | None = None, *, inputs: tuple[str, ...] = (),
                 at_ms: int | None = None, event_id: str | None = None) -> str:
        """Record the agent's decision; ``inputs`` declares the context it used."""
        inputs = tuple(inputs)
        unknown = [item for item in inputs if item not in self._event_ids]
        if unknown:
            raise ValueError(f"decision inputs refer to unrecorded events: {unknown}")
        identifier = self._new_event_id("decision", event_id)
        self._last_decision_id = self._add_event(Event(
            identifier, self.trace_id, EventType.AGENT_DECISION, self._time(at_ms),
            self.actor, inputs, dict(data or {}),
        ))
        return identifier

    def register(self, action_id: str, name: str, arguments: dict[str, Any], *,
                 contract: OutcomeContract, at_ms: int | None = None,
                 idempotency_key: str | None = None) -> Action:
        """Register the action and its outcome contract before dispatching it.

        The intent event depends on the most recent recorded decision, if any.
        """
        if self._action is not None:
            raise ValueError("a recorder captures exactly one registered action")
        registered = self._time(at_ms)
        action = Action(action_id, self.trace_id, self.actor, name, arguments, registered,
                        contract, idempotency_key)
        parents = (self._last_decision_id,) if self._last_decision_id else ()
        self._intent_id = self._add_event(Event(
            self._new_event_id("intent", None), self.trace_id, EventType.ACTION_INTENT,
            registered, self.actor, parents,
            {"action_id": action.action_id, "arguments": action.arguments},
        ))
        self._action = action
        return action

    def dispatch(self, *, attempt_id: str | None = None, at_ms: int | None = None,
                 data: dict[str, Any] | None = None) -> str:
        """Record one dispatched attempt and return its attempt identity."""
        action = self._require_action()
        extra = dict(data or {})
        if _RESERVED_DISPATCH_KEYS & extra.keys():
            raise ValueError("dispatch data cannot override action_id or attempt_id")
        if attempt_id is None:
            attempt_id = f"{action.action_id}:attempt-{len(self._dispatch_event_ids) + 1}"
        _identifier(attempt_id, "attempt_id")
        if attempt_id in self._dispatch_event_ids:
            raise ValueError(f"attempt is already dispatched: {attempt_id!r}")
        event_id = self._add_event(Event(
            self._new_event_id("dispatch", None), self.trace_id, EventType.ACTION_DISPATCH,
            self._time(at_ms), self.actor, (self._intent_id,),
            {**extra, "action_id": action.action_id, "attempt_id": attempt_id},
        ))
        self._dispatch_event_ids[attempt_id] = event_id
        return attempt_id

    def response(self, attempt_id: str, status: str | ResponseStatus, *,
                 at_ms: int | None = None, provider_request_id: str | None = None,
                 result: dict[str, Any] | None = None) -> ToolResponse:
        """Record what the tool returned for an attempt: success, error or timeout."""
        if attempt_id not in self._dispatch_event_ids:
            raise ValueError(f"response refers to an undispatched attempt: {attempt_id!r}")
        record = ToolResponse(attempt_id, ResponseStatus(status), self._time(at_ms),
                              provider_request_id if provider_request_id is not None else attempt_id,
                              dict(result or {}))
        event_id = self._add_event(Event(
            self._new_event_id("response", None), self.trace_id, EventType.TOOL_RESPONSE,
            record.time_ms, None, (self._dispatch_event_ids[attempt_id],), record.to_dict(),
        ))
        self._responses.append(record)
        self._response_event_ids.append(event_id)
        return record

    @contextmanager
    def attempt(self, *, attempt_id: str | None = None, data: dict[str, Any] | None = None,
                at_ms: int | None = None,
                classify: Callable[[Exception], str | ResponseStatus] | None = None,
                ) -> Iterator[Attempt]:
        """Record the dispatch on entry and the tool's response on exit.

        A normal exit records ``success`` unless the block set ``attempt.status``.
        An exception records ``timeout`` for ``TimeoutError`` and ``error``
        otherwise (or what ``classify`` returns), keeps only the exception's
        type name, and is re-raised. A timeout says nothing about whether the
        tool's effect happened; that is what readback is for.
        """
        handle = Attempt(self.dispatch(attempt_id=attempt_id, at_ms=at_ms, data=data))
        try:
            yield handle
        except Exception as error:
            status = (classify or _default_status)(error)
            handle.response = self.response(
                handle.attempt_id, status, at_ms=handle.at_ms,
                provider_request_id=handle.provider_request_id,
                result={**handle.result, "exception": type(error).__name__},
            )
            raise
        handle.response = self.response(handle.attempt_id, handle.status or "success",
                                        at_ms=handle.at_ms,
                                        provider_request_id=handle.provider_request_id,
                                        result=handle.result)

    def call(self, tool: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """Run ``tool(*args, **kwargs)`` as one recorded attempt and return its result.

        JSON results are kept with the response; other values keep only their
        type name. Use ``attempt`` for custom status, identity or payloads.
        """
        if inspect.iscoroutinefunction(tool):
            raise TypeError("asynchronous tools are not supported yet; use attempt() around "
                            "the awaited call")
        name = getattr(tool, "__name__", type(tool).__name__)
        with self.attempt(data={"tool": name}) as handle:
            value = tool(*args, **kwargs)
            handle.result = _result_payload(value)
        return value

    def assessment(self, status: str | AssessmentStatus, *, at_ms: int | None = None,
                   rationale: str = "", evidence: tuple[str, ...] | None = None) -> AgentAssessment:
        """Record what the agent reported about the outcome.

        ``evidence`` names the events the agent based its report on; it defaults
        to the recorded tool responses. Use ``"unknown"`` when the agent reported
        nothing. This is the agent's claim, not verification.
        """
        self._require_action()
        if self._assessment is not None:
            raise ValueError("the agent's assessment is already recorded")
        evidence = tuple(self._response_event_ids if evidence is None else evidence)
        unknown = [item for item in evidence if item not in self._event_ids]
        if unknown:
            raise ValueError(f"assessment evidence refers to unrecorded events: {unknown}")
        record = AgentAssessment(AssessmentStatus(status), self._time(at_ms), evidence, rationale)
        self._add_event(Event(
            self._new_event_id("assessment", None), self.trace_id, EventType.AGENT_ASSESSMENT,
            record.time_ms, self.actor, evidence, record.to_dict(),
        ))
        self._assessment = record
        return record

    def observe(self, observation: Observation) -> Observation:
        """Retain an independently captured readback observation."""
        if not isinstance(observation, Observation):
            raise TypeError("observe requires an Observation")
        for existing in self._observations:
            if existing.observation_id == observation.observation_id:
                if existing == observation:
                    return existing
                raise ValueError("a different observation with this observation_id is recorded")
        self._observations.append(observation)
        return observation

    def verify(self, observation: Observation, *,
               verifier: Verifier | None = None) -> VerificationResult:
        """Verify a readback with the built-in or a supplied verifier and keep the receipt.

        Earlier receipts are retained; a later readback can resolve an earlier
        ``unknown`` without rewriting it.
        """
        action = self._require_action()
        recorded = self.observe(observation)
        receipt = _verify(action, recorded, verifier=verifier)
        self._verifications.append(receipt)
        return receipt

    def trace(self) -> Trace:
        """Return the validated trace captured so far."""
        action = self._require_action()
        if self._assessment is None:
            raise ValueError("record the agent's assessment first; use 'unknown' if it "
                             "reported nothing")
        return Trace(self.trace_id, action, tuple(self._events), tuple(self._responses),
                     self._assessment, tuple(self._observations), tuple(self._verifications))


def capture_tool(recorder: TraceRecorder, *,
                 classify: Callable[[Exception], str | ResponseStatus] | None = None,
                 ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a synchronous tool so every call is one recorded attempt.

    The wrapped function behaves as before: it returns the tool's result or
    re-raises its exception after the response is recorded.
    """
    if not isinstance(recorder, TraceRecorder):
        raise TypeError("capture_tool requires a TraceRecorder")

    def decorate(tool: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(tool):
            raise TypeError("asynchronous tools are not supported yet")
        name = getattr(tool, "__name__", type(tool).__name__)

        @functools.wraps(tool)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with recorder.attempt(data={"tool": name}, classify=classify) as handle:
                value = tool(*args, **kwargs)
                handle.result = _result_payload(value)
            return value

        return wrapped

    return decorate
