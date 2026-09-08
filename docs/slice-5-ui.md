# Slice 5 — AImmune UI v0

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Specs (source of truth — do not fork):**  
[`docs/slice-2-auditor.md`](slice-2-auditor.md) · [`docs/slice-4-preempt.md`](slice-4-preempt.md) · [`docs/plane-client.md`](plane-client.md)

Site-local operator console. Tickets are **intent**. Actuation source of truth is the site receipt chain. The UI must **not** claim blocked from resolve alone. No `/v1/ir/chat`, no prompts, no EVE payloads.

## Locked design (Chris 2026-09-07/08)

| | Rule |
|---|------|
| A | Next.js App Router + shadcn/ui in this repo (`ui/`). Not FastAPI+HTMX. |
| B | Auth is `AIMMUNE_UI_TOKEN` bearer. Bind **127.0.0.1** by default (`AIMMUNE_UI_HOST` / `AIMMUNE_UI_PORT`). SociACL is slice 8. |
| C | Site UI may **local-approve/deny** a held companion when `plane_reachable=false` **or** no plane ticket exists yet. When an auditor watch/ticket exists and the plane is up, show waiting-on-plane (slice 2 poll applies) — **do not double-resolve** from the site. |
| D | Write surface is local approve/deny plus optional grant propose / plane-down mint-local. Optional short redacted annotate note. No rule-pack editor, no SID UI. |
| E | Run: `cd ui && npm run dev` / production `npm run start`. Optional `python -m aimmune ui` prints the env checklist and can `--start` Next. |
| F | Pure status-copy helpers + unit tests. Never “blocked” from resolve alone; pending-intent; timed_out waiting; blocked only after a site apply receipt that actually blocked **and** the ack path. Iface-pin CI stays. UI CI is lint / typecheck / vitest (no Playwright). |

## What this slice includes

| Piece | Module | Notes |
|-------|--------|--------|
| Status copy | `aimmune.ui.status` | Pure map of queue / watch / apply receipt → display enum + label |
| Snapshot | `aimmune.ui.snapshot` | Redacted JSON for the console (`aimmune ui-snapshot`) |
| Local resolve | `aimmune.owner.local` | Reuses `aimmune.notify.drain.apply_resolution` — no forked apply |
| CLI | `aimmune owner approve\|deny` · `ui-snapshot` · `ui` | Writes stay in Python |
| Console | `ui/` | Next.js App Router + shadcn. Reads spawn `ui-snapshot`; writes spawn owner CLI |
| Auth | `ui/proxy.ts` + `/api/session` | Bearer or httpOnly cookie. Fail closed if token unset in production |

## Status copy (source of truth)

Python tests in `tests/test_ui_status.py` are the contract. The snapshot embeds `status_catalog` so the UI does not invent labels.

| Status | When | Blocked? |
|--------|------|----------|
| `pending_intent` | Held companion, not yet applied | no |
| `waiting_on_plane` | Non-terminal auditor watch **and** plane reachable | no |
| `timed_out_waiting` | Plane resolution `timed_out`, site has not written the apply receipt | no |
| `approved_pending_apply` | Plane/local intent `approved`, site has not applied | no |
| `applied_pending_ack` | Site apply receipt applied a block; ack not completed | no |
| `blocked` | Site apply receipt applied `firewall.block_ip` **and** ack / local-owner ack | **yes** |
| `observed` | Apply ran and did **not** block (deny / timed_out observe / failed block) | no |

Resolve (`approved` / `denied` / `timed_out` / `amended`) **alone** is never `blocked`.

## Local owner approve / deny

`aimmune.owner.local.local_resolve` loads the held companion from the notify queue or receipt, then calls **the same** `apply_resolution` path as `poll-tickets`.

Allowed when:

- `AIMMUNE_PLANE_REACHABLE` is false, **or**
- no non-terminal `auditor_watch` row exists for that receipt

Refused (exit 2 / HTTP 409) when a watch is open **and** the plane is reachable.

After apply:

- the notify queue row is `mark_drained`
- if a watch existed only because the plane was down, it is marked `acked` with `local_owner=true` and `site_acked_receipt_id` so a later poll does not double-apply

Optional `--note` is a short redacted `receipt.annotate` (max 500).

## Pages

| Route | Content |
|-------|---------|
| `/` | site_id, plane_reachable, sell_state (last receipt / env; **stale unknown OK**) |
| `/receipts` | last N receipts — id, **actor kind/id**, purpose, policy.decision, tools, effects, human, parent_id |
| `/holds` | notify_queue + auditor_watch with status copy; local approve/deny when allowed |
| `/incidents` | `incidents.jsonl` overlay (slice 3 enrich: kind / status / subjects / links / counts + human close) |
| `/grants` | slice 7 snapshot list + minimal propose / mint-local; ticket approve ≠ elevation |
| `/preempt` | pending `preempt_queue.jsonl` + recent `hypermesh.*` receipts |
| `/settings` | token field → httpOnly cookie |

**Not present:** IR chat, Hypermesh `/v1/ir/chat`, model chat, rule-pack editor, SID UI.

The API serializer (`aimmune.ui.serialize`) allowlists digest / effect / policy fields and recursively strips prompt / payload / EVE-like keys.

## Environment

Same as slices 1–2 / 4, plus:

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_UI_TOKEN` | unset | **Required to serve.** Production fails closed if missing. |
| `AIMMUNE_UI_HOST` | `127.0.0.1` | Bind address. `0.0.0.0` is an explicit opt-in only. |
| `AIMMUNE_UI_PORT` | `3000` | Port |
| `AIMMUNE_STATE_DIR` | `/var/lib/aimmune` | Receipts / queue / watches / incidents |
| `AIMMUNE_PLANE_REACHABLE` | `false` | Gates waiting-on-plane vs local resolve |
| `AIMMUNE_PYTHON` | `python3` | Interpreter the Next API uses to spawn `python -m aimmune` |
| `AIMMUNE_REPO_ROOT` | parent of `ui/` | Used to set `PYTHONPATH=src` |

## Run against a mock state dir

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
python -m pip install -e '.[dev]'

export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_EXEC_MOCK=1
export SITE_ID=net-tn-cottage
export AIMMUNE_PLANE_REACHABLE=0
export AIMMUNE_UI_TOKEN=dev-token   # pick a local secret; do not commit it

# seed receipts / a hold
python -m aimmune cycle

# checklist (optional --start spawns Next)
python -m aimmune ui
python -m aimmune ui-snapshot --limit 20
python -m aimmune owner approve --receipt-id <held-receipt-id>
python -m aimmune owner deny --receipt-id <held-receipt-id> --note "cottage owner"

cd ui
npm install
npm run dev          # 127.0.0.1:3000
# production:
# npm run build && npm run start
```

Open `http://127.0.0.1:3000/settings`, paste the same token, then use Overview / Receipts / Holds.

`AIMMUNE_UI_HOST=0.0.0.0` is documented only as an explicit opt-in. Prefer loopback + SSH tunnel.

## Tests

```bash
pytest -q
cd ui && npm ci && npm run lint && npm run typecheck && npm test
```

Copy-rule coverage lives in `tests/test_ui_status.py`. Local apply / plane-up refuse lives in `tests/test_owner_local.py`. UI vitest covers the blocked-enum guard and bearer compare.

## Out of scope

SociACL / dual auth (slice 8) · privilege grants (slice 7) · model triage (slice 6) · IR chat · FastAPI+HTMX · `schemas/` edits · bumping the iface pin · site-implemented plane `POST …/resolve`.
