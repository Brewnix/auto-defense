"""Preempt runner — policy + receipts + H3. Separate from the IDS cycle."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from aimmune.canonical import features_digest, rfc3339
from aimmune.notify.held import snapshot_from_proposals
from aimmune.notify.queue import NotifyQueueError
from aimmune.plane.posture import map_receipt_sell_state
from aimmune.preempt.h3 import DrainResult, drain_h3
from aimmune.preempt.hook import (
    HOOK_ACTOR,
    REASON,
    build_hook_proposals,
    hook_digest,
    hook_judgment,
    hook_should_fire,
    leases_for_device,
)
from aimmune.preempt.policy import HYPERMESH_TOOLS, decide_preempt
from aimmune.receipt.chain import build_receipt
from aimmune.schema import validate_envelope, validate_receipt

EXECUTOR_NOTIFY = "auditor-api@site"
ACTOR_CLI = {"kind": "human", "id": "aimmune-cli/preempt", "purpose": "triage"}


def door_for(reason_code: str) -> str:
    if reason_code in {"site_defense", "incident_preempt"}:
        return "site_defense"
    return "ops"


def purpose_for(reason_code: str) -> str:
    if reason_code in {"health_evacuate", "owner_stop_selling", "owner_primary"}:
        return "health"
    return "triage"


def _execution(
    *,
    call_id: str,
    tool: str,
    status: str,
    executor: str,
    started,
    finished,
    effect: dict[str, Any],
    error: str | None,
) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "tool": tool,
        "status": status,
        "executor": executor,
        "started_at": rfc3339(started) if not isinstance(started, str) else started,
        "finished_at": rfc3339(finished) if not isinstance(finished, str) else finished,
        "effect": effect,
        "error": error,
    }


def _receipt_posture(rt, *, host_sell_state: str | None = None) -> dict[str, Any]:
    if host_sell_state is not None:
        sell = map_receipt_sell_state(host_sell_state)
    else:
        sell = rt.config.sell_state if rt.config.sell_state in {"off", "on", "paused", "n/a"} else "off"
    return {
        "wan_up": rt.config.wan_up,
        "plane_reachable": rt.config.plane_reachable,
        "path_b": "n/a",
        "sell_state": sell,
    }


def _make_envelope(
    *,
    site_id: str,
    actor: dict[str, Any],
    observed_at,
    digest: str,
    judgment: dict[str, Any],
    proposals: list[dict[str, Any]],
    needs_human: bool,
) -> dict[str, Any]:
    return {
        "schema": "fyber.inference_iface/v0",
        "trace_id": str(uuid4()),
        "site_id": site_id,
        "actor": dict(actor),
        "observed_at": rfc3339(observed_at) if not isinstance(observed_at, str) else observed_at,
        "inputs_digest": digest,
        "judgment": judgment,
        "proposals": proposals,
        "confidence": 1.0,
        "needs_human": needs_human,
    }


def _notify_execution(
    rt,
    result,
    receipt_id: str,
    incident_id: str | None,
    device_id: str | None = None,
) -> dict[str, Any] | None:
    if result.notify is None:
        return None
    started = rt.clock.now()
    queued = True
    status = "applied"
    error = None
    try:
        held = snapshot_from_proposals(result.proposals)
        if held is not None and device_id and not held.get("device_id"):
            held["device_id"] = device_id
        rt.notify.enqueue(
            queued_at=started,
            site_id=rt.config.site_id,
            receipt_id=receipt_id,
            trace_id=str(uuid4()),
            proposal=result.notify,
            policy_decision=result.decision,
            incident_id=incident_id,
            held=held,
        )
    except NotifyQueueError as exc:
        status = "failed"
        queued = False
        error = str(exc)[:500]
    finished = rt.clock.now()
    effect: dict[str, Any] = {
        "channel": "fyber.auditor",
        "ticket_id": None,
        "queued": queued,
        "receipt_id": receipt_id,
    }
    if incident_id:
        effect["incident_id"] = incident_id
    return _execution(
        call_id=result.notify["call_id"],
        tool="notify.operator",
        status=status,
        executor=EXECUTOR_NOTIFY,
        started=started,
        finished=finished,
        effect=effect,
        error=error,
    )


def _attempts_to_executions(rt, drain: DrainResult) -> list[dict[str, Any]]:
    executions: list[dict[str, Any]] = []
    now = rt.clock.now()
    for attempt in drain.attempts:
        if attempt.skipped:
            effect: dict[str, Any] = {
                "device_id": attempt.device_id,
                "skipped": True,
                "skip_reason": attempt.skip_reason,
            }
            if attempt.lease_id:
                effect["lease_id"] = attempt.lease_id
            executions.append(
                _execution(
                    call_id=attempt.call_id or str(uuid4()),
                    tool=attempt.tool,
                    status="denied",
                    executor=attempt.executor,
                    started=now,
                    finished=now,
                    effect=effect,
                    error=None,
                )
            )
            continue
        payload = attempt.result or {}
        effect = {
            "device_id": attempt.device_id,
            "passed": payload.get("passed"),
        }
        if attempt.lease_id:
            effect["lease_id"] = attempt.lease_id
        if payload.get("sell_state") is not None:
            effect["sell_state"] = payload.get("sell_state")
        if payload.get("image_hash") is not None:
            effect["image_hash"] = payload.get("image_hash")
        if payload.get("until") is not None:
            effect["until"] = payload.get("until")
        if payload.get("job_id") is not None:
            effect["job_id"] = payload.get("job_id")
        status = "applied" if attempt.success else "failed"
        executions.append(
            _execution(
                call_id=attempt.call_id or str(uuid4()),
                tool=attempt.tool,
                status=status,
                executor=attempt.executor,
                started=now,
                finished=now,
                effect=effect,
                error=attempt.error,
            )
        )
    return executions


def run_preempt(
    rt,
    *,
    proposals: list[dict[str, Any]],
    device_id: str,
    reason_code: str,
    actor: dict[str, Any],
    origin_actor_kind: str,
    judgment: dict[str, Any],
    human_approved: bool = False,
    owner_ack: bool = False,
    incident_id: str | None = None,
    parent_id: str | None = None,
    ticket_id: str | None = None,
    digest: str | None = None,
    last_known: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Apply the matrix; H3 only for execute-eligible tools. Writes a receipt."""
    receipt_id = str(uuid4())
    policy = decide_preempt(
        proposals,
        pin=rt.config.iface_pin,
        site_id=rt.config.site_id,
        receipt_id=receipt_id,
        actor_kind=str(actor.get("kind") or "rule"),
        origin_actor_kind=origin_actor_kind,
        reason_code=reason_code,
        rails_profile=rt.config.rails_profile,
        allow_sell_pause_execute=rt.config.allow_sell_pause_execute,
        human_approved=human_approved,
        owner_ack=owner_ack,
        incident_id=incident_id,
        lease_stop_rate=rt.lease_stop_rate,
        now=rt.clock.now(),
        device_id=device_id,
        severity=str(judgment.get("severity") or "high"),
    )
    envelope = _make_envelope(
        site_id=rt.config.site_id,
        actor=actor,
        observed_at=rt.clock.now(),
        digest=digest or features_digest({"preempt": reason_code, "device_id": device_id}),
        judgment=judgment,
        proposals=policy.proposals,
        needs_human=policy.human_required,
    )
    validate_envelope(envelope, rt.config.iface_pin)

    executions: list[dict[str, Any]] = []
    drain: DrainResult | None = None
    host_state = None
    decision = policy.decision

    if policy.execute_tools:
        drain = drain_h3(
            policy.items,
            jobs=rt.jobs,
            posture=rt.posture,
            owner=rt.owner,
            plane_reachable=rt.config.plane_reachable,
            origin_actor_kind=origin_actor_kind,
            allow_stop_while_selling=rt.config.allow_stop_while_selling,
            last_known=last_known,
        )
        executions.extend(_attempts_to_executions(rt, drain))
        if drain.last_sell_state.get(device_id) is not None:
            host_state = drain.last_sell_state.get(device_id)
        elif drain.attempts:
            for attempt in reversed(drain.attempts):
                if attempt.result and attempt.result.get("sell_state"):
                    host_state = attempt.result.get("sell_state")
                    break
        if drain.hold_human:
            decision = "hold_human"
            policy.human_required = True
        for attempt in drain.attempts:
            if (
                attempt.kind == "lease_stop"
                and attempt.success
                and attempt.enqueued
                and rt.lease_stop_rate is not None
            ):
                rt.lease_stop_rate.record(rt.clock.now(), str(attempt.lease_id or device_id))

    notify_exec = None
    if policy.notify is not None and (
        decision in {"propose", "hold_human"} or drain is None or drain.notify_required
    ):
        notify_exec = _notify_execution(rt, policy, receipt_id, incident_id, device_id)
        if notify_exec:
            executions.append(notify_exec)
    elif drain is not None and drain.notify_required and policy.notify is None:
        # Stop-failure notify even when pause already executed.
        from aimmune.preempt.policy import _make_notify

        policy.notify = _make_notify(
            reason_code="preempt_stop_failed",
            severity=str(judgment.get("severity") or "high"),
            site_id=rt.config.site_id,
            receipt_id=receipt_id,
            text=f"lease_stop failed site={rt.config.site_id} device_id={device_id}",
        )
        policy.proposals.append(policy.notify)
        notify_exec = _notify_execution(rt, policy, receipt_id, incident_id, device_id)
        if notify_exec:
            executions.append(notify_exec)

    if incident_id:
        for row in executions:
            if isinstance(row.get("effect"), dict) and "incident_id" not in row["effect"]:
                row["effect"] = {**row["effect"], "incident_id": incident_id}

    resolved_by = None
    resolution = None
    resolved_at = None
    if human_approved or owner_ack:
        resolved_by = "owner-console" if owner_ack else "auditor:approved"
        resolution = "approved"
        resolved_at = rt.clock.now()

    receipt = build_receipt(
        site_id=rt.config.site_id,
        trace_id=envelope["trace_id"],
        ts=rt.clock.now(),
        purpose=purpose_for(reason_code),
        posture=_receipt_posture(rt, host_sell_state=host_state),
        features_digest=envelope["inputs_digest"],
        window_s=rt.config.window_s,
        judgment=judgment,
        actor=actor,
        proposals=policy.proposals,
        policy_decision=decision,
        policy_rule_ids=policy.rule_ids or [reason_code],
        execution=executions,
        human_required=policy.human_required,
        prev_hash=rt.chain.tip_hash(),
        parent_id=parent_id,
        receipt_id=receipt_id,
        sources=["hypermesh_host"],
        door=door_for(reason_code),
        resolved_by=resolved_by,
        resolved_at=resolved_at,
        resolution=resolution,
    )
    validate_receipt(receipt, rt.config.iface_pin)
    rt.chain.append(receipt)
    if incident_id:
        rt.incidents.attach_receipt(str(incident_id), receipt_id)
    if ticket_id and rt.auditor is not None and decision in {"execute", "observe", "hold_human", "propose"}:
        if any(e.get("tool") in HYPERMESH_TOOLS and e.get("status") in {"applied", "failed", "denied"} for e in executions) or decision != "execute":
            try:
                rt.auditor.ack_ticket(str(ticket_id), receipt_id)
                watch = rt.watches.get(str(ticket_id))
                if watch:
                    watch.update(
                        {
                            "status": "acked",
                            "site_acked_receipt_id": receipt_id,
                            "updated_at": rfc3339(rt.clock.now()),
                        }
                    )
                    rt.watches.upsert(watch)
            except Exception:  # noqa: BLE001 — receipt already written
                pass
    return receipt


