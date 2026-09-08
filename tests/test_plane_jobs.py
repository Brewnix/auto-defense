"""Mock Panopticon #40 site jobs — lease_id required, enqueue ≠ apply."""

from __future__ import annotations

import pytest

from aimmune.plane.jobs import JobsError, SiteJobsClient
from tests.plane_fake import FakePlane

DEVICE = "jetson-cottage-01"
LEASE = "lease-203-0-113-50"


def test_enqueue_sell_pause_and_poll() -> None:
    fake = FakePlane()
    client = fake.jobs_client()
    job = client.enqueue_sell_pause(device_id=DEVICE)
    assert job["kind"] == "sell_pause"
    assert job["device_id"] == DEVICE
    assert job["passed"] is True
    assert job["sell_state"] == "paused"
    polled = client.get_job(job["job_id"])
    assert polled["job_id"] == job["job_id"]
    assert fake.enqueue_order == [f"sell_pause:{DEVICE}"]


def test_lease_stop_requires_lease_id_client_side() -> None:
    fake = FakePlane()
    client = fake.jobs_client()
    with pytest.raises(JobsError, match="lease_id") as exc:
        client.enqueue_lease_stop(device_id=DEVICE, lease_id="")
    assert exc.value.status_code == 422
    assert fake.posts == 0


def test_lease_stop_plane_rejects_missing_lease_id() -> None:
    fake = FakePlane()
    # Bypass client-side check to prove the door.
    raw = SiteJobsClient(
        "https://panopticon.test",
        fake.token,
        transport=fake.transport,
    )
    with pytest.raises(JobsError) as exc:
        raw._request(
            "POST",
            "/api/v1/hypermesh/site/jobs",
            json={"kind": "lease_stop", "device_id": DEVICE},
        )
    assert exc.value.status_code == 422


def test_does_not_send_reason_code() -> None:
    fake = FakePlane()
    client = fake.jobs_client()
    job = client.enqueue_lease_stop(device_id=DEVICE, lease_id=LEASE)
    stored = fake.jobs[job["job_id"]]
    assert "reason_code" not in stored
    assert stored["lease_id"] == LEASE


def test_device_id_required() -> None:
    fake = FakePlane()
    client = fake.jobs_client()
    with pytest.raises(JobsError, match="device_id"):
        client.enqueue_sell_pause(device_id="")


def test_await_job_timeout_on_pending() -> None:
    fake = FakePlane()
    fake.pause_result = {"status": "pending", "passed": None, "sell_state": None}
    client = fake.jobs_client(poll_timeout_s=0.01, poll_interval_s=0.2)
    job = client.enqueue_sell_pause(device_id=DEVICE)
    with pytest.raises(JobsError, match="timeout"):
        client.await_job(job["job_id"], timeout_s=0.01, interval_s=0.2, sleeper=lambda _s: None)
