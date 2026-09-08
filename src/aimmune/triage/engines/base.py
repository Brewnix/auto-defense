"""Engine interface: redacted bundle in → envelope or engine_unavailable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class EngineResult:
    envelope: dict[str, Any] | None = None
    unavailable: bool = False
    reason: str | None = None
    engine_id: str | None = None

    @classmethod
    def ok(cls, envelope: dict[str, Any], *, engine_id: str) -> EngineResult:
        return cls(envelope=envelope, engine_id=engine_id)

    @classmethod
    def engine_unavailable(cls, *, engine_id: str, reason: str = "engine_unavailable") -> EngineResult:
        return cls(unavailable=True, reason=reason, engine_id=engine_id)


class Engine(Protocol):
    id: str
    kind: str
    call_count: int

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
    ) -> EngineResult: ...
