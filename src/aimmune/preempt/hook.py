"""Thin site_defense rules hook — flag-gated, emits proposals into the runner.

Trigger (exact — do not invent SID→lease_stop):
  1. ``AIMMUNE_SITE_DEFENSE_PREEMPT=true`` (or ``Config.site_defense_preempt``)
  2. At least one explicit ``AIMMUNE_HYPERMESH_DEVICE_IDS`` entry
  3. This IDS cycle applied a **critical** ``firewall.block_ip`` (rules path)
  4. Actor is ``kind: rule``

Then emit one envelope per configured device:
  - ``hypermesh.sell_pause`` with ``reason_code: site_defense``
  - ``hypermesh.lease_stop`` only when that device has an explicit lease_id
    in ``AIMMUNE_HYPERMESH_LEASE_IDS`` (``device_id:lease_id`` or a bare
    lease_id when exactly one device is configured). Never omit / pick-active.

Policy matrix still applies (strict: both tools propose+notify). The hook
does **not** await Host jobs and never selects ``preempt_mode=hard``.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from aimmune.canonical import features_digest
from aimmune.preempt.policy import HYPERMESH_TOOLS

HOOK_ACTOR = {
    "kind": "rule",
    "id": "brewnix-rules/hypermesh-preempt-v0",
    "purpose": "triage",
}
REASON = "site_defense"


def critical_contain_applied(receipts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for receipt in receipts:
        if (receipt.get("judgment") or {}).get("severity") != "critical":
            continue
        if (receipt.get("actor") or {}).get("kind") != "rule":
            continue
        if (receipt.get("policy") or {}).get("decision") != "execute":
            continue
        for row in receipt.get("execution") or []:
            if row.get("tool") == "firewall.block_ip" and row.get("status") == "applied":
                return receipt
    return None


def build_hook_proposals(
    *,
    device_id: str,
    lease_ids: list[str],
) -> list[dict[str, Any]]:
    proposals = [
        {
            "call_id": str(uuid4()),
            "tool": "hypermesh.sell_pause",
            "mode": "propose",
            "reason_code": REASON,
            "args": {"device_id": device_id},
        }
    ]
    for lease_id in lease_ids:
        if not lease_id:
            continue
        proposals.append(
            {
                "call_id": str(uuid4()),
                "tool": "hypermesh.lease_stop",
                "mode": "propose",
                "reason_code": REASON,
                "args": {"lease_id": lease_id, "reason_code": REASON},
            }
        )
    return proposals


def hook_should_fire(cfg, receipts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not cfg.site_defense_preempt:
        return None
    if not cfg.hypermesh_device_ids:
        return None
    return critical_contain_applied(receipts)


def leases_for_device(cfg, device_id: str) -> list[str]:
    return [lease for dev, lease in cfg.lease_bindings if dev == device_id]


def hook_judgment(parent: dict[str, Any], device_id: str) -> dict[str, Any]:
    parent_j = parent.get("judgment") or {}
    classes = list(parent_j.get("classes") or ["port_scan"])
    subjects = [
        {"kind": "host", "value": device_id},
        *[s for s in (parent_j.get("subjects") or []) if s.get("kind") == "ip"],
    ]
    return {
        "severity": "critical",
        "classes": classes,
        "subjects": subjects,
        "summary": f"site_defense preempt propose for {device_id}"[:280],
        "evidence_refs": ["eve:window", "contain:applied"],
    }


def hook_digest(device_id: str, proposals: list[dict[str, Any]]) -> str:
    return features_digest(
        {
            "hook": "site_defense",
            "device_id": device_id,
            "tools": [p.get("tool") for p in proposals if p.get("tool") in HYPERMESH_TOOLS],
        }
    )
