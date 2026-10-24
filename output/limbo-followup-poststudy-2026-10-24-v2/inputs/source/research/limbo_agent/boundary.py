"""Prospective public LIMBO runtime view; no upstream imports or task execution.

This is a trusted-code access boundary, not a Python/OS security sandbox. It
copies declared public data and keeps native objects/callbacks in trusted module
state. Hostile Python introspection, monkeypatching and untrusted callbacks are
outside its claim. Domain-specific verification shapes/costs and an unchanged
native-guard integration are still unvalidated (see ``DESIGN.md``).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Callable
from weakref import WeakKeyDictionary


class BoundaryRefusal(ValueError):
    """An input, unsupported public value or prospective work ceiling was refused."""


class PublicRuntimeError(RuntimeError):
    """A delegated API raised; the raw native exception is not a policy input."""


class BoundaryJournalError(RuntimeError):
    """The trusted audit sink failed; execution must stop rather than run unlogged."""


def _copy(value: Any, _ancestors: frozenset[int] = frozenset()) -> Any:
    """Copy plain public values without invoking object hooks or string coercions."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) in (tuple, list, dict):
        if id(value) in _ancestors or len(_ancestors) >= 64:
            raise BoundaryRefusal("Public data cannot be cyclic or more than 64 containers deep")
        _ancestors = _ancestors | {id(value)}
    if type(value) in (tuple, list):
        result = [_copy(item, _ancestors) for item in value]
        return tuple(result) if type(value) is tuple else result
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _copy(item, _ancestors) for key, item in value.items()}
    raise BoundaryRefusal("Public values must be finite plain data; objects are not exposed")


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise BoundaryRefusal(label + " must be a finite nonnegative number")
    return float(value)


def _text(value: Any, label: str) -> str:
    if type(value) is not str:
        raise BoundaryRefusal(label + " must be a string")
    return value


