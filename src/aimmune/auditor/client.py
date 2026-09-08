"""fyber.auditor site client — create / get / ack only.

Resolve is plane-only (human / timeout worker). This client must never POST
``/resolve``. Tickets are intent; actuation SoT is the site receipt.
"""

from __future__ import annotations

from typing import Any

import httpx

TICKETS_PATH = "/api/v1/auditor/v0/tickets"
DEFAULT_TIMEOUT_S = 3.0


class AuditorError(RuntimeError):
    pass


class AuditorClient:
    """Site-token client for Panopticon #39 auditor tickets.

    Does **not** implement resolve. Plane owns ``timed_out`` and human resolve.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise AuditorError("PANOPTICON_BASE_URL is required")
        if not token:
            raise AuditorError("HM_SITE_TOKEN is required")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
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

    def __enter__(self) -> AuditorClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def create_ticket(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", TICKETS_PATH, json=body)

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        return self._request("GET", f"{TICKETS_PATH}/{ticket_id}")

    def ack_ticket(self, ticket_id: str, receipt_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{TICKETS_PATH}/{ticket_id}/ack",
            json={"receipt_id": receipt_id},
        )

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise AuditorError(f"auditor timeout {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise AuditorError(f"auditor unreachable {method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise AuditorError(f"auditor HTTP {response.status_code} {method} {path}")
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise AuditorError(f"auditor invalid JSON {method} {path}") from exc
        if not isinstance(payload, dict):
            raise AuditorError(f"auditor unexpected body {method} {path}")
        return payload
