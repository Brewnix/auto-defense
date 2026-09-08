"""CLI: cycle, loop, status, drain, poll-tickets, preempt, incident, grant, owner, ui-snapshot.

Plane resolve / grant resolve stay plane-only. Site-local owner
approve/deny is slice 5. Incident close/sweep is slice 3 (overlay;
never gates contain). Home grant mint is site-local only.
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
from aimmune.grants.client import GrantError
from aimmune.grants.home import PlaneUpMintError, mint_local
from aimmune.grants.hotreload import elevation_from_runtime
from aimmune.grants.poll import poll_grants
from aimmune.grants.propose import build_asks, build_propose_body
from aimmune.grants.validate import GrantValidationError
from aimmune.incident.minimal import GrantActiveError, IncidentError
from aimmune.notify.drain import drain_queue, poll_tickets
from aimmune.owner.annotate import local_annotate
from aimmune.owner.local import LocalResolveError, WaitingOnPlaneError, local_resolve
from aimmune.preempt.runner import cli_preempt, run_preempt_queue
from aimmune.receipt.chain import verify_chain
from aimmune.status import build_status, format_status_text
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
        "grants": result.grants,
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


def cmd_status(args: argparse.Namespace) -> int:
    """Read-only summary. Always exits 0 (informational)."""
    cfg = load_config(
        state_dir=args.state_dir,
        site_id=args.site_id,
        eve_path=args.eve,
        whitelist_path=args.whitelist,
    )
    payload = build_status(cfg)
    if args.json:
        print(canonical_dumps(payload))
    else:
        print(format_status_text(payload), end="")
    return 0


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
    if args.owner_cmd == "annotate":
        try:
            child = local_annotate(rt, args.receipt_id, args.note)
        except LocalResolveError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(
            canonical_dumps(
                {
                    "receipt_id": child.get("receipt_id"),
                    "parent_id": child.get("parent_id"),
                    "purpose": child.get("purpose"),
                    "decision": (child.get("policy") or {}).get("decision"),
                    "annotate": True,
                }
            )
        )
        return 0
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
    except LocalResolveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
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


def _asks_from_args(args: argparse.Namespace) -> list:
    return build_asks(
        tools=list(args.tool or []),
        rate_limit=args.rate_limit,
        model_tier=args.tier,
        budget_tokens=args.budget,
        template_ids=list(args.template or []),
    )


def cmd_grant(args: argparse.Namespace) -> int:
    """propose / get / list / poll / mint-local / status. Resolve is plane-only."""
    rt = _runtime_from_args(args)
    cmd = args.grant_cmd
    if cmd == "status":
        now = rt.clock.now()
        if args.incident_id:
            grant = rt.grants.active_for_incident(args.incident_id, now)
            elev = elevation_from_runtime(rt, incident_id=args.incident_id, now=now)
            print(
                canonical_dumps(
                    {
                        "incident_id": args.incident_id,
                        "grant": grant,
                        "allow_model_execute": elev.allow_model_execute,
                        "profile": elev.profile,
                        "source": elev.source,
                        "tool_allowlist": sorted(elev.tool_allowlist),
                    }
                )
            )
            return 0
        rows = []
        for grant in rt.grants.list():
            rows.append(
                {
                    "grant_id": grant.get("grant_id"),
                    "incident_id": grant.get("incident_id"),
                    "status": grant.get("status"),
                    "active_until": grant.get("active_until"),
                    "rails_profile": (grant.get("resolution") or {}).get("rails_profile")
                    or grant.get("rails_profile_requested"),
                }
            )
        print(canonical_dumps({"grants": rows, "count": len(rows)}))
        return 0
    if cmd == "poll":
        result = poll_grants(rt)
        print(canonical_dumps(result))
        return 0 if not result.get("errors") else 1
    if cmd == "list":
        if rt.grant_client is None:
            rows = rt.grants.list()
            if args.status:
                rows = [r for r in rows if r.get("status") == args.status]
            if args.incident_id:
                rows = [r for r in rows if r.get("incident_id") == args.incident_id]
            print(canonical_dumps({"grants": rows, "count": len(rows), "source": "cache"}))
            return 0
        try:
            rows = rt.grant_client.list_grants(
                status=args.status, incident_id=args.incident_id
            )
        except GrantError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(canonical_dumps({"grants": rows, "count": len(rows), "source": "plane"}))
        return 0
    if cmd == "get":
        if rt.grant_client is None:
            row = rt.grants.get(args.id)
            if row is None:
                print("ERROR: grant not in site cache", file=sys.stderr)
                return 1
            print(canonical_dumps(row))
            return 0
        try:
            row = rt.grant_client.get_grant(args.id)
        except GrantError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        rt.grants.upsert(row)
        print(canonical_dumps(row))
        return 0
    if cmd == "propose":
        try:
            asks = _asks_from_args(args)
            body = build_propose_body(
                site_id=rt.config.site_id,
                incident_id=args.incident_id,
                reason_redacted=args.reason,
                asks=asks,
                profile=args.profile,
                ttl_s=args.ttl,
                now=rt.clock.now(),
                trace_id=args.trace_id,
                ticket_id=args.ticket_id,
                requested_by={
                    "kind": args.requested_by_kind,
                    "id": args.requested_by_id,
                },
            )
        except (GrantValidationError, IncidentError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if rt.grant_client is None:
            print(
                "ERROR: PANOPTICON_BASE_URL and HM_SITE_TOKEN required for propose; "
                "use mint-local when the plane is down",
                file=sys.stderr,
            )
            return 1
        try:
            created = rt.grant_client.propose(
                body,
                idempotency_key=args.idempotency_key
                or f"{rt.config.site_id}:{args.incident_id}:{body['trace_id']}",
            )
        except GrantError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if created.get("grant_id"):
            rt.grants.upsert(created)
        print(canonical_dumps(created))
        return 0
    if cmd == "mint-local":
        try:
            grant = mint_local(
                store=rt.grants,
                incidents=rt.incidents,
                site_id=rt.config.site_id,
                incident_id=args.incident_id,
                ticket_id=args.ticket_id,
                notes=args.notes,
                reason_redacted=args.reason,
                asks=_asks_from_args(args),
                profile=args.profile,
                ttl_s=args.ttl,
                trace_id=args.trace_id,
                requested_by={
                    "kind": args.requested_by_kind,
                    "id": args.requested_by_id,
                },
                now=rt.clock.now(),
                plane_reachable=rt.config.plane_reachable,
            )
        except PlaneUpMintError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        except (GrantValidationError, IncidentError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(canonical_dumps(grant))
        return 0
    print(f"ERROR: unknown grant command {cmd}", file=sys.stderr)
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
        "AIMMUNE_OWNER_PRINCIPALS": list(cfg.owner_principals),
        "AIMMUNE_UI_SMOKE_PRINCIPAL": "set" if cfg.ui_smoke_principal else "unset",
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

    status = sub.add_parser(
        "status",
        help="read-only site summary (journald companion; always exits 0)",
    )
    _add_shared(status)
    status.add_argument(
        "--json",
        action="store_true",
        help="print canonical JSON instead of the text dump",
    )
    status.set_defaults(func=cmd_status)

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

    grant = sub.add_parser(
        "grant",
        help=(
            "privilege grant propose/get/list/poll/mint-local/status. "
            "Resolve/revoke are plane-only — this CLI does not call them."
        ),
    )
    grant_sub = grant.add_subparsers(dest="grant_cmd", required=True)

    def _add_grant_ask_flags(p: argparse.ArgumentParser) -> None:
        _add_shared(p)
        p.add_argument("--incident-id", required=True)
        p.add_argument("--profile", default="ir_elevated", choices=("ir_elevated", "break_glass"))
        p.add_argument("--ttl", type=int, default=1800, help="requested TTL seconds (clamped)")
        p.add_argument("--reason", required=True, help="redacted reason (no prompts)")
        p.add_argument("--ticket-id", default=None)
        p.add_argument("--trace-id", default=None)
        p.add_argument("--tool", action="append", default=[], help="tool_allowlist_add entry (repeat)")
        p.add_argument("--tier", default=None, help="model_tier ask")
        p.add_argument("--budget", type=int, default=None, help="budget_tokens.max_tokens")
        p.add_argument("--template", action="append", default=[], help="prompt_route template id")
        p.add_argument("--rate-limit", type=int, default=None, help="blocks_per_hour cap")
        p.add_argument("--requested-by-kind", default="human", choices=("human", "automation"))
        p.add_argument("--requested-by-id", default="aimmune-cli/grant")

    g_propose = grant_sub.add_parser(
        "propose",
        help="POST a grant propose to the plane (idempotent site_id+incident_id+trace_id)",
    )
    _add_grant_ask_flags(g_propose)
    g_propose.add_argument("--idempotency-key", default=None)
    g_propose.set_defaults(func=cmd_grant, grant_cmd="propose")

    g_get = grant_sub.add_parser("get", help="GET one grant (incl. terminal) from plane or cache")
    _add_shared(g_get)
    g_get.add_argument("--id", required=True, help="grant UUID")
    g_get.set_defaults(func=cmd_grant, grant_cmd="get")

    g_list = grant_sub.add_parser(
        "list",
        help="list grants (plane when configured, else site cache)",
    )
    _add_shared(g_list)
    g_list.add_argument("--status", default=None, choices=("proposed", "approved", "denied", "timed_out", "revoked", "expired"))
    g_list.add_argument("--incident-id", default=None)
    g_list.set_defaults(func=cmd_grant, grant_cmd="list")

    g_poll = grant_sub.add_parser(
        "poll",
        help="cycle-end poll: approved/proposed by incident → cache (never blocks contain)",
    )
    _add_shared(g_poll)
    g_poll.set_defaults(func=cmd_grant, grant_cmd="poll")

    g_mint = grant_sub.add_parser(
        "mint-local",
        help="home offline mint into the site cache (plane-down only; never POST /resolve)",
    )
    _add_grant_ask_flags(g_mint)
    g_mint.add_argument("--notes", required=True, help="required redacted notes for local mint")
    g_mint.set_defaults(func=cmd_grant, grant_cmd="mint-local", profile="break_glass")

    g_status = grant_sub.add_parser(
        "status",
        help="show cached grants / active elevation for an incident",
    )
    _add_shared(g_status)
    g_status.add_argument("--incident-id", default=None)
    g_status.set_defaults(func=cmd_grant, grant_cmd="status")

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

    ann = owner_sub.add_parser("annotate", help="write-only redacted annotate (does not resolve)")
    _add_shared(ann)
    ann.add_argument("--receipt-id", required=True)
    ann.add_argument("--note", required=True, help="short redacted annotate note (max 500)")
    ann.set_defaults(func=cmd_owner, owner_cmd="annotate")

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