@dataclass(frozen=True)
class BoundaryLimits:
    """Prospective counts of real delegated calls, not native physical effects."""

    execute: int
    verify: int
    wait: int
    total_wait_seconds: float

    def __post_init__(self) -> None:
        for name in ("execute", "verify", "wait"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise BoundaryRefusal(name + " ceiling must be a nonnegative integer")
        _number(self.total_wait_seconds, "total wait ceiling")


class _State:
    def __init__(self, runtime: Any, limits: BoundaryLimits, journal: Callable) -> None:
        # This constructor is trusted runner code. No raw runtime, ToolSpec,
        # Contract, world or callable is returned through the view's API.
        self.execute = runtime.execute
        self.verify = runtime.verify
        self.clock = lambda: runtime.world.clock
        self.advance = runtime.world.advance
        self.limits, self.journal = limits, journal
        self.tools: dict[str, dict[str, Any]] = {}
        self.contracts: dict[str, Any] = {}
        for name, spec in runtime.tools.items():
            name = _text(name, "tool name")
            contract = spec.contract
            flags = {}
            for field in ("write", "idempotent", "destructive", "irreversible"):
                value = getattr(contract, field)
                if type(value) is not bool:
                    raise BoundaryRefusal("Contract flags must be booleans")
                flags[field] = value
            for field in ("batch_field", "compensator"):
                value = getattr(contract, field)
                if value is not None and type(value) is not str:
                    raise BoundaryRefusal("Declared batch/compensator names must be strings or None")
            drift = contract.drift
            if drift is not None and (type(drift) is not tuple or len(drift) != 2
                                      or any(type(item) is not str for item in drift)):
                raise BoundaryRefusal("Declared drift must be a pair of strings or None")
            if type(spec.parameters) is not dict:
                raise BoundaryRefusal("Declared tool parameters must be a plain dictionary")
            self.tools[name] = _copy({
                "name": _text(spec.name, "declared tool name"),
                "domain": _text(spec.domain, "domain"),
                "description": _text(spec.description, "description"),
                "parameters": spec.parameters,
                "explicit_note": _text(spec.explicit_note, "explicit note"),
                "consistency_note": _text(spec.consistency_note, "consistency note"),
                "latency": _number(spec.latency, "declared latency"),
                "contract": {**flags, "batch_field": contract.batch_field,
                             "compensator": contract.compensator, "drift": contract.drift,
                             "has_identity": contract.identity is not None},
            })
            if spec.name != name:
                raise BoundaryRefusal("Tool-map and declared names differ")
            # Keep only declared public metadata evaluators, never handler or
            # verifier callbacks. Purity is a trusted-source requirement.
            self.contracts[name] = (contract.identity, contract.supports_key,
                                    contract.visibility_sla)
        self.counts = {"execute": 0, "verify": 0, "wait": 0}
        self.metadata_calls = {"identity": 0, "supports_key": 0, "visibility_sla": 0}
        self.wait_seconds = 0.0
        self.previous_dispatch_start: float | None = None
        self.sequence = 0
        self.tainted = False

    def emit(self, event: dict[str, Any]) -> None:
        if self.tainted:
            raise BoundaryJournalError("Audit sink previously failed; boundary is closed")
        try:
            self.journal(_copy(event))
        except Exception:
            self.tainted = True
            raise BoundaryJournalError("Trusted audit sink failed; boundary is closed") from None

    def run(self, kind: str, inputs: dict, call: Callable, *, work: bool = False) -> Any:
        start = _number(self.clock(), "virtual clock")
        self.sequence += 1
        seq = self.sequence
        self.emit({"sequence": seq, "operation": kind, "phase": "start",
                   "virtual_start": start, "inputs": _copy(inputs)})
        wall = time.perf_counter()
        dispatched = False
        try:
            if work:
                if self.counts[kind] >= getattr(self.limits, kind):
                    raise BoundaryRefusal(kind + " ceiling exhausted")
                if kind == "wait" and (self.wait_seconds + inputs["seconds"]
                                       > self.limits.total_wait_seconds):
                    raise BoundaryRefusal("Total virtual wait ceiling exhausted")
                self.counts[kind] += 1
                if kind == "wait":
                    self.wait_seconds += inputs["seconds"]
                if kind == "execute":
                    self.previous_dispatch_start = start
            dispatched = work
            result = _copy(call())
            end = _number(self.clock(), "virtual clock")
            if end < start:
                raise BoundaryRefusal("Virtual clock moved backwards")
        except Exception as exc:
            self.emit({"sequence": seq, "operation": kind, "phase": "error",
                       "virtual_start": start, "virtual_end": _number(self.clock(), "virtual clock"),
                       "wall_seconds": time.perf_counter() - wall,
                       "delegated": dispatched, "error_type": type(exc).__name__})
            if isinstance(exc, BoundaryRefusal):
                raise
            raise PublicRuntimeError(kind + " raised " + type(exc).__name__) from None
        self.emit({"sequence": seq, "operation": kind, "phase": "return",
                   "virtual_start": start, "virtual_end": end,
                   "wall_seconds": time.perf_counter() - wall,
                   "delegated": dispatched, "result": result})
        return _copy(result)


_STATES: WeakKeyDictionary = WeakKeyDictionary()


def _validated(state: _State, operation: str, check: Callable) -> Any:
    """Audit malformed attempts without serializing objects, cycles or repr hooks."""
    try:
        return check()
    except BoundaryRefusal as exc:
        reason = str(exc)  # Only this module's fixed validation messages.

        def refuse() -> None:
            raise BoundaryRefusal(reason)

        return state.run(operation + "_input_refused", {
            "reason": reason,
            "full_input_preserved": False,
            "scope": "Malformed data withheld; no native operation was delegated",
        }, refuse)


class PublicRuntimeBoundary:
    """Only explicit public operations; no tools/world/events/attribute forwarding.

    Native ``OutcomeGuard`` cannot take this view unchanged: it directly reads
    ``rt.tools``, ``rt.world`` and event objects. A later reviewed policy adapter
    must use these explicit methods and prove matched guard decisions. This file
    alone is not native execution, replay validation or a package receipt layer.
    """

    __slots__ = ("__weakref__",)

    def __init__(self) -> None:
        raise TypeError("Use bind_public_runtime in the trusted runner")

    def tool_metadata(self) -> dict[str, Any]:
        """Copied schema/contract declarations, excluding all raw callbacks."""
        state = _STATES[self]
        return state.run("tool_metadata", {}, lambda: state.tools)

    def contract(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Compute public payload-dependent identity/key support/visibility values."""
        state = _STATES[self]
        name, args = _validated(state, "contract", lambda: _arguments(name, args))

        def evaluate() -> dict:
            if name not in state.tools:
                raise BoundaryRefusal("No declared public contract for this tool")
            identity, supports_key, visibility_sla = state.contracts[name]
            # Each trusted evaluator receives an independent copy of public args.
            if identity is None:
                ident = None
            else:
                state.metadata_calls["identity"] += 1
                ident = identity(_copy(args))
            if ident is not None and type(ident) is not tuple:
                raise BoundaryRefusal("Declared identity must return a tuple or None")
            state.metadata_calls["supports_key"] += 1
            key = supports_key(_copy(args))
            if type(key) is not bool:
                raise BoundaryRefusal("Declared key support must return a boolean")
            state.metadata_calls["visibility_sla"] += 1
            visibility = _number(visibility_sla(_copy(args)), "visibility SLA")
            return {**_copy(state.tools[name]["contract"]), "identity": _copy(ident),
                    "supports_key": key, "visibility_sla": visibility}

        return state.run("contract", {"name": name, "args": args}, evaluate)

    def execute(self, name: str, args: dict[str, Any], *, source: str = "agent",
                note: str = "") -> dict[str, Any]:
        """Dispatch the real native API once; never synthesize a write or success."""
        state = _STATES[self]
        def validate() -> tuple:
            parsed = _arguments(name, args)
            parsed_source, parsed_note = _text(source, "source"), _text(note, "note")
            if parsed_source not in ("agent", "harness"):
                raise BoundaryRefusal("Only agent/harness dispatch sources are public")
            return *parsed, parsed_source, parsed_note

        name, args, source, note = _validated(state, "execute", validate)

        def dispatch() -> dict:
            result = state.execute(name, _copy(args), source=source, note=note)
            if type(result) is not dict:
                raise BoundaryRefusal("Native observation must be a dictionary")
            return result

        return state.run("execute", {"name": name, "args": args, "source": source,
                                     "note": note}, dispatch, work=True)

    def verify(self, name: str, args: dict[str, Any], t_call: float, *,
               truth: bool = False) -> dict[str, Any]:
        """Return current public status/detail only; no origin/durability assertion."""
        state = _STATES[self]
        parsed, t_call = _validated(state, "verify", lambda: (
            _arguments(name, args), _number(t_call, "previous call time")))
        name, args = parsed

        def check() -> dict:
            if truth is not False:
                raise BoundaryRefusal("Privileged truth verification is forbidden")
            result = state.verify(name, _copy(args), t_call, truth=False)
            if type(result.status) is not str or type(result.detail) is not dict:
                raise BoundaryRefusal("Verification must expose string status and dict detail")
            # Preserve unknown, partial and future native statuses verbatim.
            return {"status": result.status, "detail": _copy(result.detail)}

        # Rejection is audited, and consumes no native-verify call allowance.
        if truth is not False:
            return state.run("verify_refused", {"name": name, "args": args,
                                               "t_call": t_call, "truth": "refused"}, check)
        return state.run("verify", {"name": name, "args": args, "t_call": t_call,
                                    "truth": False}, check, work=True)

    def wait(self, seconds: float) -> dict[str, float]:
        """Delegate world.advance; it may execute delayed effects in the native world."""
        state = _STATES[self]
        seconds = _validated(state, "wait", lambda: _number(seconds, "virtual wait"))

        def advance() -> dict:
            state.advance(seconds)
            return {"requested_seconds": seconds,
                    "clock_after": _number(state.clock(), "virtual clock")}

        return state.run("wait", {"seconds": seconds}, advance, work=True)

    @property
    def clock(self) -> float:
        state = _STATES[self]
        return state.run("clock", {}, lambda: _number(state.clock(), "virtual clock"))

    @property
    def last_dispatch_start(self) -> float | None:
        state = _STATES[self]
        return state.run("last_dispatch_start", {}, lambda: state.previous_dispatch_start)

    def accounting(self) -> dict[str, Any]:
        """Counts include delegated calls that raised; they are not effect counts/costs."""
        state = _STATES[self]
        return state.run("accounting", {}, lambda: {
            "delegated_calls": state.counts,
            "metadata_callback_calls": state.metadata_calls,
            "requested_virtual_wait_seconds": state.wait_seconds,
            "native_physical_effect_count": None,
            "verification_cost": None,
        })


def _arguments(name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name = _text(name, "tool name")
    if type(args) is not dict:
        raise BoundaryRefusal("Tool arguments must be a plain dictionary")
    return name, _copy(args)


def bind_public_runtime(runtime: Any, *, limits: BoundaryLimits,
                        journal: Callable[[dict[str, Any]], None]) -> PublicRuntimeBoundary:
    """Trusted construction only; neither native runtime nor journal goes to policy.

    The caller retains the complete evaluator runtime/journal independently.
    Only the declared ToolSpec/Contract fields and execute/verify/world-clock/
    advance capabilities are read here. No target, ledger, fault/event attribute,
    handler or verifier callback is inspected. A single serial caller is required.
    """
    if type(limits) is not BoundaryLimits or not callable(journal):
        raise BoundaryRefusal("Explicit limits and a trusted audit sink are required")
    state = _State(runtime, limits, journal)
    view = object.__new__(PublicRuntimeBoundary)
    _STATES[view] = state
    state.emit({"sequence": 0, "operation": "bind", "phase": "return",
                "metadata": state.tools,
                "limits": {"execute": limits.execute, "verify": limits.verify,
                           "wait": limits.wait, "total_wait_seconds": limits.total_wait_seconds},
                "scope": "current public data only; origin and durable settlement unproven"})
    return view
