"""Local privilege-grant ladder validation before POST / home mint.

Five ask kinds only. Empty asks → refuse (use a ticket). Profile ladder
is strict / ir_elevated≤8h / break_glass≤60m. ``hypermesh.*`` is never
implied by profile. No schema file — docs-first fyber.privilege_grant/v0.
"""

from __future__ import annotations

from typing import Any

from aimmune.grants.registry import (
    EMERGENCY_PACK_ID,
    PROMPT_ROUTE_TEMPLATES,
    TOOL_NAMES,
    expand_tool_entry,
)
from aimmune.incident.minimal import require_grant_incident_id

ASK_KINDS = frozenset(
    {
        "tool_allowlist_add",
        "rate_limit_raise",
        "budget_tokens",
        "model_tier",
        "prompt_route",
    }
)
CUT_ASK_KINDS = frozenset(
    {
        "rails_profile",
        "shell_unrestricted",
        "disable_receipts",
        "skip_human",
        "exfil_ok",
        "trust_plane_execute",
        "mcp_allowlist",
        "knowledge_pack",
    }
)
ASK_KEYS = {
    "tool_allowlist_add": frozenset({"kind", "tools"}),
    "rate_limit_raise": frozenset({"kind", "metric", "limit"}),
    "budget_tokens": frozenset({"kind", "max_tokens"}),
    "model_tier": frozenset({"kind", "tier"}),
    "prompt_route": frozenset({"kind", "template_ids"}),
}
GRANT_KEYS = frozenset(
    {
        "schema",
        "grant_id",
        "site_id",
        "incident_id",
        "trace_id",
        "requested_at",
        "requested_by",
        "reason_redacted",
        "asks",
        "rails_profile_requested",
        "ttl_s_requested",
        "blast_radius",
        "status",
        "resolution",
        "active_until",
        "parent_grant_id",
        "ticket_id",
        "integrity",
    }
)
PROFILES = frozenset({"strict", "ir_elevated", "break_glass"})
LOCAL_TIERS = frozenset({"local_small", "local_large"})
GRANT_TIERS = frozenset({"plane_ir", "host_leased"})
VALID_TIERS = LOCAL_TIERS | GRANT_TIERS
HYPERMESH_TOOLS = frozenset({"hypermesh.lease_stop", "hypermesh.sell_pause"})
NOT_IMPLIED_TOOLS = HYPERMESH_TOOLS | {"net.quarantine_host"}
IR_ELEVATED_TOOLS = frozenset(
    {"health.restart_service", "notify.operator", "ids.suricata_pass"}
)
IR_ELEVATED_MAX_TTL = 28800
BREAK_GLASS_MAX_TTL = 3600
BREAK_GLASS_PREFER_TTL = 1800
PROMPT_MARKERS = ("SYSTEM:", "You are a", "<<<EVE>>>", "prompt:")


class GrantValidationError(ValueError):
    """Local ladder / ask validation failed. Grant must not be POSTed."""


def clamp_ttl(profile: str | None, ttl_s: int) -> int:
    """Clamp requested TTL to the profile max. break_glass prefers 1800."""
    if ttl_s < 1:
        raise GrantValidationError("ttl_s_requested must be a positive int")
    if profile == "break_glass":
        if ttl_s > BREAK_GLASS_MAX_TTL:
            return BREAK_GLASS_PREFER_TTL
        return ttl_s
    if profile == "ir_elevated":
        return min(ttl_s, IR_ELEVATED_MAX_TTL)
    return ttl_s


def _reject_prompts(text: str, field: str) -> None:
    blob = text or ""
    for marker in PROMPT_MARKERS:
        if marker in blob:
            raise GrantValidationError(f"{field} must not contain prompts")


