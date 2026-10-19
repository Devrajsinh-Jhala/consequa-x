from dataclasses import FrozenInstanceError, dataclass, replace
import json
import unittest

from consequa_x.errors import ConsequaTypeError
from consequa_x.models import (
    FrozenDict, FrozenList,
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
    TimeBase, Trace,
    VerificationResult,
    VerificationStatus,
    to_dict,
)


def sample_trace() -> Trace:
    contract = OutcomeContract(
        contract_id="contract-1", predicate="refund_processed",
        expected={"payment_id": "pay_42", "amount_minor": 500_000, "currency": "INR"},
        deadline_ms=10, stability_ms=5,
    )
    action = Action(
        action_id="action-1", actor="agent", name="refund", arguments=dict(contract.expected), registered_at_ms=0,
        contract=contract, idempotency_key="refund-order-1",
    )
    events = (
        Event(id="context-1", type=EventType.USER_INPUT, time_ms=0, data={"text": "Refund ₹5,000"}),
        Event(id="dispatch-1", type=EventType.ACTION_DISPATCH, time_ms=1, actor="agent", parent_ids=("context-1",)),
        Event(id="response-1", type=EventType.TOOL_RESPONSE, time_ms=2, parent_ids=("dispatch-1",)),
    )
    response = ToolResponse(attempt_id="attempt-1", status=ResponseStatus.TIMEOUT, time_ms=2, provider_request_id="provider-request-1", action_id="action-1")
    observation = Observation(
        observation_id="observation-1", source="refund_readback", observed_at_ms=15, as_of_ms=15, scope={"payment_id": "pay_42"},
        records=({"effect_id": "effect-1", **contract.expected, "committed_at_ms": 1, "status": "processed"},),
    )
    verification = VerificationResult(
        contract_id="contract-1", status=VerificationStatus.SATISFIED, observed_at_ms=15,
        evidence=(Evidence(observation_id="observation-1", source="refund_readback", as_of_ms=15, details={"effect_id": "effect-1"}),),
        origin=OriginStatus.CONFIRMED, effect_ids=("effect-1",), attributable_effect_ids=("effect-1",), reason="Independent readback confirms refund", action_id="action-1",
    )
    return Trace(
        trace_id="trace-1", time_base=TimeBase.RELATIVE_MS, actions=(action,), events=events, responses=(response,),
        assessments=(AgentAssessment(status=AssessmentStatus.FAILURE, time_ms=2, evidence_event_ids=("response-1",), rationale="No acknowledgement", assessment_id="assessment-1", action_id="action-1"),),
        observations=(observation,), verifications=(verification,),
    )


