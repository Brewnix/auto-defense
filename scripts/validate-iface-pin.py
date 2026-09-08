#!/usr/bin/env python3
"""Validate the pinned Brewnix/inference-iface schemas + examples.

Fails if the git submodule pin is missing, if Draft 2020-12 schemas are
invalid, or if pin examples do not validate against schemas/*.v0.json.

Does not fetch https://fyberlabs.com/schemas/* — $id URIs map to sibling
files under vendor/inference-iface/schemas/ (never weaken or fork those
locks).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "vendor" / "inference-iface"
SCHEMAS = PIN / "schemas"
EXAMPLES = PIN / "examples"
GITMODULES = ROOT / ".gitmodules"

EXPECTED_SCHEMA_FILES = (
    "common.v0.json",
    "feature_bundle.v0.json",
    "inference_iface.v0.json",
    "receipt.v0.json",
)

SCHEMA_CONST = {
    "fyber.inference_iface/v0": "https://fyberlabs.com/schemas/fyber.inference_iface/v0",
    "fyber.receipt/v0": "https://fyberlabs.com/schemas/fyber.receipt/v0",
}

FEATURE_BUNDLE_ID = "https://fyberlabs.com/schemas/fyber.feature_bundle/v0"

DOCS_THAT_MUST_CITE_SHA = (
    ROOT / "README.md",
    ROOT / "docs" / "slice-0-inventory.md",
)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def pin_sha() -> str:
    if not PIN.is_dir():
        fail(f"pin missing: {PIN} is not a directory")
    git_marker = PIN / ".git"
    if not git_marker.exists():
        fail(
            f"pin missing: {PIN}/.git not found "
            "(clone with --recurse-submodules or git submodule update --init)"
        )
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(PIN), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        fail(f"cannot resolve pin SHA in {PIN}: {exc}")
    if not sha:
        fail("empty pin SHA")
    return sha


def require_pin_layout() -> None:
    if not GITMODULES.is_file():
        fail(".gitmodules missing — inference-iface pin is not recorded")
    text = GITMODULES.read_text(encoding="utf-8")
    if "vendor/inference-iface" not in text:
        fail(".gitmodules does not record vendor/inference-iface")
    if "Brewnix/inference-iface" not in text:
        fail(".gitmodules must point at Brewnix/inference-iface (no fork)")
    if not SCHEMAS.is_dir():
        fail(f"pin missing schemas/: {SCHEMAS}")
    if not EXAMPLES.is_dir():
        fail(f"pin missing examples/: {EXAMPLES}")
    missing = [name for name in EXPECTED_SCHEMA_FILES if not (SCHEMAS / name).is_file()]
    if missing:
        fail(f"pin missing schema file(s): {', '.join(missing)}")


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON {path}: {exc}")


def build_registry() -> Registry:
    registry: Registry = Registry()
    for path in sorted(SCHEMAS.glob("*.v0.json")):
        contents = load_json(path)
        if not isinstance(contents, dict) or "$id" not in contents:
            fail(f"{path} is not a schema object with $id")
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(contents["$id"], resource)
    return registry


def validate_metaschemas() -> int:
    count = 0
    for name in EXPECTED_SCHEMA_FILES:
        path = SCHEMAS / name
        schema = load_json(path)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            fail(f"schema invalid {path}: {exc}")
        print(f"ok schema {path.relative_to(ROOT)}")
        count += 1
    return count


def validator_for(schema_id: str, registry: Registry) -> Draft202012Validator:
    retrieved = registry.get_or_retrieve(schema_id)
    return Draft202012Validator(retrieved.value.contents, registry=registry)


def validate_instance(
    instance: object,
    schema_id: str,
    registry: Registry,
    label: str,
) -> None:
    try:
        validator_for(schema_id, registry).validate(instance)
    except ValidationError as exc:
        fail(f"{label} failed {schema_id}: {exc.message}")
    print(f"ok example {label} → {schema_id}")


def walk_and_validate(obj: object, registry: Registry, label: str) -> int:
    found = 0
    if isinstance(obj, dict):
        const = obj.get("schema")
        if isinstance(const, str) and const in SCHEMA_CONST:
            validate_instance(obj, SCHEMA_CONST[const], registry, label)
            found += 1
        for key, value in obj.items():
            found += walk_and_validate(value, registry, f"{label}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            found += walk_and_validate(value, registry, f"{label}[{i}]")
    return found


def validate_examples(registry: Registry) -> int:
    count = 0
    paths = sorted(EXAMPLES.glob("*.json"))
    if not paths:
        fail(f"no examples under {EXAMPLES}")
    for path in paths:
        data = load_json(path)
        rel = str(path.relative_to(ROOT))
        if path.name == "feature_bundle.example.json":
            validate_instance(data, FEATURE_BUNDLE_ID, registry, rel)
            count += 1
            continue
        found = walk_and_validate(data, registry, rel)
        if found == 0:
            print(f"ok json {rel} (no schemas/*.v0.json instance; parsed only)")
        else:
            count += found
    return count


def require_docs_cite_sha(sha: str) -> None:
    short = sha[:12]
    for path in DOCS_THAT_MUST_CITE_SHA:
        if not path.is_file():
            fail(f"missing {path.relative_to(ROOT)}")
        text = path.read_text(encoding="utf-8")
        if sha not in text and short not in text:
            fail(
                f"{path.relative_to(ROOT)} must document pin SHA {sha} "
                f"(or prefix {short})"
            )
        print(f"ok docs cite pin SHA in {path.relative_to(ROOT)}")


def main() -> None:
    require_pin_layout()
    sha = pin_sha()
    print(f"pin Brewnix/inference-iface @ {sha}")
    require_docs_cite_sha(sha)
    registry = build_registry()
    n_schemas = validate_metaschemas()
    n_examples = validate_examples(registry)
    print(
        f"slice-0 pin OK: {n_schemas} schemas, "
        f"{n_examples} schema-backed example instance(s)"
    )


if __name__ == "__main__":
    main()
