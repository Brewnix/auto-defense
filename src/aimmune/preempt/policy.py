"""Execute vs propose matrix for hypermesh.* under default rails_profile=strict.

``rails_profile`` never implies ``hypermesh.*``. Elevated auto-execute is
deferred to privilege grants (slice 7). Unknown ``reason_code`` is not
execute-eligible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from aimmune.policy import RateLimiter
from aimmune.schema import SchemaValidationError, validate_tool_args

HYPERMESH_TOOLS = frozenset({"hypermesh.sell_pause", "hypermesh.lease_stop"})
REASON_ALLOW = frozenset(
    {
        "site_defense",
        "owner_primary",
        "health_evacuate",
        "owner_stop_selling",
        "incident_preempt",
    }
)
SELL_PAUSE_AUTO_REASONS = frozenset({"health_evacuate", "owner_stop_selling"})
MAX_SELL_PAUSE = 1
MAX_LEASE_STOP = 8
NOTIFY_CHANNEL = "fyber.auditor"
POLICY_ENGINE = "brewnix-policy/v0"


@dataclass
class PreemptItem:
    proposal: dict[str, Any]
    device_id: str
    lease_id: str | None
    reason_code: str
    execute_eligible: bool = False
    hold: bool = False
    strip: bool = False
    reject_reason: str | None = None


@dataclass
class PreemptDecision:
    decision: str
    rule_ids: list[str]
    proposals: list[dict[str, Any]]
    items: list[PreemptItem]
    human_required: bool
    reason: str
    notify: dict[str, Any] | None = None
    execute_tools: list[str] = field(default_factory=list)
    preempt_mode: str = "drain"
    extras_stripped: int = 0


_PROPOSAL_KEYS = frozenset({"call_id", "tool", "mode", "reason_code", "args", "ttl_s"})


def schema_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in proposal.items() if key in _PROPOSAL_KEYS}


def strip_extras(proposals: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep first valid sell_pause + first 8 lease_stop. Do not fail the envelope."""
    kept: list[dict[str, Any]] = []
    pauses = 0
    stops = 0
    stripped = 0
    for proposal in proposals:
        tool = proposal.get("tool")
        if tool == "hypermesh.sell_pause":
            if pauses >= MAX_SELL_PAUSE:
                stripped += 1
                continue
            pauses += 1
            kept.append(proposal)
            continue
        if tool == "hypermesh.lease_stop":
            if stops >= MAX_LEASE_STOP:
                stripped += 1
                continue
            stops += 1
            kept.append(proposal)
            continue
        kept.append(proposal)
    return kept, stripped


def _device_id_of(proposal: dict[str, Any], fallback: str | None) -> str:
    args = proposal.get("args") or {}
    raw = args.get("device_id") or proposal.get("device_id") or fallback or ""
    return str(raw).strip()


def _lease_id_of(proposal: dict[str, Any]) -> str:
    args = proposal.get("args") or {}
    return str(args.get("lease_id") or "").strip()


def _make_notify(
    *,
    reason_code: str,
    severity: str,
    site_id: str,
    receipt_id: str,
    text: str,
) -> dict[str, Any]:
    return {
        "call_id": str(uuid4()),
        "tool": "notify.operator",
        "mode": "execute",
        "reason_code": reason_code,
        "args": {
            "channel": NOTIFY_CHANNEL,
            "severity": severity,
            "text_redacted": text[:1000],
        },
    }


