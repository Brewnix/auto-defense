"""Call gates, single-winner selection, tool strip, subject-bind."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aimmune.canonical import rfc3339
from aimmune.triage.settings import HYPERMESH_TOOLS, RailsStub, profile_catalog

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
KNOWN_TOOLS = frozenset(
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
COMPANION_TOOLS = frozenset(
    {
        "firewall.block_ip",
        "firewall.unblock_ip",
        "net.quarantine_host",
        "ids.suricata_pass",
        "health.restart_service",
        "health.set_nvpmodel",
        "hypermesh.lease_stop",
        "hypermesh.sell_pause",
    }
)
IP_ARG_TOOLS = frozenset(
    {"firewall.block_ip", "firewall.unblock_ip", "net.quarantine_host"}
)


@dataclass
class Winner:
    envelope: dict[str, Any]
    source: str
    reason: str
    failure: str | None = None
    engine_id: str | None = None
    rules_logged: bool = False


def _rule_ids(envelope: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for proposal in envelope.get("proposals") or []:
        code = proposal.get("reason_code")
        if code and code not in ids:
            ids.append(str(code))
    return ids


def is_auto_execute(
    envelope: dict[str, Any], auto_rule_ids: frozenset[str] | set[str]
) -> bool:
    actor = envelope.get("actor") or {}
    if actor.get("kind") == "model":
        return False
    return any(rid in auto_rule_ids for rid in _rule_ids(envelope))


def _is_noise_or_whitelist(envelope: dict[str, Any]) -> bool:
    ids = set(_rule_ids(envelope))
    if ids & {"noise_ignore", "whitelist"}:
        return True
    summary = str((envelope.get("judgment") or {}).get("summary") or "")
    return summary.startswith("noise_ignore")


def should_call_model(
    rules_envelope: dict[str, Any],
    *,
    mode: str,
    enrich: bool,
    auto_rule_ids: frozenset[str] | set[str],
) -> bool:
    """Never on auto-execute. ``rules_primary`` gates as model-triage-v0."""
    if mode == "rules_only":
        return False
    if is_auto_execute(rules_envelope, auto_rule_ids):
        return False
    if _is_noise_or_whitelist(rules_envelope):
        return False
    if mode == "model_assist":
        return True
    severity = str((rules_envelope.get("judgment") or {}).get("severity") or "info")
    if SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK["high"]:
        return True
    if enrich:
        if rules_envelope.get("needs_human"):
            return True
        for proposal in rules_envelope.get("proposals") or []:
            if proposal.get("mode") in {"propose", "hold_human"}:
                return True
    return False


def allow_model_execute(rails: RailsStub, now: datetime | None = None) -> bool:
    """Derived from the rails stub. Not an envelope field. No grant store."""
    if rails.profile not in {"ir_elevated", "break_glass"}:
        return False
    if not rails.grant_active:
        return False
    if rails.active_until is not None:
        clock = now or datetime.now(timezone.utc)
        if clock >= rails.active_until:
            return False
    return True


def execute_allowlist(rails: RailsStub, now: datetime | None = None) -> frozenset[str]:
    if not allow_model_execute(rails, now):
        return frozenset()
    catalog = profile_catalog(rails.profile, extra_allowlist=())
    if rails.tool_allowlist:
        allowed = set(rails.tool_allowlist) & (set(catalog) | set(rails.tool_allowlist))
        # hypermesh only if explicitly listed on the stub allowlist
        if not (set(rails.tool_allowlist) & HYPERMESH_TOOLS):
            allowed -= HYPERMESH_TOOLS
        return frozenset(allowed)
    return catalog - HYPERMESH_TOOLS


def strip_unknown_tools(envelope: dict[str, Any]) -> dict[str, Any]:
    """Drop tools outside the locked ToolName enum before policy."""
    out = dict(envelope)
    kept: list[dict[str, Any]] = []
    for proposal in envelope.get("proposals") or []:
        if proposal.get("tool") in KNOWN_TOOLS:
            kept.append(proposal)
    out["proposals"] = kept
    return out


def bundle_bound_values(bundle: dict[str, Any], *, site_id: str | None = None) -> set[str]:
    values: set[str] = set()
    if site_id:
        values.add(site_id)
    for subject in bundle.get("top_subjects") or []:
        ip = subject.get("ip")
        if ip:
            values.add(str(ip))
    for ip in (bundle.get("counts") or {}).get("by_src") or {}:
        values.add(str(ip))
    for row in bundle.get("prior_blocks") or []:
        ip = row.get("ip")
        if ip:
            values.add(str(ip))
    return values


def subject_bind(
    envelope: dict[str, Any],
    bundle: dict[str, Any],
    *,
    site_id: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Strip IP / subject leaks that are not in the redacted bundle."""
    allowed = bundle_bound_values(bundle, site_id=site_id)
    violations: list[str] = []
    out = dict(envelope)
    judgment = dict(envelope.get("judgment") or {})
    subjects = []
    for sub in judgment.get("subjects") or []:
        value = str(sub.get("value") or "")
        kind = sub.get("kind")
        if kind == "ip" and value not in allowed:
            violations.append(f"subject:{value}")
            continue
        subjects.append(sub)
    if not subjects:
        # Schema requires ≥1 subject; keep a host bind to site if we stripped all.
        if site_id:
            subjects = [{"kind": "host", "value": site_id}]
        elif allowed:
            first = next(iter(allowed))
            subjects = [{"kind": "ip", "value": first}]
    judgment["subjects"] = subjects
    out["judgment"] = judgment

    kept: list[dict[str, Any]] = []
    for proposal in envelope.get("proposals") or []:
        tool = proposal.get("tool")
        args = proposal.get("args") or {}
        ip = args.get("ip")
        if tool in IP_ARG_TOOLS and ip and str(ip) not in allowed:
            violations.append(f"arg:{ip}")
            continue
        kept.append(proposal)
    out["proposals"] = kept
    return out, violations


