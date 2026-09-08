"""H3 drain executor — Brewnix sequences two CP jobs. Never a Host mega-job.

v0 never selects ``preempt_mode=hard`` (Host has no signal).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aimmune.host.owner import OwnerClient, OwnerError
from aimmune.plane.jobs import JobsError, SiteJobsClient
from aimmune.plane.posture import (
    STOP_ONLY_OK_STATES,
    DevicePosture,
    SitePostureClient,
    pause_result_success,
)
from aimmune.preempt.policy import HYPERMESH_TOOLS, PreemptItem

PREEMPT_MODE = "drain"
EXECUTOR_PAUSE = "panopticon:job:sell_pause"
EXECUTOR_STOP = "panopticon:job:lease_stop"
EXECUTOR_OWNER = "hypermesh-host@site:owner"


@dataclass
class JobAttempt:
    tool: str
    kind: str
    device_id: str
    lease_id: str | None
    call_id: str
    enqueued: bool
    result: dict[str, Any] | None
    success: bool
    error: str | None
    executor: str
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class DrainResult:
    preempt_mode: str = PREEMPT_MODE
    attempts: list[JobAttempt] = field(default_factory=list)
    hold_human: bool = False
    hold_reason: str | None = None
    notify_required: bool = False
    last_sell_state: dict[str, str | None] = field(default_factory=dict)
    enqueue_log: list[str] = field(default_factory=list)

    @property
    def pause_failed(self) -> bool:
        return any(
            a.kind == "sell_pause" and a.enqueued and not a.success for a in self.attempts
        )


def _site_defense_pause_fail_exception(
    items: list[PreemptItem],
    *,
    origin_actor_kind: str,
) -> bool:
    """Allow execute-eligible stops after a failed pause on rules + site_defense."""
    if origin_actor_kind != "rule":
        return False
    stops = [
        i
        for i in items
        if i.proposal.get("tool") == "hypermesh.lease_stop" and i.execute_eligible
    ]
    if not stops:
        return False
    return all(i.reason_code == "site_defense" for i in stops)


def _group_by_device(items: list[PreemptItem]) -> dict[str, list[PreemptItem]]:
    grouped: dict[str, list[PreemptItem]] = {}
    for item in items:
        if item.proposal.get("tool") not in HYPERMESH_TOOLS:
            continue
        if not item.execute_eligible or item.reject_reason:
            continue
        grouped.setdefault(item.device_id, []).append(item)
    return grouped


def drain_h3(
    items: list[PreemptItem],
    *,
    jobs: SiteJobsClient | None,
    posture: SitePostureClient | None,
    owner: OwnerClient | None,
    plane_reachable: bool,
    origin_actor_kind: str,
    allow_stop_while_selling: bool = False,
    last_known: dict[str, str] | None = None,
) -> DrainResult:
    """Await each sell_pause result before any lease_stop on that device.

    Different devices may be sequenced independently (order recorded).
    Prefer sync await of the pause result. ``preempt_mode`` stays ``drain``.
    """
    result = DrainResult(preempt_mode=PREEMPT_MODE)
    known = dict(last_known or {})
    grouped = _group_by_device(items)

    for device_id, device_items in grouped.items():
        pauses = [i for i in device_items if i.proposal.get("tool") == "hypermesh.sell_pause"]
        stops = [i for i in device_items if i.proposal.get("tool") == "hypermesh.lease_stop"]
        # Sort: all sell_pause before any lease_stop. Stable within each group.
        ordered = pauses + stops
        _ = ordered

        if pauses:
            pause_ok = True
            for pause in pauses:
                attempt = _run_pause(
                    pause,
                    jobs=jobs,
                    owner=owner,
                    plane_reachable=plane_reachable,
                    result=result,
                )
                if attempt.success and attempt.result:
                    state = attempt.result.get("sell_state")
                    if isinstance(state, str):
                        known[device_id] = state
                        result.last_sell_state[device_id] = state
                if not attempt.success:
                    pause_ok = False
            if pause_ok:
                for stop in stops:
                    _run_stop(
                        stop,
                        jobs=jobs,
                        owner=owner,
                        plane_reachable=plane_reachable,
                        result=result,
                    )
                continue
            # Pause fail / timeout / passed but still selling.
            result.notify_required = True
            if _site_defense_pause_fail_exception(
                device_items, origin_actor_kind=origin_actor_kind
            ):
                for stop in stops:
                    _run_stop(
                        stop,
                        jobs=jobs,
                        owner=owner,
                        plane_reachable=plane_reachable,
                        result=result,
                    )
            else:
                result.hold_human = True
                result.hold_reason = "pause_fail"
                for stop in stops:
                    result.attempts.append(
                        JobAttempt(
                            tool="hypermesh.lease_stop",
                            kind="lease_stop",
                            device_id=device_id,
                            lease_id=stop.lease_id,
                            call_id=str(stop.proposal.get("call_id") or ""),
                            enqueued=False,
                            result=None,
                            success=False,
                            error=None,
                            executor=EXECUTOR_STOP if plane_reachable else EXECUTOR_OWNER,
                            skipped=True,
                            skip_reason="pause_fail",
                        )
                    )
            continue

        # Stop-only envelope (no sell_pause proposal this cycle).
        live = _read_posture(
            device_id,
            posture=posture,
            plane_reachable=plane_reachable,
            last_known=known.get(device_id),
        )
        if live is not None:
            result.last_sell_state[device_id] = live.effective_sell_state
        effective = None if live is None else live.effective_sell_state
        if live is not None and live.stale:
            effective = None  # posture unknown → automated stop-only holds

        automated = origin_actor_kind in {"rule", "model"}
        allowed = False
        if effective in STOP_ONLY_OK_STATES:
            allowed = True
        elif not automated:
            allowed = True
        elif allow_stop_while_selling:
            allowed = True
        # site_defense pause-fail exception does NOT apply: pause was never attempted.

        if not allowed:
            result.hold_human = True
            result.hold_reason = "stop_only_selling" if effective == "selling" else "sell_state_unknown"
            result.notify_required = True
            for stop in stops:
                result.attempts.append(
                    JobAttempt(
                        tool="hypermesh.lease_stop",
                        kind="lease_stop",
                        device_id=device_id,
                        lease_id=stop.lease_id,
                        call_id=str(stop.proposal.get("call_id") or ""),
                        enqueued=False,
                        result=None,
                        success=False,
                        error=None,
                        executor=EXECUTOR_STOP if plane_reachable else EXECUTOR_OWNER,
                        skipped=True,
                        skip_reason=result.hold_reason,
                    )
                )
            continue
        for stop in stops:
            _run_stop(
                stop,
                jobs=jobs,
                owner=owner,
                plane_reachable=plane_reachable,
                result=result,
            )
            if result.attempts and not result.attempts[-1].success and not result.attempts[-1].skipped:
                result.notify_required = True
                # Keep sell paused. No auto-resume. Continue other stops.

    return result


def _read_posture(
    device_id: str,
    *,
    posture: SitePostureClient | None,
    plane_reachable: bool,
    last_known: str | None,
) -> DevicePosture | None:
    if plane_reachable and posture is not None:
        try:
            return posture.get_device(device_id)
        except Exception:  # noqa: BLE001 — fail-closed as unknown
            return DevicePosture(
                device_id=device_id,
                site_id=None,
                sell_state=None,
                last_heartbeat_at=None,
                stale=True,
            )
    # Plane-down: do not require the site GET. Last local known still applies.
    if last_known in STOP_ONLY_OK_STATES or last_known == "selling":
        return DevicePosture(
            device_id=device_id,
            site_id=None,
            sell_state=last_known,
            last_heartbeat_at=None,
            stale=False,
        )
    return DevicePosture(
        device_id=device_id,
        site_id=None,
        sell_state=None,
        last_heartbeat_at=None,
        stale=True,
    )


def _run_pause(
    item: PreemptItem,
    *,
    jobs: SiteJobsClient | None,
    owner: OwnerClient | None,
    plane_reachable: bool,
    result: DrainResult,
) -> JobAttempt:
    until = (item.proposal.get("args") or {}).get("until")
    until_s = str(until) if until else None
    if plane_reachable:
        if jobs is None:
            attempt = JobAttempt(
                tool="hypermesh.sell_pause",
                kind="sell_pause",
                device_id=item.device_id,
                lease_id=None,
                call_id=str(item.proposal.get("call_id") or ""),
                enqueued=False,
                result=None,
                success=False,
                error="site jobs client not configured",
                executor=EXECUTOR_PAUSE,
            )
            result.attempts.append(attempt)
            return attempt
        try:
            enqueued = jobs.enqueue_sell_pause(device_id=item.device_id, until=until_s)
            result.enqueue_log.append(f"sell_pause:{item.device_id}")
            job_id = str(enqueued.get("job_id") or "")
            polled = jobs.await_job(job_id) if job_id else enqueued
            ok = pause_result_success(polled)
            attempt = JobAttempt(
                tool="hypermesh.sell_pause",
                kind="sell_pause",
                device_id=item.device_id,
                lease_id=None,
                call_id=str(item.proposal.get("call_id") or ""),
                enqueued=True,
                result=polled,
                success=ok,
                error=None if ok else _pause_error(polled),
                executor=EXECUTOR_PAUSE,
            )
        except JobsError as exc:
            attempt = JobAttempt(
                tool="hypermesh.sell_pause",
                kind="sell_pause",
                device_id=item.device_id,
                lease_id=None,
                call_id=str(item.proposal.get("call_id") or ""),
                enqueued=True,
                result=None,
                success=False,
                error=str(exc)[:500],
                executor=EXECUTOR_PAUSE,
            )
        result.attempts.append(attempt)
        return attempt

    if owner is None:
        attempt = JobAttempt(
            tool="hypermesh.sell_pause",
            kind="sell_pause",
            device_id=item.device_id,
            lease_id=None,
            call_id=str(item.proposal.get("call_id") or ""),
            enqueued=False,
            result=None,
            success=False,
            error="H4 owner client not configured",
            executor=EXECUTOR_OWNER,
        )
        result.attempts.append(attempt)
        return attempt
    try:
        payload = owner.sell_pause(device_id=item.device_id, until=until_s)
        result.enqueue_log.append(f"owner:sell_pause:{item.device_id}")
        ok = pause_result_success(payload)
        attempt = JobAttempt(
            tool="hypermesh.sell_pause",
            kind="sell_pause",
            device_id=item.device_id,
            lease_id=None,
            call_id=str(item.proposal.get("call_id") or ""),
            enqueued=True,
            result=payload,
            success=ok,
            error=None if ok else _pause_error(payload),
            executor=EXECUTOR_OWNER,
        )
    except OwnerError as exc:
        attempt = JobAttempt(
            tool="hypermesh.sell_pause",
            kind="sell_pause",
            device_id=item.device_id,
            lease_id=None,
            call_id=str(item.proposal.get("call_id") or ""),
            enqueued=True,
            result=None,
            success=False,
            error=str(exc)[:500],
            executor=EXECUTOR_OWNER,
        )
    result.attempts.append(attempt)
    return attempt


def _run_stop(
    item: PreemptItem,
    *,
    jobs: SiteJobsClient | None,
    owner: OwnerClient | None,
    plane_reachable: bool,
    result: DrainResult,
) -> JobAttempt:
    if plane_reachable:
        if jobs is None:
            attempt = JobAttempt(
                tool="hypermesh.lease_stop",
                kind="lease_stop",
                device_id=item.device_id,
                lease_id=item.lease_id,
                call_id=str(item.proposal.get("call_id") or ""),
                enqueued=False,
                result=None,
                success=False,
                error="site jobs client not configured",
                executor=EXECUTOR_STOP,
            )
            result.attempts.append(attempt)
            return attempt
        try:
            enqueued = jobs.enqueue_lease_stop(
                device_id=item.device_id, lease_id=str(item.lease_id)
            )
            result.enqueue_log.append(f"lease_stop:{item.device_id}:{item.lease_id}")
            job_id = str(enqueued.get("job_id") or "")
            polled = jobs.await_job(job_id) if job_id else enqueued
            ok = polled.get("passed") is True or polled.get("status") == "passed"
            attempt = JobAttempt(
                tool="hypermesh.lease_stop",
                kind="lease_stop",
                device_id=item.device_id,
                lease_id=item.lease_id,
                call_id=str(item.proposal.get("call_id") or ""),
                enqueued=True,
                result=polled,
                success=ok,
                error=None if ok else str(polled.get("error") or "lease_stop failed")[:500],
                executor=EXECUTOR_STOP,
            )
        except JobsError as exc:
            attempt = JobAttempt(
                tool="hypermesh.lease_stop",
                kind="lease_stop",
                device_id=item.device_id,
                lease_id=item.lease_id,
                call_id=str(item.proposal.get("call_id") or ""),
                enqueued=True,
                result=None,
                success=False,
                error=str(exc)[:500],
                executor=EXECUTOR_STOP,
            )
            result.notify_required = True
        result.attempts.append(attempt)
        if not attempt.success:
            result.notify_required = True
        return attempt

    if owner is None:
        attempt = JobAttempt(
            tool="hypermesh.lease_stop",
            kind="lease_stop",
            device_id=item.device_id,
            lease_id=item.lease_id,
            call_id=str(item.proposal.get("call_id") or ""),
            enqueued=False,
            result=None,
            success=False,
            error="H4 owner client not configured",
            executor=EXECUTOR_OWNER,
        )
        result.attempts.append(attempt)
        result.notify_required = True
        return attempt
    try:
        payload = owner.lease_stop(lease_id=str(item.lease_id), device_id=item.device_id)
        result.enqueue_log.append(f"owner:lease_stop:{item.lease_id}")
        ok = payload.get("passed") is True
        attempt = JobAttempt(
            tool="hypermesh.lease_stop",
            kind="lease_stop",
            device_id=item.device_id,
            lease_id=item.lease_id,
            call_id=str(item.proposal.get("call_id") or ""),
            enqueued=True,
            result=payload,
            success=ok,
            error=None if ok else str(payload.get("error") or "lease_stop failed")[:500],
            executor=EXECUTOR_OWNER,
        )
    except OwnerError as exc:
        attempt = JobAttempt(
            tool="hypermesh.lease_stop",
            kind="lease_stop",
            device_id=item.device_id,
            lease_id=item.lease_id,
            call_id=str(item.proposal.get("call_id") or ""),
            enqueued=True,
            result=None,
            success=False,
            error=str(exc)[:500],
            executor=EXECUTOR_OWNER,
        )
        result.notify_required = True
    result.attempts.append(attempt)
    if not attempt.success:
        result.notify_required = True
    return attempt


def _pause_error(payload: dict[str, Any]) -> str:
    if payload.get("passed") is True and payload.get("sell_state") == "n/a":
        return "invalid pause result: passed=true with sell_state=n/a"
    if payload.get("sell_state") == "selling":
        return "pause did not leave selling"
    return str(payload.get("error") or "sell_pause failed")[:500]
