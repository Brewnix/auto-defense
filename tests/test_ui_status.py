"""Status-copy rules: never blocked from resolve alone; pending / timed_out / ack."""

from __future__ import annotations

from aimmune.ui.serialize import serialize_receipt, strip_unsafe
from aimmune.ui.status import (
    APPLIED_PENDING_ACK,
    APPROVED_PENDING_APPLY,
    BLOCKED,
    OBSERVED,
    PENDING_INTENT,
    TIMED_OUT_WAITING,
    WAITING_ON_PLANE,
    display_hold_status,
    display_receipt_status,
    find_apply_receipt,
    is_blocked_status,
    receipt_applied_block,
)


def _receipt(
    *,
    receipt_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    parent_id=None,
    resolution=None,
    decision="propose",
    execution=None,
    purpose="triage",
    extra=None,
):
    row = {
        "receipt_id": receipt_id,
        "parent_id": parent_id,
        "purpose": purpose,
        "policy": {"decision": decision, "rule_ids": []},
        "human": {"required": True, "resolution": resolution, "resolved_by": None, "resolved_at": None},
        "execution": execution or [],
        "proposals": [],
        "input": {"features_digest": "sha256:" + ("0" * 64), "window_s": 300, "sources": ["opnsense"]},
        "judgment": {"severity": "high", "classes": ["ssh_brute"], "subjects": [], "summary": "x"},
        "actor": {"kind": "rule", "id": "brewnix-rules/v0.1", "purpose": "triage"},
        "posture": {"wan_up": True, "plane_reachable": False, "path_b": "n/a", "sell_state": "off"},
        "integrity": {"body_hash": "sha256:" + ("a" * 64), "prev_hash": None},
    }
    if extra:
        row.update(extra)
    return row


def _block_exec(status="applied"):
    return [
        {
            "tool": "firewall.block_ip",
            "status": status,
            "executor": "opnsense-api@site",
            "effect": {"ip": "203.0.113.50", "alias": "ai_autoblock"},
            "error": None,
        }
    ]


def test_resolve_alone_never_blocked() -> None:
    for resolution in ("approved", "denied", "timed_out", "amended"):
        receipt = _receipt(resolution=resolution, decision="observe")
        assert not receipt_applied_block(receipt)
        view = display_hold_status(
            watch={"status": "resolved", "resolution": resolution},
            apply_receipt=None,
            plane_reachable=False,
        )
        assert view["status"] != BLOCKED
        assert not view["blocked"]
        assert "blocked" not in view["label"].lower() or view["status"] != BLOCKED
        rec_view = display_receipt_status(receipt)
        assert rec_view["status"] != BLOCKED
        assert not is_blocked_status(rec_view["status"])


def test_pending_intent_on_held_queue() -> None:
    view = display_hold_status(
        queue={"drained": False, "receipt_id": "r1"},
        watch=None,
        apply_receipt=None,
        plane_reachable=False,
    )
    assert view["status"] == PENDING_INTENT
    assert view["can_local_resolve"] is True
    assert view["label"] == "Pending intent — not blocked"


def test_waiting_on_plane_when_watch_open_and_plane_up() -> None:
    view = display_hold_status(
        queue={"drained": True, "ticket_id": "t1"},
        watch={"status": "open", "ticket_id": "t1", "resolution": None},
        apply_receipt=None,
        plane_reachable=True,
    )
    assert view["status"] == WAITING_ON_PLANE
    assert view["can_local_resolve"] is False
    assert view["blocked"] is False


def test_plane_down_open_watch_is_pending_local() -> None:
    view = display_hold_status(
        queue={"drained": True, "ticket_id": "t1"},
        watch={"status": "open", "ticket_id": "t1"},
        apply_receipt=None,
        plane_reachable=False,
    )
    assert view["status"] == PENDING_INTENT
    assert view["can_local_resolve"] is True


def test_timed_out_waiting_before_site_apply() -> None:
    view = display_hold_status(
        watch={"status": "resolved", "resolution": "timed_out", "ticket_id": "t1"},
        apply_receipt=None,
        plane_reachable=True,
    )
    assert view["status"] == TIMED_OUT_WAITING
    assert view["blocked"] is False
    assert view["can_local_resolve"] is False
    assert "blocked" not in view["label"].lower()


def test_approved_intent_not_blocked_before_apply() -> None:
    view = display_hold_status(
        watch={"status": "resolved", "resolution": "approved"},
        apply_receipt=None,
        plane_reachable=True,
    )
    assert view["status"] == APPROVED_PENDING_APPLY
    assert view["blocked"] is False
    assert "not blocked" in view["label"]


