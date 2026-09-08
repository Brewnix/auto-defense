"""Thin OPNsense alias_util client (add/delete, no full ruleset reload)."""

from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
from typing import Protocol
from urllib.parse import quote

DEFAULT_ALIAS = "ai_autoblock"


class AliasError(RuntimeError):
    pass


class AliasStore(Protocol):
    def add(self, address: str, alias: str = DEFAULT_ALIAS) -> None: ...
    def delete(self, address: str, alias: str = DEFAULT_ALIAS) -> None: ...
    def list_members(self, alias: str = DEFAULT_ALIAS) -> list[str]: ...


class MockAliasStore:
    """In-memory alias table for tests and AIMMUNE_EXEC_MOCK=1."""

    def __init__(self, members: set[str] | None = None) -> None:
        self._tables: dict[str, set[str]] = {DEFAULT_ALIAS: set(members or [])}

    def add(self, address: str, alias: str = DEFAULT_ALIAS) -> None:
        self._tables.setdefault(alias, set()).add(address)

    def delete(self, address: str, alias: str = DEFAULT_ALIAS) -> None:
        self._tables.setdefault(alias, set()).discard(address)

    def list_members(self, alias: str = DEFAULT_ALIAS) -> list[str]:
        return sorted(self._tables.get(alias, set()))


class OpnsenseAliasClient:
    """POST /api/firewall/alias_util/{add,delete}/<alias> with {address}."""

    def __init__(
        self,
        base_url: str,
        key: str,
        secret: str,
        *,
        verify: bool = True,
        opener: object | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
        self._auth = f"Basic {token}"
        self.verify = verify
        self._opener = opener

    def add(self, address: str, alias: str = DEFAULT_ALIAS) -> None:
        self._post(f"/api/firewall/alias_util/add/{quote(alias, safe='')}", address)

    def delete(self, address: str, alias: str = DEFAULT_ALIAS) -> None:
        self._post(f"/api/firewall/alias_util/delete/{quote(alias, safe='')}", address)

    def list_members(self, alias: str = DEFAULT_ALIAS) -> list[str]:
        payload = self._request(
            "GET", f"/api/firewall/alias_util/list/{quote(alias, safe='')}"
        )
        return _parse_members(payload)

    def _post(self, path: str, address: str) -> None:
        payload = self._request("POST", path, {"address": address})
        if isinstance(payload, dict):
            status = str(payload.get("status", "done")).lower()
            if status not in {"done", "ok", "success", ""}:
                raise AliasError(f"alias_util {path} status={status}: {payload}")

    def _request(
        self, method: str, path: str, body: dict[str, str] | None = None
    ) -> object:
        url = self.base_url + path
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        context: ssl.SSLContext | None
        if url.startswith("https://") and not self.verify:
            context = ssl._create_unverified_context()
        elif url.startswith("https://"):
            context = ssl.create_default_context()
        else:
            context = None
        try:
            if self._opener is not None:
                handle = self._opener.open(req, timeout=15)
            else:
                handle = urllib.request.urlopen(req, timeout=15, context=context)
            with handle as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise AliasError(f"HTTP {exc.code} {path}") from exc
        except urllib.error.URLError as exc:
            raise AliasError(f"alias_util unreachable {path}: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}


def _parse_members(payload: object) -> list[str]:
    rows: list[object]
    if isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("items") or payload.get("data") or []
        if not rows and isinstance(payload.get("addresses"), list):
            rows = payload["addresses"]
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    members: list[str] = []
    for row in rows:
        if isinstance(row, str):
            members.append(row)
        elif isinstance(row, dict):
            addr = row.get("ip") or row.get("address") or row.get("name")
            if addr:
                members.append(str(addr))
    return members


def build_alias_store(
    *,
    exec_mock: bool,
    url: str | None,
    key: str | None,
    secret: str | None,
    verify: bool = True,
) -> AliasStore:
    if exec_mock or not url:
        return MockAliasStore()
    if not key or not secret:
        raise AliasError("OPNsense key/secret required when AIMMUNE_OPNSENSE_URL is set")
    return OpnsenseAliasClient(url, key, secret, verify=verify)
