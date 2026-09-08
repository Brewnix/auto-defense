from __future__ import annotations

from pathlib import Path

from aimmune.canonical import features_digest, receipt_body_hash
from aimmune.cycle import run_cycle
from aimmune.schema import validate_bundle, validate_envelope, validate_receipt
from tests.conftest import ATTACKER, port_scan_burst, write_eve


def test_pin_examples_and_generated_instances(tmp_state, pin: Path) -> None:
    write_eve(tmp_state.config.eve_path, port_scan_burst(ATTACKER, tmp_state.clock.now()))
    result = run_cycle(tmp_state)
    validate_bundle(result.bundle, pin)
    for env in result.envelopes:
        validate_envelope(env, pin)
        assert env["inputs_digest"] == features_digest(result.bundle)
    for rec in result.receipts:
        validate_receipt(rec, pin)
        assert rec["integrity"]["body_hash"] == receipt_body_hash(rec)
        assert rec["integrity"]["sig"] is None


def test_hash_omits_integrity() -> None:
    receipt = {
        "schema": "fyber.receipt/v0",
        "receipt_id": "550e8400-e29b-41d4-a716-446655440010",
        "integrity": {
            "body_hash": "sha256:" + "b" * 64,
            "prev_hash": None,
            "sig": None,
        },
        "site_id": "net-tn-cottage",
    }
    first = receipt_body_hash(receipt)
    receipt["integrity"]["body_hash"] = "sha256:" + "c" * 64
    assert receipt_body_hash(receipt) == first
