#!/usr/bin/env python3
"""Validate technique cards structurally and against the operation registry.

Reuses the project's self-contained Draft 2020-12 validator from
scripts/verify_ai_darkroom_contracts.py. Exit 0 only if every given card passes
both JSON Schema and semantic admission; prints one line per card.
"""

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "scripts"))
from verify_ai_darkroom_contracts import LocalDraft202012Validator, SCHEMA_PATHS  # noqa: E402
from operation_registry import (  # noqa: E402
    OperationRegistryError,
    load_operation_registry,
    semantic_card_errors,
)

CARD_ID = "https://darkroom-finish.local/schemas/technique-card-v1.schema.json"


def load_validator() -> tuple[LocalDraft202012Validator, dict]:
    schemas = {name: json.loads(path.read_text()) for name, path in SCHEMA_PATHS.items()}
    return LocalDraft202012Validator(schemas), schemas


def validate_card(path: Path, validator=None, schemas=None, registry=None) -> list[str]:
    """Return a list of error strings; empty list means valid."""
    if validator is None:
        validator, schemas = load_validator()
    errors = []
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    try:
        validator.validate(card, schemas["card"], base_uri=CARD_ID)
    except Exception as e:  # validator raises AssertionError subclasses
        errors.append(str(e))
        return errors
    try:
        registry = registry or load_operation_registry()
        errors.extend(semantic_card_errors(card, registry))
    except OperationRegistryError as e:
        errors.append(str(e))
    return errors


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        paths = sorted((PROJECT / "knowledge" / "cards").glob("*.json"))
    if not paths:
        print("no cards found", file=sys.stderr)
        return 1
    validator, schemas = load_validator()
    try:
        registry = load_operation_registry()
    except OperationRegistryError as e:
        print(f"FAIL operation registry: {e}", file=sys.stderr)
        return 1
    failed = 0
    for p in paths:
        errs = validate_card(p, validator, schemas, registry)
        if errs:
            failed += 1
            print(f"FAIL {p.name}: {'; '.join(errs)}")
        else:
            print(f"PASS {p.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
