"""Redacted serializers for the site UI. Digests / effects / policy only."""

from __future__ import annotations

from typing import Any

STRIP_KEYS = frozenset(
    {
        "prompt",
        "prompts",
        "payload",
        "payloads",
        "eve",
        "eve_raw",
        "chat",
        "messages",
        "completion",
        "ir_chat",
        "model_input",
        "raw_event",
        "packet",
        "http",
        "payload_printable",
        "payload_hex",
    }
)

SAFE_ARG_KEYS = frozenset(
    {
        "ip",
        "alias",
        "ttl_s",
        "device_id",
        "lease_id",
        "reason_code",
        "severity",
        "text_redacted",
        "channel",
        "until",
        "receipt_id",
        "queued",
        "ticket_id",
        "incident_id",
        "resolution",
        "patch_applied",
        "cause",
    }
)

SAFE_EFFECT_KEYS = frozenset(
    {
        "alias",
        "ip",
        "ttl_s",
        "ticket_id",
        "queued",
        "receipt_id",
        "incident_id",
        "resolution",
        "patch_applied",
        "cause",
        "device_id",
        "lease_id",
        "channel",
        "job_id",
        "sell_state",
        "passed",
    }
)


def strip_unsafe(value: Any) -> Any:
    """Recursively drop prompt / payload / EVE-like keys."""
    if isinstance(value, dict):
        return {
            key: strip_unsafe(item)
            for key, item in value.items()
            if key not in STRIP_KEYS
        }
    if isinstance(value, list):
        return [strip_unsafe(item) for item in value]
    return value


def _pick(src: dict[str, Any] | None, keys: frozenset[str]) -> dict[str, Any]:
    if not src:
        return {}
    return {key: src[key] for key in keys if key in src and key not in STRIP_KEYS}


def serialize_receipt(receipt: dict[str, Any], *, display: dict[str, Any] | None = None) -> dict[str, Any]:
    """Allowlisted receipt view: no prompts, payloads, or EVE."""
    policy = receipt.get("policy") or {}
    human = receipt.get("human") or {}
    inp = receipt.get("input") or {}
    judgment = receipt.get("judgment") or {}
    actor = receipt.get("actor") or {}
    integrity = receipt.get("integrity") or {}
    out: dict[str, Any] = {
        "receipt_id": receipt.get("receipt_id"),
        "parent_id": receipt.get("parent_id"),
        "site_id": receipt.get("site_id"),
        "ts": receipt.get("ts"),
        "door": receipt.get("door"),
        "purpose": receipt.get("purpose"),
        "posture": strip_unsafe(receipt.get("posture") or {}),
        "policy": {
            "decision": policy.get("decision"),
            "rule_ids": list(policy.get("rule_ids") or []),
        },
        "human": {
            "required": bool(human.get("required")),
            "resolution": human.get("resolution"),
            "resolved_by": human.get("resolved_by"),
            "resolved_at": human.get("resolved_at"),
        },
        "tools": [],
        "effects": [],
        "input": {
            "features_digest": inp.get("features_digest"),
            "window_s": inp.get("window_s"),
            "sources": list(inp.get("sources") or []),
        },
        "judgment": {
            "severity": judgment.get("severity"),
            "classes": list(judgment.get("classes") or []),
            "subjects": strip_unsafe(judgment.get("subjects") or []),
            "summary": judgment.get("summary"),
        },
        "actor": {
            "kind": actor.get("kind"),
            "id": actor.get("id"),
            "purpose": actor.get("purpose"),
        },
        "integrity": {
            "body_hash": integrity.get("body_hash"),
            "prev_hash": integrity.get("prev_hash"),
        },
    }
    for proposal in receipt.get("proposals") or []:
        tool = proposal.get("tool")
        if tool:
            out["tools"].append(tool)
    out["tools"] = list(dict.fromkeys(out["tools"]))
    for row in receipt.get("execution") or []:
        effect = _pick(row.get("effect") if isinstance(row.get("effect"), dict) else {}, SAFE_EFFECT_KEYS)
        out["effects"].append(
            {
                "tool": row.get("tool"),
                "status": row.get("status"),
                "executor": row.get("executor"),
                "effect": strip_unsafe(effect),
                "error": row.get("error"),
            }
        )
    out["proposals"] = []
    for proposal in receipt.get("proposals") or []:
        out["proposals"].append(
            {
                "tool": proposal.get("tool"),
                "mode": proposal.get("mode"),
                "reason_code": proposal.get("reason_code"),
                "ttl_s": proposal.get("ttl_s"),
                "args": strip_unsafe(_pick(proposal.get("args") or {}, SAFE_ARG_KEYS)),
            }
        )
    if display is not None:
        out["display"] = display
    return strip_unsafe(out)


def serialize_incident(row: dict[str, Any]) -> dict[str, Any]:
    return strip_unsafe(
        {
            "incident_id": row.get("incident_id"),
            "site_id": row.get("site_id"),
            "kind": row.get("kind"),
            "status": row.get("status"),
            "severity": row.get("severity"),
            "summary_redacted": row.get("summary_redacted"),
            "opened_at": row.get("opened_at"),
            "primary_subjects": row.get("primary_subjects") or [],
            "flags": row.get("flags") or {},
        }
    )


def serialize_held(held: dict[str, Any] | None) -> dict[str, Any] | None:
    if not held:
        return None
    return strip_unsafe(
        {
            "tool": held.get("tool"),
            "subject": held.get("subject"),
            "reason_code": held.get("reason_code"),
            "ttl_s": held.get("ttl_s"),
            "device_id": held.get("device_id"),
            "args": _pick(held.get("args") or {}, SAFE_ARG_KEYS),
        }
    )


def serialize_preempt_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    tools = [p.get("tool") for p in (row.get("proposals") or []) if p.get("tool")]
    return strip_unsafe(
        {
            "queue_id": row.get("queue_id"),
            "queued_at": row.get("queued_at"),
            "device_id": row.get("device_id"),
            "reason_code": row.get("reason_code"),
            "tools": tools,
            "human_approved": bool(row.get("human_approved")),
            "owner_ack": bool(row.get("owner_ack")),
            "done": bool(row.get("done")),
            "parent_receipt_id": row.get("parent_receipt_id"),
            "ticket_id": row.get("ticket_id"),
        }
    )
