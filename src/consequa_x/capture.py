"""Record consequential actions as they happen and build a validated trace.

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

from .errors import ConsequaTypeError, RecorderError
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
    TimeBase,
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
        raise RecorderError(f"{label} must be a nonempty string")
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
    """One in-flight tool attempt inside ``attempt()``.

    Set ``result`` to keep a JSON payload with the response, ``status`` to
    report an error the tool returned without raising,
    ``provider_request_id`` when the provider supplies one, and ``at_ms`` to
    give the response an explicit time instead of the recorder's clock.
    """

    def __init__(self, attempt_id: str, action_id: str) -> None:
        self.attempt_id = attempt_id
        self.action_id = action_id
        self.status: str | ResponseStatus | None = None
        self.result: dict[str, Any] = {}
        self.provider_request_id: str | None = None
        self.at_ms: int | None = None
        self.response: ToolResponse | None = None


class ActionCapture:
    """Capture calls for one registered action; returned by ``TraceRecorder.register``.

    Every record made through this handle names its action, so several actions
    can be captured in one trace without mixing their attempts, assessments or
    verifications.
    """

    def __init__(self, recorder: TraceRecorder, action: Action, intent_id: str) -> None:
        self._recorder = recorder
        self.action = action
        self._intent_id = intent_id
        self._attempts = 0
        self._response_event_ids: list[str] = []

    @property
    def action_id(self) -> str:
        return self.action.action_id

    def dispatch(self, *, attempt_id: str | None = None, at_ms: int | None = None,
                 data: dict[str, Any] | None = None) -> str:
        """Record one dispatched attempt of this action and return its attempt identity."""
        recorder = self._recorder
        extra = dict(data or {})
        if _RESERVED_DISPATCH_KEYS & extra.keys():
            raise RecorderError("dispatch data cannot override action_id or attempt_id")
        if attempt_id is None:
            attempt_id = f"{self.action_id}:attempt-{self._attempts + 1}"
        _identifier(attempt_id, "attempt_id")
        if attempt_id in recorder._attempts:
            raise RecorderError(f"attempt is already dispatched: {attempt_id!r}")
        event_id = recorder._add_event(Event(
            id=recorder._new_event_id("dispatch", None), type=EventType.ACTION_DISPATCH,
            time_ms=recorder._time(at_ms), actor=self.action.actor, parent_ids=(self._intent_id,),
            data={**extra, "action_id": self.action_id, "attempt_id": attempt_id},
        ))
        self._attempts += 1
        recorder._attempts[attempt_id] = (self, event_id)
        return attempt_id

    def response(self, attempt_id: str, status: str | ResponseStatus, *,
                 at_ms: int | None = None, provider_request_id: str | None = None,
                 result: dict[str, Any] | None = None) -> ToolResponse:
        """Record what the tool returned for an attempt: success, error or timeout."""
        owner = self._recorder._attempts.get(attempt_id)
        if owner is None:
            raise RecorderError(f"response refers to an undispatched attempt: {attempt_id!r}")
        if owner[0] is not self:
            raise RecorderError(f"attempt {attempt_id!r} belongs to another action")
        recorder = self._recorder
        record = ToolResponse(
            attempt_id=attempt_id, action_id=self.action_id, status=ResponseStatus(status),
            time_ms=recorder._time(at_ms),
            provider_request_id=provider_request_id if provider_request_id is not None else attempt_id,
            result=dict(result or {}),
        )
        event_id = recorder._add_event(Event(
            id=recorder._new_event_id("response", None), type=EventType.TOOL_RESPONSE,
            time_ms=record.time_ms, parent_ids=(owner[1],), data=record.to_dict(),
        ))
        recorder._responses.append(record)
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
        tool's effect happened; that is what readback is for. The block may
        ``await``: the context manager itself is synchronous.
        """
        handle = Attempt(self.dispatch(attempt_id=attempt_id, at_ms=at_ms, data=data),
                         self.action_id)
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
            raise ConsequaTypeError("asynchronous tools are not supported here; use attempt() "
                                    "around the awaited call")
        name = getattr(tool, "__name__", type(tool).__name__)
        with self.attempt(data={"tool": name}) as handle:
            value = tool(*args, **kwargs)
            handle.result = _result_payload(value)
        return value

    def assessment(self, status: str | AssessmentStatus, *, at_ms: int | None = None,
                   rationale: str = "", evidence: tuple[str, ...] | None = None,
                   assessment_id: str | None = None) -> AgentAssessment:
        """Record what the agent reported about this action's outcome.

        An action may have several assessments, for example before and after a
        retry. ``evidence`` names the events the agent based its report on; it
        defaults to this action's recorded tool responses. Use ``"unknown"``
        when the agent made no explicit claim. This is the agent's claim, not
        verification.
        """
        recorder = self._recorder
        evidence = tuple(self._response_event_ids if evidence is None else evidence)
        unknown = [item for item in evidence if item not in recorder._event_ids]
        if unknown:
            raise RecorderError(f"assessment evidence refers to unrecorded events: {unknown}")
        event_id = recorder._new_event_id("assessment", None)
        if assessment_id is None:
            assessment_id = event_id
        _identifier(assessment_id, "assessment_id")
        if assessment_id in recorder._assessment_ids:
            raise RecorderError(f"assessment_id is already recorded: {assessment_id!r}")
        record = AgentAssessment(
            assessment_id=assessment_id, action_id=self.action_id, status=AssessmentStatus(status),
            time_ms=recorder._time(at_ms), evidence_event_ids=evidence, rationale=rationale,
        )
        recorder._add_event(Event(
            id=event_id, type=EventType.AGENT_ASSESSMENT, time_ms=record.time_ms,
            actor=self.action.actor, parent_ids=evidence, data=record.to_dict(),
        ))
        recorder._assessments.append(record)
        recorder._assessment_ids.add(assessment_id)
        return record

    def verify(self, observation: Observation, *,
               verifier: Verifier | None = None) -> VerificationResult:
        """Verify a readback for this action and keep the receipt.

        Earlier receipts are retained; a later readback can resolve an earlier
        ``unknown`` without rewriting it.
        """
        recorder = self._recorder
        recorded = recorder.observe(observation)
        receipt = _verify(self.action, recorded, verifier=verifier)
        recorder._verifications.append(receipt)
        return receipt


