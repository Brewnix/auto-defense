"""Validate envelopes / receipts / bundles against the pinned inference-iface schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_IDS = {
    "envelope": "https://fyberlabs.com/schemas/fyber.inference_iface/v0",
    "receipt": "https://fyberlabs.com/schemas/fyber.receipt/v0",
    "bundle": "https://fyberlabs.com/schemas/fyber.feature_bundle/v0",
    "common": "https://fyberlabs.com/schemas/fyber.common/v0",
}


class SchemaValidationError(ValueError):
    pass


@lru_cache(maxsize=8)
def _registry(pin_str: str) -> Registry:
    pin = Path(pin_str)
    registry: Registry = Registry()
    for path in sorted((pin / "schemas").glob("*.v0.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(contents["$id"], resource)
    return registry


def registry_for(pin: Path) -> Registry:
    return _registry(str(pin.resolve()))


def _validator(pin: Path, schema_id: str) -> Draft202012Validator:
    retrieved = registry_for(pin).get_or_retrieve(schema_id)
    return Draft202012Validator(retrieved.value.contents, registry=registry_for(pin))


def validate_instance(instance: object, pin: Path, schema_id: str, label: str) -> None:
    try:
        _validator(pin, schema_id).validate(instance)
    except ValidationError as exc:
        raise SchemaValidationError(f"{label} failed {schema_id}: {exc.message}") from exc


def validate_envelope(envelope: dict[str, Any], pin: Path) -> None:
    validate_instance(envelope, pin, SCHEMA_IDS["envelope"], "envelope")


def validate_receipt(receipt: dict[str, Any], pin: Path) -> None:
    validate_instance(receipt, pin, SCHEMA_IDS["receipt"], "receipt")


def validate_bundle(bundle: dict[str, Any], pin: Path) -> None:
    validate_instance(bundle, pin, SCHEMA_IDS["bundle"], "feature_bundle")


def validate_tool_args(proposal: dict[str, Any], pin: Path) -> None:
    """Validate a ToolCall (unknown tools / extra args fail)."""
    validator = Draft202012Validator(
        {"$ref": f"{SCHEMA_IDS['common']}#/$defs/ToolCall"},
        registry=registry_for(pin),
    )
    try:
        validator.validate(proposal)
    except ValidationError as exc:
        raise SchemaValidationError(f"tool call failed: {exc.message}") from exc
