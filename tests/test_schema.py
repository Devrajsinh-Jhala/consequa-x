"""Portable schema conformance and stricter cross-record trace validation."""

from dataclasses import MISSING, fields, replace
import json
import unittest

from jsonschema import Draft202012Validator

from consequa_x import models
from consequa_x.models import AgentAssessment, AssessmentStatus, Trace
from consequa_x.schema import generate_trace_schema, get_trace_schema, validate_trace
from test_models import sample_trace


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = get_trace_schema()
        self.validator = Draft202012Validator(self.schema)

    def test_packaged_schema_matches_dataclass_generator_and_is_valid(self):
        self.assertEqual(self.schema, generate_trace_schema())
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(self.schema["$id"], "urn:consequa-x:trace:1.0")
        for name, definition in self.schema["$defs"].items():
            if name == "JSONValue":
                continue
            record_type = getattr(models, name)
            self.assertEqual(set(definition["properties"]), {item.name for item in fields(record_type)})
            self.assertEqual(set(definition["required"]), {
                item.name for item in fields(record_type)
                if item.default is MISSING and item.default_factory is MISSING
            })
            self.assertFalse(definition["additionalProperties"])

    def test_schema_copies_and_version_selection_are_isolated(self):
        self.schema["$defs"]["Trace"]["properties"]["trace_id"]["pattern"] = "changed"
        self.assertNotEqual(self.schema, get_trace_schema())
        for function in (get_trace_schema, generate_trace_schema):
            with self.assertRaisesRegex(ValueError, "schema_version"):
                function("0.1")
            with self.assertRaises(TypeError):
                function(1.0)

    def test_complete_trace_and_minimal_manual_trace_validate_and_round_trip(self):
        trace = sample_trace()
        self.validator.validate(trace.to_dict())
        self.assertEqual(validate_trace(trace.to_dict()), trace)
        self.assertEqual(validate_trace(trace.to_json()), trace)
        manual = replace(trace, events=(), responses=(), observations=(), verifications=(),
                         assessments=(AgentAssessment(status=AssessmentStatus.UNKNOWN, time_ms=0, assessment_id="assessment-1", action_id=trace.single_action.action_id),))
        payload = manual.to_dict()
        for field in ("observations", "verifications", "schema_version"):
            payload.pop(field)
        self.validator.validate(payload)
        self.assertEqual(validate_trace(payload), manual)

    def test_schema_rejects_unknown_record_fields_and_missing_required_fields(self):
        paths = (
            (), ("actions", 0), ("actions", 0, "contract"), ("events", 0),
            ("responses", 0), ("assessments", 0), ("observations", 0),
            ("verifications", 0), ("verifications", 0, "evidence", 0),
        )
        for path in paths:
            with self.subTest(path=path):
                payload = sample_trace().to_dict()
                target = payload
                for item in path:
                    target = target[item]
                target["unexpected"] = True
                self.assertFalse(self.validator.is_valid(payload))
                with self.assertRaisesRegex(ValueError, "unknown fields"):
                    validate_trace(payload)
        payload = sample_trace().to_dict()
        del payload["actions"][0]["contract"]["deadline_ms"]
        self.assertFalse(self.validator.is_valid(payload))
        with self.assertRaisesRegex(ValueError, "missing required"):
            validate_trace(payload)

    def test_schema_rejects_structural_type_status_and_origin_errors(self):
        mutations = (
            (("schema_version",), "999"),
            (("trace_id",), "  "),
            (("actions", 0, "registered_at_ms"), True),
            (("events", 0, "time_ms"), -1),
            (("responses", 0, "status"), "satisfied"),
            (("observations", 0, "available"), "true"),
            (("verifications", 0, "evidence"), []),
            (("verifications", 0, "attributable_effect_ids"), []),
            (("verifications", 0, "origin"), "other_actor"),
            (("assessments", 0, "evidence_event_ids"), ["response-1", "response-1"]),
        )
        for path, value in mutations:
            with self.subTest(path=path, value=value):
                payload = sample_trace().to_dict()
                target = payload
                for item in path[:-1]:
                    target = target[item]
                target[path[-1]] = value
                self.assertFalse(self.validator.is_valid(payload))
                with self.assertRaises((TypeError, ValueError)):
                    validate_trace(payload)

    def test_arbitrary_nested_json_payloads_are_valid_but_unsafe_values_are_rejected(self):
        payload = sample_trace().to_dict()
        payload["actions"][0]["arguments"]["metadata"] = {
            "nullable": None, "bool": True, "list": [1, 1.25, "", {"key": []}],
        }
        self.validator.validate(payload)
        self.assertEqual(validate_trace(payload).to_dict(), payload)
        payload["actions"][0]["arguments"]["metadata"]["bad"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_trace(payload)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_trace('{"trace_id":"one","trace_id":"two"}')
        with self.assertRaisesRegex(ValueError, "non-finite"):
            validate_trace('{"trace_id":Infinity}')

    def test_runtime_checks_relationships_outside_json_schema_expressiveness(self):
        mutations = (
            (("assessments", 0, "evidence_event_ids"), ["missing"]),
            (("events", 1, "parent_ids"), ["missing"]),
            (("responses", 0, "action_id"), "undeclared_action"),
            (("verifications", 0, "action_id"), "undeclared_action"),
            (("verifications", 0, "evidence", 0, "observation_id"), "missing"),
            (("verifications", 0, "evidence", 0, "source"), "other_source"),
            (("verifications", 0, "attributable_effect_ids"), ["unobserved"]),
        )
        for path, value in mutations:
            with self.subTest(path=path):
                payload = sample_trace().to_dict()
                target = payload
                for item in path[:-1]:
                    target = target[item]
                target[path[-1]] = value
                self.validator.validate(payload)
                with self.assertRaises(ValueError):
                    validate_trace(payload)

    def test_schema_can_be_exported_as_ordinary_json(self):
        serialized = json.loads(json.dumps(self.schema, allow_nan=False))
        self.assertEqual(serialized, generate_trace_schema())
        self.assertIsInstance(validate_trace(sample_trace().to_dict()), Trace)


if __name__ == "__main__":
    unittest.main()