class ModelTests(unittest.TestCase):
    def test_complete_trace_round_trip_preserves_types_and_identifiers(self):
        original = sample_trace()
        exported = original.to_dict()
        self.assertEqual(exported["events"][0]["type"], "user_input")
        self.assertEqual(exported["schema_version"], "1.0")
        self.assertEqual(exported["time_base"], "relative_ms")
        self.assertIsInstance(exported["observations"][0]["records"], list)
        for restored in (Trace.from_dict(exported), Trace.from_json(original.to_json(indent=2))):
            with self.subTest(method=type(restored)):
                self.assertEqual(restored, original)
                self.assertIs(restored.events[0].type, EventType.USER_INPUT)
                self.assertIs(restored.responses[0].status, ResponseStatus.TIMEOUT)
                self.assertIs(restored.latest_assessment().status, AssessmentStatus.FAILURE)
                self.assertIs(restored.time_base, TimeBase.RELATIVE_MS)
                self.assertIs(restored.verifications[0].status, VerificationStatus.SATISFIED)
                self.assertIs(restored.verifications[0].origin, OriginStatus.CONFIRMED)
                self.assertIsInstance(restored.observations, tuple)
                self.assertIsInstance(restored.observations[0].records, tuple)
                self.assertIsInstance(restored.verifications[0].evidence[0], Evidence)
                self.assertEqual(restored.single_action.action_id, "action-1")
                self.assertEqual(restored.responses[0].attempt_id, "attempt-1")
                self.assertEqual(restored.responses[0].provider_request_id, "provider-request-1")
                self.assertEqual(restored.verifications[0].effect_ids, ("effect-1",))

    def test_contract_horizon_and_optional_count(self):
        contract = sample_trace().single_action.contract
        self.assertEqual(contract.horizon_ms, 15)
        self.assertIsNone(replace(contract, exact_count=None).exact_count)
        self.assertEqual(replace(contract, exact_count=0).exact_count, 0)

    def test_constructor_and_exports_do_not_alias_input_payloads(self):
        payload = {"nested": {"values": [1, None, True, 1.25]}}
        event = Event(id="e", type=EventType.USER_INPUT, time_ms=0, data=payload)
        payload["nested"]["values"].append(2)
        exported = event.to_dict()
        exported["data"]["nested"]["values"].append(3)
        self.assertEqual(event.data["nested"]["values"], [1, None, True, 1.25])
        with self.assertRaises(FrozenInstanceError):
            event.id = "changed"

    def test_invalid_time_values_and_future_watermarks_are_rejected(self):
        for invalid in (-1, True, 1.5, "1"):
            with self.subTest(invalid=invalid), self.assertRaises((TypeError, ValueError)):
                Event(id="e", type=EventType.USER_INPUT, time_ms=invalid)
        with self.assertRaisesRegex(ValueError, "as_of_ms"):
            Observation(observation_id="o", source="readback", observed_at_ms=1, as_of_ms=2, scope={})
        with self.assertRaises(TypeError):
            Observation(observation_id="o", source="readback", observed_at_ms=1, as_of_ms=1, scope={}, complete=1)

    def test_json_payload_rejects_non_json_values_and_cycles(self):
        for invalid in (float("nan"), float("inf"), {1, 2}, b"secret", object(), (1, 2)):
            with self.subTest(invalid=type(invalid)), self.assertRaises((TypeError, ValueError)):
                Event(id="e", type=EventType.USER_INPUT, time_ms=0, data={"invalid": invalid})
        with self.assertRaises(TypeError):
            Event(id="e", type=EventType.USER_INPUT, time_ms=0, data={1: "not a JSON key"})
        circular = {}
        circular["self"] = circular
        with self.assertRaisesRegex(ValueError, "circular"):
            Event(id="e", type=EventType.USER_INPUT, time_ms=0, data=circular)

    def test_captured_payloads_are_deeply_read_only(self):
        trace = sample_trace()
        arguments = trace.single_action.arguments
        self.assertIsInstance(arguments, FrozenDict)
        for change in (lambda: arguments.__setitem__("bad", 1), lambda: arguments.pop("x", None),
                       lambda: arguments.update(bad=1), lambda: arguments.clear(),
                       lambda: arguments.setdefault("bad", 1)):
            with self.assertRaisesRegex(ConsequaTypeError, "read-only"):
                change()
        nested = OutcomeContract(contract_id="c", predicate="p", expected={"items": [{"a": 1}]}, deadline_ms=10).expected
        self.assertIsInstance(nested["items"], FrozenList)
        self.assertEqual(nested, {"items": [{"a": 1}]})
        for change in (lambda: nested["items"].append(2), lambda: nested["items"].sort(),
                       lambda: nested["items"].__setitem__(0, 1),
                       lambda: nested["items"][0].__setitem__("a", 2)):
            with self.assertRaises(ConsequaTypeError):
                change()

    def test_read_only_payloads_export_copy_and_pickle_as_plain_json(self):
        import copy
        import pickle

        contract = OutcomeContract(contract_id="c", predicate="p", expected={"items": [{"a": 1}], "n": 2}, deadline_ms=10)
        exported = contract.to_dict()["expected"]
        self.assertIs(type(exported), dict)
        self.assertIs(type(exported["items"]), list)
        exported["items"].append(3)  # Exports are ordinary, independent copies.
        self.assertEqual(contract.expected, {"items": [{"a": 1}], "n": 2})
        self.assertEqual(json.loads(json.dumps(contract.expected)), {"items": [{"a": 1}], "n": 2})
        self.assertIs(copy.deepcopy(contract.expected), contract.expected)
        restored = pickle.loads(pickle.dumps(contract))
        self.assertEqual(restored, contract)
        self.assertIsInstance(restored.expected["items"], FrozenList)

    def test_shared_serializer_rejects_a_payload_changed_by_bypassing_read_only(self):
        trace = sample_trace()
        dict.__setitem__(trace.single_action.arguments, "bad", float("nan"))
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
            (), ("actions", 0), ("actions", 0, "contract"), ("events", 0),
            ("responses", 0), ("assessments", 0), ("observations", 0),
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
        del encoded["actions"][0]["action_id"]
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
        encoded["actions"][0]["arguments"]["number"] = float("inf")
        with self.assertRaisesRegex(ValueError, "finite"):
            Trace.from_json(json.dumps(encoded))

    def test_identity_and_duplicate_integrity_validation(self):
        trace = sample_trace()
        with self.assertRaisesRegex(ValueError, "unique action_id"):
            replace(trace, actions=trace.actions + trace.actions)
        with self.assertRaisesRegex(ValueError, "response.action_id"):
            replace(trace, responses=(replace(trace.responses[0], action_id="other-action"),))
        with self.assertRaisesRegex(ValueError, "verification.action_id"):
            replace(trace, verifications=(replace(trace.verifications[0], action_id="other"),))
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
            ToolResponse(attempt_id="attempt", status=VerificationStatus.SATISFIED, time_ms=0, provider_request_id="request", action_id="action-1")
        with self.assertRaises(TypeError):
            AgentAssessment(status=ResponseStatus.SUCCESS, time_ms=0, assessment_id="assessment-1", action_id="action-1")
        with self.assertRaises(TypeError):
            Event(id="e", type="user_input", time_ms=0)
        verification = sample_trace().verifications[0]
        with self.assertRaisesRegex(ValueError, "subset"):
            replace(verification, attributable_effect_ids=("unobserved-effect",))

    def test_trace_rejects_missing_parent_and_assessment_event_references(self):
        trace = sample_trace()
        with self.assertRaisesRegex(ValueError, "parent_ids.*missing"):
            replace(trace, events=trace.events + (
                Event(id="orphan", type=EventType.RETRIEVAL, time_ms=0, parent_ids=("missing",)),
            ))
        with self.assertRaisesRegex(ValueError, "evidence_event_ids.*missing"):
            replace(trace, assessments=(replace(trace.latest_assessment(), evidence_event_ids=("missing",)),))

    def test_trace_rejects_indirect_dependency_cycles(self):
        trace = sample_trace()
        cyclic = (
            Event(id="a", type=EventType.USER_INPUT, time_ms=0, parent_ids=("b",)),
            Event(id="b", type=EventType.RETRIEVAL, time_ms=0, parent_ids=("a",)),
        )
        with self.assertRaisesRegex(ValueError, "acyclic"):
            replace(trace, events=cyclic, assessments=(AgentAssessment(status=AssessmentStatus.UNKNOWN, time_ms=0, assessment_id="assessment-1", action_id="action-1"),))

    def test_long_acyclic_dependencies_and_empty_manual_trace_are_valid(self):
        trace = sample_trace()
        events = tuple(
            Event(id=f"e-{index}", type=EventType.RETRIEVAL, time_ms=index,
                  parent_ids=(f"e-{index - 1}",) if index else ())
            for index in range(1500)
        )
        assessment = AgentAssessment(status=AssessmentStatus.UNKNOWN, time_ms=1500, assessment_id="assessment-1", action_id="action-1")
        self.assertEqual(len(replace(trace, events=events, assessments=(assessment,)).events), 1500)
        manual = replace(trace, events=(), responses=(), assessments=(assessment,),
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
