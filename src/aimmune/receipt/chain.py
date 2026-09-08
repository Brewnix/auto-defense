"""Append-only fyber.receipt/v0 JSONL hash chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from aimmune.canonical import receipt_body_hash, rfc3339
from aimmune.store import append_jsonl, read_jsonl


def build_receipt(
    *,
    site_id: str,
    trace_id: str,
    ts,
    purpose: str,
    posture: dict[str, Any],
    features_digest: str,
    window_s: int,
    judgment: dict[str, Any],
    actor: dict[str, Any],
    proposals: list[dict[str, Any]],
    policy_decision: str,
    policy_rule_ids: list[str],
    execution: list[dict[str, Any]],
    human_required: bool,
    prev_hash: str | None,
    parent_id: str | None = None,
    receipt_id: str | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": "fyber.receipt/v0",
        "receipt_id": receipt_id or str(uuid4()),
        "parent_id": parent_id,
        "site_id": site_id,
        "trace_id": trace_id,
        "ts": rfc3339(ts) if not isinstance(ts, str) else ts,
        "door": "site_defense",
        "purpose": purpose,
        "posture": posture,
        "input": {
            "sources": sources or ["suricata", "opnsense"],
            "features_digest": features_digest,
            "window_s": window_s,
        },
        "judgment": judgment,
        "actor": actor,
        "proposals": proposals,
        "policy": {
            "engine": "brewnix-policy/v0",
            "decision": policy_decision,
            "rule_ids": policy_rule_ids,
        },
        "execution": execution,
        "human": {
            "required": human_required,
            "resolved_by": None,
            "resolved_at": None,
            "resolution": None,
        },
    }
    receipt["integrity"] = {
        "body_hash": receipt_body_hash(receipt),
        "prev_hash": prev_hash,
        "sig": None,
    }
    return receipt


def verify_chain(receipts: list[dict[str, Any]]) -> None:
    prev: str | None = None
    for i, receipt in enumerate(receipts):
        integrity = receipt.get("integrity") or {}
        expected = receipt_body_hash(receipt)
        actual = integrity.get("body_hash")
        if actual != expected:
            raise ValueError(f"receipt[{i}] body_hash mismatch")
        if integrity.get("prev_hash") != prev:
            raise ValueError(f"receipt[{i}] prev_hash broken")
        prev = actual


class ReceiptChain:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        return read_jsonl(self.path)

    def tip_hash(self) -> str | None:
        rows = self.load()
        if not rows:
            return None
        return (rows[-1].get("integrity") or {}).get("body_hash")

    def append(self, receipt: dict[str, Any]) -> dict[str, Any]:
        append_jsonl(self.path, receipt)
        return receipt
