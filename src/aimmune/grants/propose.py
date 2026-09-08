"""Build a validated propose body (CLI + library). Auto-propose is optional."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339
from aimmune.grants.validate import validate_grant_body


def build_asks(
    *,
    tools: list[str] | None = None,
    rate_limit: int | None = None,
    model_tier: str | None = None,
    budget_tokens: int | None = None,
    template_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    asks: list[dict[str, Any]] = []
    if tools:
        asks.append({"kind": "tool_allowlist_add", "tools": list(tools)})
    if rate_limit is not None:
        asks.append(
            {
                "kind": "rate_limit_raise",
                "metric": "blocks_per_hour",
                "limit": int(rate_limit),
            }
        )
    if model_tier:
        asks.append({"kind": "model_tier", "tier": model_tier})
    if budget_tokens is not None:
        asks.append({"kind": "budget_tokens", "max_tokens": int(budget_tokens)})
    if template_ids:
        asks.append({"kind": "prompt_route", "template_ids": list(template_ids)})
    return asks


def build_propose_body(
    *,
    site_id: str,
    incident_id: str,
    reason_redacted: str,
    asks: list[dict[str, Any]],
    profile: str,
    ttl_s: int,
    now,
    trace_id: str | None = None,
    ticket_id: str | None = None,
    requested_by: dict[str, str] | None = None,
    parent_grant_id: str | None = None,
) -> dict[str, Any]:
    body = {
        "schema": "fyber.privilege_grant/v0",
        "site_id": site_id,
        "incident_id": incident_id,
        "trace_id": trace_id or str(uuid4()),
        "requested_at": rfc3339(now),
        "requested_by": requested_by
        or {"kind": "human", "id": "aimmune-cli/grant"},
        "reason_redacted": reason_redacted,
        "asks": asks,
        "rails_profile_requested": profile,
        "ttl_s_requested": ttl_s,
        "blast_radius": "site",
        "status": "proposed",
        "resolution": None,
        "active_until": None,
        "parent_grant_id": parent_grant_id,
        "ticket_id": ticket_id,
    }
    return validate_grant_body(body)


def auto_propose(
    client,
    body: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Thin library helper. Not wired to ChatOps or the detect cycle."""
    return client.propose(body, idempotency_key=idempotency_key)
