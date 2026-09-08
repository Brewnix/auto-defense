"""Host H4 owner-console client — unix socket, plane-down execute.

Talks to ``$HOST_STATE_DIR/owner.sock`` with bearer
``$HOST_STATE_DIR/owner.token`` (Host writes the token **0600**). Reuses
H1/H2 actuators. Does **not** enqueue CP jobs. Effects land in
``owner-effects.jsonl`` (Host log — not ``fyber.receipt``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from aimmune.store import read_jsonl

DEFAULT_TIMEOUT_S = 3.0
SELL_PAUSE_PATH = "/v0/sell_pause"
LEASE_STOP_PATH = "/v0/lease_stop"


class OwnerError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def read_owner_token(path: Path) -> str:
    if not path.is_file():
        raise OwnerError(f"owner token missing: {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise OwnerError(f"owner token empty: {path}")
    return token


class OwnerClient:
    """H4 ``POST /v0/sell_pause`` and ``POST /v0/lease_stop`` over unix socket."""

    def __init__(
        self,
        sock_path: Path | str,
        token: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        effects_path: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not sock_path:
            raise OwnerError("owner.sock path is required")
        if not token:
            raise OwnerError("owner.token is required")
        self.sock_path = Path(sock_path)
        self.effects_path = effects_path
        self.timeout_s = timeout_s
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if transport is None:
            transport = httpx.HTTPTransport(uds=str(self.sock_path))
        self._http = httpx.Client(
            base_url="http://owner",
            headers=headers,
            timeout=timeout_s,
            transport=transport,
        )

    @classmethod
    def from_host_state(
        cls,
        host_state_dir: Path,
        *,
        sock_path: Path | None = None,
        token_path: Path | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> OwnerClient:
        sock = sock_path or host_state_dir / "owner.sock"
        token = read_owner_token(token_path or host_state_dir / "owner.token")
        return cls(
            sock,
            token,
            timeout_s=timeout_s,
            effects_path=host_state_dir / "owner-effects.jsonl",
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OwnerClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def sell_pause(
        self,
        *,
        device_id: str,
        until: str | None = None,
    ) -> dict[str, Any]:
        if not device_id or not str(device_id).strip():
            raise OwnerError("device_id is required on sell_pause", status_code=422)
        body: dict[str, Any] = {"device_id": str(device_id)}
        if until:
            body["until"] = until
        return self._request("POST", SELL_PAUSE_PATH, json=body)

    def lease_stop(self, *, lease_id: str, device_id: str | None = None) -> dict[str, Any]:
        if not lease_id or not str(lease_id).strip():
            raise OwnerError(
                "lease_id is required on lease_stop (no omit-for-active)",
                status_code=422,
            )
        body: dict[str, Any] = {"lease_id": str(lease_id)}
        if device_id:
            body["device_id"] = str(device_id)
        return self._request("POST", LEASE_STOP_PATH, json=body)

    def read_effects(self) -> list[dict[str, Any]]:
        if self.effects_path is None:
            return []
        return read_jsonl(self.effects_path)

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise OwnerError(f"owner timeout {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise OwnerError(f"owner unreachable {method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise OwnerError(
                f"owner HTTP {response.status_code} {method} {path}",
                status_code=response.status_code,
            )
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise OwnerError(f"owner invalid JSON {method} {path}") from exc
        if not isinstance(payload, dict):
            raise OwnerError(f"owner unexpected body {method} {path}")
        return payload
