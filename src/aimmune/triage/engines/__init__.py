"""Ordered engine walk: mock (CI), optional ollama, PAIR stub."""

from aimmune.triage.engines.base import Engine, EngineResult
from aimmune.triage.engines.mock import MockEngine
from aimmune.triage.engines.pair import PairEngine

__all__ = [
    "Engine",
    "EngineResult",
    "MockEngine",
    "OllamaEngine",
    "PairEngine",
]


def __getattr__(name: str):
    if name == "OllamaEngine":
        from aimmune.triage.engines.ollama import OllamaEngine

        return OllamaEngine
    raise AttributeError(name)
