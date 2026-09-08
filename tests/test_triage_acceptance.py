"""Acceptance 1–8 from model-triage-v0 plus theta / bind / mode."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from aimmune.cycle import run_cycle
from aimmune.receipt.chain import verify_chain
from aimmune.schema import validate_envelope, validate_receipt
from aimmune.triage.eval_log import load_eval
from aimmune.triage.settings import RailsStub
from aimmune.ui.serialize import serialize_receipt
from aimmune.ui.snapshot import build_snapshot

from tests.conftest import ATTACKER, enable_triage, port_scan_burst, ssh_brute_burst, write_eve

PROMPT_MARKERS = ("SYSTEM:", "You are a judge", "prompt:", "<<<EVE>>>")


def _applied_blocks(receipts):
    return [
        rec
        for rec in receipts
        if any(
            ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
            for ex in rec["execution"]
        )
    ]


def test_1_rules_only_engines_stopped_critical_still_blocks(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert _applied_blocks(result.receipts)
    assert ATTACKER in tmp_state.alias.list_members()
    assert result.receipts[0]["actor"]["kind"] == "rule"
    assert tmp_state.triage_engines == []


def test_2_auto_execute_does_not_call_mock(tmp_state) -> None:
    mock = enable_triage(tmp_state, mode="rules_primary", scenario="propose")
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert mock.call_count == 0
    assert _applied_blocks(result.receipts)
    assert result.policy_inputs[0]["actor"]["kind"] == "rule"


def test_3_schema_fail_fallback_no_model_execute(tmp_state) -> None:
    mock = enable_triage(tmp_state, mode="rules_primary", scenario="schema_fail")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert mock.call_count == 1
    winner = result.policy_inputs[0]
    assert winner["actor"]["kind"] == "rule"
    assert not _applied_blocks(result.receipts)
    assert ATTACKER not in tmp_state.alias.list_members()
    model_exec = [
        rec
        for rec in result.receipts
        if rec["actor"]["kind"] == "model"
        and any(
            ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
            for ex in rec["execution"]
        )
    ]
    assert model_exec == []
    assert result.receipts[0]["policy"]["decision"] == "propose"


def test_4_strict_no_grant_model_propose_only(tmp_state) -> None:
    enable_triage(tmp_state, mode="rules_primary", scenario="execute")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    winner = result.policy_inputs[0]
    assert winner["actor"]["kind"] == "model"
    rec = result.receipts[0]
    assert rec["actor"]["kind"] == "model"
    assert rec["policy"]["decision"] == "propose"
    assert not _applied_blocks(result.receipts)
    assert ATTACKER not in tmp_state.alias.list_members()
    assert any(p.get("tool") == "notify.operator" for p in rec["proposals"])
    for proposal in rec["proposals"]:
        if proposal.get("tool") == "firewall.block_ip":
            assert proposal.get("mode") == "propose"


def test_5_elevated_stub_execute_then_expiry_back_to_propose(tmp_state) -> None:
    now = tmp_state.clock.now()
    rails = RailsStub(
        profile="ir_elevated",
        grant_active=True,
        active_until=now + timedelta(hours=1),
        tool_allowlist=("firewall.block_ip", "notify.operator"),
    )
    enable_triage(tmp_state, mode="rules_primary", scenario="execute", rails=rails)
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    assert first.policy_inputs[0]["actor"]["kind"] == "model"
    assert _applied_blocks(first.receipts)
    assert ATTACKER in tmp_state.alias.list_members()
    assert first.receipts[0]["policy"]["decision"] == "execute"

    # Expire the stub; new subject must return to propose-only.
    other = "203.0.113.77"
    tmp_state.config = replace(
        tmp_state.config,
        triage=replace(
            tmp_state.config.triage,
            rails=RailsStub(
                profile="ir_elevated",
                grant_active=True,
                active_until=now,
                tool_allowlist=("firewall.block_ip",),
            ),
        ),
    )
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(other, tmp_state.clock.now()))
    second = run_cycle(tmp_state)
    assert second.policy_inputs[0]["actor"]["kind"] == "model"
    assert second.receipts[0]["policy"]["decision"] == "propose"
    assert other not in tmp_state.alias.list_members()


def test_6_pair_unavailable_next_engine_never_fail_open(tmp_state) -> None:
    mock = enable_triage(
        tmp_state,
        mode="rules_primary",
        scenario="propose",
        engine_order=("pair", "mock"),
    )
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    pair = tmp_state.triage_engines[0]
    assert pair.kind == "pair"
    assert pair.call_count == 1
    assert mock.call_count == 1
    assert result.policy_inputs[0]["actor"]["kind"] == "model"
    assert result.receipts[0]["policy"]["decision"] != "execute"
    assert ATTACKER not in tmp_state.alias.list_members()


def test_7_exactly_one_winner_envelope(tmp_state) -> None:
    enable_triage(tmp_state, mode="rules_primary", scenario="propose")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert len(result.policy_inputs) == 1
    winner = result.policy_inputs[0]
    assert winner["actor"]["kind"] == "model"
    tools_from_rules = {"port_scan_burst"}
    # Not a concatenation: model fixture uses ssh_brute only.
    codes = [p.get("reason_code") for p in winner.get("proposals") or []]
    assert "port_scan_burst" not in codes
    assert winner is result.envelopes[0]
    _ = tools_from_rules


def test_8_no_prompt_in_receipt_ticket_incident(tmp_state) -> None:
    enable_triage(tmp_state, mode="rules_primary", scenario="propose")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    verify_chain(tmp_state.chain.load())
    for rec in result.receipts:
        validate_receipt(rec, tmp_state.config.iface_pin)
        blob = str(rec)
        for marker in PROMPT_MARKERS:
            assert marker not in blob
        assert "You are a site-local judge" not in blob
    for env in result.envelopes:
        validate_envelope(env, tmp_state.config.iface_pin)
    for item in tmp_state.notify.pending():
        blob = str(item)
        for marker in PROMPT_MARKERS:
            assert marker not in blob
    if tmp_state.config.incidents_path.is_file():
        blob = tmp_state.config.incidents_path.read_text(encoding="utf-8")
        for marker in PROMPT_MARKERS:
            assert marker not in blob
    snap = build_snapshot(tmp_state)
    snap_blob = str(snap)
    for marker in PROMPT_MARKERS:
        assert marker not in snap_blob
    assert snap["receipts"][0]["actor"]["kind"] == "model"
    view = serialize_receipt(result.receipts[0])
    assert view["actor"]["kind"] == "model"
    rows = load_eval(tmp_state.config.triage_eval_path)
    assert rows
    for row in rows:
        for marker in PROMPT_MARKERS:
            assert marker not in str(row)
        assert "prompt" not in row
        assert "messages" not in row


def test_subject_bind_rejected(tmp_state) -> None:
    mock = enable_triage(tmp_state, mode="rules_primary", scenario="unbound")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert mock.call_count == 1
    rec = result.receipts[0]
    assert rec["policy"]["decision"] in {"observe", "propose"}
    assert ATTACKER not in tmp_state.alias.list_members()
    assert "198.51.100.99" not in tmp_state.alias.list_members()


def test_below_theta_proposes_even_when_elevated(tmp_state) -> None:
    rails = RailsStub(
        profile="ir_elevated",
        grant_active=True,
        tool_allowlist=("firewall.block_ip",),
    )
    enable_triage(
        tmp_state, mode="rules_primary", scenario="low_confidence", rails=rails, theta=0.6
    )
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert result.receipts[0]["actor"]["kind"] == "model"
    assert result.receipts[0]["policy"]["decision"] == "propose"
    assert result.receipts[0]["policy"]["rule_ids"]
    assert ATTACKER not in tmp_state.alias.list_members()


def test_model_assist_token_calls_on_medium_gap(tmp_state) -> None:
    # Quiet window is a non-auto gap; model_assist may call.
    mock = enable_triage(tmp_state, mode="model_assist", scenario="propose")
    result = run_cycle(tmp_state)
    assert mock.call_count == 1
    assert result.policy_inputs[0]["actor"]["kind"] == "model"


def test_incident_opened_by_not_model(tmp_state) -> None:
    enable_triage(tmp_state, mode="rules_primary", scenario="propose")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    incident_id = tmp_state.incidents.find_by_receipt(result.receipts[0]["receipt_id"])
    assert incident_id
    rec = tmp_state.incidents.get(incident_id)
    assert rec["opened_by"]["kind"] in {"rule", "automation", "human"}
    assert rec["opened_by"]["kind"] != "model"
