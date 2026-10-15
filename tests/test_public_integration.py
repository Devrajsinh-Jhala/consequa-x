"""Public application adapters preserve evidence boundaries and domain semantics."""

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

from consequa_x import (
    Action, AgentAssessment, AssessmentStatus, Observation, OriginStatus, OutcomeContract,
    TargetMatcher, Trace, VerificationStatus, explain, verify,
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
    receipt = _example.ArtifactVerifier().verify(trace.action, observation)
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
        verify(trace.action, observation, verifier=FixedVerifier(receipt))


def test_custom_verifier_return_type_and_input_types_are_checked():
    trace = _example.build_trace()
    with pytest.raises(TypeError, match="VerificationResult"):
        verify(trace.action, trace.observations[0], verifier=FixedVerifier({"status": "satisfied"}))
    with pytest.raises(TypeError, match="Action and an Observation"):
        verify(trace.action.to_dict(), trace.observations[0], verifier=FixedVerifier(None))


@pytest.mark.parametrize("adapter", [object(), {}, "verifier", SimpleNamespace(verify=17)])
def test_custom_verifier_requires_a_callable_method(adapter):
    trace = _example.build_trace()
    with pytest.raises(TypeError, match="callable verify method"):
        verify(trace.action, trace.observations[0], verifier=adapter)


@pytest.mark.parametrize("trace", [None, {}, "trace", []])
def test_explain_requires_a_typed_trace(trace):
    with pytest.raises(TypeError, match="explain requires a Trace"):
        explain(trace)


@pytest.mark.parametrize("unknown", [False, True])
@pytest.mark.parametrize("adapter", [object(), {}, "matcher",
                                   SimpleNamespace(matching_effect_ids=17)])
def test_target_matcher_requires_a_callable_method_without_executing_unknowns(adapter, unknown):
    observation = _example.captured_readback(available=not unknown)
    trace = _example.build_trace(observation)
    with pytest.raises(TypeError, match="callable matching_effect_ids method"):
        explain(trace, target_matcher=adapter)


def test_builtin_verifier_remains_explicitly_refund_only():
    trace = _example.build_trace()
    with pytest.raises(ValueError, match="Unsupported predicate"):
        verify(trace.action, trace.observations[0])


def test_offline_artifact_example_round_trips_and_qualifies_a_target_match():
    trace = _example.build_trace()
    restored = Trace.from_json(trace.to_json())
    assert validate_trace(restored.to_json()) == trace
    assert restored.verifications[0].status is VerificationStatus.SATISFIED
    assert restored.verifications[0].origin is OriginStatus.CONFIRMED
    assert trace.observations[0].records[0]["sha256"] == trace.action.contract.expected["sha256"]
    explanation = explain(restored, target_matcher=_example.ArtifactTargetMatcher())
    assert explanation.assessment_alignment == "contradicted"
    assert explanation.diagnosis == "BELIEF / RESPONSE DIVERGENCE"
    assert set(explanation.diagnoses) == {
        "ASSESSMENT_DIVERGENCE", "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE",
    }


def test_custom_predicate_is_unassessable_without_an_explicit_domain_matcher():
    trace = _example.build_trace()
    receipt = trace.verifications[0]
    # Linked IDs and an unrelated, valid-JSON detail payload are insufficient.
    receipt = replace(receipt, evidence=(replace(receipt.evidence[0], details={
        "records": [17], "matching_count": "not a refund count",
    }),))
    trace = replace(trace, verifications=(receipt,))
    explanation = explain(trace)
    assert explanation.assessment_alignment == "unassessable"
    assert explanation.diagnoses == ("UNASSESSABLE_ASSESSMENT",)
    assert "PARAMETER_MISMATCH" not in explanation.diagnoses
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" not in explanation.diagnoses


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
    explanation = explain(trace, target_matcher=_example.ArtifactTargetMatcher())
    assert explanation.assessment_alignment == alignment
    assert required in explanation.diagnoses
    assert not {"PARTIAL_EFFECT", "PARAMETER_MISMATCH", "DUPLICATE_EFFECT",
                "EXCESS_EFFECTS", "REVERSED_EFFECT"} & set(explanation.diagnoses)


def test_target_matcher_cannot_qualify_an_unrelated_attributable_effect_as_a_target():
    trace = _example.build_trace()
    receipt = trace.verifications[0]
    wrong_record = {**receipt.evidence[0].details["records"][0], "sha256": "0" * 64}
    # A satisfied state receipt and propagated action metadata alone do not
    # prove this action produced the requested artifact.
    receipt = replace(receipt, evidence=(replace(receipt.evidence[0],
                                               details={"records": [wrong_record]}),))
    explanation = explain(replace(trace, verifications=(receipt,)),
                          target_matcher=_example.ArtifactTargetMatcher())
    assert explanation.assessment_alignment == "unassessable"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" not in explanation.diagnoses


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
    if committed_at > trace.action.contract.horizon_ms:
        assert trace.verifications[0].effect_ids == ("artifact-revision-7",)
    else:
        assert trace.verifications[0].effect_ids == ("artifact-revision-7", "extra-delivery")
    matching = _example.ArtifactTargetMatcher().matching_effect_ids(
        trace.action, trace.verifications[0],
    )
    assert ("extra-delivery" in matching) is (committed_at <= trace.action.contract.deadline_ms)


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
    action = replace(trace.action, registered_at_ms=10)
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
def test_unknown_artifact_does_not_call_a_target_matcher(missing_witness):
    view = _example.captured_readback()
    record = {**view.records[0], "present_through_ms": 69}
    if missing_witness:
        record.pop("present_through_ms")
    trace = _example.build_trace(replace(view, records=(record,)))
    assert trace.verifications[0].status is VerificationStatus.UNKNOWN

    class UnexpectedMatcher:
        def matching_effect_ids(self, action, verification):
            raise AssertionError("An unknown outcome's source payload must not be interpreted")

    explanation = explain(trace, target_matcher=UnexpectedMatcher())
    assert explanation.assessment_alignment == "unassessable"
    assert explanation.diagnoses == ("UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT")


@pytest.mark.parametrize("ids", [["artifact-revision-7"], ("unobserved",),
                                ("artifact-revision-7", "artifact-revision-7"), (17,), (" ",)])
def test_target_matcher_result_is_a_unique_subset_of_attributable_ids(ids):
    class BadMatcher:
        def matching_effect_ids(self, action, verification):
            return ids

    with pytest.raises(ValueError, match="unique attributable effect IDs"):
        explain(_example.build_trace(), target_matcher=BadMatcher())


def refund_trace():
    expected = {"payment_id": "p1", "amount_minor": 2000, "currency": "INR"}
    action = Action("refund-1", "refund-test", "agent", "refund", expected, 0,
                    OutcomeContract("refund-contract", "refund_processed", expected, 100))
    observation = Observation("refund-observation", "independent-ledger", 200, 200,
                              {"payment_id": "p1"}, ({
                                  "effect_id": "refund-effect", **expected, "committed_at_ms": 50,
                                  "status": "processed", "action_id": "refund-1", "actor": "agent",
                              },))
    return Trace(action.trace_id, action, (), (), AgentAssessment(AssessmentStatus.SUCCESS, 80),
                 (observation,), (verify(action, observation),))


@pytest.mark.parametrize("details", [
    {"records": [17]}, {"records": {}}, {"records": None},
    {"records": [], "matching_count": True}, {"records": [], "peak_matching_count": "2"},
    {"records": [], "eligible_count": -1}, {"records": [], "relevant_count": []},
])
def test_known_refund_malformed_detail_shapes_raise_controlled_errors(details):
    trace = refund_trace()
    receipt = trace.verifications[0]
    receipt = replace(receipt, evidence=(replace(receipt.evidence[0], details=details),))
    malformed = replace(trace, verifications=(receipt,))
    # All these values pass wire validation; refund interpretation validates
    # its own domain instead of leaking AttributeError or comparing JSON types.
    assert Trace.from_json(malformed.to_json()) == malformed
    with pytest.raises(ValueError, match="Refund evidence"):
        explain(malformed)


@pytest.mark.parametrize("changes", [
    {"amount_minor": []}, {"amount_minor": True}, {"currency": None},
    {"payment_id": []}, {"committed_at_ms": "50"}, {"committed_at_ms": True},
    {"committed_at_ms": 201}, {"status": []}, {"status": "reversed"},
    {"reversed_at_ms": None}, {"reversed_at_ms": 49}, {"reversed_at_ms": 70},
    {"status": "reversed", "reversed_at_ms": 201},
])
def test_known_linked_refund_malformed_payload_is_rejected(changes):
    trace = refund_trace()
    receipt = trace.verifications[0]
    details = {**receipt.evidence[0].details,
               "records": [{**receipt.evidence[0].details["records"][0], **changes}]}
    receipt = replace(receipt, evidence=(replace(receipt.evidence[0], details=details),))
    with pytest.raises(ValueError, match="Linked refund evidence"):
        explain(replace(trace, verifications=(receipt,)))


def test_unknown_refund_keeps_malformed_source_evidence_without_claiming_alignment():
    trace = refund_trace()
    receipt = trace.verifications[0]
    receipt = VerificationResult(receipt.contract_id, VerificationStatus.UNKNOWN, 200,
                                 (Evidence("refund-observation", "independent-ledger", 200,
                                           {"records": [17]}),))
    explanation = explain(replace(trace, verifications=(receipt,)))
    assert explanation.assessment_alignment == "unassessable"
    assert explanation.diagnoses == ("UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT")


def test_refund_explanation_default_and_public_matcher_export_remain_available():
    assert TargetMatcher is not None
    explanation = explain(refund_trace())
    assert explanation.assessment_alignment == "consistent"
    assert explanation.diagnoses == ("CONSISTENT_OUTCOME",)
