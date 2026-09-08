# Slice 2 — `notify.operator` → fyber.auditor client

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Specs (source of truth — do not fork):**  
[`notify-operator-audit-door.md`](../vendor/inference-iface/docs/notify-operator-audit-door.md) · [`fyber-auditor-api-v0.md`](../vendor/inference-iface/docs/fyber-auditor-api-v0.md) · [`docs/plane-client.md`](plane-client.md)

Site drains the local notify queue to Panopticon `#39` (`POST /api/v1/auditor/v0/tickets`), polls `GET` each cycle, applies **approved / denied / timed_out / amended** on the site, writes a **child** `fyber.receipt/v0`, then `POST …/ack`. Resolve is **intent**. Actuation source of truth is the site receipt. UI must **not** claim blocked from resolve alone.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | Drain + poll at **end** of each cycle when the plane is reachable (short timeout). Also CLI `aimmune drain` / `aimmune poll-tickets`. Detect / expiry never wait on a long plane RTT. |
| B | Persist a **held companion snapshot** on enqueue (`call_id`, `tool`, `args`, `subject`). Old queue rows without `held` load the held receipt by `receipt_id` and take the non-`notify.operator` proposal. |
| C | Poll every cycle (120s default). **No long-poll.** Plane owns `timed_out`. |
| D | **Phase A only** — no `post_action_audit`. |
| E | On propose / hold enqueue, open or join a minimal local security incident (side-record). Never wait on the plane. |
| F | Tests: httpx mock create / get / resolve / ack; idempotent create; approved → child apply + ack; amended `ttl_s` only / reject unknown keys client-side; plane down leaves the queue pending. |

## What this slice includes

| Piece | Module | Notes |
|-------|--------|--------|
| Auditor client | `aimmune.auditor.client` | `POST` create, `GET`, `POST` ack. **No resolve.** Site token. |
| Watch file | `aimmune.auditor.watch` | `$STATE_DIR/auditor_watch.jsonl` |
| Drain | `aimmune.notify.drain` | Queue → ticket body → upsert → `mark_drained(ticket_id)` → watch |
| Poll / apply | `aimmune.notify.drain` | On `resolved`, apply + child receipt + ack |
| Held snapshot | `aimmune.notify.held` + queue enqueue | Compat with slice-1 rows |
| Cycle | `aimmune.cycle` | Detect + expiry first; drain/poll only if `plane_reachable` |
| CLI | `aimmune drain` · `aimmune poll-tickets` | Explicit; still short-timeout |

## Plane doors (site token)

Transport: **WireGuard** via `PANOPTICON_BASE_URL`. Auth: `Authorization: Bearer ${HM_SITE_TOKEN}`. `SITE_ID` must match the token site. **Not Tailscale.**

| Method | Path | Who |
|--------|------|-----|
| `POST` | `/api/v1/auditor/v0/tickets` | site (idempotent upsert) |
| `GET` | `/api/v1/auditor/v0/tickets/{id}` | site |
| `POST` | `/api/v1/auditor/v0/tickets/{id}/ack` | site |
| `POST` | `/api/v1/auditor/v0/tickets/{id}/resolve` | **plane only — not implemented here** |

Default client timeout is **3s** (`AIMMUNE_PLANE_TIMEOUT_S`). Create upsert key is `(site_id, receipt_id)` when `receipt_id` is set.

## Site behavior after `GET` `status: resolved`

| Resolution | Site |
|------------|------|
| `approved` | Re-execute the held companion (`firewall.block_ip` / `firewall.unblock_ip`). Child receipt; `parent_id` = held receipt. Then ack. |
| `denied` | `observe`. Child receipt. Then ack. |
| `timed_out` | Same as denied for actuation. Plane owns the timeout. |
| `amended` | Apply **allowlisted `ttl_s` only**. Unknown / extra patch keys are **rejected client-side** (no companion apply). Annotate. Then ack. |

Never rewrite the original held receipt. Never treat resolve as a block.

## State directory (additions)

```
$AIMMUNE_STATE_DIR/
  notify_queue.jsonl      # slice 1; now includes held snapshot
  auditor_watch.jsonl     # slice 2
```

## Environment

Same as slice 1, plus:

| Name | Required (plane-up) | Meaning |
|------|---------------------|---------|
| `PANOPTICON_BASE_URL` | yes | Gateway origin over WireGuard, no trailing slash |
| `HM_SITE_TOKEN` | yes | `hm_site_…` machine token |
| `SITE_ID` | yes | Must equal token `site_id` |
| `AIMMUNE_PLANE_REACHABLE` | cycle drain/poll | `true` to sync at cycle end |
| `AIMMUNE_PLANE_TIMEOUT_S` | no (default `3`) | Short HTTP timeout |

## Run

```bash
export PANOPTICON_BASE_URL=https://panopticon.wg.example
export HM_SITE_TOKEN=hm_site_…
export SITE_ID=net-tn-cottage
export AIMMUNE_PLANE_REACHABLE=1
export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_EXEC_MOCK=1

python -m aimmune cycle              # detect+expiry, then drain+poll if reachable
python -m aimmune drain              # queue → tickets (CLI; does not wait on detect)
python -m aimmune poll-tickets       # GET watches; apply/ack resolved
pytest
```

## Out of scope

Phase B `post_action_audit` · privilege grants / SociACL · preempt / H3 · Tailscale · `schemas/` edits · site-implemented resolve. AImmune UI is slice 5.

## Intent vs actuation

`POST …/resolve` is plane intent. The site writes the apply / observe receipt, then acks. Copy and UI must not say the subject is blocked until that ack (or a timed_out waiting state) **and** the acked receipt applied a block.
