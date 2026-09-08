"""Optional local Ollama HTTP adapter. CI must not require a live daemon."""

from __future__ import annotations

import json
from typing import Any

import httpx

from aimmune.triage.engines.base import EngineResult

# System text stays ephemeral — never written to receipts / eval-log / tickets.
_SYSTEM = (
    "You are a site-local judge. Reply with a single fyber.inference_iface/v0 "
    "JSON object. actor.kind must be model. Do not execute anything. "
    "Do not include prompts, EVE payloads, or packet captures."
)


class OllamaEngine:
    kind = "ollama"

    def __init__(
        self,
        *,
        engine_id: str,
        url: str = "http://127.0.0.1:11434",
        model: str | None = None,
        timeout_s: float = 3.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.id = engine_id
        self.url = url.rstrip("/")
        self.model = model or engine_id
        self.timeout_s = timeout_s
        self._client = client
        self.call_count = 0

    def infer(
        self,
        bundle: dict[str, Any],
        *,
        site_id: str,
        observed_at: str,
        inputs_digest: str,
        rails_profile: str,
        allowlisted_tools: list[str],
        incident_id: str | None = None,
    ) -> EngineResult:
        self.call_count += 1
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "bundle": bundle,
                            "site_id": site_id,
                            "observed_at": observed_at,
                            "inputs_digest": inputs_digest,
                            "rails_profile": rails_profile,
                            "allowlisted_tools": allowlisted_tools,
                            "incident_id": incident_id,
                        },
                        sort_keys=True,
                    ),
                },
            ],
        }
        try:
            client = self._client or httpx.Client(timeout=self.timeout_s)
            close = self._client is None
            try:
                response = client.post(f"{self.url}/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
            finally:
                if close:
                    client.close()
        except (httpx.HTTPError, json.JSONDecodeError, OSError, ValueError):
            return EngineResult.engine_unavailable(engine_id=self.id)
        content = ((body.get("message") or {}).get("content")) or body.get("response")
        if not content:
            return EngineResult.engine_unavailable(
                engine_id=self.id, reason="empty_response"
            )
        try:
            envelope = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            return EngineResult.engine_unavailable(
                engine_id=self.id, reason="schema_invalid"
            )
        if not isinstance(envelope, dict):
            return EngineResult.engine_unavailable(
                engine_id=self.id, reason="schema_invalid"
            )
        envelope.setdefault("inputs_digest", inputs_digest)
        envelope.setdefault("site_id", site_id)
        envelope.setdefault("observed_at", observed_at)
        actor = dict(envelope.get("actor") or {})
        actor.setdefault("kind", "model")
        actor.setdefault("id", self.id)
        actor.setdefault("purpose", "triage")
        envelope["actor"] = actor
        return EngineResult.ok(envelope, engine_id=self.id)


def ollama_reachable(url: str = "http://127.0.0.1:11434", timeout_s: float = 0.4) -> bool:
    try:
        response = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=timeout_s)
        return response.status_code < 500
    except httpx.HTTPError:
        return False
