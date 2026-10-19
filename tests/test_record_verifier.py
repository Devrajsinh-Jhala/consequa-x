"""RecordVerifier keeps the refund verifier's evidence discipline for any record."""

import pytest

from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Observation, OriginStatus, OutcomeContract,
    RecordVerifier, ResponseStatus, ToolResponse, TimeBase, Trace, VerificationResult,
    VerificationStatus, explain, verify,
)


EXPECTED = {"order_id": "o-17", "amount_minor": 5000, "currency": "INR"}
VERIFIER = RecordVerifier(scope_fields=("order_id",))


def action(*, exact_count=1, expected=None, predicate="record_present", deadline=100):
    contract = OutcomeContract(contract_id="contract-1", predicate=predicate,
                               expected=dict(EXPECTED if expected is None else expected),
                               deadline_ms=deadline, exact_count=exact_count, stability_ms=50)
    return Action(action_id="refund-1", actor="agent", name="issue_refund", arguments={"order_id": "o-17"}, registered_at_ms=10, contract=contract)


def row(effect_id="r1", committed=20, **fields):
    record = {**EXPECTED, "effect_id": effect_id, "committed_at_ms": committed,
              "action_id": "refund-1", "attempt_id": "refund-1:attempt-1", "actor": "agent"}
    record.update(fields)
    return {key: value for key, value in record.items() if value is not None}


def observe(*records, watermark=200, scope=None, complete=True, available=True):
    return Observation(observation_id="readback-1", source="orders-db (read-only)", observed_at_ms=watermark, as_of_ms=watermark,
                       scope={"order_id": "o-17"} if scope is None else scope, records=tuple(records),
                       complete=complete, available=available)


def check(observation, **kwargs):
    return verify(action(**kwargs), observation, verifier=VERIFIER)


def test_linked_record_satisfies_and_confirms_origin():
    receipt = check(observe(row()))
    assert receipt.status is VerificationStatus.SATISFIED
    assert receipt.origin is OriginStatus.CONFIRMED
    assert receipt.attributable_effect_ids == ("r1",)
    assert receipt.evidence[-1].details["fields"]["scope_fields"] == ["order_id"]


def test_other_actor_record_satisfies_state_but_not_origin():
    receipt = check(observe(row(action_id=None, attempt_id=None, actor="support-staff")))
    assert receipt.status is VerificationStatus.SATISFIED
    assert receipt.origin is OriginStatus.OTHER_ACTOR
    assert receipt.attributable_effect_ids == ()


@pytest.mark.parametrize("observation,reason", [
    (observe(row(), available=False), "unavailable"),
    (observe(row(), scope={}), "scope does not cover"),
    (observe(row(), scope={"order_id": "o-99"}), "scope does not cover"),
    (observe(row(), complete=False), "not exhaustive"),
    (observe(row(), watermark=120), "watermark precedes"),
    (observe(row(effect_id="")), "invalid or duplicate"),
    (observe(row(), row()), "invalid or duplicate"),
    (observe(row(committed="20")), "invalid or duplicate"),
    (observe(row(committed=250)), "invalid or duplicate"),
    (observe(row(actor="")), "invalid origin metadata"),
    (observe(row(removed_at_ms=5)), "invalid removal time"),
    (observe(row(order_id="o-99")), "outside its declared scope"),
])
def test_insufficient_or_malformed_readback_stays_unknown(observation, reason):
    receipt = check(observation)
    assert receipt.status is VerificationStatus.UNKNOWN
    assert reason in receipt.reason
    assert receipt.origin is OriginStatus.UNKNOWN


def test_counts_deadline_and_persistence():
    assert check(observe(row(), row("r2"))).status is VerificationStatus.VIOLATED
    assert check(observe(row(), row("r2")), exact_count=None).status is VerificationStatus.SATISFIED
    assert check(observe(), exact_count=0).status is VerificationStatus.SATISFIED
    assert check(observe(row()), exact_count=0).status is VerificationStatus.VIOLATED
    # A later duplicate inside the stability window violates an exact count.
    assert check(observe(row(), row("r2", committed=130))).status is VerificationStatus.VIOLATED
    # Committing only after the deadline is not on time.
    assert check(observe(row(committed=130))).status is VerificationStatus.VIOLATED
    # Removal before the horizon fails persistence; removal after it does not.
    assert check(observe(row(removed_at_ms=140))).status is VerificationStatus.VIOLATED
    assert check(observe(row(removed_at_ms=180))).status is VerificationStatus.SATISFIED
    # Records before registration or after the horizon are not relevant.
    early = check(observe(row(committed=5)))
    assert early.status is VerificationStatus.VIOLATED and early.effect_ids == ()


def test_wrong_value_is_relevant_but_not_matching():
    receipt = check(observe(row(amount_minor=4000)))
    assert receipt.status is VerificationStatus.VIOLATED
    assert receipt.origin is OriginStatus.CONFIRMED
    assert receipt.target_effect_ids == ()
    assert [item.code for item in receipt.findings] == ["PARAMETER_MISMATCH"]
    assert receipt.findings[0].effect_ids == ("r1",)