def test_blocked_only_after_apply_receipt_and_ack() -> None:
    apply = _receipt(
        receipt_id="child",
        parent_id="held",
        resolution="approved",
        decision="execute",
        purpose="contain",
        execution=_block_exec("applied"),
    )
    # Apply without ack — not yet "blocked" on the hold row.
    pending_ack = display_hold_status(
        watch={"status": "resolved", "resolution": "approved", "apply_receipt_id": "child"},
        apply_receipt=apply,
        plane_reachable=True,
    )
    assert pending_ack["status"] == APPLIED_PENDING_ACK
    assert pending_ack["blocked"] is False

    acked = display_hold_status(
        watch={
            "status": "acked",
            "resolution": "approved",
            "site_acked_receipt_id": "child",
        },
        apply_receipt=apply,
        plane_reachable=True,
    )
    assert acked["status"] == BLOCKED
    assert acked["blocked"] is True
    assert acked["label"] == "Blocked"


def test_failed_block_apply_is_not_blocked() -> None:
    apply = _receipt(
        receipt_id="child",
        parent_id="held",
        resolution="approved",
        decision="execute",
        execution=_block_exec("failed"),
    )
    view = display_hold_status(
        watch={"status": "acked", "resolution": "approved", "site_acked_receipt_id": "child"},
        apply_receipt=apply,
        plane_reachable=False,
    )
    assert view["status"] == OBSERVED
    assert view["blocked"] is False


def test_denied_apply_is_observed_not_blocked() -> None:
    apply = _receipt(
        receipt_id="child",
        parent_id="held",
        resolution="denied",
        decision="observe",
        execution=[{"tool": "receipt.annotate", "status": "applied", "effect": {}, "error": None}],
    )
    view = display_hold_status(
        watch={"status": "acked", "resolution": "denied", "site_acked_receipt_id": "child"},
        apply_receipt=apply,
        plane_reachable=False,
    )
    assert view["status"] == OBSERVED
    assert view["blocked"] is False


def test_local_apply_without_watch_counts_as_acked() -> None:
    apply = _receipt(
        receipt_id="child",
        parent_id="held",
        resolution="approved",
        decision="execute",
        purpose="contain",
        execution=_block_exec("applied"),
    )
    view = display_hold_status(
        queue={"drained": True, "receipt_id": "held"},
        watch=None,
        apply_receipt=apply,
        plane_reachable=False,
    )
    assert view["status"] == BLOCKED


def test_find_apply_receipt_by_parent_and_watch() -> None:
    held = _receipt(receipt_id="held")
    child = _receipt(
        receipt_id="child",
        parent_id="held",
        resolution="approved",
        execution=_block_exec(),
    )
    assert find_apply_receipt([held, child], "held") is child
    via_watch = find_apply_receipt(
        [held, child],
        "held",
        {"site_acked_receipt_id": "child"},
    )
    assert via_watch is child


def test_serializer_strips_prompt_and_payload() -> None:
    dirty = _receipt(
        extra={
            "prompt": "SYSTEM: leak",
            "payload": {"eve": {"raw": "alert"}},
            "proposals": [
                {
                    "tool": "firewall.block_ip",
                    "mode": "execute",
                    "args": {"ip": "203.0.113.50", "prompt": "nope", "payload": "x"},
                }
            ],
        }
    )
    clean = serialize_receipt(dirty)
    blob = str(clean)
    assert "SYSTEM" not in blob
    assert "prompt" not in blob
    assert "payload" not in blob
    assert "SYSTEM" not in blob
    assert "eve_raw" not in blob
    assert clean["receipt_id"] == dirty["receipt_id"]
    assert "ip" in (clean["proposals"][0]["args"] or {})
    assert clean["actor"]["kind"] == "rule"


def test_serializer_shows_model_actor_without_eval_prompt() -> None:
    dirty = _receipt(
        extra={
            "actor": {
                "kind": "model",
                "id": "mock-engine@sha256:" + ("a" * 64),
                "purpose": "triage",
            },
            "prompt": "You are a judge. SYSTEM leak",
            "eval_log": {"prompt": "never", "messages": ["x"]},
        }
    )
    clean = serialize_receipt(dirty)
    assert clean["actor"]["kind"] == "model"
    assert clean["actor"]["id"].startswith("mock-engine@")
    blob = str(clean)
    assert "SYSTEM leak" not in blob
    assert "You are a judge" not in blob
    assert "eval_log" not in blob


def test_strip_unsafe_nested() -> None:
    cleaned = strip_unsafe({"ok": 1, "chat": {"messages": ["hi"]}, "nested": {"ir_chat": "x"}})
    assert cleaned == {"ok": 1, "nested": {}}


def test_catalog_blocked_flag_only_on_blocked() -> None:
    from aimmune.ui.status import STATUS_CATALOG

    blocked_rows = [row for row in STATUS_CATALOG if row["blocked"]]
    assert len(blocked_rows) == 1
    assert blocked_rows[0]["status"] == BLOCKED
