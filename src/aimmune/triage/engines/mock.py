"""Fixture-backed engine for CI. Never talks to a live model."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from aimmune.triage.engines.base import EngineResult

SCENARIOS = frozenset(
    {"propose", "execute", "schema_fail", "unavailable", "low_confidence", "unbound"}
)


def _actor_id(engine_id: str) -> str:
    digest = hashlib.sha256(engine_id.encode("utf-8")).hexdigest()
    return f"{engine_id}@sha256:{digest}"


def _primary_ip(bundle: dict[str, Any], fallback: str = "203.0.113.50") -> str:
    for subject in bundle.get("top_subjects") or []:
        if subject.get("ip"):
            return str(subject["ip"])
    for ip in (bundle.get("counts") or {}).get("by_src") or {}:
        return str(ip)
    return fallback


def fixture_envelope(
    *,
    scenario: str,
    bundle: dict[str, Any],
    site_id: str,
    observed_at: str,
    inputs_digest: str,
    engine_id: str,
    alias: str = "ai_autoblock",
) -> dict[str, Any]:
    """Build a schema-shaped (or intentionally invalid) model envelope."""
    ip = _primary_ip(bundle)
    actor = {
        "kind": "model",
        "id": _actor_id(engine_id),
        "purpose": "triage",
    }
    if scenario == "schema_fail":
        return {
            "schema": "fyber.inference_iface/v0",
            "actor": actor,
            "judgment": {"severity": "high"},
            "proposals": [{"tool": "not.a.tool", "mode": "execute"}],
        }
    if scenario == "unbound":
        ip = "198.51.100.99"
    mode = "execute" if scenario == "execute" else "propose"
    confidence = 0.41 if scenario == "low_confidence" else 0.74
    severity = "critical" if scenario == "execute" else "high"
    block = {
        "call_id": str(uuid4()),
        "tool": "firewall.block_ip",
        "mode": mode,
        "ttl_s": 86400,
        "reason_code": "ssh_brute",
        "args": {
            "ip": ip,
            "alias": alias,
            "direction": "wan_in",
            "ttl_s": 86400,
        },
    }
    notify = {
        "call_id": str(uuid4()),
        "tool": "notify.operator",
        "mode": "execute",
        "reason_code": "propose_needs_ack",
        "args": {
            "channel": "fyber.auditor",
            "severity": severity,
            "text_redacted": (
                f"propose_needs_ack site={site_id} actor=model ip={ip} "
                "rails_profile=strict"
            )[:1000],
        },
    }
    proposals = [block, notify] if mode == "propose" else [block]
    return {
        "schema": "fyber.inference_iface/v0",
        "trace_id": str(uuid4()),
        "site_id": site_id,
        "actor": actor,
        "observed_at": observed_at,
        "inputs_digest": inputs_digest,
        "judgment": {
            "severity": severity,
            "classes": ["brute_force"],
            "subjects": [{"kind": "ip", "value": ip}],
            "summary": f"model {scenario} for {ip}"[:280],
            "evidence_refs": ["eve:window"],
        },
        "proposals": proposals,
        "confidence": confidence,
        "needs_human": mode != "execute",
    }


class MockEngine:
    kind = "mock"

    def __init__(
        self,
        *,
        engine_id: str = "mock-engine",
        scenario: str = "propose",
        envelopes_by_ip: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.id = engine_id
        self.scenario = scenario if scenario in SCENARIOS else "propose"
        self.envelopes_by_ip = envelopes_by_ip or {}
        self.call_count = 0

    def infer(
        self,
        bundle: dict[str, Any],
        *,
        site_id: str,
        observed_at: str,
        inputs_digest: str,
        rails_profile: str,
        allowlisted_tools: list[str],
        incident_id: str | None = None,
    ) -> EngineResult:
        _ = (rails_profile, allowlisted_tools, incident_id)
        self.call_count += 1
        if self.scenario == "unavailable":
            return EngineResult.engine_unavailable(engine_id=self.id)
        ip = _primary_ip(bundle)
        if ip in self.envelopes_by_ip:
            env = dict(self.envelopes_by_ip[ip])
            env.setdefault("inputs_digest", inputs_digest)
            env.setdefault("site_id", site_id)
            env.setdefault("observed_at", observed_at)
            return EngineResult.ok(env, engine_id=self.id)
        envelope = fixture_envelope(
            scenario=self.scenario,
            bundle=bundle,
            site_id=site_id,
            observed_at=observed_at,
            inputs_digest=inputs_digest,
            engine_id=self.id,
        )
        return EngineResult.ok(envelope, engine_id=self.id)
