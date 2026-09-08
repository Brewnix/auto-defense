"""Drain notify queue to fyber.auditor and poll watches (slice 2, Phase A)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from aimmune.auditor.client import AuditorError
from aimmune.canonical import rfc3339
from aimmune.notify.held import resolve_held, snapshot_from_proposals
from aimmune.preempt.policy import HYPERMESH_TOOLS
from aimmune.receipt.chain import build_receipt
from aimmune.schema import validate_receipt

TICKET_SCHEMA = "fyber.auditor.ticket/v0"
EXECUTOR_FW = "opnsense-api@site"
EXECUTOR_NOTIFY = "auditor-api@site"
ALLOWED_PATCH_KEYS = {
    "firewall.block_ip": frozenset({"ttl_s"}),
}
TTL_MIN = 1
TTL_MAX = 604800


class AmendedPatchError(ValueError):
    pass


class DrainResult:
    def __init__(self) -> None:
        self.drained = 0
        self.skipped = 0
        self.errors: list[str] = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "drained": self.drained,
            "skipped": self.skipped,
            "errors": list(self.errors),
        }


class PollResult:
    def __init__(self) -> None:
        self.polled = 0
        self.acked = 0
        self.errors: list[str] = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "polled": self.polled,
            "acked": self.acked,
            "errors": list(self.errors),
        }


def ticket_body_from_queue_item(
    item: dict[str, Any],
    held: dict[str, Any],
) -> dict[str, Any]:
    proposal = item.get("proposal") or {}
    args = proposal.get("args") or {}
    display: dict[str, Any] = {
        "tool": held["tool"],
        "subject": held["subject"],
    }
    ttl = held.get("ttl_s") or (held.get("args") or {}).get("ttl_s")
    if ttl is not None:
        display["ttl_s"] = int(ttl)
    return {
        "schema": TICKET_SCHEMA,
        "site_id": item["site_id"],
        "trace_id": item["trace_id"],
        "receipt_id": item.get("receipt_id"),
        "held_call_id": held["call_id"],
        "reason_code": proposal.get("reason_code"),
        "severity": args.get("severity"),
        "text_redacted": args.get("text_redacted"),
        "display": display,
    }


def validate_amended_patch(tool: str, patch: dict[str, Any] | None) -> int:
    """Return patched ttl_s. Reject empty / unknown keys client-side."""
    if not patch:
        raise AmendedPatchError("amended patch missing")
    allowed = ALLOWED_PATCH_KEYS.get(tool, frozenset())
    unknown = sorted(set(patch) - allowed)
    if unknown:
        raise AmendedPatchError(f"unknown patch keys: {unknown}")
    if "ttl_s" not in patch:
        raise AmendedPatchError("amended patch missing ttl_s")
    try:
        ttl_s = int(patch["ttl_s"])
    except (TypeError, ValueError) as exc:
        raise AmendedPatchError("ttl_s must be an integer") from exc
    if ttl_s < TTL_MIN or ttl_s > TTL_MAX:
        raise AmendedPatchError("ttl_s out of range")
    return ttl_s


def drain_queue(rt: Any) -> DrainResult:
    result = DrainResult()
    if rt.auditor is None:
        result.errors.append("auditor client not configured")
        return result
    for item in rt.notify.pending():
        try:
            receipt = rt.chain.get(item["receipt_id"])
            held = resolve_held(item, receipt)
            if held is None:
                result.skipped += 1
                result.errors.append(
                    f"no held companion for receipt {item.get('receipt_id')}"
                )
                continue
            body = ticket_body_from_queue_item(item, held)
            ticket = rt.auditor.create_ticket(body)
            ticket_id = str(ticket.get("ticket_id") or "")
            if not ticket_id:
                result.errors.append("create returned no ticket_id")
                continue
            rt.notify.mark_drained(item["receipt_id"], ticket_id)
            now = rfc3339(rt.clock.now())
            rt.watches.upsert(
                {
                    "ticket_id": ticket_id,
                    "receipt_id": item["receipt_id"],
                    "trace_id": item["trace_id"],
                    "site_id": item["site_id"],
                    "incident_id": item.get("incident_id"),
                    "held": held,
                    "status": ticket.get("status") or "open",
                    "resolution": ticket.get("resolution"),
                    "site_acked_receipt_id": ticket.get("site_acked_receipt_id"),
                    "updated_at": now,
                }
            )
            if item.get("incident_id"):
                rt.incidents.attach_ticket(str(item["incident_id"]), ticket_id)
            result.drained += 1
        except AuditorError as exc:
            result.errors.append(str(exc)[:200])
        except Exception as exc:  # noqa: BLE001 — leave row pending
            result.errors.append(str(exc)[:200])
    return result


def poll_tickets(rt: Any) -> PollResult:
    result = PollResult()
    if rt.auditor is None:
        result.errors.append("auditor client not configured")
        return result
    for watch in rt.watches.open_watches():
        ticket_id = watch.get("ticket_id")
        if not ticket_id:
            continue
        result.polled += 1
        try:
            ticket = rt.auditor.get_ticket(str(ticket_id))
        except AuditorError as exc:
            result.errors.append(str(exc)[:200])
            continue
        if watch.get("preempt_queued"):
            continue
        status = ticket.get("status")
        if status == "acked":
            watch.update(
                {
                    "status": "acked",
                    "resolution": ticket.get("resolution"),
                    "site_acked_receipt_id": ticket.get("site_acked_receipt_id"),
                    "updated_at": rfc3339(rt.clock.now()),
                }
            )
            rt.watches.upsert(watch)
            continue
        if status != "resolved":
            watch["status"] = status or "open"
            watch["updated_at"] = rfc3339(rt.clock.now())
            rt.watches.upsert(watch)
            continue
        try:
            child = apply_resolution(rt, watch, ticket)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(str(exc)[:200])
            continue
        if watch.get("preempt_queued"):
            # Host jobs run in `aimmune preempt run`, which acks after apply.
            continue
        try:
            acked = rt.auditor.ack_ticket(str(ticket_id), child["receipt_id"])
        except AuditorError as exc:
            result.errors.append(str(exc)[:200])
            watch.update(
                {
                    "status": "resolved",
                    "resolution": ticket.get("resolution"),
                    "apply_receipt_id": child["receipt_id"],
                    "updated_at": rfc3339(rt.clock.now()),
                }
            )
            rt.watches.upsert(watch)
            continue
        watch.update(
            {
                "status": acked.get("status") or "acked",
                "resolution": ticket.get("resolution"),
                "site_acked_receipt_id": acked.get("site_acked_receipt_id")
                or child["receipt_id"],
                "updated_at": rfc3339(rt.clock.now()),
            }
        )
        rt.watches.upsert(watch)
        result.acked += 1
    return result


def sync_plane(rt: Any) -> dict[str, Any]:
    """Drain then poll. Short timeouts live on the client; never raise."""
    drained = drain_queue(rt)
    polled = poll_tickets(rt)
    return {"drain": drained.as_dict(), "poll": polled.as_dict()}


def apply_resolution(
    rt: Any,
    watch: dict[str, Any],
    ticket: dict[str, Any],
) -> dict[str, Any]:
    held_receipt = rt.chain.get(watch["receipt_id"])
    if held_receipt is None:
        raise RuntimeError(f"held receipt {watch.get('receipt_id')} missing")
    held = watch.get("held") or resolve_held(watch, held_receipt)
    if held is None:
        held = snapshot_from_proposals(held_receipt.get("proposals") or [])
    if held is None:
        raise RuntimeError("held companion missing")

    resolution = ticket.get("resolution")
    if resolution not in {"approved", "denied", "timed_out", "amended"}:
        raise RuntimeError(f"unknown resolution {resolution}")

    executions: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    decision = "observe"
    applied_block = False
    annotate_text = None
    ttl_s: int | None = held.get("ttl_s") or (held.get("args") or {}).get("ttl_s")
    patch_ok = True

    if str(held.get("tool") or "") in HYPERMESH_TOOLS:
        return _queue_hypermesh_resolution(rt, watch, ticket, held, held_receipt, resolution)

    if resolution == "approved":
        decision = "execute"
        proposal = _companion_proposal(held, ttl_s=ttl_s)
        proposals.append(proposal)
        execution, applied_block = _actuate_companion(rt, held, proposal, ttl_s)
        executions.append(execution)
        if applied_block:
            _record_ledger(rt, held, proposal, held_receipt, ttl_s)
    elif resolution == "amended":
        try:
            ttl_s = validate_amended_patch(str(held["tool"]), ticket.get("patch"))
        except AmendedPatchError as exc:
            patch_ok = False
            annotate_text = f"amended patch rejected: {exc}"
        else:
            decision = "execute"
            proposal = _companion_proposal(held, ttl_s=ttl_s)
            proposals.append(proposal)
            execution, applied_block = _actuate_companion(rt, held, proposal, ttl_s)
            executions.append(execution)
            if applied_block:
                _record_ledger(rt, held, proposal, held_receipt, ttl_s)
            annotate_text = f"amended ttl_s={ttl_s}"
    else:
        annotate_text = f"auditor {resolution}; observe only"

    owner_note = ticket.get("owner_note")
    if isinstance(owner_note, str) and owner_note.strip():
        extra = owner_note.strip()[:500]
        annotate_text = f"{annotate_text}; {extra}" if annotate_text else extra

    if annotate_text:
        annotate = {
            "call_id": str(uuid4()),
            "tool": "receipt.annotate",
            "mode": "execute",
            "reason_code": "auditor_annotate",
            "args": {
                "receipt_id": held_receipt["receipt_id"],
                "text": annotate_text[:2000],
            },
        }
        proposals.append(annotate)
        now = rt.clock.now()
        executions.append(
            {
                "call_id": annotate["call_id"],
                "tool": "receipt.annotate",
                "status": "applied",
                "executor": EXECUTOR_NOTIFY,
                "started_at": rfc3339(now),
                "finished_at": rfc3339(now),
                "effect": {
                    "ticket_id": ticket.get("ticket_id") or watch.get("ticket_id"),
                    "resolution": resolution,
                    "patch_applied": patch_ok and resolution == "amended",
                },
                "error": None,
            }
        )

    incident_id = watch.get("incident_id") or rt.incidents.find_by_receipt(
        held_receipt["receipt_id"]
    )
    if incident_id:
        for row in executions:
            if isinstance(row.get("effect"), dict):
                row["effect"] = {**row["effect"], "incident_id": incident_id}

    child_id = str(uuid4())
    receipt = build_receipt(
        site_id=rt.config.site_id,
        trace_id=str(uuid4()),
        ts=rt.clock.now(),
        purpose="contain" if applied_block else "triage",
        posture={
            "wan_up": rt.config.wan_up,
            "plane_reachable": rt.config.plane_reachable,
            "path_b": "n/a",
            "sell_state": (
                rt.config.sell_state
                if rt.config.sell_state in {"off", "on", "paused", "n/a"}
                else "off"
            ),
        },
        features_digest=(held_receipt.get("input") or {}).get("features_digest")
        or "sha256:" + ("0" * 64),
        window_s=int((held_receipt.get("input") or {}).get("window_s") or rt.config.window_s),
        judgment=held_receipt.get("judgment") or {
            "severity": "info",
            "classes": ["unknown"],
            "subjects": [held.get("subject") or {"kind": "host", "value": rt.config.site_id}],
            "summary": f"auditor {resolution}",
            "evidence_refs": ["auditor:ticket"],
        },
        actor=held_receipt.get("actor")
        or {"kind": "rule", "id": "brewnix-rules/v0.1", "purpose": "triage"},
        proposals=proposals,
        policy_decision=decision,
        policy_rule_ids=list((held_receipt.get("policy") or {}).get("rule_ids") or []),
        execution=executions,
        human_required=True,
        prev_hash=rt.chain.tip_hash(),
        parent_id=held_receipt["receipt_id"],
        receipt_id=child_id,
        sources=["opnsense"],
        resolved_by=ticket.get("resolved_by"),
        resolved_at=ticket.get("resolved_at") or rfc3339(rt.clock.now()),
        resolution=resolution,
    )
    validate_receipt(receipt, rt.config.iface_pin)
    rt.chain.append(receipt)
    if incident_id:
        rt.incidents.attach_receipt(str(incident_id), child_id, now=rt.clock.now())
    return receipt


def _queue_hypermesh_resolution(
    rt: Any,
    watch: dict[str, Any],
    ticket: dict[str, Any],
    held: dict[str, Any],
    held_receipt: dict[str, Any],
    resolution: str,
) -> dict[str, Any]:
    """Auditor-approved hypermesh.* goes to the preempt runner — no Host RTT here."""
    if resolution == "approved":
        device_id = str(
            held.get("device_id")
            or (held.get("args") or {}).get("device_id")
            or ""
        )
        if not device_id:
            raise RuntimeError("hypermesh companion missing device_id")
        reason = str(
            held.get("reason_code")
            or (held.get("args") or {}).get("reason_code")
            or "site_defense"
        )
        proposals = [
            {
                "call_id": p["call_id"],
                "tool": p["tool"],
                "mode": "execute",
                "reason_code": p.get("reason_code") or reason,
                "args": dict(p.get("args") or {}),
            }
            for p in (held_receipt.get("proposals") or [])
            if p.get("tool") in HYPERMESH_TOOLS
        ]
        if not proposals:
            args = dict(held.get("args") or {})
            if held.get("tool") == "hypermesh.lease_stop":
                args["reason_code"] = args.get("reason_code") or reason
            proposals = [
                {
                    "call_id": held["call_id"],
                    "tool": held["tool"],
                    "mode": "execute",
                    "reason_code": reason,
                    "args": args,
                }
            ]
        rt.preempt_queue.enqueue(
            queued_at=rt.clock.now(),
            site_id=rt.config.site_id,
            device_id=device_id,
            proposals=proposals,
            origin_actor=held_receipt.get("actor")
            or {"kind": "rule", "id": "brewnix-rules/hypermesh-preempt-v0", "purpose": "triage"},
            reason_code=str(held.get("reason_code") or proposal.get("reason_code") or "site_defense"),
            human_approved=True,
            owner_ack=False,
            trace_id=watch.get("trace_id"),
            parent_receipt_id=held_receipt["receipt_id"],
            incident_id=watch.get("incident_id"),
            ticket_id=ticket.get("ticket_id") or watch.get("ticket_id"),
            judgment=held_receipt.get("judgment"),
        )
        watch.update(
            {
                "status": "resolved",
                "preempt_queued": True,
                "resolution": resolution,
                "updated_at": rfc3339(rt.clock.now()),
            }
        )
        rt.watches.upsert(watch)
        return held_receipt

    annotate_text = f"auditor {resolution}; observe only"
    annotate = {
        "call_id": str(uuid4()),
        "tool": "receipt.annotate",
        "mode": "execute",
        "reason_code": "auditor_annotate",
        "args": {
            "receipt_id": held_receipt["receipt_id"],
            "text": annotate_text[:2000],
        },
    }
    now = rt.clock.now()
    child_id = str(uuid4())
    receipt = build_receipt(
        site_id=rt.config.site_id,
        trace_id=str(uuid4()),
        ts=now,
        purpose="triage",
        posture={
            "wan_up": rt.config.wan_up,
            "plane_reachable": rt.config.plane_reachable,
            "path_b": "n/a",
            "sell_state": (
                rt.config.sell_state
                if rt.config.sell_state in {"off", "on", "paused", "n/a"}
                else "off"
            ),
        },
        features_digest=(held_receipt.get("input") or {}).get("features_digest")
        or "sha256:" + ("0" * 64),
        window_s=int((held_receipt.get("input") or {}).get("window_s") or rt.config.window_s),
        judgment=held_receipt.get("judgment") or {
            "severity": "info",
            "classes": ["unknown"],
            "subjects": [held.get("subject") or {"kind": "host", "value": rt.config.site_id}],
            "summary": f"auditor {resolution}",
            "evidence_refs": ["auditor:ticket"],
        },
        actor=held_receipt.get("actor")
        or {"kind": "rule", "id": "brewnix-rules/hypermesh-preempt-v0", "purpose": "triage"},
        proposals=[annotate],
        policy_decision="observe",
        policy_rule_ids=list((held_receipt.get("policy") or {}).get("rule_ids") or []),
        execution=[
            {
                "call_id": annotate["call_id"],
                "tool": "receipt.annotate",
                "status": "applied",
                "executor": EXECUTOR_NOTIFY,
                "started_at": rfc3339(now),
                "finished_at": rfc3339(now),
                "effect": {
                    "ticket_id": ticket.get("ticket_id") or watch.get("ticket_id"),
                    "resolution": resolution,
                    "patch_applied": False,
                },
                "error": None,
            }
        ],
        human_required=True,
        prev_hash=rt.chain.tip_hash(),
        parent_id=held_receipt["receipt_id"],
        receipt_id=child_id,
        sources=["hypermesh_host"],
        door="site_defense",
        resolved_by=ticket.get("resolved_by"),
        resolved_at=ticket.get("resolved_at") or rfc3339(now),
        resolution=resolution,
    )
    validate_receipt(receipt, rt.config.iface_pin)
    rt.chain.append(receipt)
    return receipt


def _companion_proposal(held: dict[str, Any], *, ttl_s: int | None) -> dict[str, Any]:
    args = dict(held.get("args") or {})
    if ttl_s is not None:
        args["ttl_s"] = int(ttl_s)
    proposal: dict[str, Any] = {
        "call_id": held["call_id"],
        "tool": held["tool"],
        "mode": "execute",
        "reason_code": "auditor_approved",
        "args": args,
    }
    if ttl_s is not None:
        proposal["ttl_s"] = int(ttl_s)
    return proposal


def _actuate_companion(
    rt: Any,
    held: dict[str, Any],
    proposal: dict[str, Any],
    ttl_s: int | None,
) -> tuple[dict[str, Any], bool]:
    args = proposal.get("args") or {}
    ip = str(args.get("ip") or (held.get("subject") or {}).get("value") or "")
    alias = str(args.get("alias") or rt.config.alias)
    started = rt.clock.now()
    applied = False
    error = None
    status = "failed"
    tool = held["tool"]
    try:
        if tool == "firewall.block_ip":
            rt.alias.add(ip, alias)
            status = "applied"
            applied = True
        elif tool == "firewall.unblock_ip":
            rt.alias.delete(ip, alias)
            status = "applied"
            applied = False
        else:
            status = "failed"
            error = f"companion tool {tool} not actuable"
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)[:500]
    finished = rt.clock.now()
    effect: dict[str, Any] = {"alias": alias, "ip": ip}
    if ttl_s is not None:
        effect["ttl_s"] = int(ttl_s)
    return (
        {
            "call_id": proposal["call_id"],
            "tool": tool,
            "status": status,
            "executor": EXECUTOR_FW,
            "started_at": rfc3339(started),
            "finished_at": rfc3339(finished),
            "effect": effect,
            "error": error,
        },
        applied,
    )


def _record_ledger(
    rt: Any,
    held: dict[str, Any],
    proposal: dict[str, Any],
    held_receipt: dict[str, Any],
    ttl_s: int | None,
) -> None:
    args = proposal.get("args") or {}
    ip = str(args.get("ip") or (held.get("subject") or {}).get("value") or "")
    alias = str(args.get("alias") or rt.config.alias)
    ttl = int(ttl_s or rt.config.block_ttl_s or 86400)
    finished = rt.clock.now()
    rt.rate_limit.record(finished, ip)
    rt.ledger.record(
        ip=ip,
        alias=alias,
        expire_at=rt.ledger.expire_at_from_ttl(finished, ttl),
        parent_receipt_id=held_receipt["receipt_id"],
        call_id=proposal["call_id"],
        classes=list((held_receipt.get("judgment") or {}).get("classes") or []),
        incident_id=rt.incidents.find_by_receipt(held_receipt["receipt_id"]),
    )
