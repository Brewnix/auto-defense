"""Acceptance: burst → one applied; second cycle observe; no model; plane down."""

from __future__ import annotations

from aimmune.cycle import run_cycle
from aimmune.receipt.chain import verify_chain
from aimmune.schema import validate_envelope, validate_receipt

from tests.conftest import ATTACKER, port_scan_burst, write_eve


def test_synthetic_burst_one_applied_second_observe(tmp_state) -> None:
    rt = tmp_state
    write_eve(rt.config.eve_path, port_scan_burst(ATTACKER, rt.clock.now()))

    first = run_cycle(rt)
    applied = [
        rec
        for rec in first.receipts
        if any(
            ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
            for ex in rec["execution"]
        )
    ]
    assert len(applied) == 1
    assert ATTACKER in rt.alias.list_members()
    assert applied[0]["policy"]["decision"] == "execute"
    assert applied[0]["purpose"] == "contain"
    assert applied[0]["actor"]["kind"] == "rule"
    assert applied[0]["posture"]["plane_reachable"] is False

    second = run_cycle(rt)
    applied_second = [
        rec
        for rec in second.receipts
        if any(
            ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
            for ex in rec["execution"]
        )
    ]
    assert applied_second == []
    observe = [rec for rec in second.receipts if rec["policy"]["decision"] == "observe"]
    assert observe
    assert ATTACKER in rt.alias.list_members()

    chain = rt.chain.load()
    verify_chain(chain)
    for rec in chain:
        validate_receipt(rec, rt.config.iface_pin)
    for env in first.envelopes + second.envelopes:
        validate_envelope(env, rt.config.iface_pin)


def test_no_model_required(tmp_state) -> None:
    import sys

    banned = [name for name in sys.modules if "llama" in name or "openai" in name]
    assert banned == []
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert any(r["policy"]["decision"] == "execute" for r in result.receipts)


def test_incident_write_failure_still_blocks(tmp_state) -> None:
    rt = tmp_state
    rt.incidents.fail_next_write = True
    write_eve(rt.config.eve_path, port_scan_burst(ATTACKER, rt.clock.now()))
    result = run_cycle(rt)
    applied = [
        rec
        for rec in result.receipts
        if any(ex.get("status") == "applied" and ex.get("tool") == "firewall.block_ip" for ex in rec["execution"])
    ]
    assert applied
    assert ATTACKER in rt.alias.list_members()
    assert rt.incidents.find_by_receipt(applied[0]["receipt_id"]) is None


def test_quiet_observe_no_incident(tmp_state) -> None:
    result = run_cycle(tmp_state)
    assert result.receipts
    assert all(r["policy"]["decision"] == "observe" for r in result.receipts)
    assert not tmp_state.config.incidents_path.is_file() or tmp_state.incidents.get("x") is None
    assert tmp_state.incidents.find_by_receipt(result.receipts[0]["receipt_id"]) is None
