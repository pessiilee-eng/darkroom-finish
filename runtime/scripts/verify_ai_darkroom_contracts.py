from __future__ import annotations


import hashlib


import json


import math


import re


import sys


from copy import deepcopy


from fractions import Fraction


from pathlib import Path


from typing import Any


from urllib.parse import urldefrag, urljoin


ROOT = Path(__file__).resolve().parents[1]


SCHEMA_PATHS = {
    "formula": ROOT / "schemas/formula-dsl-v1.schema.json",
    "lookup": ROOT / "schemas/formula-lookup-table-v1.schema.json",
    "card": ROOT / "schemas/technique-card-v1.schema.json",
}


class SchemaValidationError(ValueError):
    """A local JSON Schema validation failure with a stable instance path."""


class LocalDraft202012Validator:
    """Dependency-free interpreter for the Draft 2020-12 subset used here.

    The implementation deliberately consumes the checked-in schemas instead of
    duplicating their field contracts in Python. Unsupported validation
    keywords fail closed so a future schema extension cannot silently bypass
    the verifier.
    """

    VALIDATION_KEYWORDS = {
        "$ref", "type", "properties", "required", "additionalProperties",
        "const", "enum", "pattern", "minLength", "maxLength", "minimum",
        "maximum", "minItems", "maxItems", "uniqueItems", "items", "oneOf",
        "allOf", "if", "then", "else", "not",
    }
    ANNOTATION_KEYWORDS = {"$schema", "$id", "$defs", "title", "description"}

    def __init__(self, schemas: dict[str, Any]):
        self.registry: dict[str, Any] = {}
        for name, schema in schemas.items():
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                raise AssertionError(f"schema {name} is not Draft 2020-12")
            schema_id = schema.get("$id")
            if not isinstance(schema_id, str):
                raise AssertionError(f"schema {name} has no absolute $id")
            self.registry[schema_id] = schema
        self._assert_supported_schemas()

    def _assert_supported_schemas(self) -> None:
        def visit(schema: Any, path: str) -> None:
            if isinstance(schema, bool):
                return
            if not isinstance(schema, dict):
                raise AssertionError(f"schema node is not an object at {path}")
            unknown = set(schema) - self.VALIDATION_KEYWORDS - self.ANNOTATION_KEYWORDS
            if unknown:
                raise AssertionError(f"unsupported JSON Schema keyword(s) at {path}: {sorted(unknown)}")

            for key in ("$schema", "$id", "title", "description", "$ref", "pattern"):
                if key in schema and not isinstance(schema[key], str):
                    raise AssertionError(f"JSON Schema keyword {key} must be a string at {path}")
            if "pattern" in schema:
                try:
                    re.compile(schema["pattern"])
                except re.error as exc:
                    raise AssertionError(f"invalid JSON Schema regex at {path}: {exc}") from exc

            if "type" in schema:
                type_value = schema["type"]
                types = type_value if isinstance(type_value, list) else [type_value]
                allowed_types = {"null", "object", "array", "string", "boolean", "integer", "number"}
                if (
                    not types
                    or any(not isinstance(item, str) or item not in allowed_types for item in types)
                    or len(types) != len(set(types))
                ):
                    raise AssertionError(f"invalid JSON Schema type declaration at {path}")
            for key in ("properties", "$defs"):
                if key in schema and not isinstance(schema[key], dict):
                    raise AssertionError(f"JSON Schema keyword {key} must be an object at {path}")
            if "required" in schema:
                required = schema["required"]
                if (
                    not isinstance(required, list)
                    or any(not isinstance(item, str) for item in required)
                    or len(required) != len(set(required))
                ):
                    raise AssertionError(f"invalid JSON Schema required list at {path}")
            if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], (bool, dict)):
                raise AssertionError(f"additionalProperties must be boolean or schema at {path}")
            if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
                raise AssertionError(f"enum must be a non-empty array at {path}")
            for key in ("minLength", "maxLength", "minItems", "maxItems"):
                if key in schema and (type(schema[key]) is not int or schema[key] < 0):
                    raise AssertionError(f"JSON Schema keyword {key} must be a non-negative integer at {path}")
            for key in ("minimum", "maximum"):
                value = schema.get(key)
                if key in schema and (
                    not isinstance(value, (int, float))
                    or type(value) is bool
                    or not math.isfinite(value)
                ):
                    raise AssertionError(f"JSON Schema keyword {key} must be a finite number at {path}")
            if "uniqueItems" in schema and type(schema["uniqueItems"]) is not bool:
                raise AssertionError(f"uniqueItems must be boolean at {path}")
            if "items" in schema and not isinstance(schema["items"], (bool, dict)):
                raise AssertionError(f"items must be a schema at {path}")
            for key in ("oneOf", "allOf"):
                value = schema.get(key)
                if key in schema and (
                    not isinstance(value, list)
                    or not value
                    or any(not isinstance(item, (bool, dict)) for item in value)
                ):
                    raise AssertionError(f"JSON Schema keyword {key} must be a non-empty schema array at {path}")
            for key in ("not", "if", "then", "else"):
                if key in schema and not isinstance(schema[key], (bool, dict)):
                    raise AssertionError(f"JSON Schema keyword {key} must be a schema at {path}")
            if ("then" in schema or "else" in schema) and "if" not in schema:
                raise AssertionError(f"then/else requires if at {path}")

            for key in ("properties", "$defs"):
                for child_name, child in schema.get(key, {}).items():
                    visit(child, f"{path}/{key}/{child_name}")
            for key in ("items", "additionalProperties", "not", "if", "then", "else"):
                child = schema.get(key)
                if isinstance(child, (dict, bool)):
                    visit(child, f"{path}/{key}")
            for key in ("oneOf", "allOf"):
                for index, child in enumerate(schema.get(key, [])):
                    visit(child, f"{path}/{key}/{index}")

        for schema_id, schema in self.registry.items():
            visit(schema, schema_id)

    @staticmethod
    def _json_equal(left: Any, right: Any) -> bool:
        try:
            return jcs_bytes(left) == jcs_bytes(right)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _matches_type(instance: Any, expected: str) -> bool:
        return {
            "null": instance is None,
            "object": isinstance(instance, dict),
            "array": isinstance(instance, list),
            "string": isinstance(instance, str),
            "boolean": type(instance) is bool,
            "integer": isinstance(instance, int) and type(instance) is not bool,
            "number": isinstance(instance, (int, float)) and type(instance) is not bool,
        }.get(expected, False)

    def _resolve_ref(self, ref: str, base_uri: str) -> tuple[Any, str]:
        absolute = urljoin(base_uri, ref)
        document_uri, fragment = urldefrag(absolute)
        if document_uri not in self.registry:
            raise AssertionError(f"unregistered local schema reference: {absolute}")
        target = self.registry[document_uri]
        if fragment:
            if not fragment.startswith("/"):
                raise AssertionError(f"unsupported JSON Pointer fragment: {absolute}")
            for raw_part in fragment[1:].split("/"):
                part = raw_part.replace("~1", "/").replace("~0", "~")
                if not isinstance(target, dict) or part not in target:
                    raise AssertionError(f"unresolvable JSON Pointer: {absolute}")
                target = target[part]
        return target, document_uri

    def validate(self, instance: Any, schema: Any, *, base_uri: str, path: str = "$") -> None:
        self._validate(instance, schema, base_uri, path)

    def _is_valid(self, instance: Any, schema: Any, base_uri: str, path: str) -> bool:
        try:
            self._validate(instance, schema, base_uri, path)
            return True
        except SchemaValidationError:
            return False

    def _validate(self, instance: Any, schema: Any, base_uri: str, path: str) -> None:
        if schema is True:
            return
        if schema is False:
            raise SchemaValidationError(f"{path}: false schema")
        if not isinstance(schema, dict):
            raise AssertionError(f"invalid schema node at {path}")

        if "$ref" in schema:
            ref_schema, ref_base = self._resolve_ref(schema["$ref"], base_uri)
            self._validate(instance, ref_schema, ref_base, path)

        expected_type = schema.get("type")
        if expected_type is not None:
            options = expected_type if isinstance(expected_type, list) else [expected_type]
            if not any(self._matches_type(instance, option) for option in options):
                raise SchemaValidationError(f"{path}: expected type {expected_type}")

        if "const" in schema and not self._json_equal(instance, schema["const"]):
            raise SchemaValidationError(f"{path}: const mismatch")
        if "enum" in schema and not any(self._json_equal(instance, item) for item in schema["enum"]):
            raise SchemaValidationError(f"{path}: enum mismatch")

        if isinstance(instance, str):
            if "minLength" in schema and len(instance) < schema["minLength"]:
                raise SchemaValidationError(f"{path}: minLength")
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                raise SchemaValidationError(f"{path}: maxLength")
            if "pattern" in schema and re.search(schema["pattern"], instance) is None:
                raise SchemaValidationError(f"{path}: pattern")

        if isinstance(instance, (int, float)) and type(instance) is not bool:
            if "minimum" in schema and instance < schema["minimum"]:
                raise SchemaValidationError(f"{path}: minimum")
            if "maximum" in schema and instance > schema["maximum"]:
                raise SchemaValidationError(f"{path}: maximum")

        if isinstance(instance, list):
            if "minItems" in schema and len(instance) < schema["minItems"]:
                raise SchemaValidationError(f"{path}: minItems")
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                raise SchemaValidationError(f"{path}: maxItems")
            if schema.get("uniqueItems"):
                encoded = [jcs_bytes(item) for item in instance]
                if len(encoded) != len(set(encoded)):
                    raise SchemaValidationError(f"{path}: uniqueItems")
            if "items" in schema:
                for index, item in enumerate(instance):
                    self._validate(item, schema["items"], base_uri, f"{path}[{index}]")

        if isinstance(instance, dict):
            required = schema.get("required", [])
            missing = [key for key in required if key not in instance]
            if missing:
                raise SchemaValidationError(f"{path}: missing required {missing}")
            properties = schema.get("properties", {})
            for key, child_schema in properties.items():
                if key in instance:
                    self._validate(instance[key], child_schema, base_uri, f"{path}.{key}")
            extras = set(instance) - set(properties)
            additional = schema.get("additionalProperties", True)
            if additional is False and extras:
                raise SchemaValidationError(f"{path}: additional properties {sorted(extras)}")
            if isinstance(additional, dict):
                for key in extras:
                    self._validate(instance[key], additional, base_uri, f"{path}.{key}")

        if "allOf" in schema:
            for index, child_schema in enumerate(schema["allOf"]):
                self._validate(instance, child_schema, base_uri, f"{path}<allOf:{index}>")
        if "oneOf" in schema:
            matches = sum(self._is_valid(instance, child, base_uri, path) for child in schema["oneOf"])
            if matches != 1:
                raise SchemaValidationError(f"{path}: oneOf matched {matches} branches")
        if "not" in schema and self._is_valid(instance, schema["not"], base_uri, path):
            raise SchemaValidationError(f"{path}: not schema matched")
        if "if" in schema:
            branch = "then" if self._is_valid(instance, schema["if"], base_uri, path) else "else"
            if branch in schema:
                self._validate(instance, schema[branch], base_uri, f"{path}<{branch}>")


def jcs_bytes(value: Any) -> bytes:
    """RFC 8785-compatible encoding for this contract's restricted JSON domain."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_jcs(value: Any) -> str:
    return hashlib.sha256(jcs_bytes(value)).hexdigest()

