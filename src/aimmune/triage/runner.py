"""Cycle placement: after rules emit / before policy. Single winner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aimmune.canonical import features_digest, rfc3339
from aimmune.schema import SchemaValidationError, validate_envelope
from aimmune.triage.decide import (
    Winner,
    allow_model_execute,
    execute_allowlist,
    is_auto_execute,
    select_winner,
    should_call_model,
    strip_unknown_tools,
    subject_bind,
)
from aimmune.triage.engines.base import Engine, EngineResult
from aimmune.triage.engines.mock import MockEngine
from aimmune.triage.engines.pair import PairEngine
from aimmune.triage.eval_log import append_eval
from aimmune.triage.settings import EngineSpec, TriageSettings


def build_engines(specs: tuple[EngineSpec, ...] | list[EngineSpec]) -> list[Engine]:
    engines: list[Engine] = []
    for spec in specs:
        if spec.kind == "mock":
            engines.append(
                MockEngine(engine_id=spec.id, scenario=spec.scenario or "propose")
            )
        elif spec.kind == "ollama":
            from aimmune.triage.engines.ollama import OllamaEngine

            engines.append(
                OllamaEngine(
                    engine_id=spec.id,
                    url=spec.url or "http://127.0.0.1:11434",
                    model=spec.model,
                    timeout_s=spec.timeout_s,
                )
            )
        elif spec.kind == "pair":
            engines.append(PairEngine(engine_id=spec.id))
        else:
            continue
    return engines


def noop_repair(envelope: dict[str, Any]) -> dict[str, Any]:
    """≤1 repair hook. Default is a no-op (then fail → fallback)."""
    return envelope


def validate_model_envelope(
    envelope: dict[str, Any],
    pin: Path,
    *,
    repair=noop_repair,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        validate_envelope(envelope, pin)
        return envelope, None
    except SchemaValidationError:
        repaired = repair(envelope)
        try:
            validate_envelope(repaired, pin)
            return repaired, None
        except SchemaValidationError:
            return None, "schema_invalid"


def walk_engines(
    engines: list[Engine],
    bundle: dict[str, Any],
    *,
    site_id: str,
    observed_at: str,
    inputs_digest: str,
    rails_profile: str,
    allowlisted_tools: list[str],
    pin: Path,
    incident_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    last_failure = "engine_unavailable"
    last_id: str | None = None
    for engine in engines:
        result: EngineResult = engine.infer(
            bundle,
            site_id=site_id,
            observed_at=observed_at,
            inputs_digest=inputs_digest,
            rails_profile=rails_profile,
            allowlisted_tools=allowlisted_tools,
            incident_id=incident_id,
        )
        last_id = result.engine_id or getattr(engine, "id", None)
        if result.unavailable or result.envelope is None:
            last_failure = result.reason or "engine_unavailable"
            continue
        valid, err = validate_model_envelope(result.envelope, pin)
        if valid is None:
            last_failure = err or "schema_invalid"
            continue
        stripped = strip_unknown_tools(valid)
        try:
            validate_envelope(stripped, pin)
        except SchemaValidationError:
            last_failure = "schema_invalid"
            continue
        return stripped, None, last_id
    return None, last_failure, last_id


def apply_triage(
    *,
    rules_envelope: dict[str, Any],
    bundle: dict[str, Any],
    settings: TriageSettings,
    auto_rule_ids: frozenset[str],
    pin: Path,
    site_id: str,
    now,
    engines: list[Engine] | None,
    eval_path: Path | None = None,
    incident_id: str | None = None,
) -> Winner:
    """Decide call → walk engines → single winner. Auto-execute never reaches engines."""
    digest = bundle.get("_digest") or features_digest(
        {k: v for k, v in bundle.items() if k != "_digest"}
    )
    redacted = {k: v for k, v in bundle.items() if k != "_digest"}
    auto = is_auto_execute(rules_envelope, auto_rule_ids)
    call = should_call_model(
        rules_envelope,
        mode=settings.mode,
        enrich=settings.enrich,
        auto_rule_ids=auto_rule_ids,
    )
    model_env = None
    failure = None
    engine_id = None
    if call and engines:
        allow = sorted(
            execute_allowlist(settings.rails, now)
            or settings.rails.tool_allowlist
            or ()
        )
        model_env, failure, engine_id = walk_engines(
            engines,
            redacted,
            site_id=site_id,
            observed_at=rfc3339(now) if not isinstance(now, str) else now,
            inputs_digest=digest,
            rails_profile=settings.rails.profile,
            allowlisted_tools=list(allow),
            pin=pin,
            incident_id=incident_id,
        )
        if model_env is not None:
            model_env, violations = subject_bind(model_env, redacted, site_id=site_id)
            if violations:
                # Keep the envelope (stripped) if it still schemas; else fail.
                try:
                    validate_envelope(model_env, pin)
                except SchemaValidationError:
                    model_env = None
                    failure = "subject_bind"
    elif call and not engines:
        failure = "engine_unavailable"

    winner = select_winner(
        rules_envelope,
        model_env,
        failure,
        auto_rule=auto,
        now=now if not isinstance(now, str) else None,
    )
    if winner.source == "model":
        bound, violations = subject_bind(winner.envelope, redacted, site_id=site_id)
        winner.envelope = bound
        if violations:
            winner.envelope = strip_unknown_tools(bound)

    if eval_path is not None:
        append_eval(
            eval_path,
            ts=now,
            trace_id=str(winner.envelope.get("trace_id") or rules_envelope.get("trace_id")),
            winner=winner.source,
            engine_id=winner.engine_id or engine_id,
            failure=winner.failure or failure,
            inputs_digest=digest,
            allow_model_execute=allow_model_execute(settings.rails, now if not isinstance(now, str) else None),
            rules_actor_id=(rules_envelope.get("actor") or {}).get("id"),
            model_actor_id=(model_env.get("actor") or {}).get("id") if model_env else None,
            called_model=bool(call),
        )
    return winner
