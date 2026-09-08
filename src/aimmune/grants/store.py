"""Site grant cache — ``$STATE_DIR/grants.jsonl``.

Plane mint is SoT when reachable. This cache is SoT for ``active_until``
if the plane drops. Home offline mint writes here only (no plane sync).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aimmune.canonical import rfc3339
from aimmune.store import read_jsonl, rewrite_jsonl


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def is_active(grant: dict[str, Any] | None, now: datetime) -> bool:
    if not grant:
        return False
    if grant.get("status") not in {"approved"}:
        return False
    until = grant.get("active_until")
    if not until:
        return False
    return _as_dt(until) > _as_dt(now)


class GrantStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list(self) -> list[dict[str, Any]]:
        return list(read_jsonl(self.path))

    def get(self, grant_id: str) -> dict[str, Any] | None:
        for row in self.list():
            if row.get("grant_id") == grant_id:
                return row
        return None

    def upsert(self, grant: dict[str, Any]) -> dict[str, Any]:
        grant_id = grant.get("grant_id")
        if not grant_id:
            raise ValueError("grant_id is required to upsert")
        rows = self.list()
        found = False
        for existing in rows:
            if existing.get("grant_id") == grant_id:
                existing.clear()
                existing.update(grant)
                found = True
                break
        if not found:
            rows.append(dict(grant))
        rewrite_jsonl(self.path, rows)
        return dict(grant)

    def active_for_incident(self, incident_id: str, now: datetime) -> dict[str, Any] | None:
        """Return the newest still-active approved grant for this incident."""
        clock = _as_dt(now)
        matches: list[dict[str, Any]] = []
        for row in self.list():
            if row.get("incident_id") != incident_id:
                continue
            if is_active(row, clock):
                matches.append(row)
        if not matches:
            return None
        matches.sort(key=lambda row: str(row.get("active_until") or ""), reverse=True)
        return matches[0]

    def expire_local(self, now: datetime) -> list[str]:
        """Mark approved grants past ``active_until`` as expired (site cache)."""
        clock = _as_dt(now)
        expired: list[str] = []
        rows = self.list()
        changed = False
        for row in rows:
            if row.get("status") != "approved":
                continue
            until = row.get("active_until")
            if until and _as_dt(until) <= clock:
                row["status"] = "expired"
                expired.append(str(row.get("grant_id") or ""))
                changed = True
        if changed:
            rewrite_jsonl(self.path, rows)
        return [gid for gid in expired if gid]

    def find_proposed(self, incident_id: str | None = None) -> list[dict[str, Any]]:
        rows = []
        for row in self.list():
            if row.get("status") != "proposed":
                continue
            if incident_id and row.get("incident_id") != incident_id:
                continue
            rows.append(row)
        return rows


def parse_active_until(value) -> datetime | None:
    if value is None:
        return None
    return _as_dt(value)


def format_until(value) -> str:
    if isinstance(value, str):
        return value
    return rfc3339(value)
