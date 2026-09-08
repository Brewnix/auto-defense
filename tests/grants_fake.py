"""In-process privilege-grant stand-in for httpx.MockTransport tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

import httpx

from aimmune.grants.client import GrantClient

GRANTS = "/api/v1/grants/v0/grants"


def _request_json(request: httpx.Request) -> dict[str, Any]:
    if not request.content:
        return {}
    payload = json.loads(request.content.decode("utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class FakeGrants:
    """Plane mock: propose / get / list / resolve / revoke.

    Site client must not call resolve or revoke.
    """

    def __init__(self, *, token: str = "hm_site_test", site_id: str = "net-tn-cottage") -> None:
        self.token = token
        self.site_id = site_id
        self.grants: dict[str, dict[str, Any]] = {}
        self.by_key: dict[tuple[str, str, str], str] = {}
        self.by_idem: dict[str, str] = {}
        self.proposes = 0
        self.gets = 0
        self.lists = 0
        self.resolves = 0
        self.revokes = 0
        self.down = False
        self.transport = httpx.MockTransport(self.handler)

    def client(self, **kwargs) -> GrantClient:
        return GrantClient(
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
        if method == "POST" and path.rstrip("/") == GRANTS:
            return self._propose(request)
        if method == "GET" and path.rstrip("/") == GRANTS:
            return self._list(request)
        if not path.startswith(GRANTS + "/"):
            return httpx.Response(404, json={"error": "not found"})
        rest = path[len(GRANTS) + 1 :]
        if rest.endswith("/resolve") and method == "POST":
            return self._resolve(rest[: -len("/resolve")], request)
        if rest.endswith("/revoke") and method == "POST":
            return self._revoke(rest[: -len("/revoke")], request)
        if method == "GET":
            return self._get(rest)
        return httpx.Response(404, json={"error": "not found"})

    def _propose(self, request: httpx.Request) -> httpx.Response:
        self.proposes += 1
        body = _request_json(request)
        site_id = str(body.get("site_id") or "")
        if site_id != self.site_id:
            return httpx.Response(403, json={"error": "site mismatch"})
        incident_id = str(body.get("incident_id") or "")
        trace_id = str(body.get("trace_id") or "")
        idem = request.headers.get("Idempotency-Key")
        if idem and idem in self.by_idem:
            return httpx.Response(200, json=self.grants[self.by_idem[idem]])
        key = (site_id, incident_id, trace_id)
        existing = self.by_key.get(key)
        if existing and existing in self.grants:
            return httpx.Response(200, json=self.grants[existing])
        grant_id = str(uuid4())
        grant = {
            "schema": "fyber.privilege_grant/v0",
            "grant_id": grant_id,
            "site_id": site_id,
            "incident_id": incident_id,
            "trace_id": trace_id,
            "requested_at": body.get("requested_at") or _rfc3339(),
            "requested_by": body.get("requested_by"),
            "reason_redacted": body.get("reason_redacted"),
            "asks": body.get("asks") or [],
            "rails_profile_requested": body.get("rails_profile_requested"),
            "ttl_s_requested": body.get("ttl_s_requested"),
            "blast_radius": body.get("blast_radius") or "site",
            "status": "proposed",
            "resolution": None,
            "active_until": None,
            "parent_grant_id": body.get("parent_grant_id"),
            "ticket_id": body.get("ticket_id"),
            "integrity": None,
        }
        self.grants[grant_id] = grant
        self.by_key[key] = grant_id
        if idem:
            self.by_idem[idem] = grant_id
        return httpx.Response(200, json=grant)

    def _get(self, grant_id: str) -> httpx.Response:
        self.gets += 1
        grant = self.grants.get(grant_id)
        if grant is None:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=grant)

    def _list(self, request: httpx.Request) -> httpx.Response:
        self.lists += 1
        query = parse_qs(urlparse(str(request.url)).query)
        status = (query.get("status") or [None])[0]
        incident_id = (query.get("incident_id") or [None])[0]
        rows = []
        for grant in self.grants.values():
            if status and grant.get("status") != status:
                continue
            if incident_id and grant.get("incident_id") != incident_id:
                continue
            rows.append(grant)
        return httpx.Response(200, json={"grants": rows})

    def _resolve(self, grant_id: str, request: httpx.Request) -> httpx.Response:
        self.resolves += 1
        grant = self.grants.get(grant_id)
        if grant is None:
            return httpx.Response(404, json={"error": "not found"})
        body = _request_json(request)
        grant["status"] = body.get("status") or "approved"
        grant["resolution"] = {
            "resolved_by": body.get("resolved_by") or "panopticon:user:chris",
            "resolved_at": _rfc3339(),
            "ttl_s": body.get("ttl_s") or grant.get("ttl_s_requested"),
            "rails_profile": body.get("rails_profile")
            or grant.get("rails_profile_requested"),
            "notes_redacted": body.get("notes_redacted"),
        }
        grant["active_until"] = body.get("active_until")
        return httpx.Response(200, json=grant)

    def _revoke(self, grant_id: str, request: httpx.Request) -> httpx.Response:
        self.revokes += 1
        grant = self.grants.get(grant_id)
        if grant is None:
            return httpx.Response(404, json={"error": "not found"})
        _ = request
        grant["status"] = "revoked"
        return httpx.Response(200, json=grant)

    def approve(
        self,
        grant_id: str,
        *,
        active_until: str,
        ttl_s: int | None = None,
        rails_profile: str | None = None,
    ) -> dict[str, Any]:
        """Test helper — plane operator. Not exposed on GrantClient."""
        request = httpx.Request(
            "POST",
            f"https://panopticon.test{GRANTS}/{grant_id}/resolve",
            json={
                "status": "approved",
                "resolved_by": "panopticon:user:chris",
                "ttl_s": ttl_s,
                "rails_profile": rails_profile,
                "active_until": active_until,
                "notes_redacted": "plane mint",
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return self.handler(request).json()
