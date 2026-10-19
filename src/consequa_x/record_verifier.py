"""A generic ``record_present`` verifier for record-shaped outcomes.

Many consequential actions leave a record behind: a database row, an order, a
ticket, a stored file. ``RecordVerifier`` checks such an outcome against an
exhaustive, read-only snapshot with the same evidence discipline as the refund
verifier. The application still owns source trust, scope and completeness
declarations; this module interprets the captured observation it is given.
"""

from __future__ import annotations

from typing import Any

from .errors import ConsequaTypeError, ContractError, ReceiptError, ValidationError
from .models import (
    Action,
    Evidence,
    Observation,
    OriginStatus,
    VerificationResult,
    VerificationStatus,
)


RECORD_PRESENT = "record_present"


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _field_name(value: object, label: str) -> str:
    if not _identifier(value):
        raise ValidationError(f"{label} must be a nonempty field name")
    return value


class RecordVerifier:
    """Check that the expected records exist, on time and persistently.

    The contract predicate is ``record_present``. ``contract.expected`` maps
    field names to the exact JSON values a matching record must carry. A
    qualifying record commits between action registration and the deadline and
    is not removed through the stability horizon. ``exact_count`` must then hold
    from the deadline through the horizon (late or transient extra matches
    violate it); ``None`` requires at least one; ``0`` requires none.

    ``scope_fields`` name the expected fields that define what the snapshot
    covers. The observation's scope must state each of them with the expected
    value, and every returned record must agree with them. The snapshot must be
    available, complete for that scope, and have a watermark at or after the
    horizon. Otherwise, or for malformed records, the result is ``unknown``.

    Each record needs a unique identifier (``effect_id_field``) and an integer
    commit time (``committed_field``). An optional removal time
    (``removed_field``) records when it stopped existing. Origin is separate
    from satisfaction: ``confirmed`` when a relevant record carries this
    action's identifier (``action_field``) without a conflicting actor,
    ``other_actor`` when every relevant record names a different actor and none
    links this action, otherwise ``unknown``. With the default field names the
    evidence graph also links each record to its dispatch through
    ``attempt_field``.
    """

    predicate = RECORD_PRESENT

    def __init__(self, *, scope_fields: tuple[str, ...], effect_id_field: str = "effect_id",
                 committed_field: str = "committed_at_ms", removed_field: str = "removed_at_ms",
                 action_field: str = "action_id", actor_field: str = "actor",
                 attempt_field: str = "attempt_id") -> None:
        scope_fields = tuple(scope_fields)
        if not scope_fields or len(set(scope_fields)) != len(scope_fields):
            raise ValidationError("scope_fields must name at least one distinct field")
        self.scope_fields = tuple(_field_name(name, "scope field") for name in scope_fields)
        self.effect_id_field = _field_name(effect_id_field, "effect_id_field")
        self.committed_field = _field_name(committed_field, "committed_field")
        self.removed_field = _field_name(removed_field, "removed_field")
        self.action_field = _field_name(action_field, "action_field")
        self.actor_field = _field_name(actor_field, "actor_field")
        self.attempt_field = _field_name(attempt_field, "attempt_field")
        self._metadata = {self.effect_id_field, self.committed_field, self.removed_field,
                          self.action_field, self.actor_field, self.attempt_field}
        if len(self._metadata) != 6:
            raise ValidationError("record metadata field names must be distinct")
        if self._metadata & set(self.scope_fields):
            raise ValidationError("scope fields cannot also be record metadata fields")

    def target_matcher(self) -> RecordTargetMatcher:
        """A matcher with the same field configuration, for ``explain``."""
        return RecordTargetMatcher(self)

    def fields(self) -> dict[str, Any]:
        return {"scope_fields": list(self.scope_fields), "effect_id": self.effect_id_field,
                "committed": self.committed_field, "removed": self.removed_field,
                "action": self.action_field, "actor": self.actor_field,
                "attempt": self.attempt_field}

    def check_contract(self, action: Action) -> dict[str, Any]:
        contract = action.contract
        if contract.predicate != RECORD_PRESENT:
            raise ContractError(f"Unsupported predicate: {contract.predicate!r}")
        expected = contract.expected
        if not expected:
            raise ContractError("record_present expects at least one field value")
        if self._metadata & expected.keys():
            raise ContractError("expected values cannot name record metadata fields")
        missing = [name for name in self.scope_fields if name not in expected]
        if missing:
            raise ContractError(f"scope fields must have expected values: {missing}")
        if contract.deadline_ms < action.registered_at_ms:
            raise ContractError("Contract deadline precedes action registration")
        return expected

    def _removed_at(self, record: dict, horizon_ms: int) -> int:
        return record.get(self.removed_field, horizon_ms + 1)

    def verify(self, action: Action, observation: Observation) -> VerificationResult:
        contract = action.contract
        expected = self.check_contract(action)
        horizon = contract.horizon_ms
        details: dict[str, Any] = {
            "predicate": RECORD_PRESENT, "fields": self.fields(),
            "scope": dict(observation.scope), "watermark_ms": observation.as_of_ms,
            "horizon_ms": horizon, "complete": observation.complete,
            "available": observation.available, "expected": dict(expected),
            "records": [dict(record) for record in observation.records],
        }

        def result(status, reason, origin=OriginStatus.UNKNOWN, effect_ids=(), linked=()):
            evidence = (Evidence(observation.observation_id, observation.source,
                                 observation.as_of_ms, details),)
            return VerificationResult(contract.contract_id, status, observation.observed_at_ms,
                                      evidence, origin, effect_ids, linked, reason)

        unknown = VerificationStatus.UNKNOWN
        if not observation.available:
            return result(unknown, "Readback source is unavailable")
        if any(observation.scope.get(name) != expected[name] for name in self.scope_fields):
            return result(unknown, "Readback scope does not cover this contract")
        if not observation.complete:
            return result(unknown, "Readback is not exhaustive for its scope")
        if observation.as_of_ms < horizon:
            return result(unknown, "Readback watermark precedes contract horizon")

        relevant, seen = [], set()
        for record in observation.records:
            effect_id = record.get(self.effect_id_field)
            committed = record.get(self.committed_field)
            if (not _identifier(effect_id) or effect_id in seen or type(committed) is not int
                    or not 0 <= committed <= observation.as_of_ms):
                return result(unknown, "Readback contains invalid or duplicate records")
            seen.add(effect_id)
            if any(name in record and not _identifier(record[name])
                   for name in (self.action_field, self.actor_field, self.attempt_field)):
                return result(unknown, "Readback contains invalid origin metadata")
            if self.removed_field in record:
                removed = record[self.removed_field]
                if type(removed) is not int or not committed <= removed <= observation.as_of_ms:
                    return result(unknown, "Readback has an invalid removal time")
            if any(name not in record or record[name] != expected[name]
                   for name in self.scope_fields):
                return result(unknown, "Readback includes records outside its declared scope")
            if action.registered_at_ms <= committed <= horizon:
                relevant.append(record)

        value_matches = [record for record in relevant
                         if all(name in record and record[name] == value
                                for name, value in expected.items())]
        persistent = [record for record in value_matches
                      if self._removed_at(record, horizon) > horizon]
        eligible = [record for record in persistent
                    if record[self.committed_field] <= contract.deadline_ms]
        peak = self._peak_count(value_matches, contract.deadline_ms, horizon)
        effect_ids = tuple(record[self.effect_id_field] for record in relevant)
        linked = tuple(record[self.effect_id_field] for record in relevant
                       if record.get(self.action_field) == action.action_id
                       and record.get(self.actor_field, action.actor) == action.actor)
        if linked:
            origin = OriginStatus.CONFIRMED
        elif relevant and all(record.get(self.actor_field)
                              and record[self.actor_field] != action.actor
                              and record.get(self.action_field) != action.action_id
                              for record in relevant):
            origin = OriginStatus.OTHER_ACTOR
        else:
            origin = OriginStatus.UNKNOWN

        details.update(matching_count=len(persistent), eligible_count=len(eligible),
                       peak_matching_count=peak, relevant_count=len(relevant))
        count_ok = bool(eligible) if contract.exact_count is None else (
            len(eligible) == contract.exact_count and peak == contract.exact_count)
        if count_ok:
            return result(VerificationStatus.SATISFIED,
                          "Record predicate is satisfied through the declared horizon",
                          origin, effect_ids, linked)
        return result(VerificationStatus.VIOLATED,
                      "Record predicate is violated in an exhaustive horizon-covering snapshot",
                      origin, effect_ids, linked)

    def _peak_count(self, records: list[dict], deadline_ms: int, horizon_ms: int) -> int:
        """Maximum matching count during the closed interval from deadline to horizon.

        Changes sharing a timestamp are applied together. A removal at the
        deadline has already taken its record out of the starting count.
        """
        count = sum(record[self.committed_field] <= deadline_ms
                    and self._removed_at(record, horizon_ms) > deadline_ms
                    for record in records)
        peak = count
        changes: dict[int, int] = {}
        for record in records:
            committed, removed = record[self.committed_field], self._removed_at(record, horizon_ms)
            if deadline_ms < committed <= horizon_ms:
                changes[committed] = changes.get(committed, 0) + 1
            if deadline_ms < removed <= horizon_ms:
                changes[removed] = changes.get(removed, 0) - 1
        for time_ms in sorted(changes):
            count += changes[time_ms]
            peak = max(peak, count)
        return peak