def _validate_ask(ask: dict[str, Any], profile: str | None) -> None:
    if not isinstance(ask, dict):
        raise GrantValidationError("ask must be an object")
    extra = set(ask) - GRANT_KEYS
    # extra keys on the ask itself, not the grant
    kind = ask.get("kind")
    if kind in CUT_ASK_KINDS or (isinstance(kind, str) and kind not in ASK_KINDS):
        raise GrantValidationError(f"unknown or CUT ask kind: {kind!r}")
    allowed = ASK_KEYS.get(str(kind), frozenset())
    extra = set(ask) - allowed
    if extra:
        raise GrantValidationError(f"extra keys on {kind} ask: {sorted(extra)}")

    if kind == "tool_allowlist_add":
        tools = ask.get("tools")
        if not isinstance(tools, list) or not tools:
            raise GrantValidationError("tool_allowlist_add.tools must be a non-empty array")
        expanded: set[str] = set()
        for raw in tools:
            entry = str(raw)
            if entry != EMERGENCY_PACK_ID and entry not in TOOL_NAMES and not entry.startswith(
                "packs/"
            ):
                raise GrantValidationError(f"unknown tool: {entry}")
            if entry.startswith("packs/") and entry != EMERGENCY_PACK_ID:
                raise GrantValidationError(f"unknown pack: {entry}")
            expanded.update(expand_tool_entry(entry))
            if entry in NOT_IMPLIED_TOOLS or (expanded & NOT_IMPLIED_TOOLS):
                if profile == "ir_elevated" or profile in {None, "strict"}:
                    raise GrantValidationError(
                        "hypermesh.*/net.quarantine_host are not in the ir_elevated catalog"
                    )
                # break_glass: only if the (empty) emergency pack lists them
                if entry in NOT_IMPLIED_TOOLS and entry not in expand_tool_entry(
                    EMERGENCY_PACK_ID
                ):
                    raise GrantValidationError(
                        "hypermesh.* is not implied by break_glass; packs/emergency-v0 is empty"
                    )
        if profile in {None, "strict"} and expanded - {
            "firewall.block_ip",
            "firewall.unblock_ip",
            "notify.operator",
        }:
            raise GrantValidationError("strict catalog does not allow elevation tools")
        if profile == "ir_elevated" and expanded - IR_ELEVATED_TOOLS - {
            "firewall.block_ip",
            "firewall.unblock_ip",
        }:
            raise GrantValidationError("ask tools exceed ir_elevated max catalog")
        return

    if kind == "rate_limit_raise":
        if ask.get("metric") != "blocks_per_hour":
            raise GrantValidationError("rate_limit_raise.metric must be blocks_per_hour")
        try:
            limit = int(ask.get("limit"))
        except (TypeError, ValueError) as exc:
            raise GrantValidationError("rate_limit_raise.limit must be a positive int") from exc
        if limit < 1:
            raise GrantValidationError("rate_limit_raise.limit must be >= 1")
        if profile in {None, "strict"}:
            raise GrantValidationError("rate_limit_raise requires ir_elevated or break_glass")
        return

    if kind == "budget_tokens":
        try:
            tokens = int(ask.get("max_tokens"))
        except (TypeError, ValueError) as exc:
            raise GrantValidationError("budget_tokens.max_tokens must be a positive int") from exc
        if tokens < 1:
            raise GrantValidationError("budget_tokens.max_tokens must be >= 1")
        if profile in {None, "strict"}:
            raise GrantValidationError("budget_tokens requires ir_elevated or break_glass")
        return

    if kind == "model_tier":
        tier = ask.get("tier")
        if tier not in VALID_TIERS:
            raise GrantValidationError(f"unknown model_tier: {tier!r}")
        if tier in GRANT_TIERS and profile != "break_glass":
            raise GrantValidationError("plane_ir/host_leased require break_glass")
        if profile in {None, "strict"}:
            raise GrantValidationError("model_tier requires ir_elevated or break_glass")
        return

    if kind == "prompt_route":
        ids = ask.get("template_ids")
        if not isinstance(ids, list) or not ids:
            raise GrantValidationError("prompt_route.template_ids must be a non-empty array")
        unknown = [tid for tid in ids if str(tid) not in PROMPT_ROUTE_TEMPLATES]
        if unknown:
            raise GrantValidationError(f"unknown prompt_route template_ids: {unknown}")
        if profile in {None, "strict"}:
            raise GrantValidationError("prompt_route requires ir_elevated or break_glass")
        return


