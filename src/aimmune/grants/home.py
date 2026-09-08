"""Home offline mint — site-local only. Never POSTs plane ``/resolve``.

Allowed only when ``plane_reachable=false``. Requires an open incident,
an auditor ticket id (or local ticket stub), and notes. break_glass TTL
is clamped to ≤3600 (prefer 1800). Plane-up break_glass stays
plane-resolved.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339, sha256_digest
from aimmune.grants.store import GrantStore
from aimmune.grants.validate import (
    BREAK_GLASS_PREFER_TTL,
    GrantValidationError,
    clamp_ttl,
    validate_grant_body,
)
from aimmune.incident.minimal import IncidentError, IncidentStore


class PlaneUpMintError(RuntimeError):
    """Plane is up — site must not locally mint / resolve."""


def mint_local(
    *,
    store: GrantStore,
    incidents: IncidentStore,
    site_id: str,
    incident_id: str,
    ticket_id: str | None,
    notes: str,
    reason_redacted: str,
    asks: list[dict[str, Any]],
    profile: str = "break_glass",
    ttl_s: int = BREAK_GLASS_PREFER_TTL,
    trace_id: str | None = None,
    requested_by: dict[str, str] | None = None,
    now,
    plane_reachable: bool,
) -> dict[str, Any]:
    """Mint an approved grant into the site cache. No plane POST."""
    if plane_reachable:
        raise PlaneUpMintError(
            "plane-up mint is plane-resolved; site never POST /grants/.../resolve"
        )
    rec = incidents.get(incident_id)
    if rec is None or rec.get("status") != "open":
        raise IncidentError("local mint requires an open incident")
    notes_text = (notes or "").strip()
    if not notes_text:
        raise GrantValidationError("break_glass local mint requires notes")
    if len(notes_text) > 1000:
        notes_text = notes_text[:1000]
    ticket = (ticket_id or "").strip() or f"local-ticket-{uuid4()}"
    actor = requested_by or {"kind": "human", "id": "aimmune-cli/grant"}
    if actor.get("kind") == "model":
        raise GrantValidationError("LLM is never requested_by / resolved_by")
    clock = now
    ttl = clamp_ttl(profile, int(ttl_s))
    body = validate_grant_body(
        {
            "schema": "fyber.privilege_grant/v0",
            "site_id": site_id,
            "incident_id": incident_id,
            "trace_id": trace_id or str(uuid4()),
            "requested_at": rfc3339(clock),
            "requested_by": actor,
            "reason_redacted": reason_redacted,
            "asks": asks,
            "rails_profile_requested": profile,
            "ttl_s_requested": ttl,
            "blast_radius": "site",
            "status": "proposed",
            "resolution": None,
            "active_until": None,
            "parent_grant_id": None,
            "ticket_id": ticket,
        }
    )
    grant_id = str(uuid4())
    resolved_at = rfc3339(clock)
    active_until = rfc3339(clock + timedelta(seconds=ttl))
    grant: dict[str, Any] = {
        **body,
        "grant_id": grant_id,
        "status": "approved",
        "active_until": active_until,
        "resolution": {
            "resolved_by": f"site:owner:{actor.get('id') or 'aimmune'}",
            "resolved_at": resolved_at,
            "ttl_s": ttl,
            "rails_profile": profile,
            "notes_redacted": notes_text,
        },
    }
    hashed = {key: value for key, value in grant.items() if key != "integrity"}
    grant["integrity"] = {"body_hash": sha256_digest(hashed)}
    store.upsert(grant)
    incidents.attach_grant(incident_id, grant_id, active_until=active_until, now=clock)
    incidents.set_grant_active(incident_id, True)
    return grant
