"""Held companion snapshot for auditor tickets (slice 2)."""

from __future__ import annotations

from typing import Any


class HeldSnapshotError(ValueError):
    pass


def subject_from_args(args: dict[str, Any]) -> dict[str, str] | None:
    if args.get("ip"):
        return {"kind": "ip", "value": str(args["ip"])}
    return None


def snapshot_from_proposal(proposal: dict[str, Any]) -> dict[str, Any] | None:
    tool = proposal.get("tool")
    if not tool or tool == "notify.operator":
        return None
    args = dict(proposal.get("args") or {})
    subject = subject_from_args(args)
    if subject is None:
        return None
    snap: dict[str, Any] = {
        "call_id": proposal.get("call_id"),
        "tool": tool,
        "args": args,
        "subject": subject,
    }
    ttl = proposal.get("ttl_s") or args.get("ttl_s")
    if ttl is not None:
        snap["ttl_s"] = int(ttl)
    return snap


def snapshot_from_proposals(proposals: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for proposal in proposals or []:
        snap = snapshot_from_proposal(proposal)
        if snap is not None:
            return snap
    return None


def resolve_held(item: dict[str, Any], receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    """Use persisted snapshot; old rows fall back to the held receipt."""
    held = item.get("held")
    if isinstance(held, dict) and held.get("call_id") and held.get("tool"):
        out = dict(held)
        args = dict(out.get("args") or {})
        out["args"] = args
        if not out.get("subject"):
            subject = subject_from_args(args)
            if subject:
                out["subject"] = subject
        return out
    if receipt is None:
        return None
    return snapshot_from_proposals(receipt.get("proposals") or [])
