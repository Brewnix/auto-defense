"""Durable queue for execute-eligible preempt work (separate from IDS cycle)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339
from aimmune.store import append_jsonl, read_jsonl, rewrite_jsonl


class PreemptQueue:
    def __init__(self, path: Path) -> None:
        self.path = path

    def enqueue(
        self,
        *,
        queued_at,
        site_id: str,
        device_id: str,
        proposals: list[dict[str, Any]],
        origin_actor: dict[str, Any],
        reason_code: str,
        human_approved: bool = False,
        owner_ack: bool = False,
        trace_id: str | None = None,
        parent_receipt_id: str | None = None,
        incident_id: str | None = None,
        ticket_id: str | None = None,
        judgment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = {
            "queue_id": str(uuid4()),
            "queued_at": rfc3339(queued_at) if not isinstance(queued_at, str) else queued_at,
            "site_id": site_id,
            "device_id": device_id,
            "proposals": proposals,
            "origin_actor": origin_actor,
            "reason_code": reason_code,
            "human_approved": human_approved,
            "owner_ack": owner_ack,
            "trace_id": trace_id or str(uuid4()),
            "parent_receipt_id": parent_receipt_id,
            "incident_id": incident_id,
            "ticket_id": ticket_id,
            "judgment": judgment,
            "done": False,
        }
        append_jsonl(self.path, item)
        return item

    def pending(self) -> list[dict[str, Any]]:
        return [row for row in read_jsonl(self.path) if not row.get("done")]

    def mark_done(self, queue_id: str, *, receipt_id: str | None = None) -> None:
        rows = read_jsonl(self.path)
        for row in rows:
            if row.get("queue_id") == queue_id:
                row["done"] = True
                if receipt_id is not None:
                    row["apply_receipt_id"] = receipt_id
        rewrite_jsonl(self.path, rows)
