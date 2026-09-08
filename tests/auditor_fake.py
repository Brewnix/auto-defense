"""In-process fyber.auditor stand-in for httpx.MockTransport tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx


def _request_json(request: httpx.Request) -> dict[str, Any]:
    if not request.content:
        return {}
    payload = json.loads(request.content.decode("utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload

TICKETS = "/api/v1/auditor/v0/tickets"


def _rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class FakeAuditor:
    """Plane mock: create / get / resolve / ack. Site client must not call resolve."""

    def __init__(self, *, token: str = "hm_site_test", site_id: str = "net-tn-cottage") -> None:
        self.token = token
        self.site_id = site_id
        self.tickets: dict[str, dict[str, Any]] = {}
        self.by_receipt: dict[tuple[str, str], str] = {}
        self.creates = 0
        self.gets = 0
        self.acks = 0
        self.resolves = 0
        self.down = False
        self.transport = httpx.MockTransport(self.handler)

    def client(self, **kwargs):
        from aimmune.auditor.client import AuditorClient

        return AuditorClient(
            "https://panopticon.test",
            self.token,
            transport=self.transport,
            **kwargs,
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("plane down")
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return httpx.Response(401, json={"error": "unauthorized"})
        path = urlparse(str(request.url)).path
        method = request.method.upper()
        if method == "POST" and path.rstrip("/") == TICKETS:
            return self._create(request)
        parts = path.rstrip("/").split("/")
        if len(parts) >= 6 and "/".join(parts[:5]) == TICKETS.lstrip("/"):
            # path like /api/v1/auditor/v0/tickets/{id}[/ack|/resolve]
            pass
        if not path.startswith(TICKETS + "/"):
            return httpx.Response(404, json={"error": "not found"})
        rest = path[len(TICKETS) + 1 :]
        if rest.endswith("/ack") and method == "POST":
            return self._ack(rest[: -len("/ack")], request)
        if rest.endswith("/resolve") and method == "POST":
            return self._resolve(rest[: -len("/resolve")], request)
        if method == "GET":
            return self._get(rest)
        return httpx.Response(404, json={"error": "not found"})

    def _create(self, request: httpx.Request) -> httpx.Response:
        self.creates += 1
        body = _request_json(request)
        site_id = body.get("site_id")
        if site_id != self.site_id:
            return httpx.Response(403, json={"error": "site mismatch"})
        receipt_id = body.get("receipt_id")
        key = (site_id, str(receipt_id)) if receipt_id else (
            site_id,
            str(body.get("trace_id")),
            str(body.get("reason_code")),
        )
        existing = self.by_receipt.get(key)  # type: ignore[arg-type]
        if existing and existing in self.tickets:
            return httpx.Response(200, json=self.tickets[existing])
        ticket_id = str(uuid4())
        ticket = {
            "schema": "fyber.auditor.ticket/v0",
            "ticket_id": ticket_id,
            "site_id": site_id,
            "trace_id": body.get("trace_id"),
            "receipt_id": receipt_id,
            "held_call_id": body.get("held_call_id"),
            "reason_code": body.get("reason_code"),
            "severity": body.get("severity"),
            "text_redacted": body.get("text_redacted"),
            "display": body.get("display"),
            "status": "open",
            "resolution": None,
            "resolved_by": None,
            "resolved_at": None,
            "patch": None,
            "notes_redacted": None,
            "site_acked_receipt_id": None,
        }
        self.tickets[ticket_id] = ticket
        self.by_receipt[key] = ticket_id  # type: ignore[index]
        return httpx.Response(200, json=ticket)

    def _get(self, ticket_id: str) -> httpx.Response:
        self.gets += 1
        ticket = self.tickets.get(ticket_id)
        if ticket is None:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=ticket)

    def _resolve(self, ticket_id: str, request: httpx.Request) -> httpx.Response:
        self.resolves += 1
        ticket = self.tickets.get(ticket_id)
        if ticket is None:
            return httpx.Response(404, json={"error": "not found"})
        body = _request_json(request)
        resolution = body.get("resolution")
        if ticket["status"] != "open":
            if ticket.get("resolution") == resolution:
                return httpx.Response(200, json=ticket)
            return httpx.Response(409, json={"error": "already resolved"})
        ticket["status"] = "resolved"
        ticket["resolution"] = resolution
        ticket["resolved_by"] = body.get("resolved_by")
        ticket["resolved_at"] = _rfc3339()
        ticket["patch"] = body.get("patch")
        ticket["notes_redacted"] = body.get("notes_redacted")
        return httpx.Response(200, json=ticket)

    def _ack(self, ticket_id: str, request: httpx.Request) -> httpx.Response:
        self.acks += 1
        ticket = self.tickets.get(ticket_id)
        if ticket is None:
            return httpx.Response(404, json={"error": "not found"})
        if ticket["status"] == "open":
            return httpx.Response(409, json={"error": "still open"})
        body = _request_json(request)
        receipt_id = body.get("receipt_id")
        if ticket["status"] == "acked" and ticket.get("site_acked_receipt_id") == receipt_id:
            return httpx.Response(200, json=ticket)
        if ticket["status"] == "acked":
            return httpx.Response(409, json={"error": "ack mismatch"})
        ticket["status"] = "acked"
        ticket["site_acked_receipt_id"] = receipt_id
        return httpx.Response(200, json=ticket)

    def resolve(
        self,
        ticket_id: str,
        *,
        resolution: str,
        resolved_by: str = "panopticon:user:chris",
        patch: dict[str, Any] | None = None,
        notes_redacted: str | None = None,
    ) -> dict[str, Any]:
        """Test helper — plane operator. Not exposed on AuditorClient."""
        request = httpx.Request(
            "POST",
            f"https://panopticon.test{TICKETS}/{ticket_id}/resolve",
            json={
                "resolution": resolution,
                "resolved_by": resolved_by,
                "patch": patch,
                "notes_redacted": notes_redacted,
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return self.handler(request).json()
