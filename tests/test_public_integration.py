"""Public application adapters preserve evidence boundaries and domain semantics."""

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Observation, OriginStatus, OutcomeContract,
    TimeBase, Trace, VerificationStatus, explain, verify,
)
from consequa_x.models import Evidence, VerificationResult
from consequa_x.schema import validate_trace


_spec = spec_from_file_location("artifact_example", Path(__file__).parents[1]
                               / "examples" / "artifact_delivery.py")
_example = module_from_spec(_spec)
_spec.loader.exec_module(_example)


class FixedVerifier:
    def __init__(self, receipt):
        self.receipt = receipt

    def verify(self, action, observation):
        return self.receipt


@pytest.mark.parametrize("change,message", [
    ("contract", "contract_id"), ("observation", "observation_id"),
    ("source", "source"), ("watermark", "watermark"), ("time", "precede"),
])
def test_custom_verifier_receipt_must_bind_to_supplied_contract_and_observation(change, message):
    trace = _example.build_trace()
    observation = replace(trace.observations[0], as_of_ms=70)
    receipt = _example.ArtifactVerifier().verify(trace.single_action, observation)
    evidence = receipt.evidence[0]
    if change == "contract":
        receipt = replace(receipt, contract_id="different-contract")
    elif change == "observation":
        receipt = replace(receipt, evidence=(replace(evidence, observation_id="unseen"),))
    elif change == "source":
        receipt = replace(receipt, evidence=(replace(evidence, source="delivery-response"),))
    elif change == "watermark":
        receipt = replace(receipt, evidence=(replace(evidence, as_of_ms=69),))
    else:
        receipt = replace(receipt, observed_at_ms=99)
    with pytest.raises(ValueError, match=message):
        verify(trace.single_action, observation, verifier=FixedVerifier(receipt))


def test_custom_verifier_return_type_and_input_types_are_checked():
    trace = _example.build_trace()
    with pytest.raises(TypeError, match="VerificationResult"):
        verify(trace.single_action, trace.observations[0], verifier=FixedVerifier({"status": "satisfied"}))
    with pytest.raises(TypeError, match="Action and an Observation"):
        verify(trace.single_action.to_dict(), trace.observations[0], verifier=FixedVerifier(None))


@pytest.mark.parametrize("adapter", [object(), {}, "verifier", SimpleNamespace(verify=17)])
def test_custom_verifier_requires_a_callable_method(adapter):
    trace = _example.build_trace()
    with pytest.raises(TypeError, match="callable verify method"):
        verify(trace.single_action, trace.observations[0], verifier=adapter)


@pytest.mark.parametrize("trace", [None, {}, "trace", []])
def test_explain_requires_a_typed_trace(trace):
    with pytest.raises(TypeError, match="explain requires a Trace"):
        explain(trace)


@pytest.mark.parametrize("adapter", [object(), SimpleNamespace(matching_effect_ids=17)])
def test_explain_takes_no_domain_matcher_because_verifiers_record_target_matches(adapter):
    with pytest.raises(TypeError):
        explain(_example.build_trace(), target_matcher=adapter)


def test_builtin_verifier_remains_explicitly_refund_only():
    trace = _example.build_trace()
    with pytest.raises(ValueError, match="Unsupported predicate"):
        verify(trace.single_action, trace.observations[0])


def test_offline_artifact_example_round_trips_and_qualifies_a_target_match():
    trace = _example.build_trace()
    restored = Trace.from_json(trace.to_json())
    assert validate_trace(restored.to_json()) == trace
    assert restored.verifications[0].status is VerificationStatus.SATISFIED
    assert restored.verifications[0].origin is OriginStatus.CONFIRMED
    assert trace.observations[0].records[0]["sha256"] == trace.single_action.contract.expected["sha256"]
    assert restored.verifications[0].target_effect_ids == ("artifact-revision-7",)
    explanation = explain(restored)
    assert explanation.single_action.assessment_alignment == "contradicted"
    assert explanation.single_action.diagnosis == "BELIEF / RESPONSE DIVERGENCE"
    assert set(explanation.single_action.codes) == {
        "ASSESSMENT_DIVERGENCE", "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE",
    }


def test_custom_predicate_is_unassessable_when_its_verifier_does_no_target_matching():
    trace = _example.build_trace()
    receipt = trace.verifications[0]
    # Linked IDs and an unrelated, valid-JSON detail payload are insufficient.
    receipt = replace(receipt, target_effect_ids=None, evidence=(replace(receipt.evidence[0], details={
        "records": [17], "matching_count": "not a refund count",
    }),))
    trace = replace(trace, verifications=(receipt,))
    explanation = explain(trace)
    assert explanation.single_action.assessment_alignment == "unassessable"
    assert explanation.single_action.codes == ("UNASSESSABLE_ASSESSMENT",)
    assert "PARAMETER_MISMATCH" not in explanation.single_action.codes
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" not in explanation.single_action.codes