def decide_preempt(
    proposals: list[dict[str, Any]],
    *,
    pin,
    site_id: str,
    receipt_id: str,
    actor_kind: str,
    origin_actor_kind: str,
    reason_code: str,
    rails_profile: str = "strict",
    allow_sell_pause_execute: bool = True,
    human_approved: bool = False,
    owner_ack: bool = False,
    incident_id: str | None = None,
    incident_open: bool = False,
    lease_stop_rate: RateLimiter | None = None,
    now: datetime | None = None,
    device_id: str | None = None,
    severity: str = "high",
) -> PreemptDecision:
    """Matrix under default ``strict``. Profile never grants hypermesh.*."""
    _ = rails_profile  # ceiling only — never a Hypermesh grant
    raw = [schema_proposal(dict(p)) for p in proposals]
    kept, extras = strip_extras(raw)
    items: list[PreemptItem] = []
    human = bool(human_approved or owner_ack)
    origin = origin_actor_kind or actor_kind
    model = actor_kind == "model" or origin == "model"
    rules = origin == "rule" and not model

    for proposal in kept:
        tool = proposal.get("tool")
        if tool == "notify.operator":
            continue
        try:
            validate_tool_args(proposal, pin)
        except SchemaValidationError:
            items.append(
                PreemptItem(
                    proposal=proposal,
                    device_id=_device_id_of(proposal, device_id),
                    lease_id=_lease_id_of(proposal) or None,
                    reason_code=str(proposal.get("reason_code") or ""),
                    reject_reason="invalid_tool_or_args",
                )
            )
            continue

        code = str(proposal.get("reason_code") or reason_code or "")
        args_code = str((proposal.get("args") or {}).get("reason_code") or "")
        if tool == "hypermesh.lease_stop" and args_code and args_code != code:
            code = args_code
        dev = _device_id_of(proposal, device_id)
        lease = _lease_id_of(proposal) or None

        if tool not in HYPERMESH_TOOLS:
            items.append(
                PreemptItem(
                    proposal=proposal,
                    device_id=dev,
                    lease_id=lease,
                    reason_code=code,
                    reject_reason="not_hypermesh",
                )
            )
            continue
        if tool == "hypermesh.sell_pause" and not dev:
            items.append(
                PreemptItem(
                    proposal=proposal,
                    device_id=dev,
                    lease_id=lease,
                    reason_code=code,
                    reject_reason="device_id_required",
                )
            )
            continue
        if tool == "hypermesh.lease_stop" and not lease:
            items.append(
                PreemptItem(
                    proposal=proposal,
                    device_id=dev,
                    lease_id=lease,
                    reason_code=code,
                    reject_reason="lease_id_required",
                )
            )
            continue
        if tool == "hypermesh.lease_stop" and not dev:
            items.append(
                PreemptItem(
                    proposal=proposal,
                    device_id=dev,
                    lease_id=lease,
                    reason_code=code,
                    reject_reason="device_id_required",
                )
            )
            continue
        if code not in REASON_ALLOW:
            items.append(
                PreemptItem(
                    proposal=proposal,
                    device_id=dev,
                    lease_id=lease,
                    reason_code=code,
                    reject_reason="unknown_reason_code",
                )
            )
            continue

        eligible = False
        hold = False
        if human:
            eligible = True
        elif model:
            eligible = False
        elif tool == "hypermesh.sell_pause":
            eligible = (
                rules
                and code in SELL_PAUSE_AUTO_REASONS
                and allow_sell_pause_execute
            )
        elif tool == "hypermesh.lease_stop":
            # strict: propose + notify only unless human / owner ack.
            # Elevated auto is slice 7 (grants). Execute still requires an
            # open incident_id — missing → force propose/hold+notify.
            eligible = False
            if lease_stop_rate is not None and now is not None and lease_stop_rate.would_exceed(now):
                hold = True

        items.append(
            PreemptItem(
                proposal=proposal,
                device_id=dev,
                lease_id=lease,
                reason_code=code,
                execute_eligible=eligible,
                hold=hold,
            )
        )

    for item in items:
        if item.reject_reason:
            item.proposal["mode"] = "propose"
            continue
        if item.hold:
            item.proposal["mode"] = "propose"
            item.execute_eligible = False
            continue
        if (
            item.proposal.get("tool") == "hypermesh.lease_stop"
            and item.execute_eligible
            and not (incident_id and incident_open)
        ):
            item.execute_eligible = False
            item.reject_reason = None
            item.proposal["mode"] = "propose"
            continue
        item.proposal["mode"] = "execute" if item.execute_eligible else "propose"

    execute_tools = [
        str(i.proposal["tool"])
        for i in items
        if i.execute_eligible and not i.reject_reason
    ]
    any_hold = any(i.hold for i in items)
    any_propose = any(
        not i.execute_eligible and not i.reject_reason for i in items
    )
    hyper = [i for i in items if i.proposal.get("tool") in HYPERMESH_TOOLS]

    if any_hold:
        decision = "hold_human"
        reason = "lease_stop_rate_hold" if any(i.hold for i in items) else "hold_human"
        human_required = True
    elif execute_tools and not any_propose:
        decision = "execute"
        reason = "preempt_execute"
        human_required = human
    elif execute_tools and any_propose:
        decision = "execute"
        reason = "preempt_partial"
        human_required = True
    elif hyper and any_propose:
        decision = "propose"
        reason = "preempt_propose"
        human_required = True
    else:
        decision = "observe"
        reason = items[0].reject_reason if items else "no_hypermesh"
        human_required = False

    notify = None
    if decision in {"propose", "hold_human"} or (decision == "execute" and any_propose):
        existing = next((p for p in kept if p.get("tool") == "notify.operator"), None)
        if existing:
            notify = existing
        else:
            codes = [i.reason_code for i in items if i.reason_code] or [reason_code]
            notify = _make_notify(
                reason_code=reason if decision == "hold_human" else "propose_needs_ack",
                severity=severity,
                site_id=site_id,
                receipt_id=receipt_id,
                text=(
                    f"{codes[0]} site={site_id} receipt_id={receipt_id} "
                    f"tool=hypermesh rails_profile=strict"
                ),
            )
            kept.append(notify)

    return PreemptDecision(
        decision=decision,
        rule_ids=[reason_code] if reason_code else [],
        proposals=kept,
        items=items,
        human_required=human_required,
        reason=reason,
        notify=notify,
        execute_tools=execute_tools,
        preempt_mode="drain",
        extras_stripped=extras,
    )
