"""Minimal local security incident side-record (slice 1).

Open {id, kind=security, open} so receipts can cite incident_id via the side
index. Never gate contain on this write. Full join/close clocks = slice 3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339
from aimmune.store import read_jsonl, rewrite_jsonl


class IncidentError(RuntimeError):
    pass


class IncidentStore:
    def __init__(self, incidents_path: Path, index_path: Path) -> None:
        self.incidents_path = incidents_path
        self.index_path = index_path
        self.fail_next_write = False

    def open_security(
        self,
        *,
        site_id: str,
        opened_at,
        opened_by: dict[str, str],
        severity: str,
        summary_redacted: str,
        ip: str,
        opening_trace_id: str,
        opening_receipt_id: str | None = None,
    ) -> dict[str, Any] | None:
        if self.fail_next_write:
            self.fail_next_write = False
            return None
        incident_id = str(uuid4())
        record = {
            "schema": "fyber.incident/v0",
            "incident_id": incident_id,
            "site_id": site_id,
            "kind": "security",
            "status": "open",
            "opened_at": rfc3339(opened_at) if not isinstance(opened_at, str) else opened_at,
            "opened_by": {"kind": opened_by.get("kind", "rule"), "id": opened_by.get("id", "")},
            "severity": severity,
            "summary_redacted": summary_redacted[:1000],
            "primary_subjects": [{"kind": "ip", "value": ip}],
            "closed_at": None,
            "close_reason": None,
            "flags": {
                "contain_applied": True,
                "grant_active": False,
            },
            "links": {
                "opening_trace_id": opening_trace_id,
                "opening_receipt_id": opening_receipt_id,
            },
        }
        try:
            rows = read_jsonl(self.incidents_path)
            rows.append(record)
            rewrite_jsonl(self.incidents_path, rows)
            index = read_jsonl(self.index_path)
            index.append(
                {
                    "incident_id": incident_id,
                    "receipt_ids": [opening_receipt_id] if opening_receipt_id else [],
                    "ticket_ids": [],
                    "grant_ids": [],
                }
            )
            rewrite_jsonl(self.index_path, index)
        except OSError:
            return None
        return record

    def attach_receipt(self, incident_id: str, receipt_id: str) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            return
        try:
            index = read_jsonl(self.index_path)
            found = False
            for row in index:
                if row.get("incident_id") == incident_id:
                    ids = list(row.get("receipt_ids") or [])
                    if receipt_id not in ids:
                        ids.append(receipt_id)
                    row["receipt_ids"] = ids
                    found = True
                    break
            if not found:
                index.append(
                    {
                        "incident_id": incident_id,
                        "receipt_ids": [receipt_id],
                        "ticket_ids": [],
                        "grant_ids": [],
                    }
                )
            rewrite_jsonl(self.index_path, index)
        except OSError:
            return

    def find_by_receipt(self, receipt_id: str) -> str | None:
        for row in read_jsonl(self.index_path):
            if receipt_id in (row.get("receipt_ids") or []):
                return str(row["incident_id"])
        return None

    def inherit_parent(self, parent_receipt_id: str, child_receipt_id: str) -> str | None:
        incident_id = self.find_by_receipt(parent_receipt_id)
        if incident_id:
            self.attach_receipt(incident_id, child_receipt_id)
        return incident_id

    def get(self, incident_id: str) -> dict[str, Any] | None:
        for row in read_jsonl(self.incidents_path):
            if row.get("incident_id") == incident_id:
                return row
        return None
