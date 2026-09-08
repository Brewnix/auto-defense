"""In-process Panopticon #40 / #41 stand-in for httpx.MockTransport tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx

from aimmune.plane.jobs import SiteJobsClient
from aimmune.plane.posture import SitePostureClient

JOBS = "/api/v1/hypermesh/site/jobs"
DEVICES = "/api/v1/hypermesh/site/devices"


def _request_json(request: httpx.Request) -> dict[str, Any]:
    if not request.content:
        return {}
    payload = json.loads(request.content.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class FakePlane:
    """Site-token jobs + device posture. Enqueue ≠ apply."""

    def __init__(
        self,
        *,
        token: str = "hm_site_test",
        site_id: str = "net-tn-cottage",
    ) -> None:
        self.token = token
        self.site_id = site_id
        self.jobs: dict[str, dict[str, Any]] = {}
        self.devices: dict[str, dict[str, Any]] = {}
        self.enqueue_order: list[str] = []
        self.posts = 0
        self.gets = 0
        self.device_gets = 0
        self.down = False
        self.pause_result: dict[str, Any] = {
            "status": "passed",
            "passed": True,
            "sell_state": "paused",
        }
        self.stop_result: dict[str, Any] = {"status": "passed", "passed": True}
        self.transport = httpx.MockTransport(self.handler)

    def set_device(
        self,
        device_id: str,
        *,
        sell_state: str = "selling",
        last_heartbeat_at: str | None = None,
        site_id: str | None = None,
    ) -> None:
        self.devices[device_id] = {
            "device_id": device_id,
            "site_id": site_id or self.site_id,
            "sell_state": sell_state,
            "last_heartbeat_at": last_heartbeat_at or _rfc3339(),
        }

    def jobs_client(self, **kwargs) -> SiteJobsClient:
        return SiteJobsClient(
            "https://panopticon.test",
            self.token,
            transport=self.transport,
            **kwargs,
        )

    def posture_client(self, **kwargs) -> SitePostureClient:
        return SitePostureClient(
            "https://panopticon.test",
            self.token,
            transport=self.transport,
            **kwargs,
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("plane down")
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return httpx.Response(401, json={"error": "unauthorized"})
        path = urlparse(str(request.url)).path
        method = request.method.upper()
        if method == "POST" and path.rstrip("/") == JOBS:
            return self._enqueue(request)
        if method == "GET" and path.startswith(JOBS + "/"):
            return self._get_job(path[len(JOBS) + 1 :])
        if method == "GET" and path.startswith(DEVICES + "/"):
            return self._get_device(path[len(DEVICES) + 1 :])
        return httpx.Response(404, json={"error": "not found"})

    def _enqueue(self, request: httpx.Request) -> httpx.Response:
        self.posts += 1
        body = _request_json(request)
        kind = body.get("kind")
        device_id = body.get("device_id")
        if kind not in {"sell_pause", "lease_stop"}:
            return httpx.Response(422, json={"error": "unknown kind"})
        if not device_id:
            return httpx.Response(422, json={"error": "device_id required"})
        if kind == "lease_stop" and not body.get("lease_id"):
            return httpx.Response(422, json={"error": "lease_id required"})
        if "reason_code" in body:
            return httpx.Response(422, json={"error": "reason_code is not a job field"})
        job_id = str(uuid4())
        if kind == "sell_pause":
            result = dict(self.pause_result)
            self.enqueue_order.append(f"sell_pause:{device_id}")
        else:
            result = dict(self.stop_result)
            self.enqueue_order.append(f"lease_stop:{device_id}:{body.get('lease_id')}")
        job = {
            "job_id": job_id,
            "kind": kind,
            "device_id": device_id,
            "lease_id": body.get("lease_id"),
            "until": body.get("until"),
            "status": result.get("status") or "pending",
            "sell_state": result.get("sell_state"),
            "passed": result.get("passed"),
            "completed_at": _rfc3339() if result.get("status") in {"passed", "failed"} else None,
            "created_at": _rfc3339(),
            "image_hash": result.get("image_hash"),
        }
        self.jobs[job_id] = job
        if kind == "sell_pause" and result.get("sell_state") and device_id in self.devices:
            if result.get("passed") is True and result.get("sell_state") != "n/a":
                self.devices[device_id]["sell_state"] = result["sell_state"]
        return httpx.Response(200, json=job)

    def _get_job(self, job_id: str) -> httpx.Response:
        self.gets += 1
        job = self.jobs.get(job_id)
        if job is None:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=job)

    def _get_device(self, device_id: str) -> httpx.Response:
        self.device_gets += 1
        device = self.devices.get(device_id)
        if device is None:
            return httpx.Response(404, json={"error": "not found"})
        if device.get("site_id") != self.site_id:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=device)
