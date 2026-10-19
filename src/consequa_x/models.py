"""Versioned records for the public trace and independently observed evidence.

Records are frozen dataclasses. JSON payloads are validated and copied on input
and made deeply read-only: objects become ``FrozenDict`` and arrays become
``FrozenList``. They still compare equal to, and serialize like, ordinary dicts
and lists, but any attempt to change them raises ``ConsequaTypeError``; create a
new record instead. ``to_dict`` returns ordinary, mutable copies. External
observations are distinct from evaluator-only simulator truth, which is
deliberately absent from this schema.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from enum import Enum
from functools import lru_cache
import json
import math
import types
from typing import Any, get_args, get_origin, get_type_hints

from .errors import ConsequaTypeError, SchemaVersionError, ValidationError


SCHEMA_VERSION = "0.1"


class EventType(str, Enum):
    USER_INPUT = "user_input"
    SYSTEM_INSTRUCTION = "system_instruction"
    RETRIEVAL = "retrieval"
    MEMORY_READ = "memory_read"
    AGENT_DECISION = "agent_decision"
    ACTION_INTENT = "action_intent"
    ACTION_DISPATCH = "action_dispatch"
    TOOL_RESPONSE = "tool_response"
    AGENT_ASSESSMENT = "agent_assessment"
    EXTERNAL_OBSERVATION = "external_observation"
    VERIFICATION = "verification"
    EXTERNAL_EFFECT = "external_effect"


class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class AssessmentStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


class OriginStatus(str, Enum):
    CONFIRMED = "confirmed"
    OTHER_ACTOR = "other_actor"
    UNKNOWN = "unknown"


def _string(value: Any, label: str, *, nonempty: bool = True) -> None:
    if not isinstance(value, str):
        raise ConsequaTypeError(f"{label} must be a string")
    if nonempty and not value.strip():
        raise ValidationError(f"{label} must not be empty")


def _time(value: Any, label: str) -> None:
    if type(value) is not int:
        raise ConsequaTypeError(f"{label} must be an integer, not a boolean")
    if value < 0:
        raise ValidationError(f"{label} must be nonnegative")


def _enum(value: Any, enum: type[Enum], label: str) -> None:
    if not isinstance(value, enum):
        raise ConsequaTypeError(f"{label} must be a {enum.__name__}")


def _string_tuple(value: Any, label: str) -> None:
    if type(value) is not tuple:
        raise ConsequaTypeError(f"{label} must be a tuple of strings")
    for index, item in enumerate(value):
        _string(item, f"{label}[{index}]")
    if len(set(value)) != len(value):
        raise ValidationError(f"{label} must not contain duplicate identifiers")


def _records(value: Any, record_type: type, label: str) -> None:
    if type(value) is not tuple:
        raise ConsequaTypeError(f"{label} must be a tuple of {record_type.__name__} records")
    for index, item in enumerate(value):
        if not isinstance(item, record_type):
            raise ConsequaTypeError(f"{label}[{index}] must be a {record_type.__name__}")


def _read_only(self: Any, *args: Any, **kwargs: Any) -> Any:
    raise ConsequaTypeError("captured payloads are read-only; create a new record instead")


class FrozenDict(dict):
    """A captured JSON object: it reads like a ``dict`` but cannot be changed."""

    __slots__ = ()
    __setitem__ = __delitem__ = __ior__ = _read_only
    clear = pop = popitem = setdefault = update = _read_only

    def __copy__(self) -> FrozenDict:
        return self

    def __deepcopy__(self, memo: dict) -> FrozenDict:
        return self

    def __reduce__(self) -> tuple:
        return (FrozenDict, (dict(self),))


class FrozenList(list):
    """A captured JSON array: it reads like a ``list`` but cannot be changed."""

    __slots__ = ()
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _read_only
    append = extend = insert = remove = pop = clear = sort = reverse = _read_only

    def __copy__(self) -> FrozenList:
        return self

    def __deepcopy__(self, memo: dict) -> FrozenList:
        return self

    def __reduce__(self) -> tuple:
        return (FrozenList, (list(self),))


_OBJECT_TYPES = (dict, FrozenDict)
_ARRAY_TYPES = (list, FrozenList)


def _json_copy(value: Any, path: str = "value", active: set[int] | None = None, *,
               frozen: bool = False) -> Any:
    """Validate strict JSON data, reject cycles, and return an isolated copy.

    With ``frozen`` the copy is deeply read-only (``FrozenDict``/``FrozenList``);
    otherwise it is made of ordinary dicts and lists.
    """
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValidationError(f"{path} must contain only finite JSON numbers")
        return value
    if type(value) not in _OBJECT_TYPES + _ARRAY_TYPES:
        raise ConsequaTypeError(f"{path} contains a non-JSON value: {type(value).__name__}")
    active = set() if active is None else active
    if id(value) in active:
        raise ValidationError(f"{path} contains a circular reference")
    active.add(id(value))
    try:
        if type(value) in _ARRAY_TYPES:
            items = [_json_copy(item, f"{path}[{index}]", active, frozen=frozen)
                     for index, item in enumerate(value)]
            return FrozenList(items) if frozen else items
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ConsequaTypeError(f"{path} keys must be strings")
            result[key] = _json_copy(item, f"{path}.{key}", active, frozen=frozen)
        return FrozenDict(result) if frozen else result
    finally:
        active.remove(id(value))


def thaw(value: Any) -> Any:
    """Return an ordinary, mutable deep copy of a captured JSON payload.

    ``copy.deepcopy`` of a read-only payload returns the same read-only value,
    as for any immutable object; use ``thaw`` to edit a copy.
    """
    return _json_copy(value, "value")


def _payload(record: Any, name: str) -> None:
    value = getattr(record, name)
    if type(value) not in _OBJECT_TYPES:
        raise ConsequaTypeError(f"{name} must be a JSON object")
    object.__setattr__(record, name, _json_copy(value, name, frozen=True))


class _Record:
    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)


@dataclass(frozen=True)
class Event(_Record):
    id: str
    trace_id: str
    type: EventType
    time_ms: int
    actor: str | None = None
    parent_ids: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _string(self.id, "id")
        _string(self.trace_id, "trace_id")
        _enum(self.type, EventType, "type")
        _time(self.time_ms, "time_ms")
        if self.actor is not None:
            _string(self.actor, "actor")
        _string_tuple(self.parent_ids, "parent_ids")
        if self.id in self.parent_ids:
            raise ValidationError("an event cannot be its own parent")
        _payload(self, "data")


@dataclass(frozen=True)
class OutcomeContract(_Record):
    contract_id: str
    predicate: str
    expected: dict[str, Any]
    deadline_ms: int
    exact_count: int | None = 1
    stability_ms: int = 0

    def __post_init__(self) -> None:
        _string(self.contract_id, "contract_id")
        _string(self.predicate, "predicate")
        _payload(self, "expected")
        _time(self.deadline_ms, "deadline_ms")
        _time(self.stability_ms, "stability_ms")
        if self.exact_count is not None:
            _time(self.exact_count, "exact_count")

    @property
    def horizon_ms(self) -> int:
        return self.deadline_ms + self.stability_ms


@dataclass(frozen=True)
class Action(_Record):
    action_id: str
    trace_id: str
    actor: str
    name: str
    arguments: dict[str, Any]
    registered_at_ms: int
    contract: OutcomeContract
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        for name in ("action_id", "trace_id", "actor", "name"):
            _string(getattr(self, name), name)
        _payload(self, "arguments")
        _time(self.registered_at_ms, "registered_at_ms")
        if not isinstance(self.contract, OutcomeContract):
            raise ConsequaTypeError("contract must be an OutcomeContract")
        if self.idempotency_key is not None:
            _string(self.idempotency_key, "idempotency_key")


@dataclass(frozen=True)
class ToolResponse(_Record):
    attempt_id: str
    status: ResponseStatus
    time_ms: int
    provider_request_id: str
    result: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _string(self.attempt_id, "attempt_id")
        _enum(self.status, ResponseStatus, "status")
        _time(self.time_ms, "time_ms")
        _string(self.provider_request_id, "provider_request_id")
        _payload(self, "result")


@dataclass(frozen=True)
class AgentAssessment(_Record):
    status: AssessmentStatus
    time_ms: int
    evidence_event_ids: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        _enum(self.status, AssessmentStatus, "status")
        _time(self.time_ms, "time_ms")
        _string_tuple(self.evidence_event_ids, "evidence_event_ids")
        _string(self.rationale, "rationale", nonempty=False)


@dataclass(frozen=True)
class Observation(_Record):
    observation_id: str
    source: str
    observed_at_ms: int
    as_of_ms: int
    scope: dict[str, Any]
    records: tuple[dict[str, Any], ...] = ()
    complete: bool = True
    available: bool = True

    def __post_init__(self) -> None:
        _string(self.observation_id, "observation_id")
        _string(self.source, "source")
        _time(self.observed_at_ms, "observed_at_ms")
        _time(self.as_of_ms, "as_of_ms")
        if self.as_of_ms > self.observed_at_ms:
            raise ValidationError("as_of_ms must not be later than observed_at_ms")
        _payload(self, "scope")
        if type(self.records) is not tuple:
            raise ConsequaTypeError("records must be a tuple of JSON objects")
        isolated = []
        for index, record in enumerate(self.records):
            if type(record) not in _OBJECT_TYPES:
                raise ConsequaTypeError(f"records[{index}] must be a JSON object")
            isolated.append(_json_copy(record, f"records[{index}]", frozen=True))
        object.__setattr__(self, "records", tuple(isolated))
        for name in ("complete", "available"):
            if type(getattr(self, name)) is not bool:
                raise ConsequaTypeError(f"{name} must be a boolean")


@dataclass(frozen=True)
class Evidence(_Record):
    observation_id: str
    source: str
    as_of_ms: int
    details: dict[str, Any]

    def __post_init__(self) -> None:
        _string(self.observation_id, "observation_id")
        _string(self.source, "source")
        _time(self.as_of_ms, "as_of_ms")
        _payload(self, "details")


@dataclass(frozen=True)
class VerificationResult(_Record):
    contract_id: str
    status: VerificationStatus
    observed_at_ms: int
    evidence: tuple[Evidence, ...]
    origin: OriginStatus = OriginStatus.UNKNOWN
    effect_ids: tuple[str, ...] = ()
    attributable_effect_ids: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        _string(self.contract_id, "contract_id")
        _enum(self.status, VerificationStatus, "status")
        _time(self.observed_at_ms, "observed_at_ms")
        _records(self.evidence, Evidence, "evidence")
        if not self.evidence:
            raise ValidationError("verification evidence must not be empty")
        _enum(self.origin, OriginStatus, "origin")
        _string_tuple(self.effect_ids, "effect_ids")
        _string_tuple(self.attributable_effect_ids, "attributable_effect_ids")
        if not set(self.attributable_effect_ids).issubset(self.effect_ids):
            raise ValidationError("attributable_effect_ids must be a subset of effect_ids")
        if self.origin is OriginStatus.CONFIRMED and not self.attributable_effect_ids:
            raise ValidationError("confirmed origin requires attributable_effect_ids")
        if self.origin is not OriginStatus.CONFIRMED and self.attributable_effect_ids:
            raise ValidationError("attributable_effect_ids require confirmed origin")
        if self.origin is OriginStatus.OTHER_ACTOR and not self.effect_ids:
            raise ValidationError("other_actor origin requires observed effect_ids")
        if any(item.as_of_ms > self.observed_at_ms for item in self.evidence):
            raise ValidationError("evidence.as_of_ms must not be later than verification observed_at_ms")
        _string(self.reason, "reason", nonempty=False)


@dataclass(frozen=True)
class Trace(_Record):
    trace_id: str
    action: Action
    events: tuple[Event, ...]
    responses: tuple[ToolResponse, ...]
    assessment: AgentAssessment
    observations: tuple[Observation, ...] = ()
    verifications: tuple[VerificationResult, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _string(self.trace_id, "trace_id")
        if self.schema_version != SCHEMA_VERSION:
            raise SchemaVersionError(f"unsupported schema_version: {self.schema_version!r}")
        if not isinstance(self.action, Action):
            raise ConsequaTypeError("action must be an Action")
        if self.action.trace_id != self.trace_id:
            raise ValidationError("action.trace_id must equal trace_id")
        if not isinstance(self.assessment, AgentAssessment):
            raise ConsequaTypeError("assessment must be an AgentAssessment")
        for name, record_type in (
            ("events", Event),
            ("responses", ToolResponse),
            ("observations", Observation),
            ("verifications", VerificationResult),
        ):
            _records(getattr(self, name), record_type, name)
        for event in self.events:
            if event.trace_id != self.trace_id:
                raise ValidationError("every event.trace_id must equal trace_id")
        for name, identity in (
            ("events", "id"),
            ("responses", "attempt_id"),
            ("observations", "observation_id"),
        ):
            identifiers = [getattr(record, identity) for record in getattr(self, name)]
            if len(set(identifiers)) != len(identifiers):
                raise ValidationError(f"{name} must have unique {identity} values")
        events_by_id = {event.id: event for event in self.events}
        for event in self.events:
            missing = set(event.parent_ids) - events_by_id.keys()
            if missing:
                raise ValidationError(f"event.parent_ids refer to missing events: {sorted(missing)}")
        missing = set(self.assessment.evidence_event_ids) - events_by_id.keys()
        if missing:
            raise ValidationError(f"assessment.evidence_event_ids refer to missing events: {sorted(missing)}")
        _validate_event_dag(self.events)
        observations_by_id = {item.observation_id: item for item in self.observations}
        for verification in self.verifications:
            if verification.contract_id != self.action.contract.contract_id:
                raise ValidationError("verification.contract_id must match the action contract")
            for evidence in verification.evidence:
                observation = observations_by_id.get(evidence.observation_id)
                if observation is None:
                    raise ValidationError("verification evidence refers to a missing observation_id")
                if evidence.source != observation.source:
                    raise ValidationError("evidence.source must match its observation source")
                if evidence.as_of_ms != observation.as_of_ms:
                    raise ValidationError("evidence.as_of_ms must match its observation watermark")
                if observation.observed_at_ms > verification.observed_at_ms:
                    raise ValidationError("verification cannot precede its evidence observation")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Trace:
        """Decode strictly: no field coercion or unknown nested record fields."""
        return _decode_record(cls, value, "trace")

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), allow_nan=False, ensure_ascii=True, indent=indent)

    @classmethod
    def from_json(cls, value: str) -> Trace:
        if type(value) is not str:
            raise ConsequaTypeError("trace JSON must be a string")
        try:
            decoded = json.loads(
                value,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except json.JSONDecodeError as error:
            raise ValidationError(f"trace is not valid JSON: {error}") from error
        return cls.from_dict(decoded)


def _validate_event_dag(events: tuple[Event, ...]) -> None:
    """Check dependency cycles iteratively, including long imported traces."""
    remaining = {event.id: len(event.parent_ids) for event in events}
    children: dict[str, list[str]] = {event.id: [] for event in events}
    for event in events:
        for parent_id in event.parent_ids:
            children[parent_id].append(event.id)
    ready = [event_id for event_id, count in remaining.items() if not count]
    visited = 0
    while ready:
        visited += 1
        for child_id in children[ready.pop()]:
            remaining[child_id] -= 1
            if not remaining[child_id]:
                ready.append(child_id)
    if visited != len(events):
        raise ValidationError("event parent dependencies must be acyclic")


def to_dict(value: Any) -> Any:
    """Serialize dataclass instances, enums and containers into JSON-safe data.

    Unlike ``dataclasses.asdict``, this function rejects arbitrary objects and
    non-finite numbers rather than letting them reach a later JSON encoder.
    """
    return _serialize(value, "value", set())


def _serialize(value: Any, path: str, active: set[int]) -> Any:
    if isinstance(value, Enum):
        if type(value.value) is not str:
            raise ConsequaTypeError(f"{path} enum must have a string value")
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        if id(value) in active:
            raise ValidationError(f"{path} contains a circular reference")
        active.add(id(value))
        try:
            return {
                item.name: _serialize(getattr(value, item.name), f"{path}.{item.name}", active)
                for item in fields(value)
            }
        finally:
            active.remove(id(value))
    if type(value) in _OBJECT_TYPES + _ARRAY_TYPES + (tuple,):
        if id(value) in active:
            raise ValidationError(f"{path} contains a circular reference")
        active.add(id(value))
        try:
            if type(value) in _OBJECT_TYPES:
                if any(type(key) is not str for key in value):
                    raise ConsequaTypeError(f"{path} keys must be strings")
                return {
                    key: _serialize(item, f"{path}.{key}", active)
                    for key, item in value.items()
                }
            return [_serialize(item, f"{path}[{index}]", active) for index, item in enumerate(value)]
        finally:
            active.remove(id(value))
    return _json_copy(value, path, active)


@lru_cache(maxsize=64)
def _record_annotations(record_type: type) -> dict:
    """Resolve static schema annotations once; record values are never cached."""
    return get_type_hints(record_type)


def _decode_record(record_type: type, value: Any, path: str) -> Any:
    if type(value) is not dict:
        raise ConsequaTypeError(f"{path} must be a JSON object")
    record_fields = fields(record_type)
    names = {item.name for item in record_fields}
    unknown = set(value) - names
    if unknown:
        raise ValidationError(f"{path} has unknown fields: {sorted(str(key) for key in unknown)}")
    missing = [
        item.name
        for item in record_fields
        if item.name not in value and item.default is MISSING and item.default_factory is MISSING
    ]
    if missing:
        raise ValidationError(f"{path} is missing required fields: {missing}")
    annotations = _record_annotations(record_type)
    arguments = {
        name: _decode_field(annotations[name], item, f"{path}.{name}")
        for name, item in value.items()
    }
    return record_type(**arguments)


def _decode_field(annotation: Any, value: Any, path: str) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is types.UnionType:
        if value is None and type(None) in args:
            return None
        return _decode_field(next(item for item in args if item is not type(None)), value, path)
    if origin is tuple:
        if type(value) is not list:
            raise ConsequaTypeError(f"{path} must be a JSON array")
        return tuple(_decode_field(args[0], item, f"{path}[{index}]") for index, item in enumerate(value))
    if origin is dict:
        if type(value) is not dict:
            raise ConsequaTypeError(f"{path} must be a JSON object")
        return _json_copy(value, path)
    if isinstance(annotation, type) and issubclass(annotation, _Record):
        return _decode_record(annotation, value, path)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if type(value) is not str:
            raise ConsequaTypeError(f"{path} must be an enum string")
        try:
            return annotation(value)
        except ValueError as error:
            raise ValidationError(f"{path} has unsupported {annotation.__name__}: {value!r}") from error
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ConsequaTypeError(f"{path} must be a {annotation.__name__}")
        return value
    raise ConsequaTypeError(f"unsupported schema field type for {path}: {annotation!r}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON number is not allowed: {value}")
