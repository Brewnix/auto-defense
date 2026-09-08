from __future__ import annotations

import json

from aimmune.exec.opnsense_alias import MockAliasStore, OpnsenseAliasClient


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeOpener:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes | None]] = []

    def open(self, req, timeout=None):  # noqa: ANN001
        body = req.data
        self.calls.append((req.get_method(), req.full_url, body))
        if "/list/" in req.full_url:
            return _FakeResponse({"rows": [{"ip": "203.0.113.50"}]})
        return _FakeResponse({"status": "done"})


def test_mock_alias_add_delete() -> None:
    store = MockAliasStore()
    store.add("203.0.113.50")
    assert store.list_members() == ["203.0.113.50"]
    store.delete("203.0.113.50")
    assert store.list_members() == []


def test_opnsense_client_alias_util_paths() -> None:
    opener = _FakeOpener()
    client = OpnsenseAliasClient(
        "https://opnsense.example",
        "key",
        "secret",
        verify=False,
        opener=opener,
    )
    client.add("203.0.113.50", "ai_autoblock")
    client.delete("203.0.113.50", "ai_autoblock")
    assert client.list_members("ai_autoblock") == ["203.0.113.50"]
    urls = [c[1] for c in opener.calls]
    assert any("/api/firewall/alias_util/add/ai_autoblock" in u for u in urls)
    assert any("/api/firewall/alias_util/delete/ai_autoblock" in u for u in urls)
    assert json.loads(opener.calls[0][2].decode()) == {"address": "203.0.113.50"}