def trace_for(receipt, observation, *, response="timeout", reported="failure"):
    act = action()
    return Trace(trace_id="trace-1", time_base=TimeBase.RELATIVE_MS, actions=(act,), events=(), responses=(ToolResponse(attempt_id="a1", status=ResponseStatus(response), time_ms=30, provider_request_id="a1", action_id=act.action_id),),
                 assessments=(AgentAssessment(status=AssessmentStatus(reported), time_ms=35, assessment_id="assessment-1", action_id=act.action_id),), observations=(observation,), verifications=(receipt,))


def test_receipt_target_matches_let_explain_judge_the_agents_report():
    observation = observe(row())
    receipt = check(observation)
    assert receipt.target_effect_ids == ("r1",) and receipt.findings == ()
    failure = explain(trace_for(receipt, observation)).single_action
    assert failure.assessment_alignment == "contradicted"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in failure.codes
    divergence = failure.diagnoses[failure.codes.index("ASSESSMENT_DIVERGENCE")]
    assert divergence.evidence == ("assessment-1", "readback-1") and divergence.message
    success = explain(trace_for(receipt, observation, response="success",
                                reported="success")).single_action
    assert success.assessment_alignment == "consistent"
    assert success.codes == ("CONSISTENT_OUTCOME",)
    unmatched = VerificationResult(**{**receipt.__dict__, "target_effect_ids": None})
    without_matching = explain(trace_for(unmatched, observation)).single_action
    assert without_matching.assessment_alignment == "unassessable"
    assert "UNASSESSABLE_ASSESSMENT" in without_matching.codes


def test_other_actor_and_unknown_cannot_judge_the_report():
    other = observe(row(action_id=None, attempt_id=None, actor="support-staff"))
    receipt = check(other)
    assert receipt.target_effect_ids == ()
    explanation = explain(trace_for(receipt, other)).single_action
    assert explanation.assessment_alignment == "unassessable"
    assert explanation.codes == ("UNASSESSABLE_ASSESSMENT", "EXTERNAL_ACTOR_EFFECT")
    assert explanation.diagnoses[-1].evidence == ("r1",)
    stale = observe(row(), watermark=120)
    unknown = check(stale)
    assert unknown.target_effect_ids is None and unknown.findings == ()
    assert explain(trace_for(unknown, stale)).single_action.codes == (
        "UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT")


def test_excess_duplicate_and_removed_records_become_findings():
    duplicate = check(observe(row("r1"), row("r2", committed=30)))
    assert duplicate.status is VerificationStatus.VIOLATED
    assert [item.code for item in duplicate.findings] == ["EXCESS_EFFECTS", "DUPLICATE_EFFECT"]
    assert duplicate.findings[1].effect_ids == ("r1", "r2")
    removed = check(observe(row(removed_at_ms=120)))
    assert removed.status is VerificationStatus.VIOLATED
    assert [item.code for item in removed.findings] == ["REMOVED_EFFECT"]
    assert removed.target_effect_ids == ()
    codes = explain(trace_for(removed, observe(row(removed_at_ms=120)))).single_action.codes
    assert "REMOVED_EFFECT" in codes and "CONSEQUENCE_VIOLATION" in codes


def test_custom_field_names():
    custom = RecordVerifier(scope_fields=("order_id",), effect_id_field="row_id",
                            committed_field="written_at", action_field="request_id",
                            actor_field="writer", removed_field="deleted_at",
                            attempt_field="call_id")
    record = {**EXPECTED, "row_id": "x1", "written_at": 20, "request_id": "refund-1",
              "writer": "agent"}
    receipt = verify(action(), observe(record), verifier=custom)
    assert receipt.status is VerificationStatus.SATISFIED
    assert receipt.origin is OriginStatus.CONFIRMED
    assert receipt.target_effect_ids == ("x1",)


@pytest.mark.parametrize("kwargs,message", [
    ({"predicate": "refund_processed"}, "Unsupported predicate"),
    ({"expected": {}}, "at least one field value"),
    ({"expected": {"amount_minor": 5000}}, "scope fields must have expected values"),
    ({"expected": {**EXPECTED, "effect_id": "r1"}}, "metadata fields"),
    ({"deadline": 5}, "deadline precedes"),
])
def test_invalid_contracts_are_refused(kwargs, message):
    with pytest.raises(ValueError, match=message):
        verify(action(**kwargs), observe(row()), verifier=VERIFIER)


def test_invalid_configuration_is_refused():
    with pytest.raises(ValueError, match="at least one distinct"):
        RecordVerifier(scope_fields=())
    with pytest.raises(ValueError, match="distinct"):
        RecordVerifier(scope_fields=("order_id",), actor_field="effect_id")
    with pytest.raises(ValueError, match="scope fields cannot"):
        RecordVerifier(scope_fields=("effect_id",))
