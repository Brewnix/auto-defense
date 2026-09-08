"""CLI: cycle, loop, drain, poll-tickets, preempt. Resolve stays plane-only."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from aimmune.canonical import canonical_dumps
from aimmune.config import load_config
from aimmune.cycle import build_runtime, run_cycle
from aimmune.notify.drain import drain_queue, poll_tickets
from aimmune.preempt.runner import cli_preempt, run_preempt_queue
from aimmune.receipt.chain import verify_chain


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

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
