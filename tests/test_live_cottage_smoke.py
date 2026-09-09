"""Live cottage v0 — default-off (`pytest -m live_cottage`).

Scripts the host-install checklist through offline contain.
Skip unless ``AIMMUNE_LIVE_COTTAGE=1``. ``AIMMUNE_EXEC_MOCK=1``.
No live alias_util / Eve / WireGuard / Panopticon / SIWE / Playwright.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from aimmune.cli import main

pytestmark = pytest.mark.live_cottage

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "scripts" / "smoke-cottage-offline.sh"

LIVE_VALUES = {"1", "true", "yes", "on"}


def _live_cottage_enabled() -> bool:
    return os.environ.get("AIMMUNE_LIVE_COTTAGE", "").strip().lower() in LIVE_VALUES


def _skip_unless_live() -> None:
    if not _live_cottage_enabled():
        pytest.skip("AIMMUNE_LIVE_COTTAGE=1 not set")


def test_live_cottage_offline_contain_script(tmp_path: Path, monkeypatch) -> None:
    _skip_unless_live()
    assert SMOKE.is_file(), SMOKE
    prefix = tmp_path / "cottage"
    prefix.mkdir()
    env = os.environ.copy()
    env["AIMMUNE_COTTAGE_PREFIX"] = str(prefix)
    env["AIMMUNE_LIVE_COTTAGE"] = "1"
    env["AIMMUNE_EXEC_MOCK"] = "1"
    env["AIMMUNE_PLANE_REACHABLE"] = "0"
    env["PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env.pop("PANOPTICON_BASE_URL", None)
    env.pop("AIMMUNE_UI_TOKEN", None)
    env.pop("AIMMUNE_LIVE_COTTAGE_SYSTEMD", None)

    proc = subprocess.run(
        ["bash", str(SMOKE)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    assert "live cottage offline contain ok" in proc.stdout

    state = prefix / "var" / "lib" / "aimmune"
    env_file = prefix / "etc" / "aimmune" / "aimmune.env"
    unit = prefix / "systemd" / "aimmune.service"
    assert unit.is_file()
    assert "aimmune loop" in unit.read_text(encoding="utf-8")
    assert env_file.is_file()
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(state.stat().st_mode) == 0o700

    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(state))
    monkeypatch.setenv("AIMMUNE_SITE_ID", "net-tn-cottage")
    monkeypatch.setenv("SITE_ID", "net-tn-cottage")
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    monkeypatch.setenv("AIMMUNE_PLANE_REACHABLE", "0")
    monkeypatch.delenv("PANOPTICON_BASE_URL", raising=False)
    monkeypatch.delenv("AIMMUNE_UI_TOKEN", raising=False)

    rc = main(["status", "--json", "--state-dir", str(state), "--site-id", "net-tn-cottage"])
    assert rc == 0
    # subprocess already printed status; re-read via build by invoking main in-process
    from aimmune.config import load_config
    from aimmune.status import build_status

    payload = build_status(load_config(state_dir=state, site_id="net-tn-cottage"))
    assert payload["site_id"] == "net-tn-cottage"
    assert payload["plane_reachable"] is False
    assert payload["exec_mock"] is True
    assert payload["state_dir_exists"] is True
    assert payload["receipts"]["count"] >= 1
    assert payload["receipts"]["last"]["receipt_id"]
    assert (state / "receipts.jsonl").is_file()
    assert (state / "last_cycle.json").is_file()
    last_cycle = json.loads((state / "last_cycle.json").read_text(encoding="utf-8"))
    assert last_cycle.get("receipt_count", 0) >= 1
