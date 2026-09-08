"""httpx-mocked fyber.auditor client — create / get / ack; no resolve."""

from __future__ import annotations

import httpx
import pytest

from aimmune.auditor.client import AuditorClient, AuditorError
from tests.auditor_fake import TICKETS, FakeAuditor


def test_create_get_ack_roundtrip() -> None:
    fake = FakeAuditor()
    client = fake.client()
    created = client.create_ticket(
        {
            "schema": "fyber.auditor.ticket/v0",
            "site_id": "net-tn-cottage",
            "trace_id": "550e8400-e29b-41d4-a716-446655440020",
            "receipt_id": "550e8400-e29b-41d4-a716-446655440030",
            "held_call_id": "550e8400-e29b-41d4-a716-446655440021",
            "reason_code": "propose_needs_ack",
            "severity": "high",
            "text_redacted": "propose site=net-tn-cottage ip=203.0.113.50",
            "display": {
                "tool": "firewall.block_ip",
                "subject": {"kind": "ip", "value": "203.0.113.50"},
                "ttl_s": 86400,
            },
        }
    )
    assert created["status"] == "open"
    assert created["site_acked_receipt_id"] is None
    ticket_id = created["ticket_id"]
    got = client.get_ticket(ticket_id)
    assert got["ticket_id"] == ticket_id
    fake.resolve(ticket_id, resolution="approved")
    after = client.get_ticket(ticket_id)
    assert after["status"] == "resolved"
    assert after["resolution"] == "approved"
    assert after["site_acked_receipt_id"] is None
    acked = client.ack_ticket(ticket_id, "550e8400-e29b-41d4-a716-446655440050")
    assert acked["status"] == "acked"
    assert acked["site_acked_receipt_id"] == "550e8400-e29b-41d4-a716-446655440050"


def test_idempotent_create_same_receipt() -> None:
    fake = FakeAuditor()
    client = fake.client()
    body = {
        "schema": "fyber.auditor.ticket/v0",
        "site_id": "net-tn-cottage",
        "trace_id": "550e8400-e29b-41d4-a716-446655440020",
        "receipt_id": "550e8400-e29b-41d4-a716-446655440030",
        "held_call_id": "550e8400-e29b-41d4-a716-446655440021",
        "reason_code": "rate_limit_hold",
        "severity": "critical",
        "text_redacted": "hold",
        "display": {
            "tool": "firewall.block_ip",
            "subject": {"kind": "ip", "value": "203.0.113.50"},
        },
    }
    first = client.create_ticket(body)
    second = client.create_ticket(body)
    assert first["ticket_id"] == second["ticket_id"]
    assert fake.creates == 2
    assert len(fake.tickets) == 1
    other = dict(body)
    other["receipt_id"] = "550e8400-e29b-41d4-a716-446655440099"
    third = client.create_ticket(other)
    assert third["ticket_id"] != first["ticket_id"]


def test_unknown_token_rejected() -> None:
    fake = FakeAuditor()
    bad = AuditorClient(
        "https://panopticon.test",
        "hm_site_garbage",
        transport=fake.transport,
    )
    with pytest.raises(AuditorError, match="401"):
        bad.create_ticket({"site_id": "net-tn-cottage", "receipt_id": "x"})


def test_client_has_no_resolve() -> None:
    assert not hasattr(AuditorClient, "resolve")
    assert not hasattr(AuditorClient, "resolve_ticket")
    client = FakeAuditor().client()
    assert not hasattr(client, "resolve")
    assert not hasattr(client, "resolve_ticket")


def test_plane_timeout_is_short() -> None:
    def hang(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow plane")

    client = AuditorClient(
        "https://panopticon.test",
        "hm_site_test",
        timeout_s=0.05,
        transport=httpx.MockTransport(hang),
    )
    with pytest.raises(AuditorError, match="timeout"):
        client.get_ticket("550e8400-e29b-41d4-a716-446655440040")


def test_mock_resolve_verb_exists_on_plane_not_client() -> None:
    fake = FakeAuditor()
    created = fake.client().create_ticket(
        {
            "schema": "fyber.auditor.ticket/v0",
            "site_id": "net-tn-cottage",
            "trace_id": "550e8400-e29b-41d4-a716-446655440020",
            "receipt_id": "550e8400-e29b-41d4-a716-446655440030",
            "held_call_id": "550e8400-e29b-41d4-a716-446655440021",
            "reason_code": "propose_needs_ack",
            "severity": "high",
            "text_redacted": "x",
            "display": {
                "tool": "firewall.block_ip",
                "subject": {"kind": "ip", "value": "203.0.113.50"},
            },
        }
    )
    raw = httpx.Client(transport=fake.transport, base_url="https://panopticon.test")
    resp = raw.post(
        f"{TICKETS}/{created['ticket_id']}/resolve",
        json={"resolution": "denied", "resolved_by": "panopticon:user:chris"},
        headers={"Authorization": "Bearer hm_site_test"},
    )
    assert resp.status_code == 200
    assert resp.json()["resolution"] == "denied"
    assert fake.resolves == 1
