"""Durable local notify.operator queue. Slice 2 drains to fyber.auditor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aimmune.canonical import rfc3339
from aimmune.store import append_jsonl, read_jsonl, rewrite_jsonl


class NotifyQueueError(RuntimeError):
    pass


class NotifyQueue:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fail_next_write = False

    def enqueue(
        self,
        *,
        queued_at,
        site_id: str,
        receipt_id: str,
        trace_id: str,
        proposal: dict[str, Any],
        incident_id: str | None = None,
        policy_decision: str,
        held: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.fail_next_write:
            self.fail_next_write = False
            raise NotifyQueueError("notify queue write failed")
        item = {
            "queued_at": rfc3339(queued_at) if not isinstance(queued_at, str) else queued_at,
            "site_id": site_id,
            "receipt_id": receipt_id,
            "trace_id": trace_id,
            "incident_id": incident_id,
            "policy_decision": policy_decision,
            "proposal": proposal,
            "held": held,
            "drained": False,
            "ticket_id": None,
        }
        append_jsonl(self.path, item)
        return item

    def pending(self) -> list[dict[str, Any]]:
        return [row for row in read_jsonl(self.path) if not row.get("drained")]

    def mark_drained(self, receipt_id: str, ticket_id: str | None = None) -> None:
        """Slice 2 hook — do not call a plane client here."""
        rows = read_jsonl(self.path)
        for row in rows:
            if row.get("receipt_id") == receipt_id:
                row["drained"] = True
                if ticket_id is not None:
                    row["ticket_id"] = ticket_id
        rewrite_jsonl(self.path, rows)
