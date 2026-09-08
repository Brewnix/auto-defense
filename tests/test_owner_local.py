"""Local owner approve/deny: reuse apply_resolution; refuse when plane+watch."""

from __future__ import annotations

import json
from dataclasses import replace

from aimmune.cli import main
from aimmune.cycle import run_cycle
from aimmune.notify.drain import drain_queue
from aimmune.owner.local import LocalResolveError, WaitingOnPlaneError, local_resolve
from aimmune.receipt.chain import verify_chain
from aimmune.schema import validate_receipt
from aimmune.ui.snapshot import build_snapshot
from aimmune.ui.status import BLOCKED, PENDING_INTENT, WAITING_ON_PLANE
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


def _held_propose(tmp_state):
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    propose = next(r for r in result.receipts if r["policy"]["decision"] == "propose")
    return propose


def test_local_approve_offline_applies_block(tmp_state) -> None:
    propose = _held_propose(tmp_state)
    assert ATTACKER not in tmp_state.alias.list_members()
    child = local_resolve(tmp_state, propose["receipt_id"], "approved")
    assert ATTACKER in tmp_state.alias.list_members()
    assert child["parent_id"] == propose["receipt_id"]
    assert child["human"]["resolution"] == "approved"
    assert child["human"]["resolved_by"] == "aimmune:owner:local"
    assert child["policy"]["decision"] == "execute"
    assert any(
        ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
        for ex in child["execution"]
    )
    validate_receipt(child, tmp_state.config.iface_pin)
    verify_chain(tmp_state.chain.load())
    assert not tmp_state.notify.pending()
    snap = build_snapshot(tmp_state)
    hold = next(h for h in snap["holds"] if h["receipt_id"] == propose["receipt_id"])
    assert hold["status"] == BLOCKED
    assert hold["blocked"] is True


def test_local_deny_observe_only(tmp_state) -> None:
    propose = _held_propose(tmp_state)
    child = local_resolve(tmp_state, propose["receipt_id"], "denied", note="cottage owner")
    assert ATTACKER not in tmp_state.alias.list_members()
    assert child["policy"]["decision"] == "observe"
    assert child["human"]["resolution"] == "denied"
    assert any("cottage owner" in str(p.get("args") or {}) for p in child["proposals"])
    validate_receipt(child, tmp_state.config.iface_pin)


def test_refuse_when_watch_open_and_plane_up(tmp_state) -> None:
    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    propose = _held_propose(tmp_state)
    watch = tmp_state.watches.open_watches()[0]
    assert watch["ticket_id"]
    try:
        local_resolve(tmp_state, propose["receipt_id"], "approved")
        raised = False
    except WaitingOnPlaneError:
        raised = True
    assert raised
    assert ATTACKER not in tmp_state.alias.list_members()
    snap = build_snapshot(tmp_state)
    hold = next(h for h in snap["holds"] if h["receipt_id"] == propose["receipt_id"])
    assert hold["status"] == WAITING_ON_PLANE
    assert hold["can_local_resolve"] is False


def test_plane_down_with_existing_watch_allows_local(tmp_state) -> None:
    fake = FakeAuditor()
    tmp_state.config = replace(
        tmp_state.config,
        plane_reachable=True,
        panopticon_base_url="https://panopticon.test",
        hm_site_token=fake.token,
    )
    tmp_state.auditor = fake.client()
    propose = _held_propose(tmp_state)
    assert tmp_state.watches.open_watches()
    # Plane drops; watch remains open.
    tmp_state.config = replace(tmp_state.config, plane_reachable=False)
    child = local_resolve(tmp_state, propose["receipt_id"], "approved")
    assert ATTACKER in tmp_state.alias.list_members()
    watch = tmp_state.watches.rows()[0]
    assert watch["status"] == "acked"
    assert watch.get("local_owner") is True
    assert watch.get("site_acked_receipt_id") == child["receipt_id"]


def test_already_applied_refuses_second_local(tmp_state) -> None:
    propose = _held_propose(tmp_state)
    local_resolve(tmp_state, propose["receipt_id"], "approved")
    try:
        local_resolve(tmp_state, propose["receipt_id"], "denied")
        raised = False
    except LocalResolveError:
        raised = True
    assert raised


def test_snapshot_pending_and_strips_secrets(tmp_state) -> None:
    propose = _held_propose(tmp_state)
    snap = build_snapshot(tmp_state, limit=10)
    assert snap["site_id"] == "net-tn-cottage"
    assert snap["plane_reachable"] is False
    assert snap["sell_state"]["stale"] is True
    assert snap["sell_state"]["value"] in {"off", "on", "paused", "n/a"}
    hold = next(h for h in snap["holds"] if h["receipt_id"] == propose["receipt_id"])
    assert hold["status"] == PENDING_INTENT
    assert hold["can_local_resolve"] is True
    blob = json.dumps(snap)
    assert "prompt" not in blob
    assert "/v1/ir/chat" not in blob
    assert any(r["receipt_id"] == propose["receipt_id"] for r in snap["receipts"])


def test_cli_owner_approve_and_ui_snapshot(tmp_state, monkeypatch) -> None:
    propose = _held_propose(tmp_state)
    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(tmp_state.config.state_dir))
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    monkeypatch.setenv("SITE_ID", tmp_state.config.site_id)
    rc = main(
        [
            "owner",
            "approve",
            "--receipt-id",
            propose["receipt_id"],
            "--state-dir",
            str(tmp_state.config.state_dir),
            "--site-id",
            tmp_state.config.site_id,
        ]
    )
    assert rc == 0
    from aimmune.store import read_jsonl

    receipts = read_jsonl(tmp_state.config.receipts_path)
    child = receipts[-1]
    assert child["parent_id"] == propose["receipt_id"]
    assert child["human"]["resolution"] == "approved"
    rc_snap = main(
        [
            "ui-snapshot",
            "--state-dir",
            str(tmp_state.config.state_dir),
            "--site-id",
            tmp_state.config.site_id,
        ]
    )
    assert rc_snap == 0


def test_cli_owner_refuses_plane_up(tmp_state, capsys, monkeypatch) -> None:
    fake = FakeAuditor()
    _plane_up(tmp_state, fake)
    propose = _held_propose(tmp_state)
    drain_queue(tmp_state)
    monkeypatch.setenv("AIMMUNE_PLANE_REACHABLE", "1")
    rc = main(
        [
            "owner",
            "deny",
            "--receipt-id",
            propose["receipt_id"],
            "--state-dir",
            str(tmp_state.config.state_dir),
            "--site-id",
            tmp_state.config.site_id,
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "waiting on plane" in err
