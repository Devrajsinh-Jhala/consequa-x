"""Typed exceptions keep 1.x compatibility while letting callers be precise."""

import json

import pytest

import consequa_x
from consequa_x import (
    Action, ConsequaError, ConsequaTypeError, ContractError, Observation, OutcomeContract,
    ReceiptError, RecorderError, RecordVerifier, SchemaVersionError, Trace, TraceRecorder,
    ValidationError, VerificationResult, VerificationStatus, Evidence, verify,
)
from consequa_x.attribution import InsufficientEvidenceError
from consequa_x.policies import PolicyError


@pytest.mark.parametrize("error,bases", [
    (ConsequaTypeError, (ConsequaError, TypeError)),
    (ValidationError, (ConsequaError, ValueError)),
    (SchemaVersionError, (ValidationError, ValueError)),
    (ContractError, (ConsequaError, ValueError)),
    (ReceiptError, (ConsequaError, ValueError)),
    (RecorderError, (ConsequaError, ValueError)),
    (InsufficientEvidenceError, (ConsequaError, ValueError)),
    (PolicyError, (ConsequaError, ValueError)),
])
def test_every_error_is_a_consequa_error_and_keeps_its_builtin_base(error, bases):
    assert issubclass(error, bases)
    assert error.__name__ in consequa_x.__all__ or error in (InsufficientEvidenceError, PolicyError)


def action(predicate="refund_processed", expected=None):
    if expected is None:
        expected = {"payment_id": "p1", "amount_minor": 500, "currency": "INR"}
    return Action(action_id="a1", actor="agent", name="refund", arguments={}, registered_at_ms=0,
                  contract=OutcomeContract(contract_id="c1", predicate=predicate, expected=expected, deadline_ms=100))


def observation(**changes):
    values = dict(observation_id="o1", source="ledger", observed_at_ms=200, as_of_ms=200,
                  scope={"payment_id": "p1"})
    values.update(changes)
    return Observation(**values)


def test_record_and_trace_errors_are_typed():
    with pytest.raises(ConsequaTypeError):
        OutcomeContract(contract_id="c1", predicate="p", expected={}, deadline_ms=True)
    with pytest.raises(ValidationError):
        OutcomeContract(contract_id="c1", predicate="p", expected={}, deadline_ms=-1)
    with pytest.raises(ValidationError, match="not valid JSON"):
        Trace.from_json("{")
    with pytest.raises(ValidationError, match="duplicate JSON object key"):
        Trace.from_json('{"a": 1, "a": 2}')


def test_unsupported_schema_version_is_a_schema_version_error():
    rec = TraceRecorder("t1", actor="agent", clock=lambda: 0)
    rec.register("a1", "refund", {}, contract=OutcomeContract(contract_id="c1", predicate="p", expected={"k": 1}, deadline_ms=10))
    rec.assessment("unknown")
    data = json.loads(rec.trace().to_json())
    data["schema_version"] = "9.9"
    with pytest.raises(SchemaVersionError, match="unsupported schema_version"):
        Trace.from_dict(data)


def test_verifiers_distinguish_unsupported_contracts_from_bad_receipts():
    with pytest.raises(ContractError, match="Unsupported predicate"):
        verify(action(predicate="other"), observation())
    with pytest.raises(ContractError, match="record_present expects"):
        RecordVerifier(scope_fields=("k",)).verify(action("record_present", {}), observation())

    class WrongContract:
        def verify(self, action, observation):
            return VerificationResult(contract_id="other", status=VerificationStatus.UNKNOWN, observed_at_ms=200,
                                      evidence=(Evidence(observation_id="o1", source="ledger", as_of_ms=200, details={}),), action_id="a1")

    with pytest.raises(ReceiptError, match="contract_id"):
        verify(action(), observation(), verifier=WrongContract())


def test_recorder_misuse_is_a_recorder_error():
    rec = TraceRecorder("t1", actor="agent", clock=lambda: 0)
    with pytest.raises(RecorderError, match="register the action"):
        rec.dispatch()
    with pytest.raises(ConsequaTypeError):
        TraceRecorder("t1", actor="agent", clock=5)
