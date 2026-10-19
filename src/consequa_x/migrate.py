"""Convert schema 0.1 traces (Consequa-X 1.x) to schema 1.0.

The conversion is structural and conservative:

- the single ``action`` becomes ``actions[0]``; the repeated ``trace_id`` on the
  action and events is checked and dropped;
- each response and verification gains the action's ``action_id``;
- the single ``assessment`` becomes ``assessments[0]``, with the ID of the
  matching ``agent_assessment`` event when there is exactly one, otherwise
  ``"assessment-1"``;
- ``time_base`` is ``relative_ms``: a 0.1 trace never recorded what its
  millisecond times count from.

Schema 0.1 receipts carry no target matches or findings, because 1.x derived
them later inside ``explain``. ``migrate_trace`` re-runs the verifier for the
action's predicate (``RefundVerifier`` for ``refund_processed`` by default) on
the recorded observation, and copies its target matches and findings only when
that run reproduces the recorded status, origin and effect identities exactly.
Otherwise ``target_effect_ids`` stays ``None`` and alignment stays
unassessable. No recorded conclusion is changed.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from .errors import ConsequaTypeError, SchemaVersionError, ValidationError
from .models import SCHEMA_VERSION, Action, Observation, Trace, _reject_constant, _unique_object
from .verification import RefundVerifier, Verifier


LEGACY_VERSION = "0.1"
_FIELDS = {
    "trace": {"trace_id", "action", "events", "responses", "assessment", "observations",
              "verifications", "schema_version"},
    "action": {"action_id", "trace_id", "actor", "name", "arguments", "registered_at_ms",
               "contract", "idempotency_key"},
    "event": {"id", "trace_id", "type", "time_ms", "actor", "parent_ids", "data"},
    "response": {"attempt_id", "status", "time_ms", "provider_request_id", "result"},
    "assessment": {"status", "time_ms", "evidence_event_ids", "rationale"},
    "verification": {"contract_id", "status", "observed_at_ms", "evidence", "origin",
                     "effect_ids", "attributable_effect_ids", "reason"},
}
_REQUIRED = {"trace": {"trace_id", "action", "events", "responses", "assessment"}}
_COMPARED = ("status", "origin", "effect_ids", "attributable_effect_ids")


class MigrationReport(dict):
    """What a migration did, for logs and command output."""


def migrate_trace(value: Mapping[str, Any] | str, *,
                  verifiers: Mapping[str, Verifier] | None = None,
                  report: MigrationReport | None = None) -> Trace:
    """Return the schema 1.0 equivalent of a schema 0.1 trace.

    ``value`` is decoded trace JSON or JSON text. ``verifiers`` maps
    predicates to verifiers used only to re-derive target matches and findings
    (see the module documentation); it defaults to the built-in refund
    verifier. A schema 1.0 trace is validated and returned unchanged. Pass a
    ``MigrationReport`` to receive counts of receipts the verifier reproduced
    (and so gained target matches and findings) and receipts it did not.
    """
    data = _decode(value)
    version = data.get("schema_version", LEGACY_VERSION) if isinstance(data, dict) else None
    if version == SCHEMA_VERSION:
        return Trace.from_dict(data)
    if version != LEGACY_VERSION:
        raise SchemaVersionError(f"cannot migrate schema_version {version!r}; expected '0.1'")
    _check_fields(data, "trace")
    action = data["action"]
    _check_fields(action, "action")
    trace_id = data["trace_id"]
    if action.get("trace_id") != trace_id:
        raise ValidationError("action.trace_id must equal trace_id")
    action_id = action.get("action_id")
    events = []
    for index, event in enumerate(_list(data["events"], "events")):
        _check_fields(event, "event", f"events[{index}]")
        if event.get("trace_id") != trace_id:
            raise ValidationError("every event.trace_id must equal trace_id")
        events.append({key: item for key, item in event.items() if key != "trace_id"})
    responses = []
    for index, response in enumerate(_list(data["responses"], "responses")):
        _check_fields(response, "response", f"responses[{index}]")
        responses.append({**response, "action_id": action_id})
    assessment = data["assessment"]
    _check_fields(assessment, "assessment")
    verifications = []
    for index, verification in enumerate(_list(data.get("verifications", []), "verifications")):
        _check_fields(verification, "verification", f"verifications[{index}]")
        verifications.append({**verification, "action_id": action_id})
    migrated = {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "time_base": "relative_ms",
        "actions": [{key: item for key, item in action.items() if key != "trace_id"}],
        "events": events,
        "responses": responses,
        "assessments": [{"assessment_id": _assessment_id(events, assessment),
                         "action_id": action_id, **assessment}],
        "observations": _list(data.get("observations", []), "observations"),
        "verifications": verifications,
    }
    trace = Trace.from_dict(migrated)
    trace, rederived = _rederive(trace, verifiers)
    if report is not None:
        report.update(source_schema_version=LEGACY_VERSION, schema_version=SCHEMA_VERSION,
                      verifications=len(trace.verifications), reproduced=rederived,
                      not_reproduced=len(trace.verifications) - rederived,
                      time_base=trace.time_base.value)
    return trace


def _decode(value: Any) -> Any:
    if type(value) is str:
        try:
            return json.loads(value, object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
        except json.JSONDecodeError as error:
            raise ValidationError(f"trace is not valid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise ConsequaTypeError("migrate_trace requires trace JSON or a decoded JSON object")
    return json.loads(json.dumps(dict(value), allow_nan=False))


def _list(value: Any, label: str) -> list:
    if type(value) is not list:
        raise ConsequaTypeError(f"{label} must be a JSON array")
    return value


def _check_fields(value: Any, kind: str, label: str | None = None) -> None:
    label = label or kind
    if type(value) is not dict:
        raise ConsequaTypeError(f"{label} must be a JSON object")
    unknown = set(value) - _FIELDS[kind]
    if unknown:
        raise ValidationError(f"{label} has unknown schema 0.1 fields: {sorted(unknown)}")
    missing = _REQUIRED.get(kind, set()) - set(value)
    if missing:
        raise ValidationError(f"{label} is missing required fields: {sorted(missing)}")


def _assessment_id(events: list[dict], assessment: dict) -> str:
    candidates = [event["id"] for event in events
                  if event.get("type") == "agent_assessment"
                  and isinstance(event.get("data"), dict)
                  and all(event["data"].get(key) == value for key, value in assessment.items())]
    return candidates[0] if len(candidates) == 1 else "assessment-1"


def _rederive(trace: Trace, verifiers: Mapping[str, Verifier] | None) -> tuple[Trace, int]:
    from dataclasses import replace

    from .verification import verify

    chosen = {"refund_processed": RefundVerifier()} if verifiers is None else dict(verifiers)
    action: Action = trace.single_action
    verifier = chosen.get(action.contract.predicate)
    observations = {item.observation_id: item for item in trace.observations}
    upgraded, count = [], 0
    for receipt in trace.verifications:
        observation: Observation | None = (
            observations.get(receipt.evidence[-1].observation_id)
            if len(receipt.evidence) == 1 else None)
        candidate = None
        if verifier is not None and observation is not None:
            try:
                candidate = verify(action, observation, verifier=verifier)
            except (TypeError, ValueError):
                candidate = None
        if candidate is not None and all(getattr(candidate, name) == getattr(receipt, name)
                                         for name in _COMPARED):
            receipt = replace(receipt, target_effect_ids=candidate.target_effect_ids,
                              findings=candidate.findings)
            count += 1
        upgraded.append(receipt)
    return replace(trace, verifications=tuple(upgraded)), count
