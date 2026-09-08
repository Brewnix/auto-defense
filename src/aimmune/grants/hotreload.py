"""Derive allow_model_execute / catalog / tier / budget from an active grant.

Active grant is SoT. No grant → strict. ``AIMMUNE_RAILS_GRANT_*`` /
``RailsStub`` is a deprecated test-only override.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aimmune.grants.registry import expand_tool_entry
from aimmune.grants.store import is_active
from aimmune.triage.decide import allow_model_execute as rails_allow_model_execute
from aimmune.triage.decide import execute_allowlist as rails_execute_allowlist
from aimmune.triage.settings import HYPERMESH_TOOLS, RailsStub, profile_catalog


@dataclass(frozen=True)
class Elevation:
    profile: str = "strict"
    allow_model_execute: bool = False
    tool_allowlist: frozenset[str] = frozenset()
    model_tier: str | None = None
    budget_tokens: int | None = None
    grant_id: str | None = None
    incident_id: str | None = None
    source: str = "strict"

    @staticmethod
    def strict() -> Elevation:
        return Elevation()


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _primary_ip(envelope: dict[str, Any]) -> str | None:
    for proposal in envelope.get("proposals") or []:
        args = proposal.get("args") or {}
        if args.get("ip"):
            return str(args["ip"])
    subjects = (envelope.get("judgment") or {}).get("subjects") or []
    for sub in subjects:
        if sub.get("kind") == "ip":
            return str(sub["value"])
    return None


def find_open_incident_id(rt: Any, envelope: dict[str, Any]) -> str | None:
    ip = _primary_ip(envelope)
    if not ip:
        return None
    finder = getattr(rt.incidents, "find_open_security_by_ip", None)
    if callable(finder):
        rec = finder(rt.config.site_id, ip)
        if rec:
            return str(rec["incident_id"])
    for rec in rt.incidents.find_open(rt.config.site_id, kind="security"):
        subjects = rec.get("primary_subjects") or []
        if subjects and subjects[0].get("kind") == "ip" and subjects[0].get("value") == ip:
            return str(rec["incident_id"])
    return None


def elevation_from_grant(grant: dict[str, Any], now: datetime) -> Elevation:
    if not is_active(grant, now):
        return Elevation.strict()
    resolution = grant.get("resolution") or {}
    profile = (
        resolution.get("rails_profile")
        or grant.get("rails_profile_requested")
        or "strict"
    )
    if profile not in {"ir_elevated", "break_glass"}:
        return Elevation.strict()
    extra: list[str] = []
    model_tier = None
    budget = None
    for ask in grant.get("asks") or []:
        kind = ask.get("kind")
        if kind == "tool_allowlist_add":
            for entry in ask.get("tools") or []:
                extra.extend(expand_tool_entry(str(entry)))
        elif kind == "model_tier":
            model_tier = str(ask.get("tier") or "") or None
        elif kind == "budget_tokens":
            try:
                budget = int(ask.get("max_tokens"))
            except (TypeError, ValueError):
                budget = None
    catalog = set(profile_catalog(profile, extra_allowlist=tuple(extra)))
    # Profile never implies hypermesh.*; only an explicit ask that survived
    # validate (emergency pack listing) can add them.
    if not (set(extra) & HYPERMESH_TOOLS):
        catalog -= HYPERMESH_TOOLS
    return Elevation(
        profile=profile,
        allow_model_execute=True,
        tool_allowlist=frozenset(catalog),
        model_tier=model_tier,
        budget_tokens=budget,
        grant_id=str(grant.get("grant_id") or "") or None,
        incident_id=str(grant.get("incident_id") or "") or None,
        source="grant",
    )


def elevation_from_rails(rails: RailsStub, now: datetime) -> Elevation:
    if not rails_allow_model_execute(rails, now):
        return Elevation(profile=rails.profile, source="rails_stub")
    warnings.warn(
        "AIMMUNE_RAILS_GRANT_* / RailsStub is a deprecated test-only override; "
        "privilege grants are the source of truth",
        DeprecationWarning,
        stacklevel=3,
    )
    return Elevation(
        profile=rails.profile,
        allow_model_execute=True,
        tool_allowlist=rails_execute_allowlist(rails, now),
        source="rails_stub",
    )


def elevation_from_runtime(
    rt: Any,
    *,
    envelope: dict[str, Any] | None = None,
    incident_id: str | None = None,
    now: datetime | None = None,
) -> Elevation:
    """Active grant first. No grant → deprecated rails stub → strict."""
    clock = now or (rt.clock.now() if getattr(rt, "clock", None) else datetime.now(timezone.utc))
    iid = incident_id
    if iid is None and envelope is not None:
        iid = find_open_incident_id(rt, envelope)
    grant = None
    if iid and getattr(rt, "grants", None) is not None:
        grant = rt.grants.active_for_incident(iid, clock)
    if grant is not None:
        return elevation_from_grant(grant, clock)
    rails = getattr(getattr(rt, "config", None), "triage", None)
    stub = getattr(rails, "rails", None) if rails is not None else None
    if stub is None:
        stub = getattr(getattr(rt, "config", None), "rails_stub", None)
    if isinstance(stub, RailsStub) and stub.grant_active:
        return elevation_from_rails(stub, clock)
    return Elevation.strict()
