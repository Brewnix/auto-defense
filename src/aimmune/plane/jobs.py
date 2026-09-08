"""Panopticon #40 site jobs client — enqueue + poll. Enqueue ≠ apply."""

from __future__ import annotations

from typing import Any

import httpx

from aimmune.clock import Clock

SITE_JOBS_PATH = "/api/v1/hypermesh/site/jobs"
ALLOWED_KINDS = frozenset({"sell_pause", "lease_stop"})
TERMINAL = frozenset({"passed", "failed"})
DEFAULT_TIMEOUT_S = 3.0
DEFAULT_POLL_TIMEOUT_S = 30.0
DEFAULT_POLL_INTERVAL_S = 0.2


class JobsError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SiteJobsClient:
    """Site-token client for ``POST``/``GET /api/v1/hypermesh/site/jobs``.

    ``lease_id`` is required on ``lease_stop`` (no omit-for-active). Do not
    send ``reason_code`` — that stays on the envelope / receipt.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        poll_timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        transport: httpx.BaseTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not base_url:
            raise JobsError("PANOPTICON_BASE_URL is required")
        if not token:
            raise JobsError("HM_SITE_TOKEN is required")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.poll_timeout_s = poll_timeout_s
        self.poll_interval_s = poll_interval_s
        self.clock = clock or Clock()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SiteJobsClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def enqueue_sell_pause(
        self,
        *,
        device_id: str,
        until: str | None = None,
    ) -> dict[str, Any]:
        if not device_id or not str(device_id).strip():
            raise JobsError("device_id is required on sell_pause", status_code=422)
        body: dict[str, Any] = {"kind": "sell_pause", "device_id": str(device_id)}
        if until:
            body["until"] = until
        return self._request("POST", SITE_JOBS_PATH, json=body)

    def enqueue_lease_stop(self, *, device_id: str, lease_id: str) -> dict[str, Any]:
        if not device_id or not str(device_id).strip():
            raise JobsError("device_id is required on lease_stop", status_code=422)
        if not lease_id or not str(lease_id).strip():
            raise JobsError(
                "lease_id is required on lease_stop (no omit-for-active)",
                status_code=422,
            )
        return self._request(
            "POST",
            SITE_JOBS_PATH,
            json={
                "kind": "lease_stop",
                "device_id": str(device_id),
                "lease_id": str(lease_id),
            },
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        if not job_id:
            raise JobsError("job_id is required")
        return self._request("GET", f"{SITE_JOBS_PATH}/{job_id}")

    def await_job(
        self,
        job_id: str,
        *,
        timeout_s: float | None = None,
        interval_s: float | None = None,
        sleeper=None,
    ) -> dict[str, Any]:
        """Poll until Host reports ``passed`` / ``failed``. Enqueue is not apply."""
        limit = self.poll_timeout_s if timeout_s is None else timeout_s
        interval = self.poll_interval_s if interval_s is None else interval_s
        sleep = sleeper or _default_sleep
        started = self.clock.now()
        last: dict[str, Any] = {}
        polls = 0
        max_polls = max(1, int(limit / interval) + 1) if interval else 1
        while True:
            last = self.get_job(job_id)
            status = last.get("status")
            if status in TERMINAL:
                return last
            polls += 1
            elapsed = (self.clock.now() - started).total_seconds()
            if elapsed >= limit or polls >= max_polls:
                raise JobsError(f"job {job_id} poll timeout after {limit}s")
            sleep(interval)

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise JobsError(f"jobs timeout {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise JobsError(f"jobs unreachable {method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise JobsError(
                f"jobs HTTP {response.status_code} {method} {path}",
                status_code=response.status_code,
            )
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise JobsError(f"jobs invalid JSON {method} {path}") from exc
        if not isinstance(payload, dict):
            raise JobsError(f"jobs unexpected body {method} {path}")
        return payload


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
