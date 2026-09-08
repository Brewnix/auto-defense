"""Slice 7 GrantStore mint-local body stays Brewnix — not a SociACL delegate."""

from uuid import uuid4

from aimmune.grants.home import mint_local
from aimmune.grants.propose import build_asks


def _open_incident(rt):
    rec = rt.incidents.open_or_join_security(
        site_id=rt.config.site_id,
        opened_at=rt.clock.now(),
        opened_by={"kind": "human", "id": "test"},
        severity="high",
        summary_redacted="grant body binding",
        ip="203.0.113.9",
        opening_trace_id=str(uuid4()),
    )
    assert rec
    return rec


def test_mint_local_is_privilege_grant_not_delegate(tmp_state) -> None:
    rec = _open_incident(tmp_state)
    body = mint_local(
        store=tmp_state.grants,
        incidents=tmp_state.incidents,
        site_id=tmp_state.config.site_id,
        incident_id=rec["incident_id"],
        ticket_id="t-1",
        notes="cottage elevate",
        reason_redacted="cottage elevate",
        asks=build_asks(tools=["notify.operator"]),
        profile="ir_elevated",
        ttl_s=3600,
        now=tmp_state.clock.now(),
        plane_reachable=False,
    )
    assert body["schema"] == "fyber.privilege_grant/v0"
    assert "mask" not in body
    assert "accessor" not in body
    assert body["asks"]
    stored = tmp_state.grants.get(body["grant_id"])
    assert stored is not None
    assert stored["schema"] == "fyber.privilege_grant/v0"
    rec = tmp_state.incidents.get(rec["incident_id"])
    assert rec["flags"]["grant_active"] is True
