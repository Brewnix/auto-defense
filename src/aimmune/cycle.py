"""One detect/expiry cycle: bundle → rules → policy → exec → receipt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from aimmune.canonical import features_digest, rfc3339
from aimmune.clock import Clock
from aimmune.config import Config, load_config
from aimmune.exec.opnsense_alias import AliasStore, build_alias_store
from aimmune.incident.minimal import IncidentStore
from aimmune.ledger.ttl import TtlLedger
from aimmune.notify.queue import NotifyQueue, NotifyQueueError
from aimmune.policy import RateLimiter, decide
from aimmune.receipt.chain import ReceiptChain, build_receipt
from aimmune.rules.engine import (
    RulePack,
    emit_detect_envelopes,
    load_rule_pack,
    quiet_envelope,
)
from aimmune.rules.expiry import emit_expiry_envelope
from aimmune.schema import validate_bundle, validate_envelope, validate_receipt
from aimmune.sensors.eve_to_bundle import build_feature_bundle, load_whitelist
from aimmune.store import rewrite_jsonl

EXECUTOR_FW = "opnsense-api@site"
EXECUTOR_NOTIFY = "auditor-api@site"


@dataclass
class CycleResult:
    bundle: dict[str, Any] | None
    envelopes: list[dict[str, Any]] = field(default_factory=list)
    receipts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Runtime:
    config: Config
    clock: Clock
    alias: AliasStore
    chain: ReceiptChain
    ledger: TtlLedger
    notify: NotifyQueue
    incidents: IncidentStore
    rate_limit: RateLimiter
    rules: RulePack


def build_runtime(
    config: Config | None = None,
    *,
    clock: Clock | None = None,
    alias: AliasStore | None = None,
) -> Runtime:
    cfg = config or load_config()
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    store = alias or build_alias_store(
        exec_mock=cfg.exec_mock,
        url=cfg.opnsense_url,
        key=cfg.opnsense_key,
        secret=cfg.opnsense_secret,
        verify=cfg.opnsense_verify,
    )
    return Runtime(
        config=cfg,
        clock=clock or Clock(),
        alias=store,
        chain=ReceiptChain(cfg.receipts_path),
        ledger=TtlLedger(cfg.ttl_ledger_path),
        notify=NotifyQueue(cfg.notify_queue_path),
        incidents=IncidentStore(cfg.incidents_path, cfg.incident_index_path),
        rate_limit=RateLimiter(cfg.rate_limit_path, max_per_hour=cfg.rate_limit_b),
        rules=load_rule_pack(cfg.rules_path, ttl_override=cfg.block_ttl_s),
    )


def _posture(cfg: Config) -> dict[str, Any]:
    sell = cfg.sell_state if cfg.sell_state in {"off", "on", "paused", "n/a"} else "off"
    return {
        "wan_up": cfg.wan_up,
        "plane_reachable": cfg.plane_reachable,
        "path_b": "n/a",
        "sell_state": sell,
    }


def _execution(
    *,
    call_id: str,
    tool: str,
    status: str,
    executor: str,
    started: datetime,
    finished: datetime,
    effect: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "tool": tool,
        "status": status,
        "executor": executor,
        "started_at": rfc3339(started),
        "finished_at": rfc3339(finished),
        "effect": effect,
        "error": error,
    }


def _persist_receipt(rt: Runtime, receipt: dict[str, Any]) -> dict[str, Any]:
    validate_receipt(receipt, rt.config.iface_pin)
    rt.chain.append(receipt)
    return receipt


def _try_open_incident(
    rt: Runtime,
    *,
    envelope: dict[str, Any],
    receipt_id: str,
    ip: str | None,
    severity: str,
    summary: str,
    contain_applied: bool,
) -> str | None:
    if not ip:
        return None
    record = rt.incidents.open_security(
        site_id=rt.config.site_id,
        opened_at=rt.clock.now(),
        opened_by={"kind": "rule", "id": (envelope.get("actor") or {}).get("id", "")},
        severity=severity,
        summary_redacted=summary,
        ip=ip,
        opening_trace_id=envelope["trace_id"],
        opening_receipt_id=receipt_id,
    )
    if record is None:
        return None
    record.setdefault("flags", {})["contain_applied"] = contain_applied
    return str(record["incident_id"])


def _run_detect_envelope(
    rt: Runtime,
    envelope: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    validate_envelope(envelope, rt.config.iface_pin)
    now = rt.clock.now()
    members = set(rt.alias.list_members(rt.config.alias))
    prior = rt.ledger.prior_blocks(now, list(members))
    whitelist = load_whitelist(rt.config.whitelist_path)
    receipt_id = str(uuid4())
    result = decide(
        envelope,
        pin=rt.config.iface_pin,
        whitelist=whitelist,
        prior_blocks=prior,
        alias_members=members,
        rate_limiter=rt.rate_limit,
        now=now,
        auto_rule_ids=rt.rules.auto_execute_rule_ids,
        receipt_id=receipt_id,
        site_id=rt.config.site_id,
    )
    envelope = dict(envelope)
    envelope["proposals"] = result.proposals
    envelope["needs_human"] = result.human_required

    executions: list[dict[str, Any]] = []
    applied_block = False
    primary_ip = None
    for proposal in result.proposals:
        if proposal.get("tool") == "firewall.block_ip":
            primary_ip = (proposal.get("args") or {}).get("ip")
            break
    if primary_ip is None:
        subjects = (envelope.get("judgment") or {}).get("subjects") or []
        for sub in subjects:
            if sub.get("kind") == "ip":
                primary_ip = sub.get("value")
                break

    if result.decision == "execute":
        for proposal in result.proposals:
            if proposal.get("tool") != "firewall.block_ip":
                continue
            args = proposal.get("args") or {}
            ip = str(args.get("ip"))
            alias = str(args.get("alias") or rt.config.alias)
            ttl_s = int(proposal.get("ttl_s") or args.get("ttl_s") or rt.rules.ttl_s)
            started = rt.clock.now()
            try:
                rt.alias.add(ip, alias)
                status = "applied"
                error = None
                applied_block = True
            except Exception as exc:  # noqa: BLE001 — record failed, do not raise
                status = "failed"
                error = str(exc)[:500]
            finished = rt.clock.now()
            executions.append(
                _execution(
                    call_id=proposal["call_id"],
                    tool="firewall.block_ip",
                    status=status,
                    executor=EXECUTOR_FW,
                    started=started,
                    finished=finished,
                    effect={"alias": alias, "ip": ip, "ttl_s": ttl_s},
                    error=error,
                )
            )
            if status == "applied":
                rt.rate_limit.record(finished, ip)
                rt.ledger.record(
                    ip=ip,
                    alias=alias,
                    expire_at=rt.ledger.expire_at_from_ttl(finished, ttl_s),
                    parent_receipt_id=receipt_id,
                    call_id=proposal["call_id"],
                    classes=list((envelope.get("judgment") or {}).get("classes") or []),
                )

    if result.decision in {"propose", "hold_human"} and result.notify:
        started = rt.clock.now()
        queued = True
        status = "applied"
        error = None
        try:
            rt.notify.enqueue(
                queued_at=started,
                site_id=rt.config.site_id,
                receipt_id=receipt_id,
                trace_id=envelope["trace_id"],
                proposal=result.notify,
                policy_decision=result.decision,
            )
        except NotifyQueueError as exc:
            status = "failed"
            queued = False
            error = str(exc)[:500]
        finished = rt.clock.now()
        executions.append(
            _execution(
                call_id=result.notify["call_id"],
                tool="notify.operator",
                status=status,
                executor=EXECUTOR_NOTIFY,
                started=started,
                finished=finished,
                effect={
                    "channel": "fyber.auditor",
                    "ticket_id": None,
                    "queued": queued,
                    "receipt_id": receipt_id,
                },
                error=error,
            )
        )

    incident_id = None
    if result.decision in {"execute", "propose", "hold_human"} and primary_ip:
        incident_id = _try_open_incident(
            rt,
            envelope=envelope,
            receipt_id=receipt_id,
            ip=str(primary_ip),
            severity=(envelope.get("judgment") or {}).get("severity", "info"),
            summary=(envelope.get("judgment") or {}).get("summary", result.reason),
            contain_applied=applied_block,
        )
        if incident_id:
            for row in executions:
                if isinstance(row.get("effect"), dict):
                    row["effect"] = {**row["effect"], "incident_id": incident_id}

    purpose = "contain" if applied_block else "triage"
    receipt = build_receipt(
        site_id=rt.config.site_id,
        trace_id=envelope["trace_id"],
        ts=rt.clock.now(),
        purpose=purpose,
        posture=_posture(rt.config),
        features_digest=bundle.get("_digest") or features_digest(
            {k: v for k, v in bundle.items() if k != "_digest"}
        ),
        window_s=int(bundle.get("window_s") or rt.config.window_s),
        judgment=envelope["judgment"],
        actor=envelope["actor"],
        proposals=result.proposals,
        policy_decision=result.decision,
        policy_rule_ids=result.rule_ids,
        execution=executions,
        human_required=result.human_required,
        prev_hash=rt.chain.tip_hash(),
        receipt_id=receipt_id,
        sources=["suricata", "opnsense"],
    )
    _persist_receipt(rt, receipt)
    if incident_id:
        rt.incidents.attach_receipt(incident_id, receipt_id)
        # Late-bind incident on ledger rows written with this receipt.
        rows = rt.ledger.rows()
        for row in rows:
            if row.get("parent_receipt_id") == receipt_id:
                row["incident_id"] = incident_id
        rewrite_jsonl(rt.config.ttl_ledger_path, rows)
    return receipt


def _run_expiry_row(rt: Runtime, row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ip = str(row["ip"])
    alias = str(row.get("alias") or rt.config.alias)
    members = set(rt.alias.list_members(alias))
    envelope, bundle = emit_expiry_envelope(
        ip,
        site_id=rt.config.site_id,
        observed_at=rt.clock.now(),
        alias=alias,
        classes=list(row.get("classes") or ["unknown"]),
        parent_receipt_id=row.get("parent_receipt_id"),
        wan_up=rt.config.wan_up,
    )
    validate_bundle(bundle, rt.config.iface_pin)
    validate_envelope(envelope, rt.config.iface_pin)
    receipt_id = str(uuid4())
    result = decide(
        envelope,
        pin=rt.config.iface_pin,
        whitelist=load_whitelist(rt.config.whitelist_path),
        prior_blocks=[{"ip": ip, "remaining_ttl_s": 0}],
        alias_members=members,
        rate_limiter=rt.rate_limit,
        now=rt.clock.now(),
        auto_rule_ids=rt.rules.auto_execute_rule_ids,
        receipt_id=receipt_id,
        site_id=rt.config.site_id,
        incident_id=row.get("incident_id"),
    )
    executions: list[dict[str, Any]] = []
    if result.decision == "execute":
        for proposal in result.proposals:
            if proposal.get("tool") != "firewall.unblock_ip":
                continue
            started = rt.clock.now()
            try:
                rt.alias.delete(ip, alias)
                status = "expired"
                error = None
            except Exception as exc:  # noqa: BLE001
                status = "failed"
                error = str(exc)[:500]
            finished = rt.clock.now()
            executions.append(
                _execution(
                    call_id=proposal["call_id"],
                    tool="firewall.unblock_ip",
                    status=status,
                    executor=EXECUTOR_FW,
                    started=started,
                    finished=finished,
                    effect={"alias": alias, "ip": ip, "cause": "ttl_expired"},
                    error=error,
                )
            )
    rt.ledger.advance(str(row["call_id"]))
    parent_incident = row.get("incident_id")
    if parent_incident:
        for item in executions:
            if isinstance(item.get("effect"), dict):
                item["effect"] = {**item["effect"], "incident_id": parent_incident}

    receipt = build_receipt(
        site_id=rt.config.site_id,
        trace_id=envelope["trace_id"],
        ts=rt.clock.now(),
        purpose="contain",
        posture=_posture(rt.config),
        features_digest=features_digest(bundle),
        window_s=int(bundle["window_s"]),
        judgment=envelope["judgment"],
        actor=envelope["actor"],
        proposals=result.proposals,
        policy_decision=result.decision,
        policy_rule_ids=result.rule_ids,
        execution=executions,
        human_required=False,
        prev_hash=rt.chain.tip_hash(),
        parent_id=row.get("parent_receipt_id"),
        receipt_id=receipt_id,
        sources=["opnsense"],
    )
    _persist_receipt(rt, receipt)
    if parent_incident:
        rt.incidents.attach_receipt(str(parent_incident), receipt_id)
    elif row.get("parent_receipt_id"):
        rt.incidents.inherit_parent(str(row["parent_receipt_id"]), receipt_id)
    return envelope, receipt


def run_cycle(rt: Runtime) -> CycleResult:
    envelopes: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    now = rt.clock.now()
    members = rt.alias.list_members(rt.config.alias)
    prior = rt.ledger.prior_blocks(now, members)
    whitelist = load_whitelist(rt.config.whitelist_path)
    bundle = build_feature_bundle(
        rt.config.eve_path,
        now=now,
        window_s=rt.config.window_s,
        whitelist=whitelist,
        prior_blocks=prior,
        wan_up=rt.config.wan_up,
    )
    validate_bundle(bundle, rt.config.iface_pin)
    digest = features_digest(bundle)
    bundle_with_digest = dict(bundle)
    bundle_with_digest["_digest"] = digest

    detect_envs = emit_detect_envelopes(
        bundle,
        rt.rules,
        site_id=rt.config.site_id,
        observed_at=now,
        alias=rt.config.alias,
        whitelist=whitelist,
    )
    if not detect_envs:
        detect_envs = [
            quiet_envelope(
                bundle,
                site_id=rt.config.site_id,
                observed_at=now,
                actor=rt.rules.actor,
                confidence=rt.rules.confidence,
            )
        ]
    for env in detect_envs:
        rec = _run_detect_envelope(rt, env, bundle_with_digest)
        envelopes.append(env)
        receipts.append(rec)

    # Expiry after detect so a still-hot window dedupes against the live alias
    # before this tick removes the member. New alerts after expire_at re-block
    # on a later cycle (no sliding TTL).
    for row in rt.ledger.due(rt.clock.now()):
        env, rec = _run_expiry_row(rt, row)
        envelopes.append(env)
        receipts.append(rec)

    return CycleResult(bundle=bundle, envelopes=envelopes, receipts=receipts)
