"""brewnix-policy/v0 — whitelist, dedupe, rate limit B=30, critical auto vs high propose."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from aimmune.schema import SchemaValidationError, validate_tool_args
from aimmune.sensors.eve_to_bundle import ip_is_whitelisted
from aimmune.store import append_jsonl, read_jsonl

POLICY_ENGINE = "brewnix-policy/v0"
NOTIFY_CHANNEL = "fyber.auditor"
HOT_PATH_TOOLS = frozenset({"firewall.block_ip", "firewall.unblock_ip"})
ALLOWED_NOTIFY_CHANNELS = frozenset({NOTIFY_CHANNEL})


@dataclass
class PolicyResult:
    decision: str
    rule_ids: list[str]
    proposals: list[dict[str, Any]]
    human_required: bool
    reason: str
    notify: dict[str, Any] | None = None
    execute_tools: list[str] = field(default_factory=list)


class RateLimiter:
    def __init__(self, path: Path, *, max_per_hour: int) -> None:
        self.path = path
        self.max_per_hour = max_per_hour

    def applied_in_window(self, now: datetime, window_s: int = 3600) -> int:
        cutoff = now - timedelta(seconds=window_s)
        count = 0
        for row in read_jsonl(self.path):
            ts = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
            if ts >= cutoff:
                count += 1
        return count

    def would_exceed(self, now: datetime) -> bool:
        return self.applied_in_window(now) >= self.max_per_hour

    def record(self, now: datetime, ip: str) -> None:
        append_jsonl(self.path, {"ts": now.isoformat().replace("+00:00", "Z"), "ip": ip})


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


def _rule_ids_from_envelope(envelope: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for proposal in envelope.get("proposals") or []:
        code = proposal.get("reason_code")
        if code and code not in ids:
            ids.append(str(code))
    if not ids:
        actor_id = (envelope.get("actor") or {}).get("id", "")
        if actor_id == "brewnix-rules/expiry":
            return ["ttl_expired"]
    return ids


def _has_notify(proposals: list[dict[str, Any]]) -> bool:
    return any(p.get("tool") == "notify.operator" for p in proposals)


def _make_notify(
    *,
    reason_code: str,
    severity: str,
    site_id: str,
    ip: str | None,
    rule_id: str,
    receipt_id: str,
    incident_id: str | None = None,
) -> dict[str, Any]:
    parts = [
        reason_code,
        f"site={site_id}",
        f"receipt_id={receipt_id}",
    ]
    if ip:
        parts.append(f"ip={ip}")
    parts.append(f"rule={rule_id}")
    if incident_id:
        parts.append(f"incident_id={incident_id}")
    text = " ".join(parts)[:1000]
    return {
        "call_id": str(uuid4()),
        "tool": "notify.operator",
        "mode": "execute",
        "reason_code": reason_code,
        "args": {
            "channel": NOTIFY_CHANNEL,
            "severity": severity,
            "text_redacted": text,
        },
    }


def remaining_ttl_s(ip: str, prior_blocks: list[dict[str, Any]]) -> int | None:
    for row in prior_blocks:
        if row.get("ip") == ip:
            return int(row.get("remaining_ttl_s", 0))
    return None


def decide(
    envelope: dict[str, Any],
    *,
    pin,
    whitelist: list[Any],
    prior_blocks: list[dict[str, Any]],
    alias_members: set[str],
    rate_limiter: RateLimiter,
    now: datetime,
    auto_rule_ids: frozenset[str],
    receipt_id: str,
    site_id: str,
    incident_id: str | None = None,
) -> PolicyResult:
    actor = envelope.get("actor") or {}
    is_expiry = actor.get("id") == "brewnix-rules/expiry"
    proposals = [dict(p) for p in (envelope.get("proposals") or [])]
    rule_ids = _rule_ids_from_envelope(envelope)
    ip = _primary_ip(envelope)
    severity = (envelope.get("judgment") or {}).get("severity", "info")

    for proposal in proposals:
        try:
            validate_tool_args(proposal, pin)
        except SchemaValidationError:
            return PolicyResult(
                decision="observe",
                rule_ids=rule_ids or ["invalid_tool"],
                proposals=proposals,
                human_required=False,
                reason="invalid_tool_or_args",
            )
        tool = proposal.get("tool")
        if tool not in HOT_PATH_TOOLS | {"notify.operator"}:
            return PolicyResult(
                decision="observe",
                rule_ids=rule_ids or ["unknown_tool"],
                proposals=proposals,
                human_required=False,
                reason="unknown_tool",
            )
        if tool == "notify.operator":
            channel = (proposal.get("args") or {}).get("channel")
            if channel not in ALLOWED_NOTIFY_CHANNELS:
                return PolicyResult(
                    decision="observe",
                    rule_ids=rule_ids or ["bad_notify_channel"],
                    proposals=proposals,
                    human_required=False,
                    reason="bad_notify_channel",
                )

    if is_expiry:
        return _decide_expiry(
            envelope,
            proposals=proposals,
            ip=ip,
            alias_members=alias_members,
            rule_ids=rule_ids,
        )

    if ip and ip_is_whitelisted(ip, whitelist):
        return PolicyResult(
            decision="observe",
            rule_ids=rule_ids or ["whitelist"],
            proposals=proposals,
            human_required=False,
            reason="whitelist",
        )

    ttl_left = remaining_ttl_s(ip, prior_blocks) if ip else None
    if ip and ip in alias_members and (ttl_left is None or ttl_left >= 0):
        return PolicyResult(
            decision="observe",
            rule_ids=rule_ids or ["dedupe"],
            proposals=proposals,
            human_required=False,
            reason="already_blocked",
        )

    block_proposals = [p for p in proposals if p.get("tool") == "firewall.block_ip"]
    if not block_proposals:
        return PolicyResult(
            decision="observe",
            rule_ids=rule_ids or ["noise_ignore"],
            proposals=proposals,
            human_required=False,
            reason="no_block_proposal",
        )

    matching_auto = any(rid in auto_rule_ids for rid in rule_ids)
    wants_execute = severity == "critical" and matching_auto

    if wants_execute and rate_limiter.would_exceed(now):
        notify = _ensure_notify(
            proposals,
            reason_code="rate_limit_hold",
            severity=severity,
            site_id=site_id,
            ip=ip,
            rule_id=rule_ids[0] if rule_ids else "rate_limit_hold",
            receipt_id=receipt_id,
            incident_id=incident_id,
        )
        return PolicyResult(
            decision="hold_human",
            rule_ids=rule_ids,
            proposals=proposals,
            human_required=True,
            reason="rate_limit_hold",
            notify=notify,
        )

    if wants_execute:
        return PolicyResult(
            decision="execute",
            rule_ids=rule_ids,
            proposals=proposals,
            human_required=False,
            reason="critical_auto",
            execute_tools=["firewall.block_ip"],
        )

    if severity == "high":
        notify = _ensure_notify(
            proposals,
            reason_code="propose_needs_ack",
            severity="high",
            site_id=site_id,
            ip=ip,
            rule_id=rule_ids[0] if rule_ids else "ssh_brute",
            receipt_id=receipt_id,
            incident_id=incident_id,
        )
        for proposal in proposals:
            if proposal.get("tool") == "firewall.block_ip":
                proposal["mode"] = "propose"
        return PolicyResult(
            decision="propose",
            rule_ids=rule_ids,
            proposals=proposals,
            human_required=True,
            reason="high_propose",
            notify=notify,
        )

    return PolicyResult(
        decision="observe",
        rule_ids=rule_ids or ["observe"],
        proposals=proposals,
        human_required=False,
        reason="not_auto",
    )


def _ensure_notify(
    proposals: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    existing = next((p for p in proposals if p.get("tool") == "notify.operator"), None)
    if existing:
        return existing
    notify = _make_notify(**kwargs)
    proposals.append(notify)
    return notify


def _decide_expiry(
    envelope: dict[str, Any],
    *,
    proposals: list[dict[str, Any]],
    ip: str | None,
    alias_members: set[str],
    rule_ids: list[str],
) -> PolicyResult:
    _ = envelope
    ids = rule_ids or ["ttl_expired"]
    # Rate limits never apply. Whitelist must not stick the ledger.
    if ip and ip not in alias_members:
        return PolicyResult(
            decision="observe",
            rule_ids=ids,
            proposals=proposals,
            human_required=False,
            reason="expiry_dedupe",
        )
    return PolicyResult(
        decision="execute",
        rule_ids=ids,
        proposals=proposals,
        human_required=False,
        reason="ttl_expired",
        execute_tools=["firewall.unblock_ip"],
    )
