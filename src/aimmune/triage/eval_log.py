"""Redacted triage eval pointer. No prompts, bundles, or envelope bodies."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from aimmune.canonical import rfc3339
from aimmune.store import append_jsonl, read_jsonl

FORBIDDEN = (
    "prompt",
    "prompts",
    "messages",
    "completion",
    "system",
    "eve",
    "payload",
    "packet",
    "chat",
)


def append_eval(
    path: Path,
    *,
    ts: datetime,
    trace_id: str,
    winner: str,
    engine_id: str | None,
    failure: str | None,
    inputs_digest: str,
    allow_model_execute: bool,
    rules_actor_id: str | None,
    model_actor_id: str | None,
    called_model: bool,
) -> dict[str, Any]:
    row = {
        "ts": rfc3339(ts) if not isinstance(ts, str) else ts,
        "trace_id": trace_id,
        "winner": winner,
        "engine_id": engine_id,
        "failure": failure,
        "inputs_digest": inputs_digest,
        "allow_model_execute": allow_model_execute,
        "rules_actor_id": rules_actor_id,
        "model_actor_id": model_actor_id,
        "called_model": called_model,
    }
    for key in FORBIDDEN:
        row.pop(key, None)
    append_jsonl(path, row)
    return row


def load_eval(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)
