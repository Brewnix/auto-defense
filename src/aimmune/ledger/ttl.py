"""TTL ledger: (ip, alias, expire_at, parent_receipt_id, call_id) on successful block."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aimmune.canonical import rfc3339
from aimmune.store import read_jsonl, rewrite_jsonl


class TtlLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def rows(self) -> list[dict[str, Any]]:
        return read_jsonl(self.path)

    def record(
        self,
        *,
        ip: str,
        alias: str,
        expire_at: datetime,
        parent_receipt_id: str,
        call_id: str,
        classes: list[str] | None = None,
        incident_id: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "ip": ip,
            "alias": alias,
            "expire_at": rfc3339(expire_at),
            "parent_receipt_id": parent_receipt_id,
            "call_id": call_id,
            "classes": classes or ["unknown"],
            "incident_id": incident_id,
            "status": "active",
        }
        rows = self.rows()
        rows.append(row)
        rewrite_jsonl(self.path, rows)
        return row

    def due(self, now: datetime) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in self.rows():
            if row.get("status") != "active":
                continue
            expire = datetime.fromisoformat(str(row["expire_at"]).replace("Z", "+00:00"))
            if expire <= now:
                out.append(row)
        return out

    def advance(self, call_id: str) -> None:
        rows = self.rows()
        changed = False
        for row in rows:
            if row.get("call_id") == call_id and row.get("status") == "active":
                row["status"] = "consumed"
                changed = True
        if changed:
            rewrite_jsonl(self.path, rows)

    def prior_blocks(self, now: datetime, alias_members: list[str]) -> list[dict[str, Any]]:
        by_ip: dict[str, int] = {}
        for row in self.rows():
            if row.get("status") != "active":
                continue
            expire = datetime.fromisoformat(str(row["expire_at"]).replace("Z", "+00:00"))
            remaining = max(0, int((expire - now).total_seconds()))
            ip = str(row["ip"])
            by_ip[ip] = remaining
        for ip in alias_members:
            by_ip.setdefault(ip, 0)
        return [{"ip": ip, "remaining_ttl_s": ttl} for ip, ttl in sorted(by_ip.items())]

    def expire_at_from_ttl(self, now: datetime, ttl_s: int) -> datetime:
        return now + timedelta(seconds=ttl_s)
