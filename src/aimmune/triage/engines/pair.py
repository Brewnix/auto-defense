"""PAIR stub: always engine_unavailable. No PAIR install in this slice."""

from __future__ import annotations

from typing import Any

from aimmune.triage.engines.base import EngineResult


class PairEngine:
    kind = "pair"

    def __init__(self, *, engine_id: str = "pair-local") -> None:
        self.id = engine_id
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
        _ = (bundle, site_id, observed_at, inputs_digest, rails_profile, allowlisted_tools, incident_id)
        self.call_count += 1
        return EngineResult.engine_unavailable(engine_id=self.id, reason="engine_unavailable")
