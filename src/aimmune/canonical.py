"""Canonical JSON + SHA-256 digests (iface: omit integrity when hashing receipts)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_digest(obj: Any) -> str:
    digest = hashlib.sha256(canonical_dumps(obj).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def features_digest(bundle: dict[str, Any]) -> str:
    return sha256_digest(bundle)


def receipt_body_hash(receipt: dict[str, Any]) -> str:
    body = {key: value for key, value in receipt.items() if key != "integrity"}
    return sha256_digest(body)


def rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")
