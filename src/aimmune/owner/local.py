"""Site-local owner approve/deny. Reuses slice-2 apply_resolution.

Allowed when ``plane_reachable=false`` **or** no non-terminal auditor watch
exists. When a watch/ticket is open and the plane is up, refuse — the
operator waits on plane poll (do not double-resolve from the site).

Apply semantics stay in ``aimmune.notify.drain.apply_resolution``.
"""

from __future__ import annotations

from typing import Any

from aimmune.canonical import rfc3339
from aimmune.notify.drain import apply_resolution
from aimmune.notify.held import resolve_held, snapshot_from_proposals
from aimmune.store import read_jsonl
from aimmune.ui.status import find_apply_receipt, receipt_applied_block, watch_nonterminal

RESOLUTIONS = frozenset({"approved", "denied"})
LOCAL_RESOLVED_BY = "aimmune:owner:local"


class LocalResolveError(RuntimeError):
    pass


class WaitingOnPlaneError(LocalResolveError):
    """Open auditor watch + plane reachable — site must not resolve."""


def _queue_row(rt: Any, receipt_id: str) -> dict[str, Any] | None:
    for row in read_jsonl(rt.config.notify_queue_path):
        if row.get("receipt_id") == receipt_id:
            return row
    return None


def _watch_for_receipt(rt: Any, receipt_id: str) -> dict[str, Any] | None:
    chosen: dict[str, Any] | None = None
    for row in rt.watches.rows():
        if row.get("receipt_id") != receipt_id:
            continue
        if watch_nonterminal(row):
            return row
        chosen = row
    return chosen


def local_resolve(
    rt: Any,
    receipt_id: str,
    resolution: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    if resolution not in RESOLUTIONS:
        raise LocalResolveError(f"resolution must be approved or denied, not {resolution}")

    held_receipt = rt.chain.get(receipt_id)
    if held_receipt is None:
        raise LocalResolveError(f"receipt {receipt_id} not found")

    queue = _queue_row(rt, receipt_id)
    watch = _watch_for_receipt(rt, receipt_id)
    apply_receipt = find_apply_receipt(rt.chain.load(), receipt_id, watch)
    if apply_receipt is not None or (watch and watch.get("status") == "acked"):
        raise LocalResolveError(f"receipt {receipt_id} already applied or acked")

    if watch_nonterminal(watch) and rt.config.plane_reachable:
        ticket_id = watch.get("ticket_id") if watch else None
        raise WaitingOnPlaneError(
            f"auditor ticket {ticket_id} is open and the plane is reachable; "
            "wait for plane resolve (do not double-resolve from the site)"
        )

    held = resolve_held(queue or watch or {}, held_receipt)
    if held is None:
        held = snapshot_from_proposals(held_receipt.get("proposals") or [])
    if held is None:
        raise LocalResolveError(f"no held companion for receipt {receipt_id}")

    synthetic_watch = dict(watch) if watch else {
        "receipt_id": receipt_id,
        "held": held,
        "incident_id": (queue or {}).get("incident_id"),
        "ticket_id": None,
        "trace_id": (queue or {}).get("trace_id") or held_receipt.get("trace_id"),
        "site_id": (queue or {}).get("site_id") or held_receipt.get("site_id"),
    }
    if not synthetic_watch.get("held"):
        synthetic_watch["held"] = held

    ticket: dict[str, Any] = {
        "resolution": resolution,
        "resolved_by": LOCAL_RESOLVED_BY,
        "resolved_at": rfc3339(rt.clock.now()),
        "ticket_id": synthetic_watch.get("ticket_id"),
    }
    if note and str(note).strip():
        ticket["owner_note"] = str(note).strip()[:500]

    child = apply_resolution(rt, synthetic_watch, ticket)

    if queue and not queue.get("drained"):
        rt.notify.mark_drained(receipt_id, ticket_id=synthetic_watch.get("ticket_id"))

    if watch and watch.get("ticket_id"):
        latest = rt.watches.get(str(watch["ticket_id"])) or dict(watch)
        if latest.get("preempt_queued"):
            latest["local_owner"] = True
            latest["updated_at"] = rfc3339(rt.clock.now())
            rt.watches.upsert(latest)
        elif latest.get("status") != "acked":
            ack_id = child.get("receipt_id")
            if ack_id == held_receipt.get("receipt_id"):
                ack_id = None
            latest.update(
                {
                    "status": "acked",
                    "resolution": resolution,
                    "site_acked_receipt_id": ack_id or latest.get("site_acked_receipt_id"),
                    "apply_receipt_id": ack_id or latest.get("apply_receipt_id"),
                    "local_owner": True,
                    "updated_at": rfc3339(rt.clock.now()),
                }
            )
            rt.watches.upsert(latest)

    # Hypermesh approved returns the held receipt (queued for preempt run).
    if receipt_applied_block(child) or child.get("receipt_id") != receipt_id:
        return child
    return child
