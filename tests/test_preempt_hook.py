"""Thin site_defense hook: flag-gated, no Host RTT on the IDS cycle."""

from __future__ import annotations

from dataclasses import replace

from aimmune.cycle import run_cycle
from aimmune.preempt.hook import hook_should_fire
from aimmune.preempt.policy import HYPERMESH_TOOLS
from tests.conftest import ATTACKER, port_scan_burst, ssh_brute_burst, write_eve
from tests.plane_fake import FakePlane

DEVICE = "jetson-cottage-01"
LEASE = "lease-203-0-113-50"


def _enable_hook(rt, *, leases: tuple[str, ...] = ()) -> None:
    rt.config = replace(
        rt.config,
        site_defense_preempt=True,
        hypermesh_device_ids=(DEVICE,),
        hypermesh_lease_ids=leases,
    )


def test_hook_off_by_default(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    tools = [p.get("tool") for r in result.receipts for p in r.get("proposals") or []]
    assert "hypermesh.sell_pause" not in tools


def test_hook_emits_propose_on_critical_contain_without_host_rtt(tmp_state) -> None:
    fake = FakePlane()
    tmp_state.jobs = fake.jobs_client()
    tmp_state.posture = fake.posture_client()
    _enable_hook(tmp_state, leases=(f"{DEVICE}:{LEASE}",))
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    hook = [
        r
        for r in result.receipts
        if any(p.get("tool") in HYPERMESH_TOOLS for p in r.get("proposals") or [])
    ]
    assert hook, [r["policy"] for r in result.receipts]
    rec = hook[0]
    assert rec["policy"]["decision"] == "propose"
    assert rec["human"]["required"] is True
    assert rec["actor"]["id"] == "brewnix-rules/hypermesh-preempt-v0"
    assert rec["door"] == "site_defense"
    codes = {p.get("reason_code") for p in rec["proposals"] if p.get("tool") in HYPERMESH_TOOLS}
    assert codes == {"site_defense"}
    tools = {p["tool"] for p in rec["proposals"] if p.get("tool") in HYPERMESH_TOOLS}
    assert tools == {"hypermesh.sell_pause", "hypermesh.lease_stop"}
    assert fake.posts == 0
    assert tmp_state.notify.pending()


def test_hook_skips_high_propose(tmp_state) -> None:
    _enable_hook(tmp_state)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    hook = [
        r
        for r in result.receipts
        if any(p.get("tool") in HYPERMESH_TOOLS for p in r.get("proposals") or [])
    ]
    assert not hook


def test_hook_requires_device_list(tmp_state) -> None:
    tmp_state.config = replace(tmp_state.config, site_defense_preempt=True)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert hook_should_fire(tmp_state.config, result.receipts) is None
    tools = [p.get("tool") for r in result.receipts for p in r.get("proposals") or []]
    assert "hypermesh.sell_pause" not in tools


def test_hook_no_lease_without_explicit_id(tmp_state) -> None:
    _enable_hook(tmp_state, leases=())
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    hook = [
        r
        for r in result.receipts
        if any(p.get("tool") == "hypermesh.sell_pause" for p in r.get("proposals") or [])
    ]
    assert hook
    stops = [
        p
        for r in hook
        for p in r["proposals"]
        if p.get("tool") == "hypermesh.lease_stop"
    ]
    assert stops == []
