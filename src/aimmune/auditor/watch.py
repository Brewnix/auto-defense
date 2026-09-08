"""Local auditor watch JSONL — ticket_id → poll state. No long-poll."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from aimmune.store import read_jsonl, rewrite_jsonl


class AuditorWatch:
    def __init__(self, path: Path) -> None:
        self.path = path

    def rows(self) -> list[dict[str, Any]]:
        return read_jsonl(self.path)

    def open_watches(self) -> list[dict[str, Any]]:
        return [row for row in self.rows() if row.get("status") != "acked"]

    def upsert(self, row: dict[str, Any]) -> dict[str, Any]:
        ticket_id = row.get("ticket_id")
        rows = self.rows()
        found = False
        for existing in rows:
            if existing.get("ticket_id") == ticket_id:
                existing.update(row)
                found = True
                break
        if not found:
            rows.append(row)
        rewrite_jsonl(self.path, rows)
        return row

    def get(self, ticket_id: str) -> dict[str, Any] | None:
        for row in self.rows():
            if row.get("ticket_id") == ticket_id:
                return row
        return None
