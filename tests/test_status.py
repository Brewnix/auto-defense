"""aimmune status — read-only summary against a tmp state dir."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from aimmune.cli import main
from aimmune.config import load_config
from aimmune.cycle import run_cycle
from aimmune.grants.store import GrantStore
from aimmune.status import build_status
from tests.conftest import ATTACKER, port_scan_burst, write_eve


def test_status_missing_state_dir_exits_zero(tmp_path, monkeypatch, capsys) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(missing))
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    monkeypatch.setenv("AIMMUNE_SITE_ID", "net-tn-cottage")
    rc = main(["status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state_dir_exists"] is False
    assert payload["site_id"] == "net-tn-cottage"
    assert payload["receipts"]["count"] == 0
    assert payload["open_incidents"] == 0
    assert payload["active_grants"] == 0
    assert missing.is_dir() is False


def test_status_after_cycle(tmp_state, monkeypatch, capsys) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert result.receipts
    assert tmp_state.config.last_cycle_path.is_file()

    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(tmp_state.config.state_dir))
    monkeypatch.setenv("AIMMUNE_SITE_ID", tmp_state.config.site_id)
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    monkeypatch.setenv("AIMMUNE_PLANE_REACHABLE", "0")
    rc = main(["status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state_dir_exists"] is True
    assert payload["receipts"]["count"] >= 1
    assert payload["receipts"]["last"]["receipt_id"]
    assert payload["last_cycle"]["receipt_count"] >= 1
    assert payload["last_cycle"]["finished_at"]
    assert payload["open_incidents"] >= 1
    assert payload["plane_reachable"] is False


def test_status_counts_active_grant(tmp_state) -> None:
    now = datetime(2026, 9, 8, 21, 0, 0, tzinfo=timezone.utc)
    GrantStore(tmp_state.config.grants_path).upsert(
        {
            "grant_id": "grant-active-1",
            "incident_id": "inc-1",
            "status": "approved",
            "active_until": "2026-09-08T22:00:00Z",
        }
    )
    GrantStore(tmp_state.config.grants_path).upsert(
        {
            "grant_id": "grant-expired-1",
            "incident_id": "inc-1",
            "status": "approved",
            "active_until": "2026-09-08T20:00:00Z",
        }
    )
    payload = build_status(tmp_state.config, now=now)
    assert payload["active_grants"] == 1
    assert payload["proposed_grants"] == 0


def test_status_text_and_module_entrypoint(tmp_path, monkeypatch) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("AIMMUNE_STATE_DIR", str(state))
    monkeypatch.setenv("AIMMUNE_EXEC_MOCK", "1")
    env = os.environ.copy()
    env["AIMMUNE_STATE_DIR"] = str(state)
    env["AIMMUNE_EXEC_MOCK"] = "1"
    root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(root / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    proc = subprocess.run(
        [sys.executable, "-m", "aimmune", "status", "--json"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["state_dir"] == str(state)
    assert payload["state_dir_exists"] is False

    cfg = load_config(state_dir=state)
    text_rc = main(["status", "--state-dir", str(state)])
    assert text_rc == 0
    assert cfg.site_id
