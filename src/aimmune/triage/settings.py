"""Triage site config. Docs-first — not a schema field. Default off."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_MODES = frozenset({"rules_only", "rules_primary", "model_assist"})
CUT_MODES = frozenset({"model_primary"})
VALID_ENGINE_KINDS = frozenset({"mock", "ollama", "pair"})
LOCAL_TIERS = frozenset({"local_small", "local_large"})
GRANT_TIERS = frozenset({"plane_ir", "host_leased"})
VALID_TIERS = LOCAL_TIERS | GRANT_TIERS
VALID_PROFILES = frozenset({"strict", "ir_elevated", "break_glass"})
VALID_FAILURE = frozenset({"fallback"})
CUT_FAILURE = frozenset({"fail_open_execute", "execute_last_rules"})

BASELINE_TOOLS = frozenset(
    {"firewall.block_ip", "firewall.unblock_ip", "notify.operator"}
)
IR_ELEVATED_EXTRA = frozenset({"health.restart_service", "ids.suricata_pass"})
HYPERMESH_TOOLS = frozenset({"hypermesh.lease_stop", "hypermesh.sell_pause"})

DEFAULT_THETA = 0.6
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_TIMEOUT_S = 3.0
DEFAULT_MOCK_ID = "mock-engine"
DEFAULT_PAIR_ID = "pair-local"


class ConfigError(ValueError):
    """Invalid triage / rails stub configuration."""


@dataclass(frozen=True)
class EngineSpec:
    kind: str
    id: str
    tier: str = "local_small"
    scenario: str | None = None
    url: str | None = None
    model: str | None = None
    timeout_s: float = DEFAULT_OLLAMA_TIMEOUT_S


@dataclass(frozen=True)
class RailsStub:
    """Deprecated test-only rails override. Privilege grants are SoT.

    ``AIMMUNE_RAILS_GRANT_*`` may still inject an elevation for pytest
    fixtures. Setting ``profile`` to ``ir_elevated`` / ``break_glass``
    without ``grant_active`` does **not** elevate. After ``active_until``
    the stub is treated as expired (strict).
    """

    profile: str = "strict"
    grant_active: bool = False
    active_until: datetime | None = None
    tool_allowlist: tuple[str, ...] = ()


@dataclass(frozen=True)
class TriageSettings:
    mode: str = "rules_only"
    default_tier: str = "local_small"
    enrich: bool = False
    confidence_theta: float = DEFAULT_THETA
    engines: tuple[EngineSpec, ...] = ()
    on_model_failure: str = "fallback"
    rails: RailsStub = RailsStub()

    @property
    def engines_configured(self) -> bool:
        return bool(self.engines)


def profile_catalog(profile: str, *, extra_allowlist: tuple[str, ...] = ()) -> frozenset[str]:
    """Execute-eligible catalog for an elevated stub. Profile never implies hypermesh.*."""
    if profile == "strict":
        catalog = set(BASELINE_TOOLS)
    elif profile == "ir_elevated":
        catalog = set(BASELINE_TOOLS) | set(IR_ELEVATED_EXTRA)
    elif profile == "break_glass":
        catalog = set(BASELINE_TOOLS) | set(IR_ELEVATED_EXTRA)
    else:
        catalog = set(BASELINE_TOOLS)
    # Explicit allowlist may add tools (including hypermesh.*) — never implied.
    catalog.update(extra_allowlist)
    return frozenset(catalog)


def _truthy(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_until(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_engines_csv(raw: str | None) -> list[dict[str, Any]]:
    if not raw or not raw.strip():
        return []
    rows: list[dict[str, Any]] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        kind = item
        ident = item
        scenario = None
        if ":" in item:
            kind, rest = item.split(":", 1)
            kind, rest = kind.strip(), rest.strip()
            ident = rest or kind
            if kind == "mock" and rest:
                scenario = rest
                ident = f"mock-{rest}" if not rest.startswith("mock") else rest
        rows.append({"kind": kind, "id": ident, "scenario": scenario})
    return rows


def _engine_from_mapping(row: dict[str, Any], *, default_tier: str) -> EngineSpec:
    kind = str(row.get("kind") or "").strip().lower()
    if kind not in VALID_ENGINE_KINDS:
        raise ConfigError(f"unknown triage engine kind: {kind!r}")
    ident = str(row.get("id") or kind)
    tier = str(row.get("tier") or default_tier)
    if tier not in VALID_TIERS:
        raise ConfigError(f"unknown engine tier: {tier!r}")
    timeout = float(row.get("timeout_s") or DEFAULT_OLLAMA_TIMEOUT_S)
    return EngineSpec(
        kind=kind,
        id=ident,
        tier=tier,
        scenario=row.get("scenario"),
        url=row.get("url") or row.get("base_url"),
        model=row.get("model"),
        timeout_s=timeout,
    )


def _load_yaml_triage(path: Path) -> dict[str, Any]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError("triage yaml must be a mapping")
    block = data.get("triage")
    if block is None:
        block = data
    if not isinstance(block, dict):
        raise ConfigError("triage yaml.triage must be a mapping")
    return block


def _resolve_mode(explicit: str | None, engines: tuple[EngineSpec, ...]) -> str:
    if explicit is None or explicit == "":
        return "rules_primary" if engines else "rules_only"
    mode = explicit.strip()
    if mode in CUT_MODES:
        raise ConfigError("model_primary is not a v0 triage_mode; use model_assist")
    if mode not in VALID_MODES:
        raise ConfigError(f"invalid triage_mode: {mode!r}")
    return mode


def _resolve_tier(raw: str, *, rails: RailsStub) -> str:
    tier = raw.strip() or "local_small"
    if tier not in VALID_TIERS:
        raise ConfigError(f"invalid default_tier: {tier!r}")
    if tier in GRANT_TIERS and not (
        rails.grant_active and rails.profile in {"ir_elevated", "break_glass"}
    ):
        raise ConfigError(
            "plane_ir/host_leased require an active elevated rails stub (slice 7 grants)"
        )
    return tier


def parse_triage_settings(
    *,
    env: dict[str, str] | None = None,
    rails_profile: str | None = None,
) -> TriageSettings:
    """Load triage settings from env and optional ``AIMMUNE_TRIAGE_FILE`` yaml."""
    environ = env if env is not None else os.environ
    yaml_block: dict[str, Any] = {}
    yaml_path = environ.get("AIMMUNE_TRIAGE_FILE") or environ.get("AIMMUNE_SITE_YAML")
    if yaml_path:
        yaml_block = _load_yaml_triage(Path(yaml_path))

    raw_engines = yaml_block.get("engines")
    if raw_engines is None:
        raw_engines = _parse_engines_csv(environ.get("AIMMUNE_TRIAGE_ENGINES"))
    if not isinstance(raw_engines, list):
        raise ConfigError("triage.engines must be a list")

    default_tier_raw = str(
        yaml_block.get("default_tier")
        or environ.get("AIMMUNE_TRIAGE_DEFAULT_TIER")
        or "local_small"
    )
    engines = tuple(
        _engine_from_mapping(row if isinstance(row, dict) else {"kind": row}, default_tier=default_tier_raw)
        for row in raw_engines
    )

    profile = (
        str(yaml_block.get("rails_profile") or "").strip()
        or (rails_profile or "").strip()
        or environ.get("AIMMUNE_RAILS_PROFILE")
        or "strict"
    )
    if profile not in VALID_PROFILES:
        raise ConfigError(f"invalid rails_profile: {profile!r}")

    grant_until = _parse_until(
        str(yaml_block.get("grant_active_until") or "")
        or environ.get("AIMMUNE_RAILS_GRANT_UNTIL")
    )
    allow_raw = yaml_block.get("tool_allowlist")
    if allow_raw is None:
        allow_csv = environ.get("AIMMUNE_RAILS_TOOL_ALLOWLIST") or ""
        allowlist = tuple(part.strip() for part in allow_csv.split(",") if part.strip())
    elif isinstance(allow_raw, (list, tuple)):
        allowlist = tuple(str(x) for x in allow_raw)
    else:
        raise ConfigError("tool_allowlist must be a list")

    grant_active = _truthy(
        str(yaml_block["grant_active"])
        if "grant_active" in yaml_block
        else environ.get("AIMMUNE_RAILS_GRANT_ACTIVE"),
        default=False,
    )
    if grant_active:
        import warnings

        warnings.warn(
            "AIMMUNE_RAILS_GRANT_* is a deprecated test-only override; "
            "privilege grants are the source of truth",
            DeprecationWarning,
            stacklevel=2,
        )
    rails = RailsStub(
        profile=profile,
        grant_active=grant_active,
        active_until=grant_until,
        tool_allowlist=allowlist,
    )

    default_tier = _resolve_tier(default_tier_raw, rails=rails)

    explicit_mode = yaml_block.get("triage_mode") or environ.get("AIMMUNE_TRIAGE_MODE")
    mode = _resolve_mode(None if explicit_mode is None else str(explicit_mode), engines)

    enrich = yaml_block.get("enrich")
    if enrich is None:
        enrich = _truthy(environ.get("AIMMUNE_TRIAGE_ENRICH"), default=False)
    else:
        enrich = bool(enrich)

    theta_raw = yaml_block.get("confidence_theta")
    if theta_raw is None:
        theta_raw = environ.get("AIMMUNE_TRIAGE_THETA") or environ.get(
            "AIMMUNE_CONFIDENCE_THETA"
        )
    theta = float(theta_raw) if theta_raw is not None else DEFAULT_THETA
    if not 0 <= theta <= 1:
        raise ConfigError("confidence_theta must be in [0, 1]")

    failure = str(
        yaml_block.get("on_model_failure")
        or environ.get("AIMMUNE_TRIAGE_ON_FAILURE")
        or "fallback"
    )
    if failure in CUT_FAILURE:
        raise ConfigError(f"{failure} is forbidden; on_model_failure must be fallback")
    if failure not in VALID_FAILURE:
        raise ConfigError(f"invalid on_model_failure: {failure!r}")

    # Fill ollama url/model from env when kind is ollama and yaml omitted them.
    filled: list[EngineSpec] = []
    for spec in engines:
        if spec.kind == "ollama":
            filled.append(
                EngineSpec(
                    kind=spec.kind,
                    id=spec.id,
                    tier=spec.tier,
                    scenario=spec.scenario,
                    url=spec.url
                    or environ.get("AIMMUNE_OLLAMA_URL")
                    or DEFAULT_OLLAMA_URL,
                    model=spec.model or environ.get("AIMMUNE_OLLAMA_MODEL") or spec.id,
                    timeout_s=float(
                        environ.get("AIMMUNE_OLLAMA_TIMEOUT_S") or spec.timeout_s
                    ),
                )
            )
            continue
        if spec.kind == "mock" and spec.scenario is None:
            filled.append(
                EngineSpec(
                    kind=spec.kind,
                    id=spec.id or DEFAULT_MOCK_ID,
                    tier=spec.tier,
                    scenario=environ.get("AIMMUNE_MOCK_ENGINE_SCENARIO") or "propose",
                    url=spec.url,
                    model=spec.model,
                    timeout_s=spec.timeout_s,
                )
            )
            continue
        if spec.kind == "pair" and spec.id == "pair":
            filled.append(
                EngineSpec(
                    kind=spec.kind,
                    id=DEFAULT_PAIR_ID,
                    tier=spec.tier,
                    scenario=spec.scenario,
                    url=spec.url,
                    model=spec.model,
                    timeout_s=spec.timeout_s,
                )
            )
            continue
        filled.append(spec)

    return TriageSettings(
        mode=mode,
        default_tier=default_tier,
        enrich=bool(enrich),
        confidence_theta=theta,
        engines=tuple(filled),
        on_model_failure=failure,
        rails=rails,
    )
