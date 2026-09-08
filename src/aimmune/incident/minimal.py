"""Local fyber.incident/v0 side-record (slices 1–3).

Security open/join (IP dominant, 4h) plus ops join (1h), human close,
auto_quiet sweep, and a grant side-index stub. Never gate contain or
plane drain on this write. Binding is side-index only — no receipt
schema amend.

Ops auto-close uses a 2h quiet (no new linked receipts) as a proxy for
health-clear until health-watch sensors exist. Do not invent
Suricata/WAN polls here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339
from aimmune.store import read_jsonl, rewrite_jsonl

JOIN_WINDOW_SECURITY = timedelta(hours=4)
JOIN_WINDOW_OPS = timedelta(hours=1)
QUIET_SECURITY = timedelta(hours=24)
QUIET_OPS = timedelta(hours=2)
SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
OPENED_BY_KINDS = frozenset({"rule", "automation", "human"})


class IncidentError(RuntimeError):
    pass


class GrantActiveError(IncidentError):
    """Close refused while a linked grant is considered active."""


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
        return self._open(
            site_id=site_id,
            opened_at=opened_at,
            opened_by=opened_by,
            severity=severity,
            summary_redacted=summary_redacted,
            kind="security",
            subjects=[{"kind": "ip", "value": ip}],
            opening_trace_id=opening_trace_id,
            opening_receipt_id=opening_receipt_id,
            contain_applied=True,
        )

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
        joined = self._try_join(
            site_id=site_id,
            kind="security",
            now=now,
            severity=severity,
            opening_receipt_id=opening_receipt_id,
            contain_applied=contain_applied,
            match=lambda row: _dominant_ip(row) == ip,
        )
        if joined is not None:
            return joined
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
        return self._persist_row(record) or record

    def open_or_join_ops(
        self,
        *,
        site_id: str,
        opened_at,
        opened_by: dict[str, str],
        severity: str,
        summary_redacted: str,
        opening_trace_id: str,
        opening_receipt_id: str | None = None,
        subject: dict[str, Any] | None = None,
        node: str | None = None,
        unit: str | None = None,
        health_class: str | None = None,
    ) -> dict[str, Any] | None:
        """Join an open ops case within 1h on the dominant subject, else open.

        Dominant subject is ``node_unit {kind,node,unit}`` or
        ``health_class {kind,value}``. Never joins a security incident.
        """
        if self.fail_next_write:
            self.fail_next_write = False
            return None
        dominant = _ops_subject(subject, node=node, unit=unit, health_class=health_class)
        now = _as_dt(opened_at)
        joined = self._try_join(
            site_id=site_id,
            kind="ops",
            now=now,
            severity=severity,
            opening_receipt_id=opening_receipt_id,
            contain_applied=False,
            match=lambda row: _dominant_subject(row) == dominant,
        )
        if joined is not None:
            return joined
        return self._open(
            site_id=site_id,
            opened_at=opened_at,
            opened_by=opened_by,
            severity=severity,
            summary_redacted=summary_redacted,
            kind="ops",
            subjects=[dominant],
            opening_trace_id=opening_trace_id,
            opening_receipt_id=opening_receipt_id,
            contain_applied=False,
        )

    def attach_ticket(self, incident_id: str, ticket_id: str) -> None:
        self._attach_id(incident_id, "ticket_ids", ticket_id)

    def attach_receipt(self, incident_id: str, receipt_id: str, now=None) -> None:
        self._attach_id(incident_id, "receipt_ids", receipt_id, now=now)

    def attach_grant(
        self,
        incident_id: str,
        grant_id: str,
        *,
        active_until=None,
        now=None,
    ) -> None:
        """Test/dev stub until slice 7 mints real grants."""
        if self.fail_next_write:
            self.fail_next_write = False
            return
        try:
            index = self._ensure_index_row(incident_id)
            ids = list(index.get("grant_ids") or [])
            if grant_id not in ids:
                ids.append(grant_id)
            index["grant_ids"] = ids
            grants = list(index.get("grants") or [])
            found = False
            until = None
            if active_until is not None:
                until = rfc3339(active_until) if not isinstance(active_until, str) else active_until
            for row in grants:
                if row.get("grant_id") == grant_id:
                    if until is not None:
                        row["active_until"] = until
                    found = True
                    break
            if not found:
                grants.append({"grant_id": grant_id, "active_until": until})
            index["grants"] = grants
            self._write_index_row(index)
            if until is not None and now is not None and _as_dt(until) > _as_dt(now):
                self.set_grant_active(incident_id, True)
            elif until is not None and now is None:
                self.set_grant_active(incident_id, True)
        except OSError:
            return

    def set_grant_active(self, incident_id: str, active: bool) -> dict[str, Any] | None:
        """Test helper: flip ``flags.grant_active`` (slice 7 will derive this)."""
        if self.fail_next_write:
            self.fail_next_write = False
            return None
        rec = self.get(incident_id)
        if rec is None:
            return None
        rec.setdefault("flags", {})["grant_active"] = bool(active)
        return self._persist_row(rec)

    def find_by_receipt(self, receipt_id: str) -> str | None:
        for row in read_jsonl(self.index_path):
            if receipt_id in (row.get("receipt_ids") or []):
                return str(row["incident_id"])
        return None

    def inherit_parent(self, parent_receipt_id: str, child_receipt_id: str, now=None) -> str | None:
        incident_id = self.find_by_receipt(parent_receipt_id)
        if incident_id:
            self.attach_receipt(incident_id, child_receipt_id, now=now)
        return incident_id

    def get(self, incident_id: str) -> dict[str, Any] | None:
        for row in read_jsonl(self.incidents_path):
            if row.get("incident_id") == incident_id:
                return row
        return None

    def is_open(self, incident_id: str | None) -> bool:
        if not incident_id:
            return False
        rec = self.get(incident_id)
        return bool(rec and rec.get("status") == "open")

    def index_get(self, incident_id: str) -> dict[str, Any] | None:
        for row in read_jsonl(self.index_path):
            if row.get("incident_id") == incident_id:
                return _normalize_index(row)
        return None

    def list_incidents(self) -> list[dict[str, Any]]:
        return list(read_jsonl(self.incidents_path))

    def find_open(self, site_id: str, *, kind: str | None = None) -> list[dict[str, Any]]:
        rows = [
            row
            for row in read_jsonl(self.incidents_path)
            if row.get("status") == "open"
            and row.get("site_id") == site_id
            and (kind is None or row.get("kind") == kind)
        ]
        rows.sort(key=lambda row: str(row.get("opened_at") or ""), reverse=True)
        return rows

    def grant_blocks_close(self, incident_id: str, now) -> bool:
        rec = self.get(incident_id)
        if rec and (rec.get("flags") or {}).get("grant_active"):
            return True
        idx = self.index_get(incident_id)
        if not idx:
            return False
        clock = _as_dt(now)
        for grant in idx.get("grants") or []:
            until = grant.get("active_until")
            if until and _as_dt(until) > clock:
                return True
        return False

    def close_human(self, incident_id: str, *, now) -> dict[str, Any] | None:
        if self.fail_next_write:
            self.fail_next_write = False
            return None
        rec = self.get(incident_id)
        if rec is None:
            raise IncidentError(f"unknown incident {incident_id}")
        if rec.get("status") == "closed":
            return rec
        if self.grant_blocks_close(incident_id, now):
            raise GrantActiveError("close refused: grant_active")
        rec["status"] = "closed"
        rec["close_reason"] = "human"
        rec["closed_at"] = rfc3339(now) if not isinstance(now, str) else now
        return self._persist_row(rec)

    def sweep(self, now) -> dict[str, Any]:
        """Auto-close quiet incidents. Fail-open: never raises to callers."""
        closed: list[str] = []
        if self.fail_next_write:
            self.fail_next_write = False
            return {"closed": closed}
        try:
            rows = read_jsonl(self.incidents_path)
        except OSError:
            return {"closed": closed}
        clock = _as_dt(now)
        for row in rows:
            if row.get("status") != "open":
                continue
            incident_id = str(row.get("incident_id") or "")
            if not incident_id:
                continue
            if self.grant_blocks_close(incident_id, clock):
                continue
            quiet = QUIET_SECURITY if row.get("kind") == "security" else QUIET_OPS
            last = self._last_activity(row)
            if clock - last < quiet:
                continue
            try:
                row["status"] = "closed"
                row["close_reason"] = "auto_quiet"
                row["closed_at"] = rfc3339(clock)
                persisted = self._persist_row(row)
                if persisted is not None:
                    closed.append(incident_id)
            except OSError:
                continue
        return {"closed": closed}

    def _last_activity(self, row: dict[str, Any]) -> datetime:
        idx = self.index_get(str(row.get("incident_id") or ""))
        if idx and idx.get("last_receipt_at"):
            return _as_dt(idx["last_receipt_at"])
        return _as_dt(row.get("opened_at"))

    def _open(
        self,
        *,
        site_id: str,
        opened_at,
        opened_by: dict[str, str],
        severity: str,
        summary_redacted: str,
        kind: str,
        subjects: list[dict[str, Any]],
        opening_trace_id: str,
        opening_receipt_id: str | None,
        contain_applied: bool,
    ) -> dict[str, Any] | None:
        if self.fail_next_write:
            self.fail_next_write = False
            return None
        incident_id = str(uuid4())
        actor_kind = opened_by.get("kind", "rule")
        if actor_kind not in OPENED_BY_KINDS:
            actor_kind = "automation"
        record = {
            "schema": "fyber.incident/v0",
            "incident_id": incident_id,
            "site_id": site_id,
            "kind": kind,
            "status": "open",
            "opened_at": rfc3339(opened_at) if not isinstance(opened_at, str) else opened_at,
            "opened_by": {"kind": actor_kind, "id": opened_by.get("id", "")},
            "severity": severity,
            "summary_redacted": summary_redacted[:1000],
            "primary_subjects": subjects[:16],
            "closed_at": None,
            "close_reason": None,
            "flags": {
                "contain_applied": contain_applied,
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
            opened = rfc3339(opened_at) if not isinstance(opened_at, str) else opened_at
            index.append(
                _normalize_index(
                    {
                        "incident_id": incident_id,
                        "receipt_ids": [opening_receipt_id] if opening_receipt_id else [],
                        "ticket_ids": [],
                        "grant_ids": [],
                        "grants": [],
                        "last_receipt_at": opened if opening_receipt_id else None,
                    }
                )
            )
            rewrite_jsonl(self.index_path, index)
        except OSError:
            return None
        return record

    def _try_join(
        self,
        *,
        site_id: str,
        kind: str,
        now: datetime,
        severity: str,
        opening_receipt_id: str | None,
        contain_applied: bool,
        match,
    ) -> dict[str, Any] | None:
        window = JOIN_WINDOW_SECURITY if kind == "security" else JOIN_WINDOW_OPS
        try:
            for row in read_jsonl(self.incidents_path):
                if not _joinable(row, site_id=site_id, kind=kind, now=now, window=window):
                    continue
                if not match(row):
                    continue
                if opening_receipt_id:
                    self.attach_receipt(str(row["incident_id"]), opening_receipt_id, now=now)
                _bump_severity(row, severity)
                if contain_applied:
                    row.setdefault("flags", {})["contain_applied"] = True
                return self._persist_row(row) or row
        except OSError:
            return None
        return None

    def _persist_row(self, record: dict[str, Any]) -> dict[str, Any] | None:
        try:
            rows = read_jsonl(self.incidents_path)
            found = False
            for existing in rows:
                if existing.get("incident_id") == record["incident_id"]:
                    existing.update(record)
                    found = True
                    break
            if not found:
                rows.append(record)
            rewrite_jsonl(self.incidents_path, rows)
        except OSError:
            return None
        return record

    def _attach_id(
        self,
        incident_id: str,
        field: str,
        value: str,
        *,
        now=None,
    ) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            return
        try:
            index = self._ensure_index_row(incident_id)
            ids = list(index.get(field) or [])
            if value not in ids:
                ids.append(value)
            index[field] = ids
            if field == "receipt_ids" and now is not None:
                index["last_receipt_at"] = rfc3339(now) if not isinstance(now, str) else now
            self._write_index_row(index)
        except OSError:
            return

    def _ensure_index_row(self, incident_id: str) -> dict[str, Any]:
        index = read_jsonl(self.index_path)
        for row in index:
            if row.get("incident_id") == incident_id:
                return _normalize_index(row)
        row = _normalize_index({"incident_id": incident_id})
        index.append(row)
        rewrite_jsonl(self.index_path, index)
        return row

    def _write_index_row(self, updated: dict[str, Any]) -> None:
        index = read_jsonl(self.index_path)
        found = False
        for row in index:
            if row.get("incident_id") == updated["incident_id"]:
                row.clear()
                row.update(_normalize_index(updated))
                found = True
                break
        if not found:
            index.append(_normalize_index(updated))
        rewrite_jsonl(self.index_path, index)


def require_grant_incident_id(grant: dict[str, Any] | None) -> str:
    """Reject fyber.privilege_grant/v0 missing / empty / null incident_id.

    Slice 7 will mint. Empty-ask one-shot approve stays on the auditor
    ticket and does not use this helper.
    """
    raw = None if grant is None else grant.get("incident_id")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise IncidentError("grant requires incident_id")
    return str(raw).strip()


def _normalize_index(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": row.get("incident_id"),
        "receipt_ids": list(row.get("receipt_ids") or []),
        "ticket_ids": list(row.get("ticket_ids") or []),
        "grant_ids": list(row.get("grant_ids") or []),
        "grants": list(row.get("grants") or []),
        "last_receipt_at": row.get("last_receipt_at"),
    }


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _joinable(
    row: dict[str, Any],
    *,
    site_id: str,
    kind: str,
    now: datetime,
    window: timedelta,
) -> bool:
    if row.get("status") != "open" or row.get("kind") != kind:
        return False
    if row.get("site_id") != site_id:
        return False
    subjects = row.get("primary_subjects") or []
    if not subjects:
        return False
    opened = _as_dt(row.get("opened_at"))
    return now - opened <= window


def _dominant_subject(row: dict[str, Any]) -> dict[str, Any]:
    subjects = row.get("primary_subjects") or []
    return dict(subjects[0]) if subjects else {}


def _dominant_ip(row: dict[str, Any]) -> str | None:
    dominant = _dominant_subject(row)
    if dominant.get("kind") != "ip":
        return None
    return dominant.get("value")


def _ops_subject(
    subject: dict[str, Any] | None,
    *,
    node: str | None,
    unit: str | None,
    health_class: str | None,
) -> dict[str, Any]:
    if subject:
        kind = subject.get("kind")
        if kind == "node_unit":
            return {
                "kind": "node_unit",
                "node": subject.get("node"),
                "unit": subject.get("unit"),
            }
        if kind == "health_class":
            return {"kind": "health_class", "value": subject.get("value")}
        raise IncidentError("ops dominant subject must be node_unit or health_class")
    if node and unit:
        return {"kind": "node_unit", "node": node, "unit": unit}
    if health_class:
        return {"kind": "health_class", "value": health_class}
    raise IncidentError("ops open requires node_unit or health_class")


def _bump_severity(row: dict[str, Any], severity: str) -> None:
    current = str(row.get("severity") or "info")
    if SEV_RANK.get(severity, 0) > SEV_RANK.get(current, 0):
        row["severity"] = severity
