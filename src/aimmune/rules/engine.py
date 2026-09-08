"""brewnix-rules/v0.1 — port_scan_burst, ssh_brute, noise_ignore."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from aimmune.canonical import features_digest, rfc3339
from aimmune.sensors.eve_to_bundle import ip_is_whitelisted

ACTOR_ID = "brewnix-rules/v0.1"
AUTO_RULE_IDS = frozenset({"port_scan_burst"})


@dataclass(frozen=True)
class RulePack:
    actor: dict[str, str]
    n: int
    m: int
    k: int
    ttl_s: int
    auto_execute_rule_ids: frozenset[str]
    scan_sids: frozenset[str]
    brute_sids: frozenset[str]
    noise_sids: frozenset[str]
    confidence: float

    def is_auto(self, rule_id: str) -> bool:
        return rule_id in self.auto_execute_rule_ids


def default_rules_path() -> Path:
    return Path(str(resources.files("aimmune.rules").joinpath("v0.1.yaml")))


def load_rule_pack(path: Path | None = None, *, ttl_override: int | None = None) -> RulePack:
    rules_path = path or default_rules_path()
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    thresholds = data.get("thresholds") or {}
    sids = data.get("sids") or {}
    actor = data.get("actor") or {
        "kind": "rule",
        "id": ACTOR_ID,
        "purpose": "triage",
    }
    auto = data.get("auto_execute_rule_ids") or ["port_scan_burst"]
    return RulePack(
        actor={"kind": "rule", "id": actor["id"], "purpose": actor.get("purpose", "triage")},
        n=int(thresholds.get("N", 10)),
        m=int(thresholds.get("M", 20)),
        k=int(thresholds.get("K", 15)),
        ttl_s=int(ttl_override if ttl_override is not None else data.get("ttl_s", 86400)),
        auto_execute_rule_ids=frozenset(str(x) for x in auto),
        scan_sids=frozenset(str(x) for x in sids.get("port_scan") or []),
        brute_sids=frozenset(str(x) for x in sids.get("ssh_brute") or []),
        noise_sids=frozenset(str(x) for x in sids.get("noise_ignore") or []),
        confidence=float(data.get("confidence", 1.0)),
    )


def _src_in_bundle(bundle: dict[str, Any], ip: str) -> bool:
    if ip in (bundle.get("counts") or {}).get("by_src") or {}:
        return True
    return any(item.get("ip") == ip for item in bundle.get("top_subjects") or [])


def _block_proposal(ip: str, rule_id: str, ttl_s: int, alias: str) -> dict[str, Any]:
    return {
        "call_id": str(uuid4()),
        "tool": "firewall.block_ip",
        "mode": "execute",
        "ttl_s": ttl_s,
        "reason_code": rule_id,
        "args": {
            "ip": ip,
            "alias": alias,
            "direction": "wan_in",
            "ttl_s": ttl_s,
        },
    }


def _envelope(
    *,
    site_id: str,
    observed_at: str,
    digest: str,
    actor: dict[str, str],
    severity: str,
    classes: list[str],
    ip: str,
    summary: str,
    evidence_refs: list[str],
    proposals: list[dict[str, Any]],
    confidence: float,
    needs_human: bool,
) -> dict[str, Any]:
    return {
        "schema": "fyber.inference_iface/v0",
        "trace_id": str(uuid4()),
        "site_id": site_id,
        "actor": dict(actor),
        "observed_at": observed_at,
        "inputs_digest": digest,
        "judgment": {
            "severity": severity,
            "classes": classes,
            "subjects": [{"kind": "ip", "value": ip}],
            "summary": summary[:280],
            "evidence_refs": evidence_refs,
        },
        "proposals": proposals,
        "confidence": confidence,
        "needs_human": needs_human,
    }


def classify_subject(
    subject: dict[str, Any],
    pack: RulePack,
    whitelist: list[Any] | None = None,
) -> tuple[str, str, list[str]] | None:
    """Return (rule_id, severity, classes) or None if no emit."""
    ip = subject["ip"]
    sids = [str(s) for s in subject.get("sids") or []]
    ports = list(subject.get("ports") or [])
    hits = int(subject.get("hits") or 0)
    scan_hits = sum(1 for sid in sids if sid in pack.scan_sids)
    # count by repeating SID membership against hits when only one SID
    # Prefer SID-set intersection against raw hits if all alerts share scan SIDs.
    brute_hits = sum(1 for sid in sids if sid in pack.brute_sids)

    if ip_is_whitelisted(ip, whitelist or []):
        return ("noise_ignore", "info", ["unknown"])

    if sids and all(sid in pack.noise_sids for sid in sids):
        return ("noise_ignore", "info", ["unknown"])

    # Reconstruct scan/brute alert counts from hits when the subject is dominated
    # by one class (tests emit one SID per burst).
    if pack.scan_sids.intersection(sids):
        scan_count = hits if scan_hits == len(sids) else scan_hits
        if len(ports) >= pack.n or scan_count >= pack.m:
            return ("port_scan_burst", "critical", ["port_scan"])
    if pack.brute_sids.intersection(sids):
        brute_count = hits if brute_hits == len(sids) else brute_hits
        if brute_count >= pack.k:
            return ("ssh_brute", "high", ["brute_force"])
    if len(ports) >= pack.n:
        return ("port_scan_burst", "critical", ["port_scan"])
    return None


def quiet_envelope(
    bundle: dict[str, Any],
    *,
    site_id: str,
    observed_at,
    actor: dict[str, str],
    confidence: float = 1.0,
) -> dict[str, Any]:
    digest = features_digest(bundle)
    return {
        "schema": "fyber.inference_iface/v0",
        "trace_id": str(uuid4()),
        "site_id": site_id,
        "actor": dict(actor),
        "observed_at": rfc3339(observed_at) if not isinstance(observed_at, str) else observed_at,
        "inputs_digest": digest,
        "judgment": {
            "severity": "info",
            "classes": ["unknown"],
            "subjects": [{"kind": "host", "value": site_id}],
            "summary": "No auto-contain rule matched in window",
            "evidence_refs": ["eve:window"],
        },
        "proposals": [],
        "confidence": confidence,
        "needs_human": False,
    }


def emit_detect_envelopes(
    bundle: dict[str, Any],
    pack: RulePack,
    *,
    site_id: str,
    observed_at,
    alias: str = "ai_autoblock",
    whitelist: list[Any] | None = None,
) -> list[dict[str, Any]]:
    digest = features_digest(bundle)
    observed = rfc3339(observed_at) if not isinstance(observed_at, str) else observed_at
    envelopes: list[dict[str, Any]] = []
    for subject in bundle.get("top_subjects") or []:
        ip = subject.get("ip")
        if not ip or not _src_in_bundle(bundle, ip):
            continue
        classified = classify_subject(subject, pack, whitelist)
        if classified is None:
            continue
        rule_id, severity, classes = classified
        if rule_id == "noise_ignore":
            envelopes.append(
                _envelope(
                    site_id=site_id,
                    observed_at=observed,
                    digest=digest,
                    actor=pack.actor,
                    severity=severity,
                    classes=classes,
                    ip=ip,
                    summary=f"noise_ignore {ip}",
                    evidence_refs=["eve:window"],
                    proposals=[],
                    confidence=pack.confidence,
                    needs_human=False,
                )
            )
            continue
        proposals = [_block_proposal(ip, rule_id, pack.ttl_s, alias)]
        envelopes.append(
            _envelope(
                site_id=site_id,
                observed_at=observed,
                digest=digest,
                actor=pack.actor,
                severity=severity,
                classes=classes,
                ip=ip,
                summary=f"{rule_id} from {ip} hits={subject.get('hits')}",
                evidence_refs=["eve:window"],
                proposals=proposals,
                confidence=pack.confidence,
                needs_human=severity == "high",
            )
        )
    return envelopes