@pytest.mark.parametrize("observation,status,origin,alignment,required", [
    (_example.captured_readback(None), VerificationStatus.VIOLATED, OriginStatus.UNKNOWN,
     "consistent", "CONSEQUENCE_VIOLATION"),
    (_example.captured_readback(b"different revision"), VerificationStatus.VIOLATED,
     OriginStatus.CONFIRMED, "consistent", "CONSEQUENCE_VIOLATION"),
    (_example.captured_readback(available=False), VerificationStatus.UNKNOWN, OriginStatus.UNKNOWN,
     "unassessable", "UNKNOWN_OUTCOME"),
    (_example.captured_readback(actor="human-editor", action_id="manual-delivery"),
     VerificationStatus.SATISFIED, OriginStatus.OTHER_ACTOR, "unassessable", "EXTERNAL_ACTOR_EFFECT"),
    (_example.captured_readback(actor=None, action_id=None), VerificationStatus.SATISFIED,
     OriginStatus.UNKNOWN, "unassessable", "UNCONFIRMED_ORIGIN"),
])
def test_custom_domain_failure_unknown_and_origin_do_not_become_refund_claims(
    observation, status, origin, alignment, required,
):
    trace = _example.build_trace(observation)
    receipt = trace.verifications[0]
    assert receipt.status is status and receipt.origin is origin
    explanation = explain(trace)
    assert explanation.single_action.assessment_alignment == alignment
    assert required in explanation.single_action.codes
    assert not {"PARTIAL_EFFECT", "PARAMETER_MISMATCH", "DUPLICATE_EFFECT",
                "EXCESS_EFFECTS", "REVERSED_EFFECT"} & set(explanation.single_action.codes)


def test_satisfied_state_and_action_metadata_without_a_target_match_cannot_judge_the_report():
    trace = _example.build_trace()
    receipt = trace.verifications[0]
    # A satisfied state receipt and propagated action metadata alone do not
    # prove this action produced the requested artifact.
    receipt = replace(receipt, target_effect_ids=())
    explanation = explain(replace(trace, verifications=(receipt,)))
    assert explanation.single_action.assessment_alignment == "unassessable"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" not in explanation.single_action.codes


@pytest.mark.parametrize("committed_at,status", [
    (0, VerificationStatus.VIOLATED), (24, VerificationStatus.VIOLATED),
    (49, VerificationStatus.VIOLATED), (50, VerificationStatus.VIOLATED),
    (51, VerificationStatus.VIOLATED), (60, VerificationStatus.VIOLATED),
    (70, VerificationStatus.VIOLATED), (71, VerificationStatus.SATISFIED),
    (100, VerificationStatus.SATISFIED),
])
def test_artifact_exact_count_includes_extra_deliveries_through_inclusive_horizon(
    committed_at, status,
):
    view = _example.captured_readback()
    extra = {**view.records[0], "effect_id": "extra-delivery", "committed_at_ms": committed_at}
    trace = _example.build_trace(replace(view, records=(*view.records, extra)))
    assert trace.verifications[0].status is status
    if committed_at > trace.single_action.contract.horizon_ms:
        assert trace.verifications[0].effect_ids == ("artifact-revision-7",)
    else:
        assert trace.verifications[0].effect_ids == ("artifact-revision-7", "extra-delivery")
    matching = trace.verifications[0].target_effect_ids
    assert ("extra-delivery" in matching) is (committed_at <= trace.single_action.contract.deadline_ms)


@pytest.mark.parametrize("committed_at,status", [
    (0, VerificationStatus.SATISFIED), (50, VerificationStatus.SATISFIED),
    (51, VerificationStatus.VIOLATED), (70, VerificationStatus.VIOLATED),
])
def test_artifact_single_delivery_requires_inclusive_deadline(committed_at, status):
    view = _example.captured_readback()
    record = {**view.records[0], "committed_at_ms": committed_at}
    assert _example.build_trace(replace(view, records=(record,))).verifications[0].status is status


def test_artifact_deliveries_before_registration_do_not_count():
    trace = _example.build_trace()
    action = replace(trace.single_action, registered_at_ms=10)
    view = trace.observations[0]
    earlier = {**view.records[0], "effect_id": "earlier-delivery", "committed_at_ms": 9}
    view = replace(view, records=(earlier, *view.records))
    receipt = verify(action, view, verifier=_example.ArtifactVerifier())
    assert receipt.status is VerificationStatus.SATISFIED
    assert receipt.effect_ids == ("artifact-revision-7",)


@pytest.mark.parametrize("present_through,status", [
    (25, VerificationStatus.UNKNOWN), (69, VerificationStatus.UNKNOWN),
    (70, VerificationStatus.SATISFIED), (100, VerificationStatus.SATISFIED),
])
def test_artifact_short_presence_witness_is_unknown_at_the_horizon_boundary(present_through, status):
    view = _example.captured_readback()
    record = {**view.records[0], "present_through_ms": present_through}
    assert _example.build_trace(replace(view, records=(record,))).verifications[0].status is status