def validate_asks(asks: Any, *, profile: str | None) -> list[dict[str, Any]]:
    if not isinstance(asks, list) or not asks:
        raise GrantValidationError("empty asks — refuse the grant; use a ticket")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for ask in asks:
        if not isinstance(ask, dict):
            raise GrantValidationError("ask must be an object")
        kind = ask.get("kind")
        if kind in seen:
            raise GrantValidationError(f"duplicate ask kind: {kind}")
        seen.add(str(kind))
        _validate_ask(ask, profile)
        out.append(ask)
    if "budget_tokens" in seen and "model_tier" not in seen:
        raise GrantValidationError("budget_tokens requires a sibling model_tier ask")
    return out


def validate_grant_body(body: dict[str, Any], *, clamp: bool = True) -> dict[str, Any]:
    """Validate (and optionally clamp TTL) a propose / mint body.

    Extra keys fail. ``incident_id`` is required. ``requested_by.kind``
    must not be ``model``.
    """
    if not isinstance(body, dict):
        raise GrantValidationError("grant body must be an object")
    extra = set(body) - GRANT_KEYS
    if extra:
        raise GrantValidationError(f"extra keys on grant: {sorted(extra)}")
    if body.get("schema") not in {None, "fyber.privilege_grant/v0"}:
        raise GrantValidationError("schema must be fyber.privilege_grant/v0")
    require_grant_incident_id(body)
    if not str(body.get("site_id") or "").strip():
        raise GrantValidationError("site_id is required")
    if not str(body.get("trace_id") or "").strip():
        raise GrantValidationError("trace_id is required")
    if not str(body.get("requested_at") or "").strip():
        raise GrantValidationError("requested_at is required")
    actor = body.get("requested_by") or {}
    if not isinstance(actor, dict):
        raise GrantValidationError("requested_by must be an object")
    if actor.get("kind") == "model":
        raise GrantValidationError("LLM is never requested_by / resolved_by")
    if actor.get("kind") not in {"automation", "human"}:
        raise GrantValidationError("requested_by.kind must be automation or human")
    if not str(actor.get("id") or "").strip():
        raise GrantValidationError("requested_by.id is required")
    reason = str(body.get("reason_redacted") or "")
    if not (1 <= len(reason) <= 1000):
        raise GrantValidationError("reason_redacted must be 1–1000 chars")
    _reject_prompts(reason, "reason_redacted")
    profile = body.get("rails_profile_requested")
    if profile is not None and profile not in PROFILES:
        raise GrantValidationError(f"invalid rails_profile_requested: {profile!r}")
    if profile == "strict":
        raise GrantValidationError("strict is not an elevation grant; use a ticket")
    blast = body.get("blast_radius", "site")
    if blast != "site":
        raise GrantValidationError("blast_radius must be site")
    try:
        ttl = int(body.get("ttl_s_requested"))
    except (TypeError, ValueError) as exc:
        raise GrantValidationError("ttl_s_requested must be a positive int") from exc
    if ttl < 1:
        raise GrantValidationError("ttl_s_requested must be a positive int")
    clamped = clamp_ttl(profile, ttl) if clamp else ttl
    if not clamp and profile == "break_glass" and ttl > BREAK_GLASS_MAX_TTL:
        raise GrantValidationError("break_glass TTL must be ≤3600")
    if not clamp and profile == "ir_elevated" and ttl > IR_ELEVATED_MAX_TTL:
        raise GrantValidationError("ir_elevated TTL must be ≤28800")
    asks = validate_asks(body.get("asks"), profile=profile)
    out = dict(body)
    out["schema"] = "fyber.privilege_grant/v0"
    out["asks"] = asks
    out["ttl_s_requested"] = clamped
    out["blast_radius"] = "site"
    return out
