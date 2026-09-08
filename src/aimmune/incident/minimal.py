"""Minimal local security incident side-record (slice 1 + slice 2 open/join).

Open or join {id, kind=security, open} so receipts can cite incident_id via
the side index. Never gate contain or plane drain on this write. Full
close clocks = slice 3.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339
from aimmune.store import read_jsonl, rewrite_jsonl

JOIN_WINDOW_SECURITY = timedelta(hours=4)
SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


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

    def open_or_join_security(
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
        contain_applied: bool = False,
    ) -> dict[str, Any] | None:
        """Join an open security case for this IP within 4h, else open."""
        if self.fail_next_write:
            self.fail_next_write = False
            return None
        now = _as_dt(opened_at)
        try:
            for row in read_jsonl(self.incidents_path):
                if not _joinable_security(row, site_id=site_id, ip=ip, now=now):
                    continue
                if opening_receipt_id:
                    self.attach_receipt(str(row["incident_id"]), opening_receipt_id)
                _bump_severity(row, severity)
                if contain_applied:
                    row.setdefault("flags", {})["contain_applied"] = True
                rows = read_jsonl(self.incidents_path)
                for existing in rows:
                    if existing.get("incident_id") == row["incident_id"]:
                        existing.update(row)
                rewrite_jsonl(self.incidents_path, rows)
                return row
        except OSError:
            return None
        record = self.open_security(
            site_id=site_id,
            opened_at=opened_at,
            opened_by=opened_by,
            severity=severity,
            summary_redacted=summary_redacted,
            ip=ip,
            opening_trace_id=opening_trace_id,
            opening_receipt_id=opening_receipt_id,
        )
        if record is None:
            return None
        record.setdefault("flags", {})["contain_applied"] = contain_applied
        try:
            rows = read_jsonl(self.incidents_path)
            for existing in rows:
                if existing.get("incident_id") == record["incident_id"]:
                    existing["flags"] = record["flags"]
            rewrite_jsonl(self.incidents_path, rows)
        except OSError:
            return record
        return record

    def attach_ticket(self, incident_id: str, ticket_id: str) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            return
        try:
            index = read_jsonl(self.index_path)
            found = False
            for row in index:
                if row.get("incident_id") == incident_id:
                    ids = list(row.get("ticket_ids") or [])
                    if ticket_id not in ids:
                        ids.append(ticket_id)
                    row["ticket_ids"] = ids
                    found = True
                    break
            if not found:
                index.append(
                    {
                        "incident_id": incident_id,
                        "receipt_ids": [],
                        "ticket_ids": [ticket_id],
                        "grant_ids": [],
                    }
                )
            rewrite_jsonl(self.index_path, index)
        except OSError:
            return

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


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _joinable_security(
    row: dict[str, Any], *, site_id: str, ip: str, now: datetime
) -> bool:
    if row.get("status") != "open" or row.get("kind") != "security":
        return False
    if row.get("site_id") != site_id:
        return False
    subjects = row.get("primary_subjects") or []
    if not subjects:
        return False
    dominant = subjects[0]
    if dominant.get("kind") != "ip" or dominant.get("value") != ip:
        return False
    opened = _as_dt(row.get("opened_at"))
    return now - opened <= JOIN_WINDOW_SECURITY


def _bump_severity(row: dict[str, Any], severity: str) -> None:
    current = str(row.get("severity") or "info")
    if SEV_RANK.get(severity, 0) > SEV_RANK.get(current, 0):
        row["severity"] = severity