@pytest.mark.parametrize("missing_witness", [False, True])
def test_unknown_artifact_records_no_target_match(missing_witness):
    view = _example.captured_readback()
    record = {**view.records[0], "present_through_ms": 69}
    if missing_witness:
        record.pop("present_through_ms")
    trace = _example.build_trace(replace(view, records=(record,)))
    assert trace.verifications[0].status is VerificationStatus.UNKNOWN
    assert trace.verifications[0].target_effect_ids is None
    explanation = explain(trace)
    assert explanation.single_action.assessment_alignment == "unassessable"
    assert explanation.single_action.codes == ("UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT")


@pytest.mark.parametrize("ids", [["artifact-revision-7"], ("unobserved",),
                                ("artifact-revision-7", "artifact-revision-7"), (17,), (" ",)])
def test_target_matches_are_a_unique_subset_of_attributable_ids(ids):
    receipt = _example.build_trace().verifications[0]
    with pytest.raises((TypeError, ValueError)):
        replace(receipt, target_effect_ids=ids)


def refund_trace():
    expected = {"payment_id": "p1", "amount_minor": 2000, "currency": "INR"}
    action = Action(action_id="refund-1", actor="agent", name="refund", arguments=expected, registered_at_ms=0,
                    contract=OutcomeContract(contract_id="refund-contract", predicate="refund_processed", expected=expected, deadline_ms=100))
    observation = Observation(observation_id="refund-observation", source="independent-ledger", observed_at_ms=200, as_of_ms=200,
                              scope={"payment_id": "p1"}, records=({
                                  "effect_id": "refund-effect", **expected, "committed_at_ms": 50,
                                  "status": "processed", "action_id": "refund-1", "actor": "agent",
                              },))
    return Trace(trace_id="refund-trace", time_base=TimeBase.RELATIVE_MS, actions=(action,), events=(), responses=(), assessments=(AgentAssessment(status=AssessmentStatus.SUCCESS, time_ms=80, assessment_id="assessment-1", action_id="refund-1"),),
                 observations=(observation,), verifications=(verify(action, observation),))


@pytest.mark.parametrize("details", [
    {"records": [17]}, {"records": {}}, {"records": None},
    {"records": [], "matching_count": True}, {"records": [], "peak_matching_count": "2"},
    {"records": [], "eligible_count": -1}, {"records": [], "relevant_count": []},
])
def test_explain_reads_receipts_and_never_reinterprets_evidence_details(details):
    trace = refund_trace()
    receipt = trace.verifications[0]
    receipt = replace(receipt, evidence=(replace(receipt.evidence[0], details=details),))
    malformed = replace(trace, verifications=(receipt,))
    # These details pass wire validation. Domain interpretation happened when
    # the verifier ran; explain uses only the receipt's recorded conclusions.
    assert Trace.from_json(malformed.to_json()) == malformed
    explanation = explain(malformed).single_action
    assert explanation.codes == ("CONSISTENT_OUTCOME",)
    assert explanation.assessment_alignment == "consistent"


@pytest.mark.parametrize("changes", [
    {"amount_minor": []}, {"amount_minor": True}, {"currency": None},
    {"payment_id": []}, {"committed_at_ms": "50"}, {"committed_at_ms": True},
    {"committed_at_ms": 201}, {"status": []}, {"status": "reversed"},
    {"reversed_at_ms": None}, {"reversed_at_ms": 49}, {"reversed_at_ms": 70},
    {"status": "reversed", "reversed_at_ms": 201},
])
def test_refund_verifier_keeps_a_malformed_linked_record_unknown(changes):
    trace = refund_trace()
    view = trace.observations[0]
    view = replace(view, records=({**view.records[0], **changes},))
    receipt = verify(trace.single_action, view)
    assert receipt.status is VerificationStatus.UNKNOWN
    assert receipt.target_effect_ids is None and receipt.findings == ()
    explanation = explain(replace(trace, observations=(view,), verifications=(receipt,)))
    assert explanation.single_action.codes == ("UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT")


def test_unknown_refund_keeps_malformed_source_evidence_without_claiming_alignment():
    trace = refund_trace()
    receipt = trace.verifications[0]
    receipt = VerificationResult(contract_id=receipt.contract_id, status=VerificationStatus.UNKNOWN, observed_at_ms=200,
                                 evidence=(Evidence(observation_id="refund-observation", source="independent-ledger", as_of_ms=200,
                                           details={"records": [17]}),), action_id=receipt.action_id)
    explanation = explain(replace(trace, verifications=(receipt,)))
    assert explanation.single_action.assessment_alignment == "unassessable"
    assert explanation.single_action.codes == ("UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT")


def test_refund_verifier_records_target_matches_for_explanation():
    trace = refund_trace()
    assert trace.verifications[0].target_effect_ids == ("refund-effect",)
    explanation = explain(trace)
    assert explanation.single_action.assessment_alignment == "consistent"
    assert explanation.single_action.codes == ("CONSISTENT_OUTCOME",)