class RecordTargetMatcher:
    """Qualify attributable records against a ``record_present`` contract.

    Returns the attributable effect identifiers whose records carry every
    expected value, committed between registration and the deadline, and
    persist through the horizon. Supplying it to ``explain`` declares that the
    agent's success or failure report refers to this contract.
    """

    def __init__(self, verifier: RecordVerifier) -> None:
        if not isinstance(verifier, RecordVerifier):
            raise ConsequaTypeError("RecordTargetMatcher requires the RecordVerifier it matches")
        self.verifier = verifier

    def matching_effect_ids(self, action: Action,
                            verification: VerificationResult) -> tuple[str, ...]:
        verifier = self.verifier
        expected = verifier.check_contract(action)
        if verification.status is VerificationStatus.UNKNOWN:
            return ()
        details = verification.evidence[-1].details
        records = details.get("records")
        if type(records) is not list or any(type(record) is not dict for record in records):
            raise ReceiptError("Record evidence must be an array of objects")
        contract = action.contract
        attributable = set(verification.attributable_effect_ids)
        matches = []
        for record in records:
            effect_id = record.get(verifier.effect_id_field)
            if effect_id not in attributable or effect_id in matches:
                continue
            committed = record.get(verifier.committed_field)
            if type(committed) is not int:
                raise ReceiptError("Linked record evidence has an invalid commit time")
            if (all(name in record and record[name] == value for name, value in expected.items())
                    and action.registered_at_ms <= committed <= contract.deadline_ms
                    and verifier._removed_at(record, contract.horizon_ms) > contract.horizon_ms):
                matches.append(effect_id)
        return tuple(matches)
