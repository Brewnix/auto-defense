"""Mock Panopticon #41 sell_state + Brewnix staleness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aimmune.clock import FrozenClock
from aimmune.plane.posture import is_stale, map_receipt_sell_state, pause_result_success
from tests.plane_fake import FakePlane

DEVICE = "jetson-cottage-01"


def test_get_device_copies_host_sell_state() -> None:
    fake = FakePlane()
    fake.set_device(DEVICE, sell_state="paused")
    client = fake.posture_client()
    posture = client.get_device(DEVICE)
    assert posture.sell_state == "paused"
    assert posture.stale is False
    assert posture.receipt_sell_state == "paused"
    assert fake.device_gets == 1


def test_stale_heartbeat_is_unknown() -> None:
    now = datetime(2026, 9, 8, 21, 10, 0, tzinfo=timezone.utc)
    old = (now - timedelta(seconds=301)).isoformat().replace("+00:00", "Z")
    fake = FakePlane()
    fake.set_device(DEVICE, sell_state="paused", last_heartbeat_at=old)
    client = fake.posture_client(stale_s=300, clock=FrozenClock(now))
    posture = client.get_device(DEVICE)
    assert posture.stale is True
    assert posture.effective_sell_state is None
    assert posture.receipt_sell_state == "n/a"


def test_fresh_heartbeat_not_stale() -> None:
    now = datetime(2026, 9, 8, 21, 10, 0, tzinfo=timezone.utc)
    hb = (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    assert is_stale(hb, now=now, stale_s=300) is False


def test_map_receipt_sell_state() -> None:
    assert map_receipt_sell_state("selling") == "on"
    assert map_receipt_sell_state("draining") == "paused"
    assert map_receipt_sell_state("off") == "off"
    assert map_receipt_sell_state(None) == "n/a"


def test_pause_success_rules() -> None:
    assert pause_result_success({"passed": True, "sell_state": "paused"})
    assert pause_result_success({"passed": True, "sell_state": "draining"})
    assert pause_result_success({"passed": True, "sell_state": "off"})
    assert not pause_result_success({"passed": True, "sell_state": "selling"})
    assert not pause_result_success({"passed": True, "sell_state": "n/a"})
    assert not pause_result_success({"passed": False, "sell_state": "paused"})
