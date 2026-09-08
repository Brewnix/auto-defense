"""Binding acceptance 1–8 + auto_quiet + lease_stop require-incident."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from aimmune.cli import main
from aimmune.cycle import run_cycle
from aimmune.incident.minimal import (
    GrantActiveError,
    IncidentError,
    IncidentStore,
    require_grant_incident_id,
)
from aimmune.preempt.runner import cli_preempt
from aimmune.schema import validate_receipt
from aimmune.ui.serialize import serialize_incident
from aimmune.ui.snapshot import build_snapshot
from tests.conftest import ATTACKER, port_scan_burst, write_eve
from tests.owner_fake import FakeOwner

OTHER = "198.51.100.77"


def _store(tmp_path) -> IncidentStore:
    return IncidentStore(tmp_path / "incidents.jsonl", tmp_path / "incident_index.jsonl")


def test_1_critical_block_opens_and_contain_survives_write_fail(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    applied = [
        rec
        for rec in first.receipts
        if any(ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied" for ex in rec["execution"])
    ]
    assert applied
    incident_id = tmp_state.incidents.find_by_receipt(applied[0]["receipt_id"])
    assert incident_id
    rec = tmp_state.incidents.get(incident_id)
    assert rec["kind"] == "security"
    assert rec["status"] == "open"
    assert ATTACKER in tmp_state.alias.list_members()

    tmp_state.incidents.fail_next_write = True
    write_eve(tmp_state.config.eve_path, port_scan_burst(OTHER, tmp_state.clock.now()))
    second = run_cycle(tmp_state)
    other_applied = [
        rec
        for rec in second.receipts
        if any(
            ex.get("tool") == "firewall.block_ip"
            and ex.get("status") == "applied"
            and (ex.get("effect") or {}).get("ip") == OTHER
            for ex in rec["execution"]
        )
    ]
    assert other_applied
    assert OTHER in tmp_state.alias.list_members()
    assert tmp_state.incidents.find_by_receipt(other_applied[0]["receipt_id"]) is None


def test_2_same_ip_joins_within_4h_new_id_after_close(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    first_id = tmp_state.incidents.find_by_receipt(first.receipts[0]["receipt_id"])
    tmp_state.clock.advance(3600)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    # still in alias → observe; force a second propose/hold via a new IP? 
    # Join path: hold/propose/contain for same IP. Dedupe observe does not join.
    # Close then re-open after unblock so the third burst is a new contain.
    closed = tmp_state.incidents.close_human(first_id, now=tmp_state.clock.now())
    assert closed["status"] == "closed"
    assert closed["close_reason"] == "human"
    tmp_state.alias.delete(ATTACKER)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    third = run_cycle(tmp_state)
    third_id = tmp_state.incidents.find_by_receipt(third.receipts[-1]["receipt_id"])
    assert third_id
    assert third_id != first_id
    assert tmp_state.incidents.get(third_id)["status"] == "open"


def test_2_join_same_ip_two_holds_one_id(tmp_state) -> None:
    from tests.conftest import ssh_brute_burst

    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    first_id = tmp_state.incidents.find_by_receipt(first.receipts[0]["receipt_id"])
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    second = run_cycle(tmp_state)
    second_id = tmp_state.incidents.find_by_receipt(second.receipts[-1]["receipt_id"])
    assert first_id == second_id
    assert len(tmp_state.incidents.list_incidents()) == 1


def test_3_ops_does_not_join_security(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    security = tmp_state.incidents.list_incidents()
    assert len(security) == 1
    assert security[0]["kind"] == "security"
    ops = tmp_state.incidents.open_or_join_ops(
        site_id=tmp_state.config.site_id,
        opened_at=tmp_state.clock.now(),
        opened_by={"kind": "rule", "id": "brewnix-rules/health-v0.1"},
        severity="high",
        summary_redacted="health_suricata_down node=opnsense-cottage unit=suricata",
        opening_trace_id=str(uuid4()),
        node="opnsense-cottage",
        unit="suricata",
    )
    assert ops is not None
    assert ops["kind"] == "ops"
    assert ops["incident_id"] != security[0]["incident_id"]
    assert len(tmp_state.incidents.list_incidents()) == 2


def test_4_grant_without_incident_id_rejected() -> None:
    try:
        require_grant_incident_id({"schema": "fyber.privilege_grant/v0", "incident_id": None})
        raised = False
    except IncidentError:
        raised = True
    assert raised
    try:
        require_grant_incident_id({"incident_id": ""})
        raised_empty = False
    except IncidentError:
        raised_empty = True
    assert raised_empty
    try:
        require_grant_incident_id({})
        raised_missing = False
    except IncidentError:
        raised_missing = True
    assert raised_missing
    assert require_grant_incident_id({"incident_id": "  abc  "}) == "abc"


def test_5_expiry_inherits_never_opens(tmp_state) -> None:
    from tests.test_expiry import replace_ttl
    from dataclasses import replace

    tmp_state.rules = replace_ttl(tmp_state, 60)
    tmp_state.config = replace(tmp_state.config, block_ttl_s=60)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    block = next(r for r in first.receipts if r["policy"]["decision"] == "execute")
    parent = tmp_state.incidents.find_by_receipt(block["receipt_id"])
    before = len(tmp_state.incidents.list_incidents())
    tmp_state.clock.advance(60)
    write_eve(tmp_state.config.eve_path, [])
    expired = run_cycle(tmp_state)
    child = next(r for r in expired.receipts if r["actor"]["id"] == "brewnix-rules/expiry")
    assert tmp_state.incidents.find_by_receipt(child["receipt_id"]) == parent
    assert len(tmp_state.incidents.list_incidents()) == before


def test_5_expiry_unscoped_when_parent_had_none(tmp_state) -> None:
    from tests.test_expiry import replace_ttl
    from dataclasses import replace

    tmp_state.rules = replace_ttl(tmp_state, 60)
    tmp_state.config = replace(tmp_state.config, block_ttl_s=60)
    tmp_state.incidents.fail_next_write = True
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    first = run_cycle(tmp_state)
    block = next(r for r in first.receipts if r["policy"]["decision"] == "execute")
    assert tmp_state.incidents.find_by_receipt(block["receipt_id"]) is None
    tmp_state.clock.advance(60)
    write_eve(tmp_state.config.eve_path, [])
    expired = run_cycle(tmp_state)
    child = next(r for r in expired.receipts if r["actor"]["id"] == "brewnix-rules/expiry")
    assert tmp_state.incidents.find_by_receipt(child["receipt_id"]) is None
    assert tmp_state.incidents.list_incidents() == []


def test_6_close_refused_while_grant_active(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    incident_id = tmp_state.incidents.list_incidents()[0]["incident_id"]
    tmp_state.incidents.attach_grant(
        incident_id,
        str(uuid4()),
        active_until=tmp_state.clock.now() + timedelta(hours=1),
        now=tmp_state.clock.now(),
    )
    try:
        tmp_state.incidents.close_human(incident_id, now=tmp_state.clock.now())
        refused = False
    except GrantActiveError:
        refused = True
    assert refused
    assert tmp_state.incidents.get(incident_id)["status"] == "open"
    tmp_state.clock.advance(25 * 3600)
    swept = tmp_state.incidents.sweep(tmp_state.clock.now())
    assert incident_id not in swept["closed"]
    tmp_state.incidents.set_grant_active(incident_id, False)
    closed = tmp_state.incidents.close_human(incident_id, now=tmp_state.clock.now())
    assert closed["status"] == "closed"
    assert closed["close_reason"] == "human"


def test_7_observe_unscoped(tmp_state) -> None:
    result = run_cycle(tmp_state)
    assert result.receipts
    assert all(r["policy"]["decision"] == "observe" for r in result.receipts)
    assert tmp_state.incidents.list_incidents() == []
    assert tmp_state.incidents.find_by_receipt(result.receipts[0]["receipt_id"]) is None


def test_8_offline_open_close_sweep(tmp_state) -> None:
    assert tmp_state.config.plane_reachable is False
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    incident_id = tmp_state.incidents.list_incidents()[0]["incident_id"]
    tmp_state.incidents.set_grant_active(incident_id, True)
    try:
        tmp_state.incidents.close_human(incident_id, now=tmp_state.clock.now())
        raised = False
    except GrantActiveError:
        raised = True
    assert raised
    tmp_state.incidents.set_grant_active(incident_id, False)
    tmp_state.clock.advance(25 * 3600)
    swept = tmp_state.incidents.sweep(tmp_state.clock.now())
    assert incident_id in swept["closed"]
    assert tmp_state.incidents.get(incident_id)["close_reason"] == "auto_quiet"


def test_auto_quiet_security_24h_ops_2h(tmp_path, clock) -> None:
    store = _store(tmp_path)
    sec = store.open_security(
        site_id="net-tn-cottage",
        opened_at=clock.now(),
        opened_by={"kind": "rule", "id": "brewnix-rules/v0.1"},
        severity="critical",
        summary_redacted="burst",
        ip=ATTACKER,
        opening_trace_id=str(uuid4()),
        opening_receipt_id=str(uuid4()),
    )
    ops = store.open_or_join_ops(
        site_id="net-tn-cottage",
        opened_at=clock.now(),
        opened_by={"kind": "automation", "id": "aimmune"},
        severity="high",
        summary_redacted="disk",
        opening_trace_id=str(uuid4()),
        opening_receipt_id=str(uuid4()),
        health_class="health_disk",
    )
    clock.advance(2 * 3600)
    swept = store.sweep(clock.now())
    assert ops["incident_id"] in swept["closed"]
    assert sec["incident_id"] not in swept["closed"]
    clock.advance(22 * 3600)
    swept = store.sweep(clock.now())
    assert sec["incident_id"] in swept["closed"]
    assert store.get(sec["incident_id"])["close_reason"] == "auto_quiet"


def test_auto_quiet_resets_on_linked_receipt_only(tmp_path, clock) -> None:
    store = _store(tmp_path)
    sec = store.open_security(
        site_id="net-tn-cottage",
        opened_at=clock.now(),
        opened_by={"kind": "rule", "id": "x"},
        severity="high",
        summary_redacted="a",
        ip=ATTACKER,
        opening_trace_id=str(uuid4()),
        opening_receipt_id=str(uuid4()),
    )
    clock.advance(23 * 3600)
    store.attach_receipt(sec["incident_id"], str(uuid4()), now=clock.now())
    clock.advance(2 * 3600)
    swept = store.sweep(clock.now())
    assert swept["closed"] == []
    clock.advance(23 * 3600)
    swept = store.sweep(clock.now())
    assert sec["incident_id"] in swept["closed"]


def test_ops_join_1h_and_severity_roll(tmp_path, clock) -> None:
    store = _store(tmp_path)
    first = store.open_or_join_ops(
        site_id="net-tn-cottage",
        opened_at=clock.now(),
        opened_by={"kind": "rule", "id": "h"},
        severity="medium",
        summary_redacted="disk",
        opening_trace_id=str(uuid4()),
        health_class="health_disk",
    )
    clock.advance(30 * 60)
    second = store.open_or_join_ops(
        site_id="net-tn-cottage",
        opened_at=clock.now(),
        opened_by={"kind": "rule", "id": "h"},
        severity="critical",
        summary_redacted="disk worse",
        opening_trace_id=str(uuid4()),
        health_class="health_disk",
    )
    assert first["incident_id"] == second["incident_id"]
    assert store.get(first["incident_id"])["severity"] == "critical"
    clock.advance(2 * 3600)
    late = store.open_or_join_ops(
        site_id="net-tn-cottage",
        opened_at=clock.now(),
        opened_by={"kind": "rule", "id": "h"},
        severity="low",
        summary_redacted="disk later",
        opening_trace_id=str(uuid4()),
        health_class="health_disk",
    )
    assert late["incident_id"] != first["incident_id"]


def test_lease_stop_execute_without_incident_does_not_execute(tmp_state) -> None:
    fake = FakeOwner()
    tmp_state.owner = fake.client()
    receipt = cli_preempt(
        tmp_state,
        kind="lease_stop",
        device_id="jetson-cottage-01",
        lease_id="lease-203-0-113-50",
        reason_code="site_defense",
        until=None,
        execute=True,
    )
    validate_receipt(receipt, tmp_state.config.iface_pin)
    assert receipt["policy"]["decision"] == "propose"
    assert not any(e.get("tool") == "hypermesh.lease_stop" and e.get("status") == "applied" for e in receipt["execution"])
    assert tmp_state.notify.pending()
    assert not fake.calls


def test_sell_pause_health_opens_ops_not_security(tmp_state) -> None:
    from aimmune.preempt.runner import run_preempt

    receipt = run_preempt(
        tmp_state,
        proposals=[
            {
                "call_id": str(uuid4()),
                "tool": "hypermesh.sell_pause",
                "mode": "propose",
                "reason_code": "health_evacuate",
                "args": {"device_id": "jetson-cottage-01"},
            }
        ],
        device_id="jetson-cottage-01",
        reason_code="health_evacuate",
        actor={"kind": "rule", "id": "brewnix-rules/hypermesh-preempt-v0", "purpose": "triage"},
        origin_actor_kind="rule",
        judgment={
            "severity": "high",
            "classes": ["health"],
            "subjects": [{"kind": "host", "value": "jetson-cottage-01"}],
            "summary": "health evacuate pause",
            "evidence_refs": ["health:thermal"],
        },
    )
    incident_id = tmp_state.incidents.find_by_receipt(receipt["receipt_id"])
    assert incident_id
    rec = tmp_state.incidents.get(incident_id)
    assert rec["kind"] == "ops"
    assert rec["primary_subjects"][0]["kind"] == "health_class"


def test_snapshot_includes_full_incident_and_index(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    snap = build_snapshot(tmp_state)
    assert snap["incidents"]
    row = snap["incidents"][0]
    for key in (
        "schema",
        "incident_id",
        "kind",
        "status",
        "opened_at",
        "opened_by",
        "severity",
        "summary_redacted",
        "primary_subjects",
        "closed_at",
        "close_reason",
        "flags",
        "links",
        "index",
    ):
        assert key in row
    assert row["schema"] == "fyber.incident/v0"
    assert row["index"]["receipt_count"] >= 1
    dirty = serialize_incident(
        {**tmp_state.incidents.list_incidents()[0], "prompt": "leak", "eve": {"raw": 1}},
        {"receipt_ids": ["x"], "ticket_ids": [], "grant_ids": []},
    )
    assert "prompt" not in dirty
    assert "eve" not in dirty


def test_cli_incident_list_close_sweep(tmp_state, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(tmp_state.config.state_dir))
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    monkeypatch.setenv("AIMMUNE_SITE_ID", tmp_state.config.site_id)
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    run_cycle(tmp_state)
    incident_id = tmp_state.incidents.list_incidents()[0]["incident_id"]
    assert main(["incident", "list", "--state-dir", str(tmp_state.config.state_dir)]) == 0
    listed = capsys.readouterr().out
    assert incident_id in listed
    tmp_state.incidents.set_grant_active(incident_id, True)
    assert main(["incident", "close", "--id", incident_id, "--state-dir", str(tmp_state.config.state_dir)]) == 2
    tmp_state.incidents.set_grant_active(incident_id, False)
    assert main(["incident", "close", "--id", incident_id, "--state-dir", str(tmp_state.config.state_dir)]) == 0
    assert tmp_state.incidents.get(incident_id)["close_reason"] == "human"
    assert main(["incident", "sweep", "--state-dir", str(tmp_state.config.state_dir)]) == 0


def test_cycle_sweep_failure_does_not_drop_receipts(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))

    def boom(_now):
        raise OSError("disk full")

    tmp_state.incidents.sweep = boom  # type: ignore[method-assign]
    result = run_cycle(tmp_state)
    assert result.receipts
    assert any(r["policy"]["decision"] == "execute" for r in result.receipts)
    assert result.sweep == {"closed": [], "error": "sweep failed"}
