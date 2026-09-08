"""In-process Host H4 owner socket stand-in."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from aimmune.host.owner import OwnerClient
from aimmune.store import append_jsonl


class FakeOwner:
    def __init__(self, *, token: str = "owner-token", effects_path=None) -> None:
        self.token = token
        self.effects_path = effects_path
        self.calls: list[str] = []
        self.pause_result: dict[str, Any] = {
            "passed": True,
            "sell_state": "paused",
            "device_id": None,
        }
        self.stop_result: dict[str, Any] = {"passed": True}
        self.down = False
        self.transport = httpx.MockTransport(self.handler)

    def client(self, effects_path=None, **kwargs) -> OwnerClient:
        return OwnerClient(
            "/tmp/owner.sock",
            self.token,
            transport=self.transport,
            effects_path=effects_path if effects_path is not None else self.effects_path,
            **kwargs,
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("owner down")
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.token}":
            return httpx.Response(401, json={"error": "unauthorized"})
        path = urlparse(str(request.url)).path
        body = {}
        if request.content:
            parsed = json.loads(request.content.decode("utf-8"))
            if isinstance(parsed, dict):
                body = parsed
        if request.method.upper() == "POST" and path == "/v0/sell_pause":
            if not body.get("device_id"):
                return httpx.Response(422, json={"error": "device_id required"})
            self.calls.append(f"sell_pause:{body['device_id']}")
            result = dict(self.pause_result)
            result["device_id"] = body["device_id"]
            if body.get("until"):
                result["until"] = body["until"]
            self._effect("sell_pause", result)
            return httpx.Response(200, json=result)
        if request.method.upper() == "POST" and path == "/v0/lease_stop":
            if not body.get("lease_id"):
                return httpx.Response(422, json={"error": "lease_id required"})
            self.calls.append(f"lease_stop:{body['lease_id']}")
            result = dict(self.stop_result)
            result["lease_id"] = body["lease_id"]
            self._effect("lease_stop", result)
            return httpx.Response(200, json=result)
        return httpx.Response(404, json={"error": "not found"})

    def _effect(self, kind: str, result: dict[str, Any]) -> None:
        if self.effects_path is None:
            return
        append_jsonl(self.effects_path, {"kind": kind, **result})
