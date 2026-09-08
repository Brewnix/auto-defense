"""Pin examples + generated preempt envelopes validate against iface schemas."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from aimmune.preempt.hook import HOOK_ACTOR, build_hook_proposals
from aimmune.preempt.runner import _make_envelope
from aimmune.schema import validate_envelope, validate_tool_args


def test_pin_hypermesh_examples_validate(pin: Path) -> None:
    path = pin / "examples" / "hypermesh-preempt.example.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, env in data.items():
        validate_envelope(env, pin)
        for proposal in env.get("proposals") or []:
            validate_tool_args(proposal, pin)
        _ = key


def test_hook_proposals_schema_valid(pin: Path) -> None:
    proposals = build_hook_proposals(
        device_id="jetson-cottage-01",
        lease_ids=["lease-203-0-113-50"],
    )
    for proposal in proposals:
        validate_tool_args(proposal, pin)
    env = _make_envelope(
        site_id="net-tn-cottage",
        actor=HOOK_ACTOR,
        observed_at="2026-09-08T21:00:00Z",
        digest="sha256:" + ("a" * 64),
        judgment={
            "severity": "critical",
            "classes": ["port_scan"],
            "subjects": [{"kind": "host", "value": "jetson-cottage-01"}],
            "summary": "site_defense preempt propose",
            "evidence_refs": ["eve:window"],
        },
        proposals=proposals,
        needs_human=True,
    )
    env["trace_id"] = str(uuid4())
    validate_envelope(env, pin)