def rules_usable(envelope: dict[str, Any] | None) -> bool:
    if not envelope:
        return False
    if not isinstance(envelope.get("judgment"), dict):
        return False
    if not envelope.get("actor"):
        return False
    return True


def _fallback_envelope(
    rules: dict[str, Any],
    *,
    decision_hint: str,
    now: datetime,
) -> dict[str, Any]:
    """hold_human+notify or observe when rules are unusable."""
    env = dict(rules)
    judgment = dict(rules.get("judgment") or {})
    severity = str(judgment.get("severity") or "info")
    if decision_hint == "hold_human":
        env["needs_human"] = True
        if SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK["high"]:
            judgment["severity"] = "high"
            env["judgment"] = judgment
        proposals = [dict(p) for p in (env.get("proposals") or [])]
        if not any(p.get("tool") == "notify.operator" for p in proposals):
            ip = None
            for sub in judgment.get("subjects") or []:
                if sub.get("kind") == "ip":
                    ip = sub.get("value")
                    break
            text_parts = ["model_fallback_hold", f"site={env.get('site_id', '')}"]
            if ip:
                text_parts.append(f"ip={ip}")
            proposals.append(
                {
                    "call_id": str(uuid4()),
                    "tool": "notify.operator",
                    "mode": "execute",
                    "reason_code": "model_fallback_hold",
                    "args": {
                        "channel": "fyber.auditor",
                        "severity": judgment.get("severity") or "high",
                        "text_redacted": " ".join(text_parts)[:1000],
                    },
                }
            )
        env["proposals"] = proposals
        env["observed_at"] = env.get("observed_at") or rfc3339(now)
        return env
    env["needs_human"] = False
    env["proposals"] = []
    return env


def select_winner(
    rules: dict[str, Any],
    model_or_none: dict[str, Any] | None,
    failure: str | None,
    *,
    auto_rule: bool,
    now: datetime | None = None,
) -> Winner:
    """Exactly one envelope. Never merge rules + model proposals."""
    clock = now or datetime.now(timezone.utc)
    if auto_rule:
        return Winner(envelope=rules, source="rules", reason="auto_execute")
    if model_or_none is not None and not failure:
        return Winner(
            envelope=model_or_none,
            source="model",
            reason="model_ok",
            engine_id=(model_or_none.get("actor") or {}).get("id"),
            rules_logged=True,
        )
    if rules_usable(rules):
        return Winner(
            envelope=rules,
            source="rules",
            reason="fallback_rules" if failure else "rules",
            failure=failure,
        )
    severity = str((rules.get("judgment") or {}).get("severity") or "info")
    if SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK["high"]:
        return Winner(
            envelope=_fallback_envelope(rules, decision_hint="hold_human", now=clock),
            source="fallback",
            reason="hold_human",
            failure=failure,
        )
    return Winner(
        envelope=_fallback_envelope(rules, decision_hint="observe", now=clock),
        source="fallback",
        reason="observe",
        failure=failure,
    )
