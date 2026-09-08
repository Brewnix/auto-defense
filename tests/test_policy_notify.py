"""High stays propose (not observe); rate-limit hold queues notify."""

from __future__ import annotations

from dataclasses import replace

from aimmune.cycle import run_cycle
from tests.conftest import ATTACKER, port_scan_burst, ssh_brute_burst, write_eve


def test_high_propose_not_observe_and_notify_queued(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    propose = [r for r in result.receipts if r["policy"]["decision"] == "propose"]
    assert propose, [r["policy"] for r in result.receipts]
    assert propose[0]["human"]["required"] is True
    assert ATTACKER not in tmp_state.alias.list_members()
    assert tmp_state.notify.pending()
    item = tmp_state.notify.pending()[0]
    assert item["proposal"]["tool"] == "notify.operator"
    assert item["proposal"]["args"]["channel"] == "fyber.auditor"
    assert item["drained"] is False
    assert any(ex.get("effect", {}).get("queued") for r in propose for ex in r["execution"])
    incident_id = tmp_state.incidents.find_by_receipt(propose[0]["receipt_id"])
    assert incident_id


def test_rate_limit_hold_requires_notify(tmp_state) -> None:
    tmp_state.rate_limit.max_per_hour = 1
    tmp_state.config = replace(tmp_state.config, rate_limit_b=1)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    assert any(r["policy"]["decision"] == "execute" for r in first.receipts)

    other = "203.0.113.77"
    write_eve(tmp_state.config.eve_path, port_scan_burst(other, tmp_state.clock.now()))
    second = run_cycle(tmp_state)
    holds = [r for r in second.receipts if r["policy"]["decision"] == "hold_human"]
    assert holds
    assert holds[0]["human"]["required"] is True
    assert other not in tmp_state.alias.list_members()
    assert any(
        p.get("tool") == "notify.operator" and p.get("reason_code") == "rate_limit_hold"
        for r in holds
        for p in r["proposals"]
    )


def test_do_not_downgrade_high_to_observe(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    decisions = {r["policy"]["decision"] for r in result.receipts}
    assert "observe" not in decisions or "propose" in decisions
    assert "propose" in decisions
    assert "execute" not in decisions
