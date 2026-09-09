"""Plane staging E2E v0 — default-off (`pytest -m plane_staging`).

Site-token **safe** subset only against a WireGuard-reachable Panopticon.
Skip unless ``PANOPTICON_BASE_URL`` + ``HM_SITE_TOKEN`` + ``SITE_ID`` are set.
Assert the site token cannot resolve/revoke tickets or grants (401/403).
No live ``lease_stop`` / preempt. No tokens written to the repo.
"""

from __future__ import annotations

import os
from datetime import timezone
from typing import Any
from uuid import uuid4

import httpx
import pytest

from aimmune.auditor.client import AuditorClient
from aimmune.clock import Clock
from aimmune.grants.client import GrantClient
from aimmune.grants.propose import build_asks, build_propose_body

pytestmark = pytest.mark.plane_staging

SITE_TOKENS_ME = "/api/v1/hypermesh/site-tokens/me"
TICKETS = "/api/v1/auditor/v0/tickets"
GRANTS = "/api/v1/grants/v0/grants"
DENIED = frozenset({401, 403})
ACK_OK = frozenset({200, 409})


def _staging_env() -> dict[str, str] | None:
    base = (os.environ.get("PANOPTICON_BASE_URL") or "").strip().rstrip("/")
    token = (os.environ.get("HM_SITE_TOKEN") or "").strip()
    site = (os.environ.get("SITE_ID") or os.environ.get("AIMMUNE_SITE_ID") or "").strip()
    if not (base and token and site):
        return None
    return {"base": base, "token": token, "site": site}


def _skip_unless_staging() -> dict[str, str]:
    env = _staging_env()
    if env is None:
        pytest.skip(
            "PANOPTICON_BASE_URL + HM_SITE_TOKEN + SITE_ID unset — plane_staging skip"
        )
    return env


def _timeout_s() -> float:
    raw = os.environ.get("AIMMUNE_PLANE_TIMEOUT_S", "5")
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return 5.0


def _site_id_from_me(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("site_id"):
        return str(payload["site_id"])
    token = payload.get("token") or payload.get("data") or {}
    if isinstance(token, dict) and token.get("site_id"):
        return str(token["site_id"])
    return None


def _assert_denied(response: httpx.Response, *, path: str) -> None:
    assert response.status_code in DENIED, (
        f"site token must not be allowed {path} "
        f"(got HTTP {response.status_code}; want 401/403)"
    )


def test_plane_staging_site_token_safe_subset() -> None:
    env = _skip_unless_staging()
    timeout = _timeout_s()
    headers = {
        "Authorization": f"Bearer {env['token']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    with httpx.Client(base_url=env["base"], headers=headers, timeout=timeout) as raw:
        me = raw.get(SITE_TOKENS_ME)
        assert me.status_code == 200, f"site-tokens/me HTTP {me.status_code}"
        me_site = _site_id_from_me(me.json())
        assert me_site == env["site"], "token site_id must equal SITE_ID"

        # Never enqueue Host jobs against rented boxes.
        assert "/site/jobs" not in SITE_TOKENS_ME

        auditor = AuditorClient(env["base"], env["token"], timeout_s=timeout)
        grants = GrantClient(env["base"], env["token"], timeout_s=timeout)
        try:
            receipt_id = str(uuid4())
            trace_id = str(uuid4())
            held_call_id = str(uuid4())
            ticket_body = {
                "schema": "fyber.auditor.ticket/v0",
                "site_id": env["site"],
                "trace_id": trace_id,
                "receipt_id": receipt_id,
                "held_call_id": held_call_id,
                "reason_code": "plane_staging_e2e_v0",
                "severity": "high",
                "text_redacted": "plane staging e2e v0 — site-token safe subset",
                "display": {
                    "tool": "notify.operator",
                    "subject": {"kind": "ip", "value": "203.0.113.80"},
                    "ttl_s": 3600,
                },
            }
            created = auditor.create_ticket(ticket_body)
            ticket_id = str(created.get("ticket_id") or "")
            assert ticket_id, "auditor create must return ticket_id"
            got_ticket = auditor.get_ticket(ticket_id)
            assert str(got_ticket.get("ticket_id")) == ticket_id
            assert got_ticket.get("site_id") in {None, env["site"]}

            incident_id = str(uuid4())
            now = Clock().now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            grant_body = build_propose_body(
                site_id=env["site"],
                incident_id=incident_id,
                reason_redacted="plane staging e2e v0 propose (notify only)",
                asks=build_asks(tools=["notify.operator"]),
                profile="ir_elevated",
                ttl_s=1800,
                now=now,
                requested_by={"kind": "automation", "id": "aimmune-plane-staging-e2e"},
            )
            proposed = grants.propose(grant_body, idempotency_key=f"staging-v0-{trace_id}")
            grant_id = str(proposed.get("grant_id") or "")
            assert grant_id, "grant propose must return grant_id"
            got_grant = grants.get_grant(grant_id)
            assert str(got_grant.get("grant_id")) == grant_id
            status = str(got_grant.get("status") or proposed.get("status") or "")
            assert status in {"proposed", "open", ""}, status

            # Optional ack after local apply. Ticket is likely still open
            # (site must not resolve). 409 = still open / not yet resolved.
            apply_receipt = str(uuid4())
            ack = raw.post(
                f"{TICKETS}/{ticket_id}/ack",
                json={"receipt_id": apply_receipt},
            )
            assert ack.status_code in ACK_OK, (
                f"optional ack: expected 200 or 409, got HTTP {ack.status_code}"
            )

            _assert_denied(
                raw.post(
                    f"{TICKETS}/{ticket_id}/resolve",
                    json={
                        "resolution": "denied",
                        "resolved_by": "aimmune-plane-staging-e2e",
                    },
                ),
                path=f"POST {TICKETS}/{{id}}/resolve",
            )
            _assert_denied(
                raw.post(
                    f"{GRANTS}/{grant_id}/resolve",
                    json={
                        "resolution": "denied",
                        "resolved_by": "aimmune-plane-staging-e2e",
                    },
                ),
                path=f"POST {GRANTS}/{{id}}/resolve",
            )
            _assert_denied(
                raw.post(f"{GRANTS}/{grant_id}/revoke", json={}),
                path=f"POST {GRANTS}/{{id}}/revoke",
            )
        finally:
            auditor.close()
            grants.close()

        # Clients stay site-safe (no resolve/revoke verbs).
        assert not hasattr(AuditorClient, "resolve")
        assert not hasattr(AuditorClient, "resolve_ticket")
        assert not hasattr(GrantClient, "resolve")
        assert not hasattr(GrantClient, "revoke")
