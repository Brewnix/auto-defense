"""brewnix-rules/expiry — ledger tick, not Suricata-driven."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from aimmune.canonical import features_digest, rfc3339
from aimmune.sensors.eve_to_bundle import stub_health

EXPIRY_ACTOR = {
    "kind": "rule",
    "id": "brewnix-rules/expiry",
    "purpose": "triage",
}


def ledger_snapshot_bundle(
    ip: str,
    *,
    alias: str = "ai_autoblock",
    wan_up: bool = True,
) -> dict[str, Any]:
    _ = alias
    return {
        "window_s": 1,
        "counts": {"alert_total": 0, "by_sid": {}, "by_src": {}},
        "top_subjects": [{"ip": ip, "hits": 1}],
        "health": stub_health(wan_up=wan_up),
        "whitelist_hits": 0,
        "prior_blocks": [{"ip": ip, "remaining_ttl_s": 0}],
    }


def emit_expiry_envelope(
    ip: str,
    *,
    site_id: str,
    observed_at,
    alias: str = "ai_autoblock",
    classes: list[str] | None = None,
    parent_receipt_id: str | None = None,
    wan_up: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle = ledger_snapshot_bundle(ip, alias=alias, wan_up=wan_up)
    digest = features_digest(bundle)
    threat_classes = classes if classes else ["unknown"]
    refs = [f"ledger:ttl:{ip}"]
    if parent_receipt_id:
        refs.append(f"receipt:{parent_receipt_id}")
    envelope = {
        "schema": "fyber.inference_iface/v0",
        "trace_id": str(uuid4()),
        "site_id": site_id,
        "actor": dict(EXPIRY_ACTOR),
        "observed_at": rfc3339(observed_at) if not isinstance(observed_at, str) else observed_at,
        "inputs_digest": digest,
        "judgment": {
            "severity": "info",
            "classes": threat_classes,
            "subjects": [{"kind": "ip", "value": ip}],
            "summary": f"TTL expired for {ip} on {alias}"[:280],
            "evidence_refs": refs[:16],
        },
        "proposals": [
            {
                "call_id": str(uuid4()),
                "tool": "firewall.unblock_ip",
                "mode": "execute",
                "reason_code": "ttl_expired",
                "args": {"ip": ip, "alias": alias},
            }
        ],
        "confidence": 1.0,
        "needs_human": False,
    }
    return envelope, bundle
