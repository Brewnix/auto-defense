"""Read-only cottage status for ``aimmune status``.

Does not create the state dir, call the plane, or mutate JSONL. Exit 0 is
always informational — missing state is reported in the payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aimmune.clock import Clock
from aimmune.config import Config
from aimmune.grants.store import GrantStore, is_active
from aimmune.incident.minimal import IncidentStore
from aimmune.notify.queue import NotifyQueue
from aimmune.preempt.queue import PreemptQueue
from aimmune.receipt.chain import ReceiptChain
from aimmune.store import read_json
from aimmune.ui.snapshot import sell_state_view


def _path_exists(path: Path) -> bool:
    return path.is_file() or path.is_dir()


def _dir_mode(path: Path) -> str | None:
    if not path.is_dir():
        return None
    try:
        return oct(path.stat().st_mode & 0o777)
    except OSError:
        return None


def _last_receipt_view(receipts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not receipts:
        return None
    last = receipts[-1]
    return {
        "receipt_id": last.get("receipt_id"),
        "ts": last.get("ts"),
        "purpose": last.get("purpose"),
        "decision": (last.get("policy") or {}).get("decision"),
    }


def build_status(
    cfg: Config,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assemble a read-only summary from ``cfg.state_dir`` + env config."""
    clock = now or Clock().now()
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)

    state_dir = cfg.state_dir
    state_exists = state_dir.is_dir()
    receipts = ReceiptChain(cfg.receipts_path).load() if state_exists else []
    pending_notify = NotifyQueue(cfg.notify_queue_path).pending() if state_exists else []
    pending_preempt = PreemptQueue(cfg.preempt_queue_path).pending() if state_exists else []
    incidents = IncidentStore(cfg.incidents_path, cfg.incident_index_path)
    open_incidents = incidents.find_open(cfg.site_id) if state_exists else []
    grant_rows = GrantStore(cfg.grants_path).list() if state_exists else []
    active_grants = [row for row in grant_rows if is_active(row, clock)]
    proposed_grants = [row for row in grant_rows if row.get("status") == "proposed"]
    last_cycle = read_json(cfg.last_cycle_path) if state_exists else None
    last_receipt = _last_receipt_view(receipts)
    if last_cycle is None and last_receipt is not None:
        last_cycle = {
            "finished_at": last_receipt.get("ts"),
            "receipt_count": 1,
            "receipt_ids": [last_receipt.get("receipt_id")],
            "decisions": [last_receipt.get("decision")],
            "purposes": [last_receipt.get("purpose")],
            "plane_reachable": cfg.plane_reachable,
            "inferred_from": "last_receipt",
        }

    paths = {
        "receipts.jsonl": _path_exists(cfg.receipts_path),
        "notify_queue.jsonl": _path_exists(cfg.notify_queue_path),
        "incidents.jsonl": _path_exists(cfg.incidents_path),
        "grants.jsonl": _path_exists(cfg.grants_path),
        "last_cycle.json": _path_exists(cfg.last_cycle_path),
        "preempt_queue.jsonl": _path_exists(cfg.preempt_queue_path),
        "auditor_watch.jsonl": _path_exists(cfg.auditor_watch_path),
        "ttl_ledger.jsonl": _path_exists(cfg.ttl_ledger_path),
    }

    ui_loopback = cfg.ui_host in {"127.0.0.1", "localhost", "::1"}
    return {
        "site_id": cfg.site_id,
        "plane_reachable": cfg.plane_reachable,
        "panopticon_configured": bool(cfg.panopticon_base_url and cfg.hm_site_token),
        "hm_site_token_set": bool(cfg.hm_site_token),
        "exec_mock": cfg.exec_mock,
        "cycle_seconds": cfg.cycle_seconds,
        "state_dir": str(state_dir),
        "state_dir_exists": state_exists,
        "state_dir_mode": _dir_mode(state_dir),
        "paths": paths,
        "receipts": {
            "count": len(receipts),
            "last": last_receipt,
        },
        "last_cycle": last_cycle,
        "pending_notify": len(pending_notify),
        "pending_preempt": len(pending_preempt),
        "open_incidents": len(open_incidents),
        "active_grants": len(active_grants),
        "proposed_grants": len(proposed_grants),
        "rails_stub_grant_active": bool(cfg.triage.rails.grant_active),
        "sell_state": sell_state_view(receipts, cfg),
        "eve_path": str(cfg.eve_path) if cfg.eve_path else None,
        "eve_path_exists": bool(cfg.eve_path and cfg.eve_path.is_file()),
        "host_owner_sock": str(cfg.resolved_owner_sock) if cfg.resolved_owner_sock else None,
        "host_owner_sock_exists": bool(
            cfg.resolved_owner_sock and cfg.resolved_owner_sock.exists()
        ),
        "ui_token_set": bool(cfg.ui_token),
        "ui_listen": f"{cfg.ui_host}:{cfg.ui_port}",
        "ui_loopback": ui_loopback,
    }


def format_status_text(payload: dict[str, Any]) -> str:
    """Human-readable dump. Same fields as the JSON payload."""
    exists = "exists" if payload.get("state_dir_exists") else "MISSING"
    mode = payload.get("state_dir_mode")
    mode_s = f" mode={mode}" if mode else ""
    last = (payload.get("receipts") or {}).get("last") or {}
    last_s = "none"
    if last.get("receipt_id"):
        last_s = f"{last.get('receipt_id')} @ {last.get('ts')} ({last.get('decision')})"
    cycle = payload.get("last_cycle") or {}
    if cycle:
        inferred = " (inferred)" if cycle.get("inferred_from") else ""
        cycle_s = (
            f"{cycle.get('receipt_count', 0)} receipt(s); "
            f"decisions={cycle.get('decisions')}; "
            f"finished_at={cycle.get('finished_at')}{inferred}"
        )
    else:
        cycle_s = "none"
    sell = payload.get("sell_state") or {}
    sell_s = f"{sell.get('value')} ({sell.get('source')}, stale={sell.get('stale')})"
    path_lines = []
    for name, present in (payload.get("paths") or {}).items():
        path_lines.append(f"    {name}: {'yes' if present else 'no'}")
    bind_note = (
        "loopback default"
        if payload.get("ui_loopback")
        else "non-loopback bind is an explicit opt-in"
    )
    lines = [
        f"site_id: {payload.get('site_id')}",
        f"plane_reachable: {payload.get('plane_reachable')}",
        f"panopticon_configured: {payload.get('panopticon_configured')}",
        f"exec_mock: {payload.get('exec_mock')}",
        f"state_dir: {payload.get('state_dir')} ({exists}{mode_s})",
        "paths:",
        *path_lines,
        f"receipts: {(payload.get('receipts') or {}).get('count', 0)}",
        f"last_receipt: {last_s}",
        f"last_cycle: {cycle_s}",
        f"pending_notify: {payload.get('pending_notify')}",
        f"pending_preempt: {payload.get('pending_preempt')}",
        f"open_incidents: {payload.get('open_incidents')}",
        f"active_grants: {payload.get('active_grants')}",
        f"proposed_grants: {payload.get('proposed_grants')}",
        f"sell_state: {sell_s}",
        f"eve_path: {payload.get('eve_path') or 'unset'} "
        f"(exists={payload.get('eve_path_exists')})",
        f"ui_token_set: {payload.get('ui_token_set')}",
        f"ui_listen: {payload.get('ui_listen')} ({bind_note})",
    ]
    return "\n".join(lines) + "\n"
