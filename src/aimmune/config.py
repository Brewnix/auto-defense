"""Environment config. State dir is an env override, not a schema field."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_DIR = Path("/var/lib/aimmune")
DEFAULT_CYCLE_SECONDS = 120
DEFAULT_WINDOW_S = 300
DEFAULT_ALIAS = "ai_autoblock"
DEFAULT_RATE_LIMIT_B = 30
DEFAULT_BLOCK_TTL_S = 86400
DEFAULT_SITE_ID = "net-tn-cottage"


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
    )
