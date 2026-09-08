"""Assemble a redacted UI snapshot from site state (reads only)."""

from __future__ import annotations

from typing import Any

from aimmune.notify.held import resolve_held
from aimmune.store import read_jsonl
from aimmune.ui.serialize import (
    serialize_held,
    serialize_incident,
    serialize_preempt_queue_row,
    serialize_receipt,
)
from aimmune.ui.status import (
    STATUS_CATALOG,
    display_hold_status,
    display_receipt_status,
    find_apply_receipt,
)


def sell_state_view(receipts: list[dict[str, Any]], cfg: Any) -> dict[str, Any]:
    """Best-effort sell_state from last receipt. Live #41 cache is optional/stale OK."""
    if receipts:
        last = receipts[-1]
        posture = last.get("posture") or {}
        value = posture.get("sell_state")
        if value in {"off", "on", "paused", "n/a"}:
            return {
                "value": value,
                "stale": True,
                "source": "last_receipt",
                "ts": last.get("ts"),
                "receipt_id": last.get("receipt_id"),
            }
    env_value = getattr(cfg, "sell_state", None)
    if env_value in {"off", "on", "paused", "n/a"}:
        return {
            "value": env_value,
            "stale": True,
            "source": "env",
            "ts": None,
            "receipt_id": None,
        }
    return {
        "value": "unknown",
        "stale": True,
        "source": None,
        "ts": None,
        "receipt_id": None,
    }


def _queue_rows(rt: Any) -> list[dict[str, Any]]:
    return read_jsonl(rt.config.notify_queue_path)


def _hold_index(
    receipts: list[dict[str, Any]],
    queue_rows: list[dict[str, Any]],
    watches: list[dict[str, Any]],
    *,
    plane_reachable: bool,
) -> list[dict[str, Any]]:
    by_receipt: dict[str, dict[str, Any]] = {}

    def bucket(receipt_id: str) -> dict[str, Any]:
        return by_receipt.setdefault(
            receipt_id,
            {"receipt_id": receipt_id, "queue": None, "watch": None},
        )

    for row in queue_rows:
        rid = row.get("receipt_id")
        if not rid:
            continue
        bucket(str(rid))["queue"] = row
    for row in watches:
        rid = row.get("receipt_id")
        if not rid:
            continue
        item = bucket(str(rid))
        # Prefer a non-acked watch when several exist.
        existing = item.get("watch")
        if existing is None or existing.get("status") == "acked":
            item["watch"] = row
        elif row.get("status") != "acked":
            item["watch"] = row

    holds: list[dict[str, Any]] = []
    for rid, item in by_receipt.items():
        receipt = next((r for r in receipts if r.get("receipt_id") == rid), None)
        held = resolve_held(item.get("queue") or item.get("watch") or {}, receipt)
        apply_receipt = find_apply_receipt(receipts, rid, item.get("watch"))
        view = display_hold_status(
            queue=item.get("queue"),
            watch=item.get("watch"),
            apply_receipt=apply_receipt,
            plane_reachable=plane_reachable,
        )
        queue = item.get("queue") or {}
        watch = item.get("watch") or {}
        holds.append(
            {
                "receipt_id": rid,
                "ticket_id": watch.get("ticket_id") or queue.get("ticket_id"),
                "trace_id": watch.get("trace_id") or queue.get("trace_id"),
                "incident_id": watch.get("incident_id") or queue.get("incident_id"),
                "queued_at": queue.get("queued_at"),
                "drained": bool(queue.get("drained")) if queue else bool(watch),
                "watch_status": watch.get("status"),
                "resolution": watch.get("resolution"),
                "held": serialize_held(held),
                "apply_receipt_id": (apply_receipt or {}).get("receipt_id"),
                **view,
            }
        )
    holds.sort(key=lambda row: str(row.get("queued_at") or ""), reverse=True)
    return holds


def _hypermesh_receipts(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for receipt in receipts:
        tools = [p.get("tool") for p in (receipt.get("proposals") or [])]
        tools.extend(ex.get("tool") for ex in (receipt.get("execution") or []))
        if any(str(t).startswith("hypermesh.") for t in tools if t):
            out.append(receipt)
    return out


def build_snapshot(rt: Any, *, limit: int = 50) -> dict[str, Any]:
    receipts = rt.chain.load()
    queue_rows = _queue_rows(rt)
    watches = rt.watches.rows()
    incidents = read_jsonl(rt.config.incidents_path)
    preempt_rows = read_jsonl(rt.config.preempt_queue_path)
    plane = bool(rt.config.plane_reachable)
    recent = receipts[-limit:] if limit else receipts
    hyper = _hypermesh_receipts(receipts)[-limit:]
    return {
        "site_id": rt.config.site_id,
        "plane_reachable": plane,
        "sell_state": sell_state_view(receipts, rt.config),
        "status_catalog": list(STATUS_CATALOG),
        "receipts": [
            serialize_receipt(row, display=display_receipt_status(row))
            for row in reversed(recent)
        ],
        "holds": _hold_index(receipts, queue_rows, watches, plane_reachable=plane),
        "incidents": [serialize_incident(row) for row in reversed(incidents[-limit:])],
        "preempt": {
            "queue": [serialize_preempt_queue_row(row) for row in preempt_rows if not row.get("done")],
            "receipts": [
                serialize_receipt(row, display=display_receipt_status(row))
                for row in reversed(hyper)
            ],
        },
    }
