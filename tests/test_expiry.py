from __future__ import annotations

from dataclasses import replace

from aimmune.cycle import run_cycle
from aimmune.receipt.chain import verify_chain
from aimmune.schema import validate_envelope, validate_receipt, validate_tool_args
from tests.conftest import ATTACKER, port_scan_burst, write_eve


def test_ttl_expiry_unblocks_once_and_chain_unbroken(tmp_state) -> None:
    tmp_state.rules = replace_ttl(tmp_state, 60)
    tmp_state.config = replace(tmp_state.config, block_ttl_s=60)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    block = next(r for r in first.receipts if r["policy"]["decision"] == "execute")
    assert ATTACKER in tmp_state.alias.list_members()

    tmp_state.clock.advance(60)
    write_eve(tmp_state.config.eve_path, [])
    expired = run_cycle(tmp_state)
    unblocks = [
        rec
        for rec in expired.receipts
        if rec["actor"]["id"] == "brewnix-rules/expiry"
    ]
    assert len(unblocks) == 1
    rec = unblocks[0]
    assert rec["policy"]["decision"] == "execute"
    assert rec["policy"]["rule_ids"] == ["ttl_expired"]
    assert rec["parent_id"] == block["receipt_id"]
    assert rec["purpose"] == "contain"
    assert any(ex.get("status") == "expired" for ex in rec["execution"])
    assert ATTACKER not in tmp_state.alias.list_members()
    assert rec["integrity"]["prev_hash"] == tmp_state.chain.load()[-2]["integrity"]["body_hash"]

    again = run_cycle(tmp_state)
    second_expiry = [r for r in again.receipts if r["actor"]["id"] == "brewnix-rules/expiry"]
    assert second_expiry == []
    verify_chain(tmp_state.chain.load())
    for r in tmp_state.chain.load():
        validate_receipt(r, tmp_state.config.iface_pin)
    for env in expired.envelopes:
        validate_envelope(env, tmp_state.config.iface_pin)

    parent_inc = tmp_state.incidents.find_by_receipt(block["receipt_id"])
    child_inc = tmp_state.incidents.find_by_receipt(rec["receipt_id"])
    assert parent_inc == child_inc


def test_expiry_dedupe_when_already_gone(tmp_state) -> None:
    tmp_state.rules = replace_ttl(tmp_state, 60)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    tmp_state.alias.delete(ATTACKER)
    tmp_state.clock.advance(60)
    write_eve(tmp_state.config.eve_path, [])
    result = run_cycle(tmp_state)
    expiry = [r for r in result.receipts if r["actor"]["id"] == "brewnix-rules/expiry"]
    assert len(expiry) == 1
    assert expiry[0]["policy"]["decision"] == "observe"
    assert all(row.get("status") == "consumed" for row in tmp_state.ledger.rows())


def test_unblock_extra_args_fail_schema(tmp_state) -> None:
    bad = {
        "call_id": "550e8400-e29b-41d4-a716-446655440061",
        "tool": "firewall.unblock_ip",
        "mode": "execute",
        "reason_code": "ttl_expired",
        "args": {"ip": ATTACKER, "alias": "ai_autoblock", "direction": "wan_in"},
    }
    try:
        validate_tool_args(bad, tmp_state.config.iface_pin)
        raised = False
    except Exception:
        raised = True
    assert raised


def replace_ttl(rt, ttl_s: int):
    from aimmune.rules.engine import load_rule_pack

    return load_rule_pack(rt.config.rules_path, ttl_override=ttl_s)
