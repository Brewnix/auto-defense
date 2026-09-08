"""Offline vertical synthetic SoT — plane down, rules-only, mock alias.

Compose existing fixtures only (conftest bursts, tmp_state MockAlias).
Does not enable triage engines, FakeAuditor, or FakeGrants.
No live Suricata / OPNsense / WireGuard / Panopticon / SIWE.
"""

from __future__ import annotations

import json
from pathlib import Path

from aimmune.cli import main
from aimmune.cycle import run_cycle
from aimmune.owner.local import local_resolve
from aimmune.receipt.chain import verify_chain
from aimmune.schema import validate_envelope, validate_receipt
from tests.conftest import (
    ATTACKER,
    BRUTE_ATTACKER,
    port_scan_burst,
    ssh_brute_burst,
    write_eve,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _applied_block(rec: dict) -> bool:
    return any(
        ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
        for ex in rec.get("execution") or []
    )


def _reason_codes(rec: dict) -> set[str]:
    return {str(p.get("reason_code")) for p in rec.get("proposals") or [] if p.get("reason_code")}


def test_offline_vertical_contain_hold_resolve_mint_status(tmp_state, monkeypatch, capsys) -> None:
    rt = tmp_state
    assert rt.config.plane_reachable is False
    assert rt.config.exec_mock is True
    assert rt.auditor is None
    assert rt.grant_client is None
    assert rt.triage_engines == []

    write_eve(
        rt.config.eve_path,
        port_scan_burst(ATTACKER, rt.clock.now())
        + ssh_brute_burst(BRUTE_ATTACKER, rt.clock.now()),
    )

    result = run_cycle(rt)
    contain = [
        rec
        for rec in result.receipts
        if rec["policy"]["decision"] == "execute"
        and _applied_block(rec)
        and "port_scan_burst" in _reason_codes(rec)
    ]
    hold = [
        rec
        for rec in result.receipts
        if rec["policy"]["decision"] == "propose" and "ssh_brute" in _reason_codes(rec)
    ]
    assert len(contain) == 1, [r["policy"] for r in result.receipts]
    assert len(hold) == 1, [r["policy"] for r in result.receipts]
    assert contain[0]["purpose"] == "contain"
    assert contain[0]["actor"]["kind"] == "rule"
    assert contain[0]["posture"]["plane_reachable"] is False
    assert ATTACKER in rt.alias.list_members()
    assert BRUTE_ATTACKER not in rt.alias.list_members()
    assert rt.notify.pending()
    assert hold[0]["human"]["required"] is True

    chain = rt.chain.load()
    verify_chain(chain)
    for rec in chain:
        validate_receipt(rec, rt.config.iface_pin)
    for env in result.envelopes:
        validate_envelope(env, rt.config.iface_pin)

    propose = hold[0]
    incident_id = rt.incidents.find_by_receipt(propose["receipt_id"])
    assert incident_id

    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(rt.config.state_dir))
    monkeypatch.setenv("AIMMUNE_SITE_ID", rt.config.site_id)
    monkeypatch.setenv("SITE_ID", rt.config.site_id)
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    monkeypatch.setenv("AIMMUNE_PLANE_REACHABLE", "0")
    monkeypatch.delenv("PANOPTICON_BASE_URL", raising=False)
    monkeypatch.delenv("AIMMUNE_TRIAGE_ENGINES", raising=False)

    rc_verify = main(
        [
            "verify-chain",
            "--state-dir",
            str(rt.config.state_dir),
            "--site-id",
            rt.config.site_id,
        ]
    )
    assert rc_verify == 0
    verify_out = json.loads(capsys.readouterr().out)
    assert verify_out["ok"] is True
    assert verify_out["count"] >= 2

    # In-process resolve keeps the tmp_state MockAlias. CLI approve would
    # build a fresh in-memory store (exec_mock) and not see this alias.
    child = local_resolve(rt, propose["receipt_id"], "approved")
    assert child["parent_id"] == propose["receipt_id"]
    assert child["policy"]["decision"] == "execute"
    assert BRUTE_ATTACKER in rt.alias.list_members()
    verify_chain(rt.chain.load())

    rc_mint = main(
        [
            "grant",
            "mint-local",
            "--state-dir",
            str(rt.config.state_dir),
            "--incident-id",
            incident_id,
            "--reason",
            "offline synthetic elevate",
            "--notes",
            "cottage owner mint after local resolve",
            "--tool",
            "notify.operator",
            "--profile",
            "break_glass",
            "--ttl",
            "1800",
        ]
    )
    assert rc_mint == 0
    minted = json.loads(capsys.readouterr().out)
    assert minted["schema"] == "fyber.privilege_grant/v0"
    assert minted["status"] == "approved"
    assert minted["incident_id"] == incident_id
    assert "mask" not in minted

    rc_status = main(["status", "--json"])
    assert rc_status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["site_id"] == "net-tn-cottage"
    assert payload["plane_reachable"] is False
    assert payload["exec_mock"] is True
    assert payload["receipts"]["count"] >= 3
    assert payload["receipts"]["last"]["receipt_id"]
    assert payload["open_incidents"] >= 1
    assert payload["active_grants"] >= 1


def test_offline_vertical_committed_eve_fixtures(tmp_state) -> None:
    """Committed JSONL fixtures compose the same two-rule burst."""
    scan = (FIXTURES / "eve_port_scan.jsonl").read_text(encoding="utf-8")
    brute = (FIXTURES / "eve_ssh_brute.jsonl").read_text(encoding="utf-8")
    tmp_state.config.eve_path.write_text(scan + brute, encoding="utf-8")

    result = run_cycle(tmp_state)
    decisions = {r["policy"]["decision"] for r in result.receipts}
    assert "execute" in decisions
    assert "propose" in decisions
    assert ATTACKER in tmp_state.alias.list_members()
    assert BRUTE_ATTACKER not in tmp_state.alias.list_members()
    verify_chain(tmp_state.chain.load())
