"""Triage config, call gates, winner selection, subject-bind, theta."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aimmune.triage.decide import (
    allow_model_execute,
    select_winner,
    should_call_model,
    strip_unknown_tools,
    subject_bind,
)
from aimmune.triage.settings import ConfigError, RailsStub, parse_triage_settings


def _rules(*, severity="high", reason="ssh_brute", auto=False, noise=False):
    rid = "port_scan_burst" if auto else ("noise_ignore" if noise else reason)
    proposals = []
    if not noise:
        proposals.append(
            {
                "call_id": "550e8400-e29b-41d4-a716-4466554400a1",
                "tool": "firewall.block_ip",
                "mode": "execute" if auto else "propose",
                "reason_code": rid,
                "args": {"ip": "203.0.113.50"},
            }
        )
    return {
        "schema": "fyber.inference_iface/v0",
        "trace_id": "550e8400-e29b-41d4-a716-4466554400aa",
        "actor": {"kind": "rule", "id": "brewnix-rules/v0.1", "purpose": "triage"},
        "judgment": {
            "severity": "info" if noise else severity,
            "classes": ["unknown"] if noise else ["brute_force"],
            "subjects": [{"kind": "ip", "value": "203.0.113.50"}],
            "summary": f"{rid} 203.0.113.50",
            "evidence_refs": ["eve:window"],
        },
        "proposals": proposals,
        "needs_human": severity == "high" and not auto,
    }


def test_default_mode_rules_only_without_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIMMUNE_TRIAGE_MODE", raising=False)
    monkeypatch.delenv("AIMMUNE_TRIAGE_ENGINES", raising=False)
    settings = parse_triage_settings(env={}, rails_profile="strict")
    assert settings.mode == "rules_only"
    assert settings.engines == ()
    assert settings.enrich is False
    assert settings.confidence_theta == 0.6


def test_default_mode_rules_primary_when_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIMMUNE_TRIAGE_MODE", raising=False)
    settings = parse_triage_settings(
        env={"AIMMUNE_TRIAGE_ENGINES": "mock:propose"},
        rails_profile="strict",
    )
    assert settings.mode == "rules_primary"
    assert settings.engines[0].kind == "mock"


def test_model_assist_explicit_not_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = parse_triage_settings(
        env={"AIMMUNE_TRIAGE_MODE": "model_assist", "AIMMUNE_TRIAGE_ENGINES": "mock"},
        rails_profile="strict",
    )
    assert settings.mode == "model_assist"
    home = parse_triage_settings(env={"AIMMUNE_TRIAGE_ENGINES": "mock"}, rails_profile="strict")
    assert home.mode == "rules_primary"


def test_model_primary_rejected() -> None:
    with pytest.raises(ConfigError, match="model_primary"):
        parse_triage_settings(env={"AIMMUNE_TRIAGE_MODE": "model_primary"}, rails_profile="strict")


def test_fail_open_execute_rejected() -> None:
    with pytest.raises(ConfigError, match="fail_open_execute"):
        parse_triage_settings(
            env={"AIMMUNE_TRIAGE_ON_FAILURE": "fail_open_execute"},
            rails_profile="strict",
        )


def test_plane_ir_without_grant_rejected() -> None:
    with pytest.raises(ConfigError, match="plane_ir"):
        parse_triage_settings(
            env={"AIMMUNE_TRIAGE_DEFAULT_TIER": "plane_ir"},
            rails_profile="strict",
        )


def test_should_call_never_on_auto_execute() -> None:
    env = _rules(severity="critical", auto=True)
    auto = frozenset({"port_scan_burst"})
    assert should_call_model(env, mode="rules_primary", enrich=True, auto_rule_ids=auto) is False
    assert should_call_model(env, mode="model_assist", enrich=True, auto_rule_ids=auto) is False
    assert should_call_model(env, mode="rules_only", enrich=False, auto_rule_ids=auto) is False


def test_rules_primary_calls_on_high_not_noise() -> None:
    auto = frozenset({"port_scan_burst"})
    assert should_call_model(
        _rules(severity="high"), mode="rules_primary", enrich=False, auto_rule_ids=auto
    )
    assert not should_call_model(
        _rules(noise=True), mode="rules_primary", enrich=False, auto_rule_ids=auto
    )
    quiet = _rules(severity="info", noise=True)
    assert not should_call_model(quiet, mode="rules_primary", enrich=False, auto_rule_ids=auto)


def test_model_assist_calls_on_non_auto_gap() -> None:
    auto = frozenset({"port_scan_burst"})
    mid = _rules(severity="medium", reason="ssh_brute")
    mid["judgment"]["severity"] = "medium"
    assert should_call_model(mid, mode="model_assist", enrich=False, auto_rule_ids=auto)
    assert not should_call_model(mid, mode="rules_primary", enrich=False, auto_rule_ids=auto)


def test_select_winner_never_merges() -> None:
    rules = _rules()
    model = dict(rules)
    model["actor"] = {"kind": "model", "id": "mock", "purpose": "triage"}
    model["proposals"] = list(rules["proposals"]) + [
        {
            "call_id": "550e8400-e29b-41d4-a716-4466554400a2",
            "tool": "notify.operator",
            "mode": "execute",
            "reason_code": "propose_needs_ack",
            "args": {"channel": "fyber.auditor", "severity": "high", "text_redacted": "x"},
        }
    ]
    winner = select_winner(rules, model, None, auto_rule=False)
    assert winner.source == "model"
    assert winner.envelope is model
    assert winner.rules_logged is True
    merged = select_winner(rules, None, "schema_invalid", auto_rule=False)
    assert merged.source == "rules"
    assert merged.envelope is rules


def test_allow_model_execute_stub_and_expiry() -> None:
    now = datetime(2026, 9, 8, 21, 0, tzinfo=timezone.utc)
    assert allow_model_execute(RailsStub(), now) is False
    assert allow_model_execute(RailsStub(profile="ir_elevated"), now) is False
    active = RailsStub(profile="ir_elevated", grant_active=True)
    assert allow_model_execute(active, now) is True
    expired = RailsStub(
        profile="break_glass",
        grant_active=True,
        active_until=now,
    )
    assert allow_model_execute(expired, now) is False
    future = RailsStub(
        profile="break_glass",
        grant_active=True,
        active_until=now + timedelta(minutes=10),
    )
    assert allow_model_execute(future, now) is True


def test_strip_unknown_tools() -> None:
    env = _rules()
    env["proposals"].append({"tool": "shell.unrestricted", "mode": "execute", "args": {}})
    stripped = strip_unknown_tools(env)
    assert [p["tool"] for p in stripped["proposals"]] == ["firewall.block_ip"]


def test_subject_bind_strips_leak() -> None:
    bundle = {
        "top_subjects": [{"ip": "203.0.113.50", "hits": 3}],
        "counts": {"by_src": {"203.0.113.50": 3}},
        "prior_blocks": [],
    }
    env = _rules()
    env["proposals"][0]["args"]["ip"] = "198.51.100.99"
    env["judgment"]["subjects"] = [{"kind": "ip", "value": "198.51.100.99"}]
    bound, violations = subject_bind(env, bundle, site_id="net-tn-cottage")
    assert violations
    assert bound["proposals"] == []
    assert all(s.get("value") != "198.51.100.99" for s in bound["judgment"]["subjects"])
