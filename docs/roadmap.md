# AImmune roadmap

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Vertical (locked):** `0 → 1 → 2 → 4 → 5` then package.

Contracts stay in [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface). This repo pins that SHA and implements the site executor + UI. Do not fork or weaken schemas.

## Vertical

| Slice | Status | What |
|-------|--------|------|
| **0** | **done** | Pin iface + plane inventory freeze. Submodule, CI, docs. No executor. |
| **1** | **done** | Zero-LLM OPNsense detect → block → `fyber.receipt/v0` + TTL expiry unblock + local notify queue stub + minimal security incident side-record. Rules actor only. [`docs/slice-1-zero-llm.md`](slice-1-zero-llm.md). |
| **2** | **this PR** | `notify.operator` → fyber.auditor client (`#39` tickets; drain / poll / apply / ack; intent ≠ actuation). [`docs/slice-2-auditor.md`](slice-2-auditor.md). |
| **3** | **parallel after 1** | Incident side index (`fyber.incident/v0` overlay). Never gates contain. |
| **4** | after 2 | Preempt client + H3 drain: `/site/jobs`, `/site/devices`, H4 offline. `lease_id` required. Enqueue ≠ apply. |
| **5** | after 4 | AImmune UI v0 (site SoT; tickets are intent; no `/v1/ir/chat`). |

Then package as one site daemon.

## After the vertical works

| Slice | When | What |
|-------|------|------|
| **6** | later | Model triage (`actor.kind: model`, local-only cottage v0). LLM judges; policy executes. |
| **7** | later | Privilege grant plane store. **After** UI (lock #5). |
| **8** | later | SociACL IR UX (`Check` / `delegate` for human resolve / mint). Dual auth with `hm_site_`. |
| **9** | later | Package: one site daemon, host image wiring. |

Slice 3 may start as soon as slice 1 writes receipts. Do not block 2 / 4 / 5 on 3. Slices 6–8 stay off the critical path until the vertical loop + UI exist.

## Slice 0 exit (landed)

- [`vendor/inference-iface`](../vendor/inference-iface) pins [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ `3621849bbf7c368b1d709356c465883144300208`
- CI: [`.github/workflows/iface-pin.yml`](../.github/workflows/iface-pin.yml) — submodule checkout, fail if pin missing, validate `schemas/*.v0.json` + examples
- Inventory: [`docs/slice-0-inventory.md`](slice-0-inventory.md)
- Plane client: [`docs/plane-client.md`](plane-client.md)

## Slice 1 exit (landed)

- Python package `aimmune` — EVE → bundle → `brewnix-rules/v0.1` → policy → `alias_util` add/delete → receipt hash chain
- Expiry: TTL ledger + `brewnix-rules/expiry` (`execution.status: expired`)
- `propose` / `hold_human` → durable `notify_queue.jsonl` (no plane POST)
- Minimal local `fyber.incident/v0` side-record; contain is not gated on that write
- Tests + pytest CI job; iface-pin CI unchanged
- Runbook: [`docs/slice-1-zero-llm.md`](slice-1-zero-llm.md)

## Slice 2 exit (this PR)

- Held companion snapshot on enqueue; old rows fall back to the held receipt
- `aimmune.auditor.client` — create / get / ack with `HM_SITE_TOKEN` (no resolve)
- Drain queue → `POST /api/v1/auditor/v0/tickets`; `auditor_watch.jsonl`
- Poll watches every cycle (no long-poll); apply approved / denied / timed_out / amended; child receipt; ack
- Cycle-end sync only when `plane_reachable` (3s default timeout); CLI `drain` / `poll-tickets`
- Phase A only; incident open/join on propose/hold; never wait on plane
- Tests (httpx mock) + iface-pin CI unchanged
- Runbook: [`docs/slice-2-auditor.md`](slice-2-auditor.md)

## Not this repo

Panopticon SaaS gateway fork · Hypermesh-router IR chat UI · `schemas/` amends · market / renter surfaces · Tailscale-as-plane-transport.