class TraceRecorder:
    """Capture the history of one run, with one or more consequential actions.

    Each method takes an optional ``at_ms``: an explicit nonnegative integer
    time in milliseconds. Without it, the recorder asks its ``clock``. By
    default that is wall-clock time in milliseconds since the Unix epoch, and the
    trace's ``time_base`` is ``unix_ms``. A custom ``clock`` (or
    ``time_base="relative_ms"`` without one) records ``relative_ms`` times;
    pass ``time_base`` explicitly if a custom clock returns Unix milliseconds.

    Typical order: optional ``context`` and ``decision`` events; ``register``
    each action with its outcome contract before dispatching it; then, through
    the returned ``ActionCapture``, its attempts, the agent's assessments and
    the verification of captured readback. While exactly one action is
    registered, the same calls can be made on the recorder itself. Recording a
    response or a success assessment establishes nothing about the outcome.
    """

    def __init__(self, trace_id: str, *, actor: str,
                 clock: Callable[[], int] | None = None,
                 time_base: str | TimeBase | None = None) -> None:
        self.trace_id = _identifier(trace_id, "trace_id")
        self.actor = _identifier(actor, "actor")
        if clock is not None and not callable(clock):
            raise ConsequaTypeError("clock must be callable and return integer milliseconds")
        if time_base is not None:
            try:
                time_base = TimeBase(time_base)
            except ValueError:
                raise RecorderError("time_base must be 'unix_ms' or 'relative_ms'") from None
        if clock is None and time_base in (None, TimeBase.UNIX_MS):
            self.time_base = TimeBase.UNIX_MS
            self._clock = lambda: time.time_ns() // 1_000_000
        elif clock is None:
            start = time.monotonic_ns()
            self.time_base = TimeBase.RELATIVE_MS
            self._clock = lambda: (time.monotonic_ns() - start) // 1_000_000
        else:
            self.time_base = time_base or TimeBase.RELATIVE_MS
            self._clock = clock
        self._events: list[Event] = []
        self._event_ids: set[str] = set()
        self._counters: dict[str, int] = {}
        self._responses: list[ToolResponse] = []
        self._assessments: list[AgentAssessment] = []
        self._assessment_ids: set[str] = set()
        self._observations: list[Observation] = []
        self._verifications: list[VerificationResult] = []
        self._captures: dict[str, ActionCapture] = {}
        self._contract_ids: set[str] = set()
        self._attempts: dict[str, tuple[ActionCapture, str]] = {}
        self._last_decision_id: str | None = None

    @property
    def actions(self) -> tuple[Action, ...]:
        """The registered actions, in registration order."""
        return tuple(capture.action for capture in self._captures.values())

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
            raise RecorderError("times must be nonnegative integer milliseconds")
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
            raise RecorderError(f"event_id is already recorded: {event_id!r}")
        return event_id

    def _add_event(self, event: Event) -> str:
        self._events.append(event)
        self._event_ids.add(event.id)
        return event.id

    def _sole(self) -> ActionCapture:
        if not self._captures:
            raise RecorderError("register the action and its outcome contract first")
        if len(self._captures) > 1:
            raise RecorderError("several actions are registered; use the ActionCapture that "
                                "register() returned, or capture_for(action_id)")
        return next(iter(self._captures.values()))

    def capture_for(self, action_id: str) -> ActionCapture:
        """The capture handle of a registered action."""
        try:
            return self._captures[action_id]
        except KeyError:
            raise RecorderError(f"no registered action {action_id!r}") from None

    def context(self, kind: str | EventType, data: dict[str, Any] | None = None, *,
                at_ms: int | None = None, event_id: str | None = None) -> str:
        """Record context the agent saw: user input, instruction, retrieval or memory."""
        event_type = EventType(kind)
        if event_type not in _CONTEXT_TYPES:
            raise RecorderError("context kind must be user_input, system_instruction, "
                                "retrieval or memory_read")
        identifier = self._new_event_id("context", event_id)
        return self._add_event(Event(id=identifier, type=event_type, time_ms=self._time(at_ms),
                                     data=dict(data or {})))

    def decision(self, data: dict[str, Any] | None = None, *, inputs: tuple[str, ...] = (),
                 at_ms: int | None = None, event_id: str | None = None) -> str:
        """Record the agent's decision; ``inputs`` declares the context it used."""
        inputs = tuple(inputs)
        unknown = [item for item in inputs if item not in self._event_ids]
        if unknown:
            raise RecorderError(f"decision inputs refer to unrecorded events: {unknown}")
        identifier = self._new_event_id("decision", event_id)
        self._last_decision_id = self._add_event(Event(
            id=identifier, type=EventType.AGENT_DECISION, time_ms=self._time(at_ms),
            actor=self.actor, parent_ids=inputs, data=dict(data or {}),
        ))
        return identifier

    def register(self, action_id: str, name: str, arguments: dict[str, Any], *,
                 contract: OutcomeContract, at_ms: int | None = None,
                 idempotency_key: str | None = None, decision: str | None = None,
                 actor: str | None = None) -> ActionCapture:
        """Register an action and its outcome contract before dispatching it.

        Returns the action's ``ActionCapture``. The intent event depends on
        ``decision`` (an event ID), or on the most recent recorded decision.
        ``actor`` defaults to the recorder's actor.
        """
        _identifier(action_id, "action_id")
        if action_id in self._captures:
            raise RecorderError(f"action is already registered: {action_id!r}")
        if not isinstance(contract, OutcomeContract):
            raise ConsequaTypeError("contract must be an OutcomeContract")
        if contract.contract_id in self._contract_ids:
            raise RecorderError(f"contract_id is already used by another action: "
                                f"{contract.contract_id!r}")
        if decision is not None and decision not in self._event_ids:
            raise RecorderError(f"decision refers to an unrecorded event: {decision!r}")
        parent = decision or self._last_decision_id
        registered = self._time(at_ms)
        action = Action(action_id=action_id, actor=actor or self.actor, name=name,
                        arguments=arguments, registered_at_ms=registered, contract=contract,
                        idempotency_key=idempotency_key)
        intent_id = self._add_event(Event(
            id=self._new_event_id("intent", None), type=EventType.ACTION_INTENT,
            time_ms=registered, actor=action.actor, parent_ids=(parent,) if parent else (),
            data={"action_id": action.action_id, "arguments": action.arguments},
        ))
        capture = ActionCapture(self, action, intent_id)
        self._captures[action_id] = capture
        self._contract_ids.add(contract.contract_id)
        return capture

    # While exactly one action is registered, these delegate to its ActionCapture.

    def dispatch(self, *, attempt_id: str | None = None, at_ms: int | None = None,
                 data: dict[str, Any] | None = None) -> str:
        """Record one dispatched attempt of the only registered action."""
        return self._sole().dispatch(attempt_id=attempt_id, at_ms=at_ms, data=data)

    def response(self, attempt_id: str, status: str | ResponseStatus, *,
                 at_ms: int | None = None, provider_request_id: str | None = None,
                 result: dict[str, Any] | None = None) -> ToolResponse:
        """Record the response to a dispatched attempt of any registered action."""
        owner = self._attempts.get(attempt_id)
        if owner is None:
            raise RecorderError(f"response refers to an undispatched attempt: {attempt_id!r}")
        return owner[0].response(attempt_id, status, at_ms=at_ms,
                                 provider_request_id=provider_request_id, result=result)

    def attempt(self, *, attempt_id: str | None = None, data: dict[str, Any] | None = None,
                at_ms: int | None = None,
                classify: Callable[[Exception], str | ResponseStatus] | None = None,
                ):
        """``ActionCapture.attempt`` for the only registered action."""
        return self._sole().attempt(attempt_id=attempt_id, data=data, at_ms=at_ms,
                                    classify=classify)

    def call(self, tool: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """``ActionCapture.call`` for the only registered action."""
        return self._sole().call(tool, *args, **kwargs)

    def assessment(self, status: str | AssessmentStatus, *, at_ms: int | None = None,
                   rationale: str = "", evidence: tuple[str, ...] | None = None,
                   assessment_id: str | None = None) -> AgentAssessment:
        """``ActionCapture.assessment`` for the only registered action."""
        return self._sole().assessment(status, at_ms=at_ms, rationale=rationale,
                                       evidence=evidence, assessment_id=assessment_id)

    def verify(self, observation: Observation, *,
               verifier: Verifier | None = None) -> VerificationResult:
        """``ActionCapture.verify`` for the only registered action."""
        return self._sole().verify(observation, verifier=verifier)

    def observe(self, observation: Observation) -> Observation:
        """Retain an independently captured readback observation."""
        if not isinstance(observation, Observation):
            raise ConsequaTypeError("observe requires an Observation")
        for existing in self._observations:
            if existing.observation_id == observation.observation_id:
                if existing == observation:
                    return existing
                raise RecorderError("a different observation with this observation_id is recorded")
        self._observations.append(observation)
        return observation

    def trace(self) -> Trace:
        """Return the validated trace captured so far."""
        if not self._captures:
            raise RecorderError("register the action and its outcome contract first")
        return Trace(trace_id=self.trace_id, time_base=self.time_base, actions=self.actions,
                     events=tuple(self._events), responses=tuple(self._responses),
                     assessments=tuple(self._assessments),
                     observations=tuple(self._observations),
                     verifications=tuple(self._verifications))


def _target(recorder: TraceRecorder | ActionCapture, label: str) -> TraceRecorder | ActionCapture:
    if not isinstance(recorder, (TraceRecorder, ActionCapture)):
        raise ConsequaTypeError(f"{label} requires a TraceRecorder or an ActionCapture")
    return recorder


def capture_tool(recorder: TraceRecorder | ActionCapture, *,
                 classify: Callable[[Exception], str | ResponseStatus] | None = None,
                 ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a synchronous tool so every call is one recorded attempt.

    Pass an ``ActionCapture`` to record attempts for that action, or the
    recorder while it has exactly one registered action. The wrapped function
    behaves as before: it returns the tool's result or re-raises its exception
    after the response is recorded.
    """
    target = _target(recorder, "capture_tool")

    def decorate(tool: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(tool):
            raise ConsequaTypeError("asynchronous tools are not supported yet")
        name = getattr(tool, "__name__", type(tool).__name__)

        @functools.wraps(tool)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with target.attempt(data={"tool": name}, classify=classify) as handle:
                value = tool(*args, **kwargs)
                handle.result = _result_payload(value)
            return value

        return wrapped

    return decorate
