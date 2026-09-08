"""Optional plane-mocked synthetic — default off (`pytest -m plane_mocked`).

Uses existing FakeAuditor / FakeGrants only. No live plane, no SIWE.
Not a second mock stack for the offline SoT; this file is opt-in contrast.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from aimmune.cycle import run_cycle
from aimmune.grants.home import PlaneUpMintError, mint_local
from aimmune.grants.propose import build_asks, build_propose_body
from aimmune.owner.local import WaitingOnPlaneError, local_resolve
from aimmune.status import build_status
from tests.auditor_fake import FakeAuditor
from tests.conftest import ATTACKER, BRUTE_ATTACKER, port_scan_burst, ssh_brute_burst, write_eve
from tests.grants_fake import FakeGrants

pytestmark = pytest.mark.plane_mocked


def _plane_up(rt, auditor: FakeAuditor, grants: FakeGrants):
    rt.config = replace(
        rt.config,
        plane_reachable=True,
        panopticon_base_url="https://panopticon.test",
        hm_site_token=auditor.token,
    )
    rt.auditor = auditor.client()
    rt.grant_client = grants.client()
    return rt


def test_plane_mocked_drain_refuses_local_mint(tmp_state) -> None:
    fake_auditor = FakeAuditor()
    fake_grants = FakeGrants()
    rt = _plane_up(tmp_state, fake_auditor, fake_grants)
    write_eve(
        rt.config.eve_path,
        port_scan_burst(ATTACKER, rt.clock.now())
        + ssh_brute_burst(BRUTE_ATTACKER, rt.clock.now()),
    )

    result = run_cycle(rt)
    contain = [r for r in result.receipts if r["policy"]["decision"] == "execute"]
    hold = [r for r in result.receipts if r["policy"]["decision"] == "propose"]
    assert contain
    assert hold
    assert ATTACKER in rt.alias.list_members()
    assert BRUTE_ATTACKER not in rt.alias.list_members()
    assert result.plane is not None
    assert result.plane["drain"]["drained"] >= 1
    assert fake_auditor.creates >= 1
    assert rt.watches.open_watches()

    propose = hold[0]
    with pytest.raises(WaitingOnPlaneError):
        local_resolve(rt, propose["receipt_id"], "approved")
    assert BRUTE_ATTACKER not in rt.alias.list_members()

    incident_id = rt.incidents.find_by_receipt(propose["receipt_id"])
    assert incident_id
    with pytest.raises(PlaneUpMintError):
        mint_local(
            store=rt.grants,
            incidents=rt.incidents,
            site_id=rt.config.site_id,
            incident_id=incident_id,
            ticket_id="t-plane",
            notes="must not mint while plane is up",
            reason_redacted="plane-up mint is plane-resolved",
            asks=build_asks(tools=["notify.operator"]),
            profile="break_glass",
            ttl_s=1800,
            now=rt.clock.now(),
            plane_reachable=True,
        )

    body = build_propose_body(
        site_id=rt.config.site_id,
        incident_id=incident_id,
        reason_redacted="plane mocked propose",
        asks=build_asks(tools=["notify.operator"]),
        profile="ir_elevated",
        ttl_s=3600,
        now=rt.clock.now(),
    )
    created = rt.grant_client.propose(body)
    assert created["grant_id"]
    assert fake_grants.proposes == 1

    payload = build_status(rt.config, now=rt.clock.now())
    assert payload["site_id"] == "net-tn-cottage"
    assert payload["plane_reachable"] is True
    assert payload["receipts"]["count"] >= 2
