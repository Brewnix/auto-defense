"""H4 owner unix-socket client — plane-down path."""

from __future__ import annotations

from pathlib import Path

import pytest

from aimmune.host.owner import OwnerError
from tests.owner_fake import FakeOwner

DEVICE = "jetson-cottage-01"
LEASE = "lease-203-0-113-50"


def test_owner_sell_pause_and_lease_stop(tmp_path: Path) -> None:
    effects = tmp_path / "owner-effects.jsonl"
    fake = FakeOwner(effects_path=effects)
    client = fake.client()
    pause = client.sell_pause(device_id=DEVICE)
    assert pause["passed"] is True
    assert pause["sell_state"] == "paused"
    stop = client.lease_stop(lease_id=LEASE, device_id=DEVICE)
    assert stop["passed"] is True
    assert fake.calls == [f"sell_pause:{DEVICE}", f"lease_stop:{LEASE}"]
    lines = client.read_effects()
    assert lines[0]["kind"] == "sell_pause"
    assert lines[1]["kind"] == "lease_stop"


def test_owner_requires_ids() -> None:
    fake = FakeOwner()
    client = fake.client()
    with pytest.raises(OwnerError, match="device_id"):
        client.sell_pause(device_id="")
    with pytest.raises(OwnerError, match="lease_id"):
        client.lease_stop(lease_id="")
