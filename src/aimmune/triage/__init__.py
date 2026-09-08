"""Judge-only model triage (slice 6). LLM never sits in the executor path."""

from aimmune.triage.decide import (
    allow_model_execute,
    is_auto_execute,
    select_winner,
    should_call_model,
    strip_unknown_tools,
    subject_bind,
)
from aimmune.triage.runner import apply_triage, build_engines
from aimmune.triage.settings import (
    ConfigError,
    EngineSpec,
    RailsStub,
    TriageSettings,
    parse_triage_settings,
    profile_catalog,
)

__all__ = [
    "ConfigError",
    "EngineSpec",
    "RailsStub",
    "TriageSettings",
    "allow_model_execute",
    "apply_triage",
    "build_engines",
    "is_auto_execute",
    "parse_triage_settings",
    "profile_catalog",
    "select_winner",
    "should_call_model",
    "strip_unknown_tools",
    "subject_bind",
]