def emit_site_defense_hook(rt, receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enqueue propose-only site_defense envelopes. No Host RTT."""
    parent = hook_should_fire(rt.config, receipts)
    if parent is None:
        return []
    written: list[dict[str, Any]] = []
    for device_id in rt.config.hypermesh_device_ids:
        proposals = build_hook_proposals(
            device_id=device_id,
            lease_ids=leases_for_device(rt.config, device_id),
        )
        judgment = hook_judgment(parent, device_id)
        rec = run_preempt(
            rt,
            proposals=proposals,
            device_id=device_id,
            reason_code=REASON,
            actor=HOOK_ACTOR,
            origin_actor_kind="rule",
            judgment=judgment,
            human_approved=False,
            owner_ack=False,
            incident_id=rt.incidents.find_by_receipt(parent["receipt_id"]),
            parent_id=parent["receipt_id"],
            digest=hook_digest(device_id, proposals),
        )
        written.append(rec)
    return written


def run_preempt_queue(rt) -> list[dict[str, Any]]:
    """Drain execute-queued items (auditor-approved / CLI). May talk to Host."""
    written: list[dict[str, Any]] = []
    for item in rt.preempt_queue.pending():
        actor = item.get("origin_actor") or HOOK_ACTOR
        judgment = item.get("judgment") or {
            "severity": "high",
            "classes": ["health"],
            "subjects": [{"kind": "host", "value": item["device_id"]}],
            "summary": f"preempt queue {item.get('reason_code')}",
            "evidence_refs": ["preempt:queue"],
        }
        rec = run_preempt(
            rt,
            proposals=list(item.get("proposals") or []),
            device_id=str(item["device_id"]),
            reason_code=str(item.get("reason_code") or "site_defense"),
            actor=actor,
            origin_actor_kind=str((actor or {}).get("kind") or "rule"),
            judgment=judgment,
            human_approved=bool(item.get("human_approved")),
            owner_ack=bool(item.get("owner_ack")),
            incident_id=item.get("incident_id"),
            parent_id=item.get("parent_receipt_id"),
            ticket_id=item.get("ticket_id"),
        )
        rt.preempt_queue.mark_done(item["queue_id"], receipt_id=rec["receipt_id"])
        written.append(rec)
    return written


def cli_preempt(
    rt,
    *,
    kind: str,
    device_id: str,
    lease_id: str | None,
    reason_code: str,
    until: str | None,
    execute: bool,
) -> dict[str, Any]:
    if not device_id:
        raise ValueError("device_id is required (no omit / pick-active)")
    proposals: list[dict[str, Any]] = []
    subjects: list[dict[str, str]] = [{"kind": "host", "value": device_id}]
    if kind in {"sell_pause", "drain"}:
        args: dict[str, Any] = {"device_id": device_id}
        if until:
            args["until"] = until
        proposals.append(
            {
                "call_id": str(uuid4()),
                "tool": "hypermesh.sell_pause",
                "mode": "execute" if execute else "propose",
                "reason_code": reason_code,
                "args": args,
            }
        )
    if kind in {"lease_stop", "drain"}:
        if not lease_id:
            raise ValueError("lease_id is required on lease_stop (no omit-for-active)")
        proposals.append(
            {
                "call_id": str(uuid4()),
                "tool": "hypermesh.lease_stop",
                "mode": "execute" if execute else "propose",
                "reason_code": reason_code,
                "args": {"lease_id": lease_id, "reason_code": reason_code},
            }
        )
        subjects.append({"kind": "lease", "value": lease_id})
    classes = ["health"] if reason_code in {"health_evacuate", "owner_stop_selling", "owner_primary"} else ["port_scan"]
    if reason_code == "site_defense":
        classes = ["port_scan"]
    judgment = {
        "severity": "high" if not execute else "critical",
        "classes": classes,
        "subjects": subjects,
        "summary": f"cli preempt {kind} {reason_code} device={device_id}"[:280],
        "evidence_refs": ["cli:preempt"],
    }
    return run_preempt(
        rt,
        proposals=proposals,
        device_id=device_id,
        reason_code=reason_code,
        actor=ACTOR_CLI,
        origin_actor_kind="human" if execute else "human",
        judgment=judgment,
        human_approved=False,
        owner_ack=execute,
    )
