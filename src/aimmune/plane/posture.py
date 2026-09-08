"""Panopticon #41 site device sell_state + Brewnix staleness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from aimmune.clock import Clock

DEVICES_PATH = "/api/v1/hypermesh/site/devices"
DEFAULT_TIMEOUT_S = 3.0
HOST_SELL_STATES = frozenset({"selling", "paused", "draining", "off", "n/a"})
PAUSE_SUCCESS_STATES = frozenset({"paused", "draining", "off"})
STOP_ONLY_OK_STATES = frozenset({"paused", "off", "n/a"})
RECEIPT_SELL_STATES = frozenset({"off", "on", "paused", "n/a"})


class PostureError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DevicePosture:
    device_id: str
    site_id: str | None
    sell_state: str | None
    last_heartbeat_at: str | None
    stale: bool

    @property
    def known(self) -> bool:
        return not self.stale and self.sell_state is not None

    @property
    def effective_sell_state(self) -> str | None:
        """Host-reported sell_state, or None when stale / unknown."""
        if self.stale:
            return None
        return self.sell_state

    @property
    def receipt_sell_state(self) -> str:
        return map_receipt_sell_state(self.effective_sell_state)


def parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_stale(
    last_heartbeat_at: str | None,
    *,
    now: datetime,
    stale_s: int,
) -> bool:
    parsed = parse_rfc3339(last_heartbeat_at)
    if parsed is None:
        return True
    return now - parsed > timedelta(seconds=stale_s)


def map_receipt_sell_state(host_state: str | None) -> str:
    """Copy Host posture onto fyber.receipt/v0 (no ``selling`` / ``draining``)."""
    if host_state in {None, ""}:
        return "n/a"
    mapping = {
        "selling": "on",
        "paused": "paused",
        "draining": "paused",
        "off": "off",
        "n/a": "n/a",
        "on": "on",
    }
    return mapping.get(str(host_state), "n/a")


def pause_result_success(result: dict[str, Any]) -> bool:
    """``passed=true`` and Host ``sell_state`` ∈ {paused, draining, off}.

    ``selling`` is not success. ``passed=true`` + ``n/a`` is invalid.
    """
    if result.get("passed") is not True:
        return False
    state = result.get("sell_state")
    if state == "n/a":
        return False
    return state in PAUSE_SUCCESS_STATES


class SitePostureClient:
    """Site-token ``GET /api/v1/hypermesh/site/devices/{device_id}``."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        stale_s: int = 300,
        transport: httpx.BaseTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not base_url:
            raise PostureError("PANOPTICON_BASE_URL is required")
        if not token:
            raise PostureError("HM_SITE_TOKEN is required")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.stale_s = stale_s
        self.clock = clock or Clock()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SitePostureClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_device(self, device_id: str) -> DevicePosture:
        if not device_id or not str(device_id).strip():
            raise PostureError("device_id is required", status_code=422)
        payload = self._request("GET", f"{DEVICES_PATH}/{device_id}")
        sell_state = payload.get("sell_state")
        if sell_state not in HOST_SELL_STATES:
            sell_state = None
        last_hb = payload.get("last_heartbeat_at")
        stale = is_stale(last_hb if isinstance(last_hb, str) else None, now=self.clock.now(), stale_s=self.stale_s)
        return DevicePosture(
            device_id=str(payload.get("device_id") or device_id),
            site_id=payload.get("site_id") if isinstance(payload.get("site_id"), str) else None,
            sell_state=sell_state if isinstance(sell_state, str) else None,
            last_heartbeat_at=last_hb if isinstance(last_hb, str) else None,
            stale=stale,
        )

    def _request(self, method: str, path: str) -> dict[str, Any]:
        try:
            response = self._http.request(method, path)
        except httpx.TimeoutException as exc:
            raise PostureError(f"posture timeout {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise PostureError(f"posture unreachable {method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise PostureError(
                f"posture HTTP {response.status_code} {method} {path}",
                status_code=response.status_code,
            )
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise PostureError(f"posture invalid JSON {method} {path}") from exc
        if not isinstance(payload, dict):
            raise PostureError(f"posture unexpected body {method} {path}")
        return payload
