from dataclasses import FrozenInstanceError, dataclass, replace
import json
import unittest

from consequa_x.models import (
    Action,
    AgentAssessment,
    AssessmentStatus,
    Event,
    EventType,
    Evidence,
    Observation,
    OriginStatus,
    OutcomeContract,
    ResponseStatus,
    ToolResponse,
    Trace,
    VerificationResult,
    VerificationStatus,
    to_dict,
)


def sample_trace() -> Trace:
    contract = OutcomeContract(
        "contract-1", "refund_processed",
        {"payment_id": "pay_42", "amount_minor": 500_000, "currency": "INR"},
        deadline_ms=10, stability_ms=5,
    )
    action = Action(
        "action-1", "trace-1", "agent", "refund", dict(contract.expected), 0,
        contract, idempotency_key="refund-order-1",
    )
    events = (
        Event("context-1", "trace-1", EventType.USER_INPUT, 0, data={"text": "Refund ₹5,000"}),
        Event("dispatch-1", "trace-1", EventType.ACTION_DISPATCH, 1, "agent", ("context-1",)),
        Event("response-1", "trace-1", EventType.TOOL_RESPONSE, 2, parent_ids=("dispatch-1",)),
    )
    response = ToolResponse("attempt-1", ResponseStatus.TIMEOUT, 2, "provider-request-1")
    observation = Observation(
        "observation-1", "refund_readback", 15, 15, {"payment_id": "pay_42"},
        ({"effect_id": "effect-1", **contract.expected, "committed_at_ms": 1, "status": "processed"},),
    )
    verification = VerificationResult(
        "contract-1", VerificationStatus.SATISFIED, 15,
        (Evidence("observation-1", "refund_readback", 15, {"effect_id": "effect-1"}),),
        OriginStatus.CONFIRMED, ("effect-1",), ("effect-1",), "Independent readback confirms refund",
    )
    return Trace(
        "trace-1", action, events, (response,),
        AgentAssessment(AssessmentStatus.FAILURE, 2, ("response-1",), "No acknowledgement"),
        (observation,), (verification,),
    )


