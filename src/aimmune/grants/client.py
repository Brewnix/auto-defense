"""fyber.privilege_grant site client — propose / get / list only.

Resolve and revoke are plane-only (human / timeout worker). This client
must never POST ``/resolve`` or ``/revoke``. Plane mint is SoT when up;
the site cache is SoT for ``active_until`` if the plane drops.
"""

from __future__ import annotations

from typing import Any

import httpx

GRANTS_PATH = "/api/v1/grants/v0/grants"
DEFAULT_TIMEOUT_S = 3.0


class GrantError(RuntimeError):
    pass


class GrantClient:
    """Site-token client for Panopticon #50 privilege grants.

    Does **not** implement resolve or revoke. Plane owns minting.
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
            raise GrantError("PANOPTICON_BASE_URL is required")
        if not token:
            raise GrantError("HM_SITE_TOKEN is required")
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

    def __enter__(self) -> GrantClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def propose(
        self,
        body: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        payload = self._request("POST", GRANTS_PATH, json=body, headers=headers)
        if not isinstance(payload, dict):
            raise GrantError("grant propose unexpected body")
        return payload

    def get_grant(self, grant_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"{GRANTS_PATH}/{grant_id}")
        if not isinstance(payload, dict):
            raise GrantError("grant get unexpected body")
        return payload

    def list_grants(
        self,
        *,
        status: str | None = None,
        incident_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if incident_id:
            params["incident_id"] = incident_id
        payload = self._request("GET", GRANTS_PATH, params=params)
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            rows = payload.get("grants") or payload.get("items") or []
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        raise GrantError("grant list unexpected body")

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = self._http.request(
                method, path, json=json, params=params, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise GrantError(f"grant timeout {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise GrantError(f"grant unreachable {method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise GrantError(f"grant HTTP {response.status_code} {method} {path}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise GrantError(f"grant invalid JSON {method} {path}") from exc
