"""Annotate-only must not apply a held companion (write ≠ execute)."""

from aimmune.cycle import run_cycle
from aimmune.owner.annotate import local_annotate
from aimmune.schema import validate_receipt
from tests.conftest import ATTACKER, ssh_brute_burst, write_eve


def test_annotate_does_not_block(tmp_state) -> None:
    write_eve(tmp_state.config.eve_path, ssh_brute_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    propose = next(r for r in result.receipts if r["policy"]["decision"] == "propose")
    child = local_annotate(tmp_state, propose["receipt_id"], "cottage note")
    assert ATTACKER not in tmp_state.alias.list_members()
    assert child["policy"]["decision"] == "observe"
    assert child["human"]["resolution"] is None
    assert any(p.get("tool") == "receipt.annotate" for p in child["proposals"])
    assert not any(p.get("tool") == "firewall.block_ip" for p in child["proposals"])
    validate_receipt(child, tmp_state.config.iface_pin)
