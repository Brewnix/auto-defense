"""Environment config. State dir is an env override, not a schema field."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from aimmune.triage.settings import RailsStub, TriageSettings, parse_triage_settings

DEFAULT_STATE_DIR = Path("/var/lib/aimmune")
DEFAULT_CYCLE_SECONDS = 120
DEFAULT_WINDOW_S = 300
DEFAULT_ALIAS = "ai_autoblock"
DEFAULT_RATE_LIMIT_B = 30
DEFAULT_BLOCK_TTL_S = 86400
DEFAULT_SITE_ID = "net-tn-cottage"
DEFAULT_PLANE_TIMEOUT_S = 3.0
DEFAULT_RAILS_PROFILE = "strict"
DEFAULT_SELL_STATE_STALE_S = 300
DEFAULT_LEASE_STOP_RATE = 10
DEFAULT_JOB_POLL_TIMEOUT_S = 30.0
DEFAULT_JOB_POLL_INTERVAL_S = 0.2
DEFAULT_PREEMPT_MODE = "drain"
DEFAULT_UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 3000


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _optional_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw)


def _csv_list(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def parse_lease_bindings(
    raw: tuple[str, ...],
    device_ids: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """Map configured lease ids to device_id. Never pick-active / omit.

    ``device_id:lease_id`` binds explicitly. Bare ``lease_id`` is allowed
    only when exactly one device_id is configured.
    """
    bindings: list[tuple[str, str]] = []
    for item in raw:
        if ":" in item:
            device_id, lease_id = item.split(":", 1)
            device_id, lease_id = device_id.strip(), lease_id.strip()
            if device_id and lease_id:
                bindings.append((device_id, lease_id))
            continue
        if len(device_ids) != 1:
            continue
        bindings.append((device_ids[0], item))
    return tuple(bindings)


def find_iface_pin(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("AIMMUNE_IFACE_PIN")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "vendor" / "inference-iface",
        Path.cwd() / "vendor" / "inference-iface",
    ]
    for cand in candidates:
        if (cand / "schemas").is_dir():
            return cand
    raise FileNotFoundError(
        "inference-iface pin not found; set AIMMUNE_IFACE_PIN or clone with submodules"
    )


@dataclass(frozen=True)
class Config:
    state_dir: Path
    site_id: str
    eve_path: Path | None
    whitelist_path: Path | None
    rules_path: Path | None
    iface_pin: Path
    window_s: int = DEFAULT_WINDOW_S
    cycle_seconds: int = DEFAULT_CYCLE_SECONDS
    alias: str = DEFAULT_ALIAS
    rate_limit_b: int = DEFAULT_RATE_LIMIT_B
    block_ttl_s: int | None = None
    plane_reachable: bool = False
    wan_up: bool = True
    sell_state: str = "off"
    exec_mock: bool = False
    opnsense_url: str | None = None
    opnsense_key: str | None = None
    opnsense_secret: str | None = None
    opnsense_verify: bool = True
    panopticon_base_url: str | None = None
    hm_site_token: str | None = None
    plane_timeout_s: float = DEFAULT_PLANE_TIMEOUT_S
    rails_profile: str = DEFAULT_RAILS_PROFILE
    allow_sell_pause_execute: bool = True
    allow_stop_while_selling: bool = False
    site_defense_preempt: bool = False
    hypermesh_device_ids: tuple[str, ...] = ()
    hypermesh_lease_ids: tuple[str, ...] = ()
    sell_state_stale_s: int = DEFAULT_SELL_STATE_STALE_S
    lease_stop_rate: int = DEFAULT_LEASE_STOP_RATE
    job_poll_timeout_s: float = DEFAULT_JOB_POLL_TIMEOUT_S
    job_poll_interval_s: float = DEFAULT_JOB_POLL_INTERVAL_S
    preempt_mode: str = DEFAULT_PREEMPT_MODE
    host_state_dir: Path | None = None
    owner_sock: Path | None = None
    owner_token_path: Path | None = None
    ui_token: str | None = None
    ui_host: str = DEFAULT_UI_HOST
    ui_port: int = DEFAULT_UI_PORT
    owner_principals: tuple[str, ...] = ()
    ui_smoke_principal: str | None = None
    sociacl_fixture: Path | None = None
    triage: TriageSettings = field(default_factory=TriageSettings)

    @property
    def lease_bindings(self) -> tuple[tuple[str, str], ...]:
        return parse_lease_bindings(self.hypermesh_lease_ids, self.hypermesh_device_ids)

    @property
    def lease_stop_rate_path(self) -> Path:
        return self.state_dir / "lease_stop_rate.jsonl"

    @property
    def preempt_queue_path(self) -> Path:
        return self.state_dir / "preempt_queue.jsonl"

    @property
    def resolved_owner_sock(self) -> Path | None:
        if self.owner_sock is not None:
            return self.owner_sock
        if self.host_state_dir is not None:
            return self.host_state_dir / "owner.sock"
        return None

    @property
    def resolved_owner_token_path(self) -> Path | None:
        if self.owner_token_path is not None:
            return self.owner_token_path
        if self.host_state_dir is not None:
            return self.host_state_dir / "owner.token"
        return None

    @property
    def owner_effects_path(self) -> Path | None:
        if self.host_state_dir is not None:
            return self.host_state_dir / "owner-effects.jsonl"
        return None

    @property
    def receipts_path(self) -> Path:
        return self.state_dir / "receipts.jsonl"

    @property
    def ttl_ledger_path(self) -> Path:
        return self.state_dir / "ttl_ledger.jsonl"

    @property
    def notify_queue_path(self) -> Path:
        return self.state_dir / "notify_queue.jsonl"

    @property
    def incidents_path(self) -> Path:
        return self.state_dir / "incidents.jsonl"

    @property
    def incident_index_path(self) -> Path:
        return self.state_dir / "incident_index.jsonl"

    @property
    def rate_limit_path(self) -> Path:
        return self.state_dir / "rate_limit.jsonl"

    @property
    def auditor_watch_path(self) -> Path:
        return self.state_dir / "auditor_watch.jsonl"

    @property
    def triage_eval_path(self) -> Path:
        return self.state_dir / "triage_eval.jsonl"

    @property
    def grants_path(self) -> Path:
        return self.state_dir / "grants.jsonl"

    @property
    def last_cycle_path(self) -> Path:
        return self.state_dir / "last_cycle.json"

    @property
    def rails_stub(self) -> RailsStub:
        return self.triage.rails


def load_config(
    *,
    state_dir: Path | None = None,
    site_id: str | None = None,
    eve_path: Path | None = None,
    whitelist_path: Path | None = None,
) -> Config:
    env_state = os.environ.get("AIMMUNE_STATE_DIR") or os.environ.get("AIMIMUNE_STATE_DIR")
    resolved_state = state_dir or (Path(env_state) if env_state else DEFAULT_STATE_DIR)
    return Config(
        state_dir=resolved_state,
        site_id=site_id
        or os.environ.get("AIMMUNE_SITE_ID")
        or os.environ.get("SITE_ID")
        or DEFAULT_SITE_ID,
        eve_path=eve_path or _optional_path("AIMMUNE_EVE_PATH"),
        whitelist_path=whitelist_path or _optional_path("AIMMUNE_WHITELIST_FILE"),
        rules_path=_optional_path("AIMMUNE_RULES_FILE"),
        iface_pin=find_iface_pin(),
        window_s=int(os.environ.get("AIMMUNE_WINDOW_S", str(DEFAULT_WINDOW_S))),
        cycle_seconds=int(
            os.environ.get("AIMMUNE_CYCLE_SECONDS", str(DEFAULT_CYCLE_SECONDS))
        ),
        alias=os.environ.get("AIMMUNE_ALIAS", DEFAULT_ALIAS),
        rate_limit_b=int(os.environ.get("AIMMUNE_RATE_LIMIT_B", str(DEFAULT_RATE_LIMIT_B))),
        block_ttl_s=(
            int(os.environ["AIMMUNE_BLOCK_TTL_S"])
            if os.environ.get("AIMMUNE_BLOCK_TTL_S")
            else None
        ),
        plane_reachable=_truthy("AIMMUNE_PLANE_REACHABLE", default=False),
        wan_up=_truthy("AIMMUNE_WAN_UP", default=True),
        sell_state=os.environ.get("AIMMUNE_SELL_STATE", "off"),
        exec_mock=_truthy("AIMMUNE_EXEC_MOCK", default=False),
        opnsense_url=os.environ.get("AIMMUNE_OPNSENSE_URL")
        or os.environ.get("OPNSENSE_URL"),
        opnsense_key=os.environ.get("AIMMUNE_OPNSENSE_KEY")
        or os.environ.get("OPNSENSE_KEY"),
        opnsense_secret=os.environ.get("AIMMUNE_OPNSENSE_SECRET")
        or os.environ.get("OPNSENSE_SECRET"),
        opnsense_verify=_truthy("AIMMUNE_OPNSENSE_VERIFY", default=True),
        panopticon_base_url=os.environ.get("PANOPTICON_BASE_URL") or None,
        hm_site_token=os.environ.get("HM_SITE_TOKEN") or None,
        plane_timeout_s=float(
            os.environ.get("AIMMUNE_PLANE_TIMEOUT_S", str(DEFAULT_PLANE_TIMEOUT_S))
        ),
        rails_profile=(
            os.environ.get("AIMMUNE_RAILS_PROFILE", DEFAULT_RAILS_PROFILE).strip()
            or DEFAULT_RAILS_PROFILE
        ),
        allow_sell_pause_execute=_truthy(
            "AIMMUNE_ALLOW_SELL_PAUSE_EXECUTE", default=True
        ),
        allow_stop_while_selling=_truthy(
            "AIMMUNE_ALLOW_STOP_WHILE_SELLING", default=False
        ),
        site_defense_preempt=_truthy("AIMMUNE_SITE_DEFENSE_PREEMPT", default=False),
        hypermesh_device_ids=_csv_list("AIMMUNE_HYPERMESH_DEVICE_IDS"),
        hypermesh_lease_ids=_csv_list("AIMMUNE_HYPERMESH_LEASE_IDS"),
        sell_state_stale_s=int(
            os.environ.get("AIMMUNE_SELL_STATE_STALE_S", str(DEFAULT_SELL_STATE_STALE_S))
        ),
        lease_stop_rate=int(
            os.environ.get("AIMMUNE_LEASE_STOP_RATE", str(DEFAULT_LEASE_STOP_RATE))
        ),
        job_poll_timeout_s=float(
            os.environ.get("AIMMUNE_JOB_POLL_TIMEOUT_S", str(DEFAULT_JOB_POLL_TIMEOUT_S))
        ),
        job_poll_interval_s=float(
            os.environ.get(
                "AIMMUNE_JOB_POLL_INTERVAL_S", str(DEFAULT_JOB_POLL_INTERVAL_S)
            )
        ),
        preempt_mode=DEFAULT_PREEMPT_MODE,
        host_state_dir=_optional_path("AIMMUNE_HOST_STATE_DIR")
        or _optional_path("HYPERMESH_STATE_DIR"),
        owner_sock=_optional_path("AIMMUNE_OWNER_SOCK"),
        owner_token_path=_optional_path("AIMMUNE_OWNER_TOKEN"),
        ui_token=os.environ.get("AIMMUNE_UI_TOKEN") or None,
        ui_host=(os.environ.get("AIMMUNE_UI_HOST") or DEFAULT_UI_HOST).strip()
        or DEFAULT_UI_HOST,
        ui_port=int(os.environ.get("AIMMUNE_UI_PORT", str(DEFAULT_UI_PORT))),
        owner_principals=_csv_list("AIMMUNE_OWNER_PRINCIPALS"),
        ui_smoke_principal=os.environ.get("AIMMUNE_UI_SMOKE_PRINCIPAL") or None,
        sociacl_fixture=_optional_path("AIMMUNE_SOCIACL_FIXTURE"),
        triage=parse_triage_settings(
            rails_profile=(
                os.environ.get("AIMMUNE_RAILS_PROFILE", DEFAULT_RAILS_PROFILE).strip()
                or DEFAULT_RAILS_PROFILE
            )
        ),
    )