class ModelTests(unittest.TestCase):
    def test_complete_trace_round_trip_preserves_types_and_identifiers(self):
        original = sample_trace()
        exported = original.to_dict()
        self.assertEqual(exported["events"][0]["type"], "user_input")
        self.assertEqual(exported["schema_version"], "0.1")
        self.assertIsInstance(exported["observations"][0]["records"], list)
        for restored in (Trace.from_dict(exported), Trace.from_json(original.to_json(indent=2))):
            with self.subTest(method=type(restored)):
                self.assertEqual(restored, original)
                self.assertIs(restored.events[0].type, EventType.USER_INPUT)
                self.assertIs(restored.responses[0].status, ResponseStatus.TIMEOUT)
                self.assertIs(restored.assessment.status, AssessmentStatus.FAILURE)
                self.assertIs(restored.verifications[0].status, VerificationStatus.SATISFIED)
                self.assertIs(restored.verifications[0].origin, OriginStatus.CONFIRMED)
                self.assertIsInstance(restored.observations, tuple)
                self.assertIsInstance(restored.observations[0].records, tuple)
                self.assertIsInstance(restored.verifications[0].evidence[0], Evidence)
                self.assertEqual(restored.action.action_id, "action-1")
                self.assertEqual(restored.responses[0].attempt_id, "attempt-1")
                self.assertEqual(restored.responses[0].provider_request_id, "provider-request-1")
                self.assertEqual(restored.verifications[0].effect_ids, ("effect-1",))

    def test_contract_horizon_and_optional_count(self):
        contract = sample_trace().action.contract
        self.assertEqual(contract.horizon_ms, 15)
        self.assertIsNone(replace(contract, exact_count=None).exact_count)
        self.assertEqual(replace(contract, exact_count=0).exact_count, 0)

    def test_constructor_and_exports_do_not_alias_input_payloads(self):
        payload = {"nested": {"values": [1, None, True, 1.25]}}
        event = Event("e", "t", EventType.USER_INPUT, 0, data=payload)
        payload["nested"]["values"].append(2)
        exported = event.to_dict()
        exported["data"]["nested"]["values"].append(3)
        self.assertEqual(event.data["nested"]["values"], [1, None, True, 1.25])
        with self.assertRaises(FrozenInstanceError):
            event.id = "changed"

    def test_invalid_time_values_and_future_watermarks_are_rejected(self):
        for invalid in (-1, True, 1.5, "1"):
            with self.subTest(invalid=invalid), self.assertRaises((TypeError, ValueError)):
                Event("e", "t", EventType.USER_INPUT, invalid)
        with self.assertRaisesRegex(ValueError, "as_of_ms"):
            Observation("o", "readback", 1, 2, {})
        with self.assertRaises(TypeError):
            Observation("o", "readback", 1, 1, {}, complete=1)

    def test_json_payload_rejects_non_json_values_and_cycles(self):
        for invalid in (float("nan"), float("inf"), {1, 2}, b"secret", object(), (1, 2)):
            with self.subTest(invalid=type(invalid)), self.assertRaises((TypeError, ValueError)):
                Event("e", "t", EventType.USER_INPUT, 0, data={"invalid": invalid})
        with self.assertRaises(TypeError):
            Event("e", "t", EventType.USER_INPUT, 0, data={1: "not a JSON key"})
        circular = {}
        circular["self"] = circular
        with self.assertRaisesRegex(ValueError, "circular"):
            Event("e", "t", EventType.USER_INPUT, 0, data=circular)

    def test_shared_serializer_rejects_unsafe_mutated_payload(self):
        trace = sample_trace()
        trace.action.arguments["bad"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            trace.to_json()
        self.assertEqual(to_dict(ResponseStatus.TIMEOUT), "timeout")

    def test_shared_serializer_supports_nested_generic_dataclass_instances(self):
        @dataclass(frozen=True)
        class Export:
            status: ResponseStatus
            children: object

        payload = {"nested": [Export(ResponseStatus.TIMEOUT, (1, None))]}
        record = Export(ResponseStatus.SUCCESS, payload)
        encoded = to_dict(record)
        self.assertEqual(encoded, {
            "status": "success",
            "children": {"nested": [{"status": "timeout", "children": [1, None]}]},
        })
        encoded["children"]["nested"].append("changed")
        self.assertEqual(len(payload["nested"]), 1)
        for unsafe in (object(), Export, Export(ResponseStatus.SUCCESS, object())):
            with self.subTest(unsafe=type(unsafe)), self.assertRaises(TypeError):
                to_dict(unsafe)
        with self.assertRaisesRegex(ValueError, "finite"):
            to_dict(Export(ResponseStatus.SUCCESS, {"number": float("inf")}))

    def test_shared_serializer_rejects_cycles_across_dataclasses_and_containers(self):
        @dataclass
        class Node:
            child: object = None

        node = Node()
        node.child = {"nodes": [node]}
        with self.assertRaisesRegex(ValueError, "circular"):
            to_dict(node)

    def test_unknown_fields_are_rejected_at_each_nested_record(self):
        paths = (
            (), ("action",), ("action", "contract"), ("events", 0),
            ("responses", 0), ("assessment",), ("observations", 0),
            ("verifications", 0), ("verifications", 0, "evidence", 0),
        )
        for path in paths:
            with self.subTest(path=path):
                encoded = sample_trace().to_dict()
                target = encoded
                for key in path:
                    target = target[key]
                target["unexpected"] = "must not disappear"
                with self.assertRaisesRegex(ValueError, "unknown fields"):
                    Trace.from_dict(encoded)

    def test_schema_version_missing_fields_and_invalid_enum_rejected(self):
        encoded = sample_trace().to_dict()
        encoded["schema_version"] = "999.0"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            Trace.from_dict(encoded)
        encoded = sample_trace().to_dict()
        del encoded["action"]["action_id"]
        with self.assertRaisesRegex(ValueError, "missing required"):
            Trace.from_dict(encoded)
        encoded = sample_trace().to_dict()
        encoded["responses"][0]["status"] = "committed"
        with self.assertRaisesRegex(ValueError, "ResponseStatus"):
            Trace.from_dict(encoded)

    def test_decoder_rejects_type_coercions(self):
        mutations = (
            ("trace_id", 42), ("events", ()), ("schema_version", 0.1),
        )
        for key, invalid in mutations:
            with self.subTest(key=key), self.assertRaises(TypeError):
                encoded = sample_trace().to_dict()
                encoded[key] = invalid
                Trace.from_dict(encoded)
        encoded = sample_trace().to_dict()
        encoded["responses"][0]["time_ms"] = True
        with self.assertRaises(TypeError):
            Trace.from_dict(encoded)

    def test_json_duplicate_keys_and_nonfinite_literals_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            Trace.from_json('{"trace_id": "one", "trace_id": "two"}')
        with self.assertRaisesRegex(ValueError, "non-finite"):
            Trace.from_json('{"trace_id": NaN}')
        encoded = sample_trace().to_dict()
        encoded["action"]["arguments"]["number"] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite"):
            Trace.from_json(json.dumps(encoded))

    def test_identity_and_duplicate_integrity_validation(self):
        trace = sample_trace()
        with self.assertRaisesRegex(ValueError, "action.trace_id"):
            replace(trace, trace_id="other-trace")
        with self.assertRaisesRegex(ValueError, "event.trace_id"):
            replace(trace, events=(replace(trace.events[0], trace_id="other-trace"),))
        with self.assertRaisesRegex(ValueError, "unique id"):
            replace(trace, events=trace.events + (trace.events[0],))
        with self.assertRaisesRegex(ValueError, "unique attempt_id"):
            replace(trace, responses=trace.responses + trace.responses)
        with self.assertRaisesRegex(ValueError, "unique observation_id"):
            replace(trace, observations=trace.observations + trace.observations)
        with self.assertRaisesRegex(ValueError, "contract_id"):
            replace(trace, verifications=(replace(trace.verifications[0], contract_id="other-contract"),))

    def test_relational_statuses_cannot_collapse_into_one_enum(self):
        with self.assertRaises(TypeError):
            ToolResponse("attempt", VerificationStatus.SATISFIED, 0, "request")
        with self.assertRaises(TypeError):
            AgentAssessment(ResponseStatus.SUCCESS, 0)
        with self.assertRaises(TypeError):
            Event("e", "t", "user_input", 0)
        verification = sample_trace().verifications[0]
        with self.assertRaisesRegex(ValueError, "subset"):
            replace(verification, attributable_effect_ids=("unobserved-effect",))

    def test_trace_rejects_missing_parent_and_assessment_event_references(self):
        trace = sample_trace()
        with self.assertRaisesRegex(ValueError, "parent_ids.*missing"):
            replace(trace, events=trace.events + (
                Event("orphan", trace.trace_id, EventType.RETRIEVAL, 0, parent_ids=("missing",)),
            ))
        with self.assertRaisesRegex(ValueError, "evidence_event_ids.*missing"):
            replace(trace, assessment=replace(trace.assessment, evidence_event_ids=("missing",)))

    def test_trace_rejects_indirect_dependency_cycles(self):
        trace = sample_trace()
        cyclic = (
            Event("a", trace.trace_id, EventType.USER_INPUT, 0, parent_ids=("b",)),
            Event("b", trace.trace_id, EventType.RETRIEVAL, 0, parent_ids=("a",)),
        )
        with self.assertRaisesRegex(ValueError, "acyclic"):
            replace(trace, events=cyclic, assessment=AgentAssessment(AssessmentStatus.UNKNOWN, 0))

    def test_long_acyclic_dependencies_and_empty_manual_trace_are_valid(self):
        trace = sample_trace()
        events = tuple(
            Event(f"e-{index}", trace.trace_id, EventType.RETRIEVAL, index,
                  parent_ids=(f"e-{index - 1}",) if index else ())
            for index in range(1500)
        )
        assessment = AgentAssessment(AssessmentStatus.UNKNOWN, 1500)
        self.assertEqual(len(replace(trace, events=events, assessment=assessment).events), 1500)
        manual = replace(trace, events=(), responses=(), assessment=assessment,
                         observations=(), verifications=())
        self.assertEqual(Trace.from_json(manual.to_json()), manual)

    def test_verification_evidence_must_resolve_to_coherent_observations(self):
        trace = sample_trace()
        verification = trace.verifications[0]
        evidence = verification.evidence[0]
        for changes, message in (
            ({"observation_id": "missing"}, "missing observation_id"),
            ({"source": "other_source"}, "evidence.source"),
            ({"as_of_ms": 14}, "evidence.as_of_ms"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                replace(trace, verifications=(replace(verification, evidence=(replace(evidence, **changes),)),))
        later = replace(trace.observations[0], observed_at_ms=20)
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            replace(trace, observations=(later,))
        # A verifier may aggregate evidence later than it was observed.
        self.assertEqual(replace(trace, verifications=(replace(verification, observed_at_ms=20),))
                         .verifications[0].observed_at_ms, 20)

    def test_verification_requires_evidence_even_for_unknown_outcomes(self):
        verification = sample_trace().verifications[0]
        with self.assertRaisesRegex(ValueError, "evidence.*empty"):
            replace(verification, evidence=())
        with self.assertRaisesRegex(ValueError, "as_of_ms"):
            replace(verification, observed_at_ms=14)

    def test_origin_links_are_consistent_without_conflating_outcome_status(self):
        verification = sample_trace().verifications[0]
        with self.assertRaisesRegex(ValueError, "confirmed origin"):
            replace(verification, attributable_effect_ids=())
        for origin in (OriginStatus.UNKNOWN, OriginStatus.OTHER_ACTOR):
            with self.subTest(origin=origin), self.assertRaisesRegex(ValueError, "require confirmed"):
                replace(verification, origin=origin)
        with self.assertRaisesRegex(ValueError, "requires observed effect_ids"):
            replace(verification, origin=OriginStatus.OTHER_ACTOR,
                    effect_ids=(), attributable_effect_ids=())
        unknown_origin = replace(verification, origin=OriginStatus.UNKNOWN,
                                 attributable_effect_ids=())
        self.assertIs(unknown_origin.status, VerificationStatus.SATISFIED)
        violated = replace(verification, status=VerificationStatus.VIOLATED)
        self.assertIs(violated.origin, OriginStatus.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
