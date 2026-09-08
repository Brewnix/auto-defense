from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dataclasses import replace

from aimmune.clock import FrozenClock
from aimmune.config import Config, find_iface_pin
from aimmune.cycle import Runtime, build_runtime
from aimmune.exec.opnsense_alias import MockAliasStore
from aimmune.triage.engines.mock import MockEngine
from aimmune.triage.settings import EngineSpec, RailsStub, TriageSettings

SCAN_SID = "2100498"
BRUTE_SID = "5721"
ATTACKER = "203.0.113.50"
BRUTE_ATTACKER = "203.0.113.60"
WHITELIST_IP = "198.51.100.10"


def rfc3339_eve(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"


def write_eve(path: Path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps(ev) + "\n" for ev in events), encoding="utf-8")


def eve_alert(src: str, dest_port: int, sid: str, ts: datetime) -> dict:
    return {
        "timestamp": rfc3339_eve(ts),
        "event_type": "alert",
        "src_ip": src,
        "dest_port": dest_port,
        "alert": {"signature_id": int(sid), "signature": "synthetic"},
    }


def port_scan_burst(src: str, ts: datetime, n_ports: int = 12, sid: str = SCAN_SID) -> list[dict]:
    return [eve_alert(src, 20 + i, sid, ts) for i in range(n_ports)]


def ssh_brute_burst(src: str, ts: datetime, k: int = 16, sid: str = BRUTE_SID) -> list[dict]:
    return [eve_alert(src, 22, sid, ts) for _ in range(k)]


@pytest.fixture
def pin() -> Path:
    return find_iface_pin()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 9, 8, 21, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def tmp_state(tmp_path: Path, clock: FrozenClock, pin: Path) -> Runtime:
    eve = tmp_path / "eve.json"
    eve.write_text("", encoding="utf-8")
    cfg = Config(
        state_dir=tmp_path / "state",
        site_id="net-tn-cottage",
        eve_path=eve,
        whitelist_path=None,
        rules_path=None,
        iface_pin=pin,
        window_s=300,
        cycle_seconds=120,
        exec_mock=True,
        plane_reachable=False,
        block_ttl_s=86400,
    )
    rt = build_runtime(cfg, clock=clock, alias=MockAliasStore())
    return rt


def enable_triage(
    rt: Runtime,
    *,
    mode: str = "rules_primary",
    scenario: str = "propose",
    rails: RailsStub | None = None,
    enrich: bool = False,
    theta: float = 0.6,
    engine_order: tuple[str, ...] = ("mock",),
) -> MockEngine:
    """Attach engines and matching triage settings (tests / cottage stub)."""
    from aimmune.triage.engines.pair import PairEngine

    mock = MockEngine(engine_id="mock-engine", scenario=scenario)
    specs: list[EngineSpec] = []
    engines: list = []
    for kind in engine_order:
        if kind == "pair":
            specs.append(EngineSpec(kind="pair", id="pair-local"))
            engines.append(PairEngine(engine_id="pair-local"))
        elif kind == "mock":
            specs.append(EngineSpec(kind="mock", id="mock-engine", scenario=scenario))
            engines.append(mock)
    rt.config = replace(
        rt.config,
        triage=TriageSettings(
            mode=mode,
            enrich=enrich,
            confidence_theta=theta,
            engines=tuple(specs),
            rails=rails or RailsStub(),
        ),
    )
    rt.triage_engines = engines
    return mock
