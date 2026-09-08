"""Slice 7 privilege-grant client, cache, home mint, poll, and elevation."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

from aimmune.canonical import rfc3339
from aimmune.cli import main
from aimmune.cycle import run_cycle
from aimmune.grants.client import GrantClient, GrantError
from aimmune.grants.home import PlaneUpMintError, mint_local
from aimmune.grants.hotreload import elevation_from_runtime
from aimmune.grants.poll import poll_grants
from aimmune.grants.propose import build_asks, build_propose_body
from aimmune.grants.validate import GrantValidationError, clamp_ttl, validate_grant_body
from aimmune.incident.minimal import GrantActiveError
from aimmune.ui.serialize import serialize_grant
from aimmune.ui.snapshot import build_snapshot
from tests.conftest import ATTACKER, enable_triage, ssh_brute_burst, write_eve
from tests.grants_fake import GRANTS, FakeGrants

INCIDENT = "550e8400-e29b-41d4-a716-446655440081"
TRACE = "550e8400-e29b-41d4-a716-446655440070"


def _asks(**kwargs):
    return build_asks(
        tools=kwargs.get("tools") or ["health.restart_service", "notify.operator"],
        rate_limit=kwargs.get("rate_limit"),
        model_tier=kwargs.get("tier"),
        budget_tokens=kwargs.get("budget"),
        template_ids=kwargs.get("templates"),
    )


def _body(**kwargs):
    return build_propose_body(
        site_id="net-tn-cottage",
        incident_id=kwargs.get("incident_id") or INCIDENT,
        reason_redacted=kwargs.get("reason") or "ir_elevated restart",
        asks=kwargs.get("asks") or _asks(),
        profile=kwargs.get("profile") or "ir_elevated",
        ttl_s=kwargs.get("ttl_s") or 14400,
        now=kwargs["now"],
        trace_id=kwargs.get("trace_id") or TRACE,
        ticket_id=kwargs.get("ticket_id"),
        requested_by=kwargs.get("requested_by")
        or {"kind": "human", "id": "aimmune-cli/grant"},
    )


def _open_incident(rt, ip=ATTACKER):
    rec = rt.incidents.open_or_join_security(
        site_id=rt.config.site_id,
        opened_at=rt.clock.now(),
        opened_by={"kind": "human", "id": "test"},
        severity="high",
        summary_redacted="grant test",
        ip=ip,
        opening_trace_id=str(uuid4()),
    )
    assert rec
    return rec


def _inject_approved(rt, incident_id, *, profile="ir_elevated", ttl_s=3600, tools=None):
    now = rt.clock.now()
    until = rfc3339(now + timedelta(seconds=ttl_s))
    grant = {
        "schema": "fyber.privilege_grant/v0",
        "grant_id": str(uuid4()),
        "site_id": rt.config.site_id,
        "incident_id": incident_id,
        "trace_id": str(uuid4()),
        "requested_at": rfc3339(now),
        "requested_by": {"kind": "human", "id": "test"},
        "reason_redacted": "fixture grant",
        "asks": [
            {
                "kind": "tool_allowlist_add",
                "tools": list(tools or ["firewall.block_ip", "notify.operator"]),
            }
        ],
        "rails_profile_requested": profile,
        "ttl_s_requested": ttl_s,
        "blast_radius": "site",
        "status": "approved",
        "resolution": {
            "resolved_by": "panopticon:user:chris",
            "resolved_at": rfc3339(now),
            "ttl_s": ttl_s,
            "rails_profile": profile,
            "notes_redacted": "fixture",
        },
        "active_until": until,
        "parent_grant_id": None,
        "ticket_id": str(uuid4()),
    }
    rt.grants.upsert(grant)
    rt.incidents.attach_grant(incident_id, grant["grant_id"], active_until=until, now=now)
    return grant


def test_propose_idempotent_site_incident_trace() -> None:
    fake = FakeGrants()
    client = fake.client()
    now = __import__("datetime").datetime(2026, 9, 8, 21, 0, tzinfo=__import__("datetime").timezone.utc)
    body = _body(now=now)
    first = client.propose(body)
    second = client.propose(body)
    assert first["grant_id"] == second["grant_id"]
    assert fake.proposes == 2
    assert len(fake.grants) == 1
    other = dict(body)
    other["trace_id"] = "550e8400-e29b-41d4-a716-446655440099"
    third = client.propose(other, idempotency_key="other-key")
    assert third["grant_id"] != first["grant_id"]


def test_list_by_incident_and_get_terminal() -> None:
    fake = FakeGrants()
    client = fake.client()
    now = __import__("datetime").datetime(2026, 9, 8, 21, 0, tzinfo=__import__("datetime").timezone.utc)
    created = client.propose(_body(now=now))
    listed = client.list_grants(status="proposed", incident_id=INCIDENT)
    assert [g["grant_id"] for g in listed] == [created["grant_id"]]
    assert client.list_grants(status="approved", incident_id=INCIDENT) == []
    fake.approve(
        created["grant_id"],
        active_until="2026-09-08T22:00:00Z",
        ttl_s=3600,
        rails_profile="ir_elevated",
    )
    got = client.get_grant(created["grant_id"])
    assert got["status"] == "approved"
    assert got["active_until"] == "2026-09-08T22:00:00Z"


def test_client_has_no_resolve_or_revoke() -> None:
    assert not hasattr(GrantClient, "resolve")
    assert not hasattr(GrantClient, "revoke")
    assert not hasattr(GrantClient, "resolve_grant")
    client = FakeGrants().client()
    assert not hasattr(client, "resolve")
    assert not hasattr(client, "revoke")


def test_site_never_calls_resolve() -> None:
    fake = FakeGrants()
    created = fake.client().propose(
        _body(
            now=__import__("datetime").datetime(
                2026, 9, 8, 21, 0, tzinfo=__import__("datetime").timezone.utc
            )
        )
    )
    raw = httpx.Client(transport=fake.transport, base_url="https://panopticon.test")
    resp = raw.post(
        f"{GRANTS}/{created['grant_id']}/resolve",
        json={"status": "approved", "resolved_by": "panopticon:user:chris"},
        headers={"Authorization": "Bearer hm_site_test"},
    )
    assert resp.status_code == 200
    assert fake.resolves == 1
    # site client did not grow a resolve method
    assert not hasattr(fake.client(), "resolve")


def test_empty_asks_rejected(clock) -> None:
    with pytest.raises(GrantValidationError, match="empty asks"):
        validate_grant_body(
            {
                "schema": "fyber.privilege_grant/v0",
                "site_id": "net-tn-cottage",
                "incident_id": INCIDENT,
                "trace_id": TRACE,
                "requested_at": rfc3339(clock.now()),
                "requested_by": {"kind": "human", "id": "x"},
                "reason_redacted": "x",
                "asks": [],
                "rails_profile_requested": "ir_elevated",
                "ttl_s_requested": 1800,
                "blast_radius": "site",
            }
        )


def test_unknown_and_cut_asks_rejected(clock) -> None:
    with pytest.raises(GrantValidationError, match="unknown"):
        _body(
            now=clock.now(),
            asks=[{"kind": "mcp_allowlist", "tools": ["x"]}],
        )
    with pytest.raises(GrantValidationError, match="CUT|unknown"):
        _body(
            now=clock.now(),
            asks=[{"kind": "shell_unrestricted"}],
        )


def test_budget_without_tier_rejected(clock) -> None:
    with pytest.raises(GrantValidationError, match="model_tier"):
        _body(
            now=clock.now(),
            asks=[{"kind": "budget_tokens", "max_tokens": 1000}],
        )


def test_hypermesh_on_ir_elevated_rejected(clock) -> None:
    with pytest.raises(GrantValidationError, match="hypermesh"):
        _body(
            now=clock.now(),
            asks=[{"kind": "tool_allowlist_add", "tools": ["hypermesh.lease_stop"]}],
        )


def test_break_glass_ttl_clamped() -> None:
    assert clamp_ttl("break_glass", 7200) == 1800
    assert clamp_ttl("break_glass", 900) == 900
    assert clamp_ttl("ir_elevated", 40000) == 28800


def test_offline_mint_and_plane_up_refused(tmp_state) -> None:
    rec = _open_incident(tmp_state)
    grant = mint_local(
        store=tmp_state.grants,
        incidents=tmp_state.incidents,
        site_id=tmp_state.config.site_id,
        incident_id=rec["incident_id"],
        ticket_id=None,
        notes="home owner mint",
        reason_redacted="break_glass suricata down",
        asks=_asks(tools=["health.restart_service", "notify.operator"], tier="local_small", budget=1000),
        profile="break_glass",
        ttl_s=7200,
        now=tmp_state.clock.now(),
        plane_reachable=False,
    )
    assert grant["status"] == "approved"
    assert grant["resolution"]["ttl_s"] == 1800
    assert grant["ticket_id"].startswith("local-ticket-")
    assert tmp_state.grants.active_for_incident(rec["incident_id"], tmp_state.clock.now())
    with pytest.raises(PlaneUpMintError):
        mint_local(
            store=tmp_state.grants,
            incidents=tmp_state.incidents,
            site_id=tmp_state.config.site_id,
            incident_id=rec["incident_id"],
            ticket_id="t",
            notes="no",
            reason_redacted="x" * 8,
            asks=_asks(),
            now=tmp_state.clock.now(),
            plane_reachable=True,
        )


def test_poll_cache_allow_model_execute(tmp_state) -> None:
    rec = _open_incident(tmp_state)
    fake = FakeGrants()
    body = _body(now=tmp_state.clock.now(), incident_id=rec["incident_id"])
    proposed = fake.client().propose(body)
    until = rfc3339(tmp_state.clock.now() + timedelta(hours=1))
    fake.approve(
        proposed["grant_id"],
        active_until=until,
        ttl_s=3600,
        rails_profile="ir_elevated",
    )
    from dataclasses import replace

    tmp_state.config = replace(tmp_state.config, plane_reachable=True)
    tmp_state.grant_client = fake.client()
    result = poll_grants(tmp_state)
    assert result["upserted"] >= 1
    cached = tmp_state.grants.active_for_incident(rec["incident_id"], tmp_state.clock.now())
    assert cached
    assert cached["grant_id"] == proposed["grant_id"]
    elev = elevation_from_runtime(tmp_state, incident_id=rec["incident_id"], now=tmp_state.clock.now())
    assert elev.allow_model_execute is True
    assert elev.source == "grant"
    assert elev.profile == "ir_elevated"


def test_after_active_until_strict(tmp_state) -> None:
    rec = _open_incident(tmp_state)
    grant = _inject_approved(tmp_state, rec["incident_id"], ttl_s=60)
    now = tmp_state.clock.now()
    assert elevation_from_runtime(
        tmp_state, incident_id=rec["incident_id"], now=now
    ).allow_model_execute
    tmp_state.grants.expire_local(now + timedelta(seconds=60))
    elev = elevation_from_runtime(
        tmp_state, incident_id=rec["incident_id"], now=now + timedelta(seconds=60)
    )
    assert elev.allow_model_execute is False
    assert elev.profile == "strict"
    _ = grant


def test_incident_close_refused_while_grant_active(tmp_state) -> None:
    rec = _open_incident(tmp_state)
    _inject_approved(tmp_state, rec["incident_id"])
    with pytest.raises(GrantActiveError):
        tmp_state.incidents.close_human(rec["incident_id"], now=tmp_state.clock.now())


def test_elevated_model_execute_uses_grant_not_rails(tmp_state) -> None:
    enable_triage(tmp_state, mode="rules_primary", scenario="execute")
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    assert first.receipts[0]["policy"]["decision"] == "propose"
    incident_id = tmp_state.incidents.find_by_receipt(first.receipts[0]["receipt_id"])
    assert incident_id
    # rails stub stays inactive — grant is SoT
    assert tmp_state.config.triage.rails.grant_active is False
    _inject_approved(
        tmp_state,
        incident_id,
        profile="ir_elevated",
        tools=["firewall.block_ip", "notify.operator"],
    )
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    second = run_cycle(tmp_state)
    assert second.policy_inputs[0]["actor"]["kind"] == "model"
    assert second.receipts[0]["policy"]["decision"] == "execute"
    assert ATTACKER in tmp_state.alias.list_members()

    tmp_state.clock.advance(3600)
    other = "203.0.113.88"
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(other, tmp_state.clock.now()))
    # new IP opens a new incident without a grant → strict propose
    third = run_cycle(tmp_state)
    assert third.receipts[0]["policy"]["decision"] == "propose"
    assert other not in tmp_state.alias.list_members()


def test_snapshot_strips_prompts(tmp_state) -> None:
    rec = _open_incident(tmp_state)
    grant = _inject_approved(tmp_state, rec["incident_id"])
    grant["prompt"] = "SYSTEM: you are a judge"
    grant["system_prompt"] = "You are a site-local judge"
    grant["asks"].append({"kind": "prompt_route", "template_ids": ["ir.triage.v0"], "prompt": "leak"})
    tmp_state.grants.upsert(grant)
    snap = build_snapshot(tmp_state)
    blob = str(snap)
    assert "SYSTEM:" not in blob
    assert "You are a site-local judge" not in blob
    assert "SYSTEM: you are a judge" not in blob
    for row in snap["grants"]:
        assert "prompt" not in row
        assert "system_prompt" not in row
        for ask in row.get("asks") or []:
            assert "prompt" not in ask
    view = serialize_grant(grant)
    assert "prompt" not in view
    assert "system_prompt" not in view


def test_grant_poll_failure_does_not_block_contain(tmp_state) -> None:
    from dataclasses import replace

    write_eve(
        tmp_state.config.eve_path,
        __import__("tests.conftest", fromlist=["port_scan_burst"]).port_scan_burst(
            ATTACKER, tmp_state.clock.now()
        ),
    )
    fake = FakeGrants()
    fake.down = True
    tmp_state.config = replace(tmp_state.config, plane_reachable=True)
    tmp_state.grant_client = fake.client()
    result = run_cycle(tmp_state)
    applied = [
        rec
        for rec in result.receipts
        if any(
            ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
            for ex in rec["execution"]
        )
    ]
    assert applied
    assert result.grants is not None


def test_cli_status_and_mint_local(tmp_state, monkeypatch, capsys) -> None:
    rec = _open_incident(tmp_state)
    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(tmp_state.config.state_dir))
    monkeypatch.setenv("AIMMUNE_SITE_ID", tmp_state.config.site_id)
    monkeypatch.setenv("AIMMUNE_PLANE_REACHABLE", "0")
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    code = main(
        [
            "grant",
            "mint-local",
            "--state-dir",
            str(tmp_state.config.state_dir),
            "--incident-id",
            rec["incident_id"],
            "--reason",
            "break_glass local",
            "--notes",
            "owner notes",
            "--tool",
            "health.restart_service",
            "--tool",
            "notify.operator",
            "--tier",
            "local_small",
            "--budget",
            "1024",
            "--profile",
            "break_glass",
            "--ttl",
            "7200",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "approved" in out
    code = main(
        [
            "grant",
            "status",
            "--state-dir",
            str(tmp_state.config.state_dir),
            "--incident-id",
            rec["incident_id"],
        ]
    )
    assert code == 0


def test_plane_timeout_is_short() -> None:
    def hang(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow plane")

    client = GrantClient(
        "https://panopticon.test",
        "hm_site_test",
        timeout_s=0.05,
        transport=httpx.MockTransport(hang),
    )
    with pytest.raises(GrantError, match="timeout"):
        client.get_grant("550e8400-e29b-41d4-a716-446655440040")
