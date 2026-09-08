"""Drain queue → tickets; poll resolve; apply + ack. Plane-down stays pending."""

from __future__ import annotations

from dataclasses import replace

from aimmune.cycle import run_cycle
from aimmune.notify.drain import (
    AmendedPatchError,
    drain_queue,
    poll_tickets,
    validate_amended_patch,
)
from aimmune.notify.queue import NotifyQueue
from aimmune.receipt.chain import verify_chain
from aimmune.schema import validate_receipt
from tests.auditor_fake import FakeAuditor
from tests.conftest import ATTACKER, ssh_brute_burst, write_eve


def _plane_up(rt, fake: FakeAuditor):
    rt.config = replace(
        rt.config,
        plane_reachable=True,
        panopticon_base_url="https://panopticon.test",
        hm_site_token=fake.token,
    )
    rt.auditor = fake.client()
    return rt


def test_held_snapshot_on_enqueue(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    item = tmp_state.notify.pending()[0]
    assert item["held"]["tool"] == "firewall.block_ip"
    assert item["held"]["call_id"]
    assert item["held"]["args"]["ip"] == ATTACKER
    assert item["held"]["subject"] == {"kind": "ip", "value": ATTACKER}
    assert item["incident_id"]


def test_plane_down_leaves_queue_pending(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert tmp_state.notify.pending()
    assert result.plane is None
    fake = FakeAuditor()
    fake.down = True
    _plane_up(tmp_state, fake)
    drained = drain_queue(tmp_state)
    assert drained.drained == 0
    assert tmp_state.notify.pending()
    assert not tmp_state.watches.rows()


def test_cycle_end_drains_when_plane_reachable(tmp_state) -> None:
    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert not tmp_state.notify.pending()
    assert result.plane["drain"]["drained"] == 1
    assert tmp_state.watches.open_watches()
    assert fake.creates == 1


def test_idempotent_drain_create(tmp_state) -> None:
    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    assert not tmp_state.notify.pending()
    first_id = tmp_state.watches.rows()[0]["ticket_id"]
    # Replay create against the same receipt key.
    again = fake.client().create_ticket(
        {
            "schema": "fyber.auditor.ticket/v0",
            "site_id": "net-tn-cottage",
            "trace_id": tmp_state.watches.rows()[0]["trace_id"],
            "receipt_id": tmp_state.watches.rows()[0]["receipt_id"],
            "held_call_id": tmp_state.watches.rows()[0]["held"]["call_id"],
            "reason_code": "propose_needs_ack",
            "severity": "high",
            "text_redacted": "replay",
            "display": {
                "tool": "firewall.block_ip",
                "subject": {"kind": "ip", "value": ATTACKER},
            },
        }
    )
    assert again["ticket_id"] == first_id
    assert drain_queue(tmp_state).drained == 0


def test_approved_applies_child_and_acks(tmp_state) -> None:
    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    propose = next(r for r in first.receipts if r["policy"]["decision"] == "propose")
    assert ATTACKER not in tmp_state.alias.list_members()
    ticket_id = tmp_state.watches.rows()[0]["ticket_id"]
    fake.resolve(ticket_id, resolution="approved")
    polled = poll_tickets(tmp_state)
    assert polled.acked == 1
    assert ATTACKER in tmp_state.alias.list_members()
    child = tmp_state.chain.load()[-1]
    assert child["parent_id"] == propose["receipt_id"]
    assert child["human"]["resolution"] == "approved"
    assert child["human"]["resolved_by"] == "panopticon:user:chris"
    assert child["policy"]["decision"] == "execute"
    assert any(
        ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
        for ex in child["execution"]
    )
    validate_receipt(child, tmp_state.config.iface_pin)
    verify_chain(tmp_state.chain.load())
    assert fake.tickets[ticket_id]["status"] == "acked"
    assert fake.tickets[ticket_id]["site_acked_receipt_id"] == child["receipt_id"]
    watch = tmp_state.watches.get(ticket_id)
    assert watch["status"] == "acked"
    assert child["receipt_id"] != propose["receipt_id"]


def test_denied_and_timed_out_observe(tmp_state) -> None:
    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    ticket_id = tmp_state.watches.rows()[0]["ticket_id"]
    fake.resolve(ticket_id, resolution="denied")
    poll_tickets(tmp_state)
    assert ATTACKER not in tmp_state.alias.list_members()
    child = tmp_state.chain.load()[-1]
    assert child["policy"]["decision"] == "observe"
    assert child["human"]["resolution"] == "denied"

    write_eve(tmp_state.config.eve_path, ssh_brute_burst("203.0.113.51", tmp_state.clock.now()))
    run_cycle(tmp_state)
    timeout_watch = next(
        row for row in tmp_state.watches.open_watches() if row["ticket_id"] != ticket_id
    )
    fake.resolve(timeout_watch["ticket_id"], resolution="timed_out")
    poll_tickets(tmp_state)
    assert "203.0.113.51" not in tmp_state.alias.list_members()
    timed = tmp_state.chain.load()[-1]
    assert timed["human"]["resolution"] == "timed_out"
    assert timed["policy"]["decision"] == "observe"


def test_amended_applies_ttl_s_only(tmp_state) -> None:
    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    ticket_id = tmp_state.watches.rows()[0]["ticket_id"]
    fake.resolve(
        ticket_id,
        resolution="amended",
        patch={"ttl_s": 3600},
        notes_redacted="shorten ttl",
    )
    poll_tickets(tmp_state)
    assert ATTACKER in tmp_state.alias.list_members()
    child = tmp_state.chain.load()[-1]
    assert child["human"]["resolution"] == "amended"
    block = next(ex for ex in child["execution"] if ex["tool"] == "firewall.block_ip")
    assert block["effect"]["ttl_s"] == 3600
    assert tmp_state.ledger.rows()[-1]["expire_at"].endswith("Z")


def test_amended_rejects_unknown_keys_client_side(tmp_state) -> None:
    try:
        validate_amended_patch("firewall.block_ip", {"ttl_s": 3600, "alias": "x"})
        raised = False
    except AmendedPatchError:
        raised = True
    assert raised
    try:
        validate_amended_patch("firewall.block_ip", {"ip": "1.2.3.4"})
        raised_ip = False
    except AmendedPatchError:
        raised_ip = True
    assert raised_ip

    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    ticket_id = tmp_state.watches.rows()[0]["ticket_id"]
    fake.resolve(
        ticket_id,
        resolution="amended",
        patch={"ttl_s": 3600, "alias": "evil"},
    )
    poll_tickets(tmp_state)
    assert ATTACKER not in tmp_state.alias.list_members()
    child = tmp_state.chain.load()[-1]
    assert child["policy"]["decision"] == "observe"
    assert child["human"]["resolution"] == "amended"
    assert not any(ex.get("tool") == "firewall.block_ip" for ex in child["execution"])


def test_old_queue_row_loads_held_from_receipt(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    pending = tmp_state.notify.pending()[0]
    # Simulate a slice-1 row: drop held, rewrite queue.
    old = {
        k: v
        for k, v in pending.items()
        if k != "held"
    }
    old["drained"] = False
    old["ticket_id"] = None
    queue = NotifyQueue(tmp_state.config.notify_queue_path)
    tmp_state.config.notify_queue_path.write_text("", encoding="utf-8")
    queue.enqueue(
        queued_at=old["queued_at"],
        site_id=old["site_id"],
        receipt_id=old["receipt_id"],
        trace_id=old["trace_id"],
        proposal=old["proposal"],
        policy_decision=old["policy_decision"],
        incident_id=old.get("incident_id"),
        held=None,
    )
    # Force a row without the held key entirely.
    raw = tmp_state.config.notify_queue_path.read_text(encoding="utf-8")
    assert '"held":null' in raw or '"held": null' in raw

    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    drained = drain_queue(tmp_state)
    assert drained.drained == 1
    watch = tmp_state.watches.rows()[0]
    assert watch["held"]["tool"] == "firewall.block_ip"
    assert watch["held"]["args"]["ip"] == ATTACKER


def test_join_same_ip_does_not_open_second_incident(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    first_id = tmp_state.incidents.find_by_receipt(first.receipts[0]["receipt_id"])
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    second = run_cycle(tmp_state)
    second_id = tmp_state.incidents.find_by_receipt(second.receipts[-1]["receipt_id"])
    assert first_id == second_id
    assert len(tmp_state.incidents.incidents_path.read_text().splitlines()) == 1
