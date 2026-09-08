"""Strict matrix: sell_pause auto only for rules + allowed reasons; lease_stop propose."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from aimmune.preempt.policy import decide_preempt, strip_extras
from aimmune.schema import SchemaValidationError, validate_tool_args

DEVICE = "jetson-cottage-01"
LEASE = "lease-203-0-113-50"


def _pause(reason="health_evacuate", mode="execute"):
    return {
        "call_id": str(uuid4()),
        "tool": "hypermesh.sell_pause",
        "mode": mode,
        "reason_code": reason,
        "args": {"device_id": DEVICE},
    }


def _stop(reason="site_defense", mode="propose"):
    return {
        "call_id": str(uuid4()),
        "tool": "hypermesh.lease_stop",
        "mode": mode,
        "reason_code": reason,
        "args": {"lease_id": LEASE, "reason_code": reason},
    }


def test_schema_valid_both_tools(pin) -> None:
    validate_tool_args(_pause(), pin)
    validate_tool_args(_stop(), pin)


def test_extra_args_fail_schema(pin) -> None:
    bad = _pause()
    bad["args"]["reason_code"] = "health_evacuate"
    try:
        validate_tool_args(bad, pin)
        raised = False
    except SchemaValidationError:
        raised = True
    assert raised


def test_strict_lease_stop_never_auto_from_rules_or_model(pin) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    rules = decide_preempt(
        [_stop()],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="site_defense",
        device_id=DEVICE,
        now=now,
    )
    assert rules.decision == "propose"
    assert rules.human_required is True
    assert not rules.execute_tools

    model = decide_preempt(
        [_stop(reason="health_evacuate")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="model",
        origin_actor_kind="model",
        reason_code="health_evacuate",
        device_id=DEVICE,
        now=now,
    )
    assert model.decision == "propose"
    assert not model.execute_tools


def test_strict_sell_pause_auto_only_allowed_reasons_and_flag(pin) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    ok = decide_preempt(
        [_pause("health_evacuate")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="health_evacuate",
        allow_sell_pause_execute=True,
        now=now,
    )
    assert ok.decision == "execute"
    assert ok.execute_tools == ["hypermesh.sell_pause"]

    owner = decide_preempt(
        [_pause("owner_stop_selling")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="owner_stop_selling",
        now=now,
    )
    assert owner.decision == "execute"

    site = decide_preempt(
        [_pause("site_defense")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="site_defense",
        now=now,
    )
    assert site.decision == "propose"
    assert not site.execute_tools

    flagged = decide_preempt(
        [_pause("health_evacuate")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="health_evacuate",
        allow_sell_pause_execute=False,
        now=now,
    )
    assert flagged.decision == "propose"


def test_model_sell_pause_stays_propose(pin) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    result = decide_preempt(
        [_pause("health_evacuate")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="model",
        origin_actor_kind="model",
        reason_code="health_evacuate",
        now=now,
    )
    assert result.decision == "propose"


def test_elevated_without_allowlist_no_execute(pin) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    result = decide_preempt(
        [_pause("health_evacuate"), _stop("incident_preempt")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="incident_preempt",
        rails_profile="ir_elevated",
        device_id=DEVICE,
        now=now,
    )
    # Profile is not a Hypermesh grant. Elevated auto is slice 7.
    assert "hypermesh.lease_stop" not in result.execute_tools
    assert result.preempt_mode == "drain"


def test_human_ack_executes_lease_stop(pin) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    result = decide_preempt(
        [_stop("site_defense")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="site_defense",
        human_approved=True,
        device_id=DEVICE,
        now=now,
        incident_id=str(uuid4()),
        incident_open=True,
    )
    assert result.decision == "execute"
    assert result.execute_tools == ["hypermesh.lease_stop"]


def test_human_ack_lease_stop_without_incident_force_propose(pin) -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    result = decide_preempt(
        [_stop("site_defense")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="site_defense",
        human_approved=True,
        owner_ack=True,
        device_id=DEVICE,
        now=now,
    )
    assert result.decision == "propose"
    assert "hypermesh.lease_stop" not in result.execute_tools
    assert result.notify is not None


def test_unknown_reason_not_execute(pin) -> None:
    result = decide_preempt(
        [_pause("not_a_real_reason")],
        pin=pin,
        site_id="net-tn-cottage",
        receipt_id=str(uuid4()),
        actor_kind="rule",
        origin_actor_kind="rule",
        reason_code="not_a_real_reason",
    )
    assert result.decision == "observe"
    assert result.items[0].reject_reason == "unknown_reason_code"


def test_strip_extras() -> None:
    pauses = [_pause() for _ in range(3)]
    stops = [_stop() for _ in range(10)]
    kept, stripped = strip_extras(pauses + stops)
    assert sum(1 for p in kept if p["tool"] == "hypermesh.sell_pause") == 1
    assert sum(1 for p in kept if p["tool"] == "hypermesh.lease_stop") == 8
    assert stripped == 4
