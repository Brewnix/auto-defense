"""CLI: cycle, loop, drain, poll-tickets, preempt, incident, owner, ui-snapshot.

Plane resolve stays plane-only. Site-local owner approve/deny is slice 5.
Incident close/sweep is slice 3 (overlay; never gates contain).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from aimmune.canonical import canonical_dumps
from aimmune.config import load_config
from aimmune.cycle import build_runtime, run_cycle
from aimmune.incident.minimal import GrantActiveError, IncidentError
from aimmune.notify.drain import drain_queue, poll_tickets
from aimmune.owner.local import WaitingOnPlaneError, local_resolve
from aimmune.preempt.runner import cli_preempt, run_preempt_queue
from aimmune.receipt.chain import verify_chain
from aimmune.ui.snapshot import build_snapshot


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--eve", type=Path, default=None)
    parser.add_argument("--whitelist", type=Path, default=None)
    parser.add_argument("--site-id", default=None)


def _runtime_from_args(args: argparse.Namespace):
    cfg = load_config(
        state_dir=args.state_dir,
        site_id=args.site_id,
        eve_path=args.eve,
        whitelist_path=args.whitelist,
    )
    return build_runtime(cfg)


def cmd_cycle(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    result = run_cycle(rt)
    summary = {
        "receipts": [r["receipt_id"] for r in result.receipts],
        "decisions": [r["policy"]["decision"] for r in result.receipts],
        "purposes": [r["purpose"] for r in result.receipts],
        "state_dir": str(rt.config.state_dir),
        "plane_reachable": rt.config.plane_reachable,
        "plane": result.plane,
        "sweep": result.sweep,
    }
    print(canonical_dumps(summary))
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    seconds = args.seconds if args.seconds is not None else rt.config.cycle_seconds
    while True:
        run_cycle(rt)
        time.sleep(seconds)


def cmd_verify(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    receipts = rt.chain.load()
    verify_chain(receipts)
    print(json.dumps({"ok": True, "count": len(receipts)}))
    return 0


def cmd_drain(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    if rt.auditor is None:
        print(
            "ERROR: PANOPTICON_BASE_URL and HM_SITE_TOKEN required for drain",
            file=sys.stderr,
        )
        return 1
    result = drain_queue(rt)
    print(canonical_dumps(result.as_dict()))
    return 0 if result.drained or not rt.notify.pending() else 1


def cmd_preempt(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    if args.preempt_cmd == "run":
        receipts = run_preempt_queue(rt)
        print(
            canonical_dumps(
                {
                    "receipts": [r["receipt_id"] for r in receipts],
                    "decisions": [r["policy"]["decision"] for r in receipts],
                    "state_dir": str(rt.config.state_dir),
                    "plane_reachable": rt.config.plane_reachable,
                }
            )
        )
        return 0
    receipt = cli_preempt(
        rt,
        kind=args.preempt_cmd,
        device_id=args.device_id,
        lease_id=getattr(args, "lease_id", None),
        reason_code=args.reason_code,
        until=getattr(args, "until", None),
        execute=bool(args.execute),
    )
    print(canonical_dumps(receipt))
    return 0


def cmd_poll_tickets(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    if rt.auditor is None:
        print(
            "ERROR: PANOPTICON_BASE_URL and HM_SITE_TOKEN required for poll-tickets",
            file=sys.stderr,
        )
        return 1
    result = poll_tickets(rt)
    print(canonical_dumps(result.as_dict()))
    return 0


def cmd_owner(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    resolution = "approved" if args.owner_cmd == "approve" else "denied"
    try:
        child = local_resolve(
            rt,
            args.receipt_id,
            resolution,
            note=args.note,
        )
    except WaitingOnPlaneError as exc:
        print(f"ERROR: waiting on plane: {exc}", file=sys.stderr)
        return 2
    print(
        canonical_dumps(
            {
                "receipt_id": child.get("receipt_id"),
                "parent_id": child.get("parent_id"),
                "resolution": resolution,
                "decision": (child.get("policy") or {}).get("decision"),
                "purpose": child.get("purpose"),
                "resolved_by": (child.get("human") or {}).get("resolved_by"),
            }
        )
    )
    return 0


def cmd_incident(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    cmd = args.incident_cmd
    if cmd == "list":
        rows = []
        for rec in reversed(rt.incidents.list_incidents()):
            idx = rt.incidents.index_get(str(rec.get("incident_id") or "")) or {}
            rows.append(
                {
                    "incident_id": rec.get("incident_id"),
                    "kind": rec.get("kind"),
                    "status": rec.get("status"),
                    "severity": rec.get("severity"),
                    "opened_at": rec.get("opened_at"),
                    "closed_at": rec.get("closed_at"),
                    "close_reason": rec.get("close_reason"),
                    "primary_subjects": rec.get("primary_subjects") or [],
                    "receipt_count": len(idx.get("receipt_ids") or []),
                    "ticket_count": len(idx.get("ticket_ids") or []),
                    "grant_active": bool((rec.get("flags") or {}).get("grant_active")),
                }
            )
        print(canonical_dumps({"incidents": rows, "count": len(rows)}))
        return 0
    if cmd == "close":
        try:
            rec = rt.incidents.close_human(args.id, now=rt.clock.now())
        except GrantActiveError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        except IncidentError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if rec is None:
            print("ERROR: incident close write failed", file=sys.stderr)
            return 1
        print(canonical_dumps(rec))
        return 0
    if cmd == "sweep":
        result = rt.incidents.sweep(rt.clock.now())
        print(canonical_dumps(result))
        return 0
    if cmd == "open-ops":
        rec = rt.incidents.open_or_join_ops(
            site_id=rt.config.site_id,
            opened_at=rt.clock.now(),
            opened_by={"kind": "human", "id": "aimmune-cli/incident"},
            severity=args.severity,
            summary_redacted=args.summary,
            opening_trace_id=args.trace_id or "cli-open-ops",
            node=args.node,
            unit=args.unit,
            health_class=args.health_class,
        )
        if rec is None:
            print("ERROR: ops incident write failed", file=sys.stderr)
            return 1
        print(canonical_dumps(rec))
        return 0
    print(f"ERROR: unknown incident command {cmd}", file=sys.stderr)
    return 1


def cmd_ui_snapshot(args: argparse.Namespace) -> int:
    rt = _runtime_from_args(args)
    snap = build_snapshot(rt, limit=args.limit)
    print(canonical_dumps(snap))
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    """Print env checklist; optionally spawn Next.js in ui/."""
    cfg = load_config(state_dir=args.state_dir, site_id=args.site_id)
    token_set = bool(cfg.ui_token)
    checklist = {
        "AIMMUNE_UI_TOKEN": "set" if token_set else "MISSING (required to serve)",
        "AIMMUNE_UI_HOST": cfg.ui_host,
        "AIMMUNE_UI_PORT": cfg.ui_port,
        "AIMMUNE_STATE_DIR": str(cfg.state_dir),
        "SITE_ID": cfg.site_id,
        "AIMMUNE_PLANE_REACHABLE": cfg.plane_reachable,
        "listen": f"{cfg.ui_host}:{cfg.ui_port}",
        "bind_note": (
            "loopback default; set AIMMUNE_UI_HOST=0.0.0.0 only as an explicit opt-in"
            if cfg.ui_host in {"127.0.0.1", "localhost", "::1"}
            else "non-loopback bind is an explicit opt-in"
        ),
    }
    print(canonical_dumps(checklist))
    if not args.start:
        print(
            "run: cd ui && npm install && npm run dev\n"
            f"  (binds {cfg.ui_host}:{cfg.ui_port}; export AIMMUNE_UI_TOKEN first)",
            file=sys.stderr,
        )
        return 0 if token_set else 1
    if not token_set:
        print("ERROR: AIMMUNE_UI_TOKEN is required to start the UI", file=sys.stderr)
        return 1
    ui_dir = Path(args.ui_dir) if args.ui_dir else Path.cwd() / "ui"
    if not (ui_dir / "package.json").is_file():
        print(f"ERROR: Next.js app not found at {ui_dir}", file=sys.stderr)
        return 1
    npm = shutil.which("npm")
    if not npm:
        print("ERROR: npm not found", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env.setdefault("AIMMUNE_UI_HOST", cfg.ui_host)
    env.setdefault("AIMMUNE_UI_PORT", str(cfg.ui_port))
    cmd = [npm, "run", "dev", "--", "-H", cfg.ui_host, "-p", str(cfg.ui_port)]
    return subprocess.call(cmd, cwd=ui_dir, env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aimmune", description="AImmune site executor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cycle = sub.add_parser("cycle", help="run one detect+expiry cycle (drain/poll if plane up)")
    _add_shared(cycle)
    cycle.set_defaults(func=cmd_cycle)

    loop = sub.add_parser("loop", help="run cycles every AIMMUNE_CYCLE_SECONDS (default 120)")
    _add_shared(loop)
    loop.add_argument("--seconds", type=int, default=None)
    loop.set_defaults(func=cmd_loop)

    verify = sub.add_parser("verify-chain", help="verify receipt hash chain")
    _add_shared(verify)
    verify.set_defaults(func=cmd_verify)

    drain = sub.add_parser("drain", help="POST pending notify queue to fyber.auditor")
    _add_shared(drain)
    drain.set_defaults(func=cmd_drain)

    poll = sub.add_parser(
        "poll-tickets",
        help="GET auditor watches and apply/ack resolved intent (no long-poll)",
    )
    _add_shared(poll)
    poll.set_defaults(func=cmd_poll_tickets)

    preempt = sub.add_parser(
        "preempt",
        help="Hypermesh preempt (separate from the IDS cycle; shared receipt/notify)",
    )
    preempt_sub = preempt.add_subparsers(dest="preempt_cmd", required=True)

    def _add_preempt_shared(p: argparse.ArgumentParser) -> None:
        _add_shared(p)
        p.add_argument("--reason-code", default="health_evacuate")
        p.add_argument(
            "--execute",
            action="store_true",
            help="owner-console ack: execute-eligible under the strict matrix",
        )

    sell = preempt_sub.add_parser("sell-pause", help="propose/execute hypermesh.sell_pause")
    _add_preempt_shared(sell)
    sell.add_argument("--device-id", required=True)
    sell.add_argument("--until", default=None, help="optional RFC3339 pause deadline")
    sell.set_defaults(func=cmd_preempt, preempt_cmd="sell_pause")

    stop = preempt_sub.add_parser("lease-stop", help="propose/execute hypermesh.lease_stop")
    _add_preempt_shared(stop)
    stop.add_argument("--device-id", required=True)
    stop.add_argument("--lease-id", required=True)
    stop.set_defaults(func=cmd_preempt, preempt_cmd="lease_stop")

    drain_p = preempt_sub.add_parser(
        "drain",
        help="H3: sell_pause then lease_stop for one device (explicit ids)",
    )
    _add_preempt_shared(drain_p)
    drain_p.add_argument("--device-id", required=True)
    drain_p.add_argument("--lease-id", required=True)
    drain_p.add_argument("--until", default=None)
    drain_p.set_defaults(func=cmd_preempt, preempt_cmd="drain")

    run_p = preempt_sub.add_parser(
        "run",
        help="drain the preempt execute queue (auditor-approved hypermesh.*)",
    )
    _add_shared(run_p)
    run_p.set_defaults(func=cmd_preempt, preempt_cmd="run")

    incident = sub.add_parser(
        "incident",
        help="local fyber.incident/v0 overlay (list / close / sweep; never gates contain)",
    )
    incident_sub = incident.add_subparsers(dest="incident_cmd", required=True)

    inc_list = incident_sub.add_parser("list", help="list local incidents + index counts")
    _add_shared(inc_list)
    inc_list.set_defaults(func=cmd_incident, incident_cmd="list")

    inc_close = incident_sub.add_parser("close", help="human-close an incident (refused if grant_active)")
    _add_shared(inc_close)
    inc_close.add_argument("--id", required=True, help="incident UUID")
    inc_close.set_defaults(func=cmd_incident, incident_cmd="close")

    inc_sweep = incident_sub.add_parser(
        "sweep",
        help="auto_quiet close (security 24h / ops 2h, no new linked receipts)",
    )
    _add_shared(inc_sweep)
    inc_sweep.set_defaults(func=cmd_incident, incident_cmd="sweep")

    inc_ops = incident_sub.add_parser(
        "open-ops",
        help="open or join an ops incident (tests/dev; 1h join window)",
    )
    _add_shared(inc_ops)
    inc_ops.add_argument("--severity", default="high")
    inc_ops.add_argument("--summary", default="cli open-ops")
    inc_ops.add_argument("--health-class", default=None)
    inc_ops.add_argument("--node", default=None)
    inc_ops.add_argument("--unit", default=None)
    inc_ops.add_argument("--trace-id", default=None)
    inc_ops.set_defaults(func=cmd_incident, incident_cmd="open-ops")

    owner = sub.add_parser(
        "owner",
        help="site-local approve/deny of a held companion (plane-down or no ticket)",
    )
    owner_sub = owner.add_subparsers(dest="owner_cmd", required=True)
    for action, help_text in (
        ("approve", "locally approve a held companion and apply"),
        ("deny", "locally deny a held companion (observe only)"),
    ):
        p = owner_sub.add_parser(action, help=help_text)
        _add_shared(p)
        p.add_argument("--receipt-id", required=True)
        p.add_argument(
            "--note",
            default=None,
            help="optional short redacted annotate note (max 500)",
        )
        p.set_defaults(func=cmd_owner, owner_cmd=action)

    snap = sub.add_parser(
        "ui-snapshot",
        help="print a redacted JSON snapshot of site state for the UI",
    )
    _add_shared(snap)
    snap.add_argument("--limit", type=int, default=50)
    snap.set_defaults(func=cmd_ui_snapshot)

    ui = sub.add_parser(
        "ui",
        help="print UI env checklist; --start spawns Next.js (cd ui && npm run dev)",
    )
    _add_shared(ui)
    ui.add_argument("--start", action="store_true", help="spawn Next.js after the checklist")
    ui.add_argument("--ui-dir", type=Path, default=None)
    ui.set_defaults(func=cmd_ui)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
