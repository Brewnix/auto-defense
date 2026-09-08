"""Ollama adapter is optional. Live daemon is skipped when unreachable."""

from __future__ import annotations

import json

import httpx
import pytest

from aimmune.triage.engines.ollama import OllamaEngine, ollama_reachable


def test_ollama_http_parses_envelope(pin) -> None:
    envelope = {
        "schema": "fyber.inference_iface/v0",
        "trace_id": "550e8400-e29b-41d4-a716-4466554400a0",
        "site_id": "net-tn-cottage",
        "actor": {
            "kind": "model",
            "id": "qwen2.5-7b-q4",
            "purpose": "triage",
        },
        "observed_at": "2026-09-08T21:00:00Z",
        "inputs_digest": "sha256:" + ("a" * 64),
        "judgment": {
            "severity": "high",
            "classes": ["brute_force"],
            "subjects": [{"kind": "ip", "value": "203.0.113.50"}],
            "summary": "ollama fixture",
            "evidence_refs": ["eve:window"],
        },
        "proposals": [],
        "confidence": 0.7,
        "needs_human": True,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200, json={"message": {"content": json.dumps(envelope)}}
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    engine = OllamaEngine(engine_id="qwen2.5-7b-q4", client=client)
    result = engine.infer(
        {"top_subjects": [], "counts": {"by_src": {}}, "prior_blocks": []},
        site_id="net-tn-cottage",
        observed_at="2026-09-08T21:00:00Z",
        inputs_digest="sha256:" + ("a" * 64),
        rails_profile="strict",
        allowlisted_tools=["notify.operator"],
    )
    assert result.envelope is not None
    assert result.envelope["actor"]["kind"] == "model"
    from aimmune.schema import validate_envelope

    validate_envelope(result.envelope, pin)


def test_ollama_down_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = OllamaEngine(engine_id="qwen", client=client, timeout_s=0.2)
    result = engine.infer(
        {},
        site_id="net-tn-cottage",
        observed_at="2026-09-08T21:00:00Z",
        inputs_digest="sha256:" + ("b" * 64),
        rails_profile="strict",
        allowlisted_tools=[],
    )
    assert result.unavailable is True
    assert result.reason == "engine_unavailable"


@pytest.mark.skipif(not ollama_reachable(), reason="ollama unreachable (optional)")
def test_live_ollama_optional() -> None:
    engine = OllamaEngine(engine_id="qwen2.5:7b", timeout_s=2.0)
    result = engine.infer(
        {
            "window_s": 300,
            "counts": {"alert_total": 0, "by_sid": {}, "by_src": {}},
            "top_subjects": [],
            "health": {
                "cpu": 0.1,
                "disk": 0.1,
                "wan_gateways": ["up"],
                "suricata": "running",
            },
            "whitelist_hits": 0,
            "prior_blocks": [],
        },
        site_id="net-tn-cottage",
        observed_at="2026-09-08T21:00:00Z",
        inputs_digest="sha256:" + ("c" * 64),
        rails_profile="strict",
        allowlisted_tools=["notify.operator"],
    )
    assert result.unavailable or result.envelope is not None
