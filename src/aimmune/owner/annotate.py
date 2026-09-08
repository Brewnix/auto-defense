"""Annotate-only write. Does not apply a held companion (write ≠ execute)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339
from aimmune.notify.held import resolve_held, snapshot_from_proposals
from aimmune.owner.local import LocalResolveError
from aimmune.receipt.chain import build_receipt
from aimmune.schema import validate_receipt
from aimmune.store import read_jsonl


def _queue_row(rt: Any, receipt_id: str) -> dict[str, Any] | None:
    for row in read_jsonl(rt.config.notify_queue_path):
        if row.get("receipt_id") == receipt_id:
            return row
    return None


def local_annotate(rt: Any, receipt_id: str, note: str) -> dict[str, Any]:
    text = (note or "").strip()[:500]
    if not text:
        raise LocalResolveError("note required")

    held_receipt = rt.chain.get(receipt_id)
    if held_receipt is None:
        raise LocalResolveError(f"receipt {receipt_id} not found")

    queue = _queue_row(rt, receipt_id)
    held = resolve_held(queue or {}, held_receipt) or snapshot_from_proposals(
        held_receipt.get("proposals") or []
    )
    now = rt.clock.now()
    call_id = str(uuid4())
    annotate = {
        "call_id": call_id,
        "tool": "receipt.annotate",
        "mode": "execute",
        "reason_code": "owner_annotate",
        "args": {"receipt_id": receipt_id, "text": text},
    }
    execution = {
        "call_id": call_id,
        "tool": "receipt.annotate",
        "status": "applied",
        "executor": "aimmune:owner:annotate",
        "started_at": rfc3339(now),
        "finished_at": rfc3339(now),
        "effect": {"receipt_id": receipt_id, "resolution": "annotate"},
        "error": None,
    }
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
        judgment=held_receipt.get("judgment")
        or {
            "severity": "info",
            "classes": ["unknown"],
            "subjects": [(held or {}).get("subject") or {"kind": "host", "value": rt.config.site_id}],
            "summary": "owner annotate",
            "evidence_refs": ["owner:annotate"],
        },
        actor={"kind": "human", "id": "aimmune:owner:annotate", "purpose": "triage"},
        proposals=[annotate],
        policy_decision="observe",
        policy_rule_ids=list((held_receipt.get("policy") or {}).get("rule_ids") or []),
        execution=[execution],
        human_required=False,
        prev_hash=rt.chain.tip_hash(),
        parent_id=held_receipt["receipt_id"],
        receipt_id=child_id,
        sources=["opnsense"],
        resolved_by="aimmune:owner:annotate",
        resolved_at=now,
        resolution=None,
    )
    validate_receipt(receipt, rt.config.iface_pin)
    rt.chain.append(receipt)
    incident_id = rt.incidents.find_by_receipt(receipt_id)
    if incident_id:
        rt.incidents.attach_receipt(str(incident_id), child_id, now=now)
    return receipt
