"""Offline pytest replay harness (schema rate, subject-bind, dry-run, contain)."""

from __future__ import annotations

from aimmune.cycle import run_cycle
from aimmune.schema import validate_envelope
from aimmune.triage.engines.mock import fixture_envelope
from aimmune.triage.runner import validate_model_envelope

from tests.conftest import ATTACKER, enable_triage, port_scan_burst, ssh_brute_burst, write_eve


def test_eval_schema_rate_and_subject_bind(tmp_state, pin) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    enable_triage(tmp_state, mode="rules_primary", scenario="propose")
    result = run_cycle(tmp_state)
    bundle = {k: v for k, v in (result.bundle or {}).items() if k != "_digest"}
    model_ok = 0
    model_total = 0
    for env in result.policy_inputs:
        if env["actor"]["kind"] != "model":
            continue
        model_total += 1
        validate_envelope(env, pin)
        model_ok += 1
        allowed = set((bundle.get("counts") or {}).get("by_src") or {})
        allowed.update(s.get("ip") for s in bundle.get("top_subjects") or [] if s.get("ip"))
        for sub in env["judgment"]["subjects"]:
            if sub.get("kind") == "ip":
                assert sub["value"] in allowed
        for proposal in env.get("proposals") or []:
            ip = (proposal.get("args") or {}).get("ip")
            if ip:
                assert ip in allowed
    assert model_total >= 1
    assert model_ok == model_total


def test_eval_strict_dry_run_over_execute_zero(tmp_state) -> None:
    enable_triage(tmp_state, mode="rules_primary", scenario="execute")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    model_companion_execute = 0
    for rec in result.receipts:
        if rec["actor"]["kind"] != "model":
            continue
        if rec["policy"]["decision"] == "execute":
            model_companion_execute += 1
        for ex in rec["execution"]:
            if ex.get("tool") in {
                "firewall.block_ip",
                "health.restart_service",
                "hypermesh.lease_stop",
                "hypermesh.sell_pause",
            } and ex.get("status") == "applied":
                model_companion_execute += 1
    assert model_companion_execute == 0


def test_eval_offline_no_engine_still_contains(tmp_state) -> None:
    assert tmp_state.config.plane_reachable is False
    assert tmp_state.triage_engines == []
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert any(r["policy"]["decision"] == "execute" for r in result.receipts)
    assert ATTACKER in tmp_state.alias.list_members()
    assert result.receipts


def test_eval_repair_once_then_drop(pin) -> None:
    bad = {"schema": "fyber.inference_iface/v0", "actor": {"kind": "model"}}
    env, err = validate_model_envelope(bad, pin)
    assert env is None
    assert err == "schema_invalid"


def test_eval_fixture_envelope_validates(tmp_state, pin) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    bundle = result.bundle or {}
    digest = bundle.get("_digest") if False else None
    from aimmune.canonical import features_digest

    digest = features_digest(bundle)
    env = fixture_envelope(
        scenario="propose",
        bundle=bundle,
        site_id=tmp_state.config.site_id,
        observed_at="2026-09-08T21:00:00Z",
        inputs_digest=digest,
        engine_id="mock-engine",
    )
    validate_envelope(env, pin)
