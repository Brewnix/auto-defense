"""Frozen prompt_route templates and empty emergency pack (slice 7 stubs)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# Tiny frozen registry. Unknown template_id → reject the grant.
PROMPT_ROUTE_TEMPLATES = frozenset(
    {
        "ir.triage.v0",
        "emergency.contain.v0",
    }
)

EMERGENCY_PACK_ID = "packs/emergency-v0"

TOOL_NAMES = frozenset(
    {
        "firewall.block_ip",
        "firewall.unblock_ip",
        "net.quarantine_host",
        "ids.suricata_pass",
        "health.restart_service",
        "health.set_nvpmodel",
        "hypermesh.lease_stop",
        "hypermesh.sell_pause",
        "notify.operator",
        "receipt.annotate",
    }
)


def _pack_paths() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        here.parent / "packs" / "emergency-v0.json",
        here.parents[3] / "packs" / "emergency-v0.json",
        Path.cwd() / "packs" / "emergency-v0.json",
    ]


@lru_cache(maxsize=1)
def emergency_pack_tools() -> frozenset[str]:
    """``packs/emergency-v0`` may ship empty and adds nothing."""
    for path in _pack_paths():
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        tools = data.get("tools") if isinstance(data, dict) else None
        if isinstance(tools, list):
            return frozenset(str(t) for t in tools)
    return frozenset()


def expand_tool_entry(entry: str) -> frozenset[str]:
    if entry == EMERGENCY_PACK_ID or entry == "emergency-v0":
        return emergency_pack_tools()
    return frozenset({entry})
