from __future__ import annotations

from dataclasses import replace

from aimmune.cycle import run_cycle
from tests.conftest import WHITELIST_IP, port_scan_burst, write_eve


def test_whitelist_never_blocked(tmp_state, tmp_path) -> None:
    allow = tmp_path / "whitelist.txt"
    allow.write_text(f"{WHITELIST_IP}\n# comment\n", encoding="utf-8")
    tmp_state.config = replace(tmp_state.config, whitelist_path=allow)
    write_eve(tmp_state.config.eve_path, port_scan_burst(WHITELIST_IP, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    assert WHITELIST_IP not in tmp_state.alias.list_members()
    assert not any(
        ex.get("tool") == "firewall.block_ip" and ex.get("status") == "applied"
        for rec in result.receipts
        for ex in rec["execution"]
    )
    assert any(r["policy"]["decision"] == "observe" for r in result.receipts)
