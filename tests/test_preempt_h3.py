"""H3 drain order, pause-fail, site_defense exception, plane-down H4."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from aimmune.preempt.h3 import drain_h3
from aimmune.preempt.policy import PreemptItem, decide_preempt
from aimmune.preempt.runner import cli_preempt, run_preempt
from aimmune.schema import validate_receipt
from tests.owner_fake import FakeOwner
from tests.plane_fake import FakePlane

DEVICE = "jetson-cottage-01"
LEASE = "lease-203-0-113-50"
LEASE_B = "lease-203-0-113-51"


def _item(tool: str, *, reason: str, device=DEVICE, lease=None, eligible=True) -> PreemptItem:
    if tool == "hypermesh.sell_pause":
        proposal = {
            "call_id": str(uuid4()),
            "tool": tool,
            "mode": "execute",
            "reason_code": reason,
            "args": {"device_id": device},
        }
    else:
        proposal = {
            "call_id": str(uuid4()),
            "tool": tool,
            "mode": "execute",
            "reason_code": reason,
            "args": {"lease_id": lease or LEASE, "reason_code": reason},
        }
    return PreemptItem(
        proposal=proposal,
        device_id=device,
        lease_id=lease or (LEASE if tool == "hypermesh.lease_stop" else None),
        reason_code=reason,
        execute_eligible=eligible,
    )


def test_h3_pause_before_stop_same_device() -> None:
    fake = FakePlane()
    fake.set_device(DEVICE, sell_state="selling")
    jobs = fake.jobs_client()
    items = [
        _item("hypermesh.lease_stop", reason="health_evacuate"),
        _item("hypermesh.sell_pause", reason="health_evacuate"),
    ]
    result = drain_h3(
        items,
        jobs=jobs,
        posture=fake.posture_client(),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    assert result.preempt_mode == "drain"
    assert result.enqueue_log == [
        f"sell_pause:{DEVICE}",
        f"lease_stop:{DEVICE}:{LEASE}",
    ]
    assert all(a.success for a in result.attempts if not a.skipped)


def test_h3_no_mega_job_kind() -> None:
    fake = FakePlane()
    result = drain_h3(
        [
            _item("hypermesh.sell_pause", reason="health_evacuate"),
            _item("hypermesh.lease_stop", reason="health_evacuate"),
        ],
        jobs=fake.jobs_client(),
        posture=fake.posture_client(),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    kinds = {job["kind"] for job in fake.jobs.values()}
    assert kinds <= {"sell_pause", "lease_stop"}
    assert "drain" not in kinds
    assert result.preempt_mode == "drain"


def test_pause_fail_non_site_defense_holds_stops() -> None:
    fake = FakePlane()
    fake.pause_result = {"status": "passed", "passed": True, "sell_state": "selling"}
    result = drain_h3(
        [
            _item("hypermesh.sell_pause", reason="health_evacuate"),
            _item("hypermesh.lease_stop", reason="health_evacuate"),
        ],
        jobs=fake.jobs_client(),
        posture=fake.posture_client(),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    assert result.hold_human is True
    assert result.hold_reason == "pause_fail"
    assert result.notify_required is True
    assert not any(a.kind == "lease_stop" and a.enqueued for a in result.attempts)
    assert any(a.kind == "sell_pause" and not a.success for a in result.attempts)


def test_site_defense_pause_fail_allows_execute_eligible_stops() -> None:
    fake = FakePlane()
    fake.pause_result = {"status": "failed", "passed": False, "sell_state": "selling"}
    result = drain_h3(
        [
            _item("hypermesh.sell_pause", reason="site_defense"),
            _item("hypermesh.lease_stop", reason="site_defense"),
        ],
        jobs=fake.jobs_client(),
        posture=fake.posture_client(),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    assert result.preempt_mode == "drain"
    assert any(a.kind == "sell_pause" and not a.success for a in result.attempts)
    assert any(a.kind == "lease_stop" and a.enqueued for a in result.attempts)
    assert fake.enqueue_order[0].startswith("sell_pause:")
    assert any(x.startswith("lease_stop:") for x in fake.enqueue_order)


def test_stop_only_selling_automated_holds() -> None:
    fake = FakePlane()
    fake.set_device(DEVICE, sell_state="selling")
    result = drain_h3(
        [_item("hypermesh.lease_stop", reason="site_defense")],
        jobs=fake.jobs_client(),
        posture=fake.posture_client(),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    assert result.hold_human is True
    assert result.hold_reason == "stop_only_selling"
    assert fake.posts == 0


def test_stop_only_while_paused_allows() -> None:
    fake = FakePlane()
    fake.set_device(DEVICE, sell_state="paused")
    result = drain_h3(
        [_item("hypermesh.lease_stop", reason="site_defense")],
        jobs=fake.jobs_client(),
        posture=fake.posture_client(),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    assert any(a.kind == "lease_stop" and a.enqueued and a.success for a in result.attempts)


def test_stale_heartbeat_stop_only_holds(tmp_state) -> None:
    from datetime import datetime, timedelta, timezone

    from aimmune.clock import FrozenClock

    now = datetime(2026, 9, 8, 21, 10, tzinfo=timezone.utc)
    old = (now - timedelta(seconds=400)).isoformat().replace("+00:00", "Z")
    fake = FakePlane()
    fake.set_device(DEVICE, sell_state="paused", last_heartbeat_at=old)
    clock = FrozenClock(now)
    result = drain_h3(
        [_item("hypermesh.lease_stop", reason="site_defense")],
        jobs=fake.jobs_client(clock=clock),
        posture=fake.posture_client(stale_s=300, clock=clock),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    assert result.hold_human is True
    assert result.hold_reason == "sell_state_unknown"
    _ = tmp_state


def test_pause_ok_stop_fail_keeps_paused_and_continues() -> None:
    fake = FakePlane()
    fake.stop_result = {"status": "failed", "passed": False}

    def _stop(lease: str) -> PreemptItem:
        return _item("hypermesh.lease_stop", reason="health_evacuate", lease=lease)

    result = drain_h3(
        [
            _item("hypermesh.sell_pause", reason="health_evacuate"),
            _stop(LEASE),
            _stop(LEASE_B),
        ],
        jobs=fake.jobs_client(),
        posture=fake.posture_client(),
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    stops = [a for a in result.attempts if a.kind == "lease_stop"]
    assert len(stops) == 2
    assert all(not a.success for a in stops)
    assert result.notify_required is True
    pause = next(a for a in result.attempts if a.kind == "sell_pause")
    assert pause.success is True
    assert pause.result["sell_state"] == "paused"


def test_hard_never_selected() -> None:
    fake = FakePlane()
    fake.pause_result = {"status": "failed", "passed": False, "sell_state": "selling"}
    result = drain_h3(
        [
            _item("hypermesh.sell_pause", reason="site_defense"),
            _item("hypermesh.lease_stop", reason="site_defense"),
        ],
        jobs=fake.jobs_client(),
        posture=None,
        owner=None,
        plane_reachable=True,
        origin_actor_kind="rule",
    )
    assert result.preempt_mode == "drain"


def test_plane_down_h4_writes_receipt(tmp_state) -> None:
    fake = FakeOwner()
    tmp_state.owner = fake.client()
    tmp_state.jobs = None
    tmp_state.posture = None
    tmp_state.config = replace(tmp_state.config, plane_reachable=False)
    receipt = cli_preempt(
        tmp_state,
        kind="drain",
        device_id=DEVICE,
        lease_id=LEASE,
        reason_code="health_evacuate",
        until=None,
        execute=True,
    )
    validate_receipt(receipt, tmp_state.config.iface_pin)
    assert receipt["input"]["sources"] == ["hypermesh_host"]
    assert receipt["door"] == "ops"
    assert receipt["purpose"] == "health"
    assert receipt["human"]["resolution"] == "approved"
    tools = [e["tool"] for e in receipt["execution"]]
    assert "hypermesh.sell_pause" in tools
    assert "hypermesh.lease_stop" in tools
    assert fake.calls[0].startswith("sell_pause:")
    assert fake.calls[1].startswith("lease_stop:")
    assert tmp_state.jobs is None


def test_cli_propose_does_not_call_host(tmp_state) -> None:
    fake = FakePlane()
    tmp_state.jobs = fake.jobs_client()
    tmp_state.posture = fake.posture_client()
    tmp_state.config = replace(tmp_state.config, plane_reachable=True)
    receipt = cli_preempt(
        tmp_state,
        kind="sell_pause",
        device_id=DEVICE,
        lease_id=None,
        reason_code="health_evacuate",
        until=None,
        execute=False,
    )
    assert receipt["policy"]["decision"] == "propose"
    assert fake.posts == 0
    assert tmp_state.notify.pending()


def test_rules_health_evacuate_executes_pause_via_runner(tmp_state) -> None:
    fake = FakePlane()
    tmp_state.jobs = fake.jobs_client()
    tmp_state.posture = fake.posture_client()
    tmp_state.config = replace(tmp_state.config, plane_reachable=True)
    proposal = {
        "call_id": str(uuid4()),
        "tool": "hypermesh.sell_pause",
        "mode": "execute",
        "reason_code": "health_evacuate",
        "args": {"device_id": DEVICE},
    }
    receipt = run_preempt(
        tmp_state,
        proposals=[proposal],
        device_id=DEVICE,
        reason_code="health_evacuate",
        actor={"kind": "rule", "id": "brewnix-rules/hypermesh-preempt-v0", "purpose": "triage"},
        origin_actor_kind="rule",
        judgment={
            "severity": "high",
            "classes": ["health"],
            "subjects": [{"kind": "host", "value": DEVICE}],
            "summary": "health evacuate pause",
            "evidence_refs": ["health:thermal"],
        },
    )
    validate_receipt(receipt, tmp_state.config.iface_pin)
    assert receipt["policy"]["decision"] == "execute"
    assert fake.enqueue_order == [f"sell_pause:{DEVICE}"]


def test_lease_id_required_on_cli(tmp_state) -> None:
    import pytest

    with pytest.raises(ValueError, match="lease_id"):
        cli_preempt(
            tmp_state,
            kind="lease_stop",
            device_id=DEVICE,
            lease_id=None,
            reason_code="site_defense",
            until=None,
            execute=False,
        )


def test_decide_preempt_used_in_h3_filter(pin) -> None:
    decision = decide_preempt(
        [
            {
                "call_id": str(uuid4()),
                "tool": "hypermesh.lease_stop",
                "mode": "execute",
                "reason_code": "site_defense",
                "args": {"lease_id": LEASE, "reason_code": "site_defense"},
            }
        ],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="site_defense",
        device_id=DEVICE,
    )
    eligible = [i for i in decision.items if i.execute_eligible]
    assert eligible == []
