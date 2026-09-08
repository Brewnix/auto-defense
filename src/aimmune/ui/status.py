"""Pure hold/ticket/receipt display status — copy rules for AImmune UI v0.

Never claim **blocked** from a plane resolve (or local intent) alone.
``blocked`` is only allowed after a site apply receipt that actually applied
``firewall.block_ip`` **and** the ack path completed (or a local-owner ack
equivalent: ``site_acked_receipt_id`` set / watch ``acked``).
"""

from __future__ import annotations

from typing import Any

# Display enums (stable; UI + tests).
PENDING_INTENT = "pending_intent"
WAITING_ON_PLANE = "waiting_on_plane"
TIMED_OUT_WAITING = "timed_out_waiting"
APPROVED_PENDING_APPLY = "approved_pending_apply"
APPLIED_PENDING_ACK = "applied_pending_ack"
BLOCKED = "blocked"
OBSERVED = "observed"

WATCH_TERMINAL = frozenset({"acked"})

STATUS_LABELS: dict[str, str] = {
    PENDING_INTENT: "Pending intent — not blocked",
    WAITING_ON_PLANE: "Waiting on plane",
    TIMED_OUT_WAITING: "Timed out — waiting on site apply",
    APPROVED_PENDING_APPLY: "Approved intent — not blocked",
    APPLIED_PENDING_ACK: "Site applied — waiting on ack",
    BLOCKED: "Blocked",
    OBSERVED: "Observed — not blocked",
}

STATUS_CATALOG: list[dict[str, Any]] = [
    {"status": key, "label": label, "blocked": key == BLOCKED}
    for key, label in STATUS_LABELS.items()
]


def is_blocked_status(status: str) -> bool:
    return status == BLOCKED


def receipt_applied_block(receipt: dict[str, Any] | None) -> bool:
    """True only when this receipt's execution applied a firewall block."""
    if not receipt:
        return False
    for row in receipt.get("execution") or []:
        if row.get("tool") == "firewall.block_ip" and row.get("status") == "applied":
            return True
    return False


def receipt_human_resolution(receipt: dict[str, Any] | None) -> str | None:
    if not receipt:
        return None
    value = (receipt.get("human") or {}).get("resolution")
    return str(value) if value else None


def watch_acked(watch: dict[str, Any] | None) -> bool:
    if not watch:
        return False
    if watch.get("status") == "acked":
        return True
    if watch.get("site_acked_receipt_id") or watch.get("local_owner"):
        return True
    return False


def watch_nonterminal(watch: dict[str, Any] | None) -> bool:
    if not watch:
        return False
    return watch.get("status") not in WATCH_TERMINAL


def find_apply_receipt(
    receipts: list[dict[str, Any]],
    held_receipt_id: str,
    watch: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Child apply receipt for a held companion, if the site has written one."""
    if watch:
        rid = watch.get("site_acked_receipt_id") or watch.get("apply_receipt_id")
        if rid:
            for row in receipts:
                if row.get("receipt_id") == rid:
                    return row
    for row in receipts:
        if row.get("parent_id") != held_receipt_id:
            continue
        if receipt_human_resolution(row):
            return row
    return None


def display_receipt_status(receipt: dict[str, Any]) -> dict[str, Any]:
    """Status for a single receipt row. Resolve alone is never blocked."""
    if receipt_applied_block(receipt) and receipt_human_resolution(receipt):
        # Apply receipt that blocked — the receipts table may say blocked
        # for *this* child. Holds still require ack (see display_hold_status).
        return _view(BLOCKED)
    if receipt_applied_block(receipt):
        return _view(BLOCKED)
    resolution = receipt_human_resolution(receipt)
    if resolution == "timed_out":
        return _view(OBSERVED)
    if resolution in {"denied", "approved", "amended"}:
        return _view(OBSERVED if not receipt_applied_block(receipt) else BLOCKED)
    decision = (receipt.get("policy") or {}).get("decision")
    if decision in {"propose", "hold_human"}:
        return _view(PENDING_INTENT)
    return _view(OBSERVED)


def display_hold_status(
    *,
    queue: dict[str, Any] | None = None,
    watch: dict[str, Any] | None = None,
    apply_receipt: dict[str, Any] | None = None,
    plane_reachable: bool = False,
) -> dict[str, Any]:
    """Map queue + watch + apply receipt → display enum/label/can_local.

    Copy rules (locked):
    - Never ``blocked`` from resolve / intent alone.
    - ``pending_intent`` while held and not yet applied.
    - ``timed_out_waiting`` when plane resolution is timed_out and site
      has not written the apply receipt.
    - ``blocked`` only after a site apply receipt that actually blocked
      **and** the ack path (or local-owner ack) completed.
    """
    resolution = None
    if watch and watch.get("resolution"):
        resolution = str(watch["resolution"])
    elif apply_receipt:
        resolution = receipt_human_resolution(apply_receipt)

    applied_block = receipt_applied_block(apply_receipt)
    acked = watch_acked(watch)
    # Local apply without a plane watch: treat the apply receipt as acked.
    if apply_receipt and not watch:
        acked = True

    if applied_block and acked:
        return _view(BLOCKED, can_local=False)
    if applied_block and not acked:
        return _view(APPLIED_PENDING_ACK, can_local=False)

    if apply_receipt and not applied_block:
        return _view(OBSERVED, can_local=False)

    if resolution == "timed_out" and apply_receipt is None:
        return _view(
            TIMED_OUT_WAITING,
            can_local=_can_local(watch, plane_reachable, applied=False),
        )
    if resolution == "approved" and apply_receipt is None:
        return _view(
            APPROVED_PENDING_APPLY,
            can_local=_can_local(watch, plane_reachable, applied=False),
        )

    if watch_nonterminal(watch) and plane_reachable:
        return _view(WAITING_ON_PLANE, can_local=False)

    pending_queue = bool(queue) and not queue.get("drained")
    if pending_queue or watch_nonterminal(watch):
        return _view(
            PENDING_INTENT,
            can_local=_can_local(watch, plane_reachable, applied=False),
        )

    return _view(PENDING_INTENT, can_local=False)


def _can_local(
    watch: dict[str, Any] | None,
    plane_reachable: bool,
    *,
    applied: bool,
) -> bool:
    if applied:
        return False
    if watch_nonterminal(watch) and plane_reachable:
        return False
    return True


def _view(status: str, *, can_local: bool | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "label": STATUS_LABELS[status],
        "blocked": is_blocked_status(status),
    }
    if can_local is not None:
        out["can_local_resolve"] = can_local
    return out
