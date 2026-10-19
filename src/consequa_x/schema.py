"""Versioned JSON Schema and strict trace decoding, using the standard library.

The portable schema validates the JSON representation of records. Relationships
between different records, such as dependency cycles and matching observation
references, are checked by :func:`validate_trace` and the ``Trace`` constructor.
JSON Schema alone cannot express these cross-record constraints.
"""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from importlib.resources import files
import json
import types
from typing import Any, get_args, get_origin, get_type_hints

from .errors import ConsequaTypeError, SchemaVersionError
from .models import SCHEMA_VERSION, Trace, to_dict


def _check_version(version: str) -> None:
    if type(version) is not str:
        raise ConsequaTypeError("schema version must be a string")
    if version != SCHEMA_VERSION:
        raise SchemaVersionError(f"unsupported schema_version: {version!r}")


def generate_trace_schema(version: str = SCHEMA_VERSION) -> dict[str, Any]:
    """Derive Draft 2020-12 structure from the versioned record dataclasses.

    This function is also used to generate the packaged JSON artifact. Each call
    returns an independent dictionary. Arbitrary contract payloads remain strict
    JSON values; this schema does not claim to verify domain postconditions.
    """
    _check_version(version)
    definitions: dict[str, Any] = {
        "JSONValue": {
            "description": "A JSON value; JSON numbers must be finite.",
            "anyOf": [
                {"type": "null"},
                {"type": "boolean"},
                {"type": "number"},
                {"type": "string"},
                {"type": "array", "items": {"$ref": "#/$defs/JSONValue"}},
                {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/JSONValue"},
                },
            ],
        },
    }

    def field_schema(annotation: Any, name: str) -> dict[str, Any]:
        origin = get_origin(annotation)
        arguments = get_args(annotation)
        if origin is types.UnionType:
            return {"anyOf": [field_schema(item, name) for item in arguments]}
        if annotation is type(None):
            return {"type": "null"}
        if origin is dict:
            return {"type": "object", "additionalProperties": {"$ref": "#/$defs/JSONValue"}}
        if origin is tuple:
            result = {"type": "array", "items": field_schema(arguments[0], name)}
            if arguments[0] is str:
                result["uniqueItems"] = True
            if name == "evidence":
                result["minItems"] = 1
            return result
        if isinstance(annotation, type) and is_dataclass(annotation):
            record_schema(annotation)
            return {"$ref": f"#/$defs/{annotation.__name__}"}
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return {"type": "string", "enum": [item.value for item in annotation]}
        if annotation is str:
            result = {"type": "string"}
            if name not in {"rationale", "reason"}:
                result["pattern"] = r"\S"
            if name == "schema_version":
                result["const"] = version
            return result
        if annotation is int:
            return {"type": "integer", "minimum": 0}
        if annotation is bool:
            return {"type": "boolean"}
        raise ConsequaTypeError(f"unsupported schema field type: {annotation!r}")

    def record_schema(record_type: type) -> None:
        name = record_type.__name__
        if name in definitions:
            return
        definition: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
        definitions[name] = definition
        annotations = get_type_hints(record_type)
        for item in fields(record_type):
            property_schema = field_schema(annotations[item.name], item.name)
            if item.default is not MISSING:
                property_schema["default"] = to_dict(item.default)
            elif item.default_factory is not MISSING:
                property_schema["default"] = to_dict(item.default_factory())
            else:
                definition["required"].append(item.name)
            definition["properties"][item.name] = property_schema
        if name == "VerificationResult":
            definition["allOf"] = [
                {
                    "if": {"properties": {"origin": {"const": "confirmed"}}, "required": ["origin"]},
                    "then": {
                        "properties": {"attributable_effect_ids": {"minItems": 1}},
                        "required": ["attributable_effect_ids"],
                    },
                    "else": {"properties": {"attributable_effect_ids": {"maxItems": 0}}},
                },
                {
                    "if": {"properties": {"origin": {"const": "other_actor"}}, "required": ["origin"]},
                    "then": {
                        "properties": {"effect_ids": {"minItems": 1}},
                        "required": ["effect_ids"],
                    },
                },
            ]
        if name == "Trace":
            definition["description"] = (
                "A trace holds one or more actions. Responses, assessments and verifications name "
                "a declared action; identities are unique and each action has its own contract. "
                "Event and assessment references must resolve; event dependencies must be acyclic. "
                "Verification evidence must resolve to observations with matching source and watermark. "
                "Validate these relationships with consequa_x.schema.validate_trace; JSON Schema "
                "covers record structure only."
            )

    record_schema(Trace)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:consequa-x:trace:{version}",
        "title": f"ConseqaX Trace v{version}",
        "description": "Public evidence-aware trace. Evaluator-only simulator truth is excluded.",
        "$ref": "#/$defs/Trace",
        "$defs": definitions,
    }


def get_trace_schema(version: str = SCHEMA_VERSION) -> dict[str, Any]:
    """Read an isolated copy of the JSON Schema bundled in the installed package."""
    _check_version(version)
    resource = files("consequa_x").joinpath("schemas", f"trace-v{version}.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_trace(value: dict[str, Any] | str) -> Trace:
    """Strictly decode JSON data and validate structure and record relationships.

    This has no ``jsonschema`` runtime dependency. It returns the typed trace
    rather than coercing fields or discarding unsupported keys. JSON strings
    additionally reject duplicate object keys and non-finite number literals.
    """
    return Trace.from_json(value) if type(value) is str else Trace.from_dict(value)
