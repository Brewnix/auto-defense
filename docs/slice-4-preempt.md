# Slice 4 — Hypermesh preempt client + H3 drain

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Specs (source of truth — do not fork):**  
[`hypermesh-preempt-v0.md`](../vendor/inference-iface/docs/hypermesh-preempt-v0.md) · [`docs/plane-client.md`](plane-client.md) · Panopticon [`#40`](https://github.com/FyberLabs/panopticon/pull/40) / [`#41`](https://github.com/FyberLabs/panopticon/pull/41)

Brewnix **proposes**. Host **executes**. Drain is two CP jobs sequenced here (H3) — not a Host mega-job. `preempt_mode` stays **`drain`**. Host has no hard-preempt signal; v0 never selects `hard`.

The preempt runner is **separate from the IDS cycle**. Shared receipt chain + notify queue. The Suricata / OPNsense loop never awaits Host job RTT.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | Proposal sources: CLI `aimmune preempt …`; auditor-approved held `hypermesh.*` (slice 2); **and** a thin site_defense rules hook when the site flag is on. Not Suricata-SID→`lease_stop` blindly. |
| B | Default `rails_profile=strict`. `sell_pause` auto only for **rules** + `health_evacuate` / `owner_stop_selling` + `allow_sell_pause_execute`. `lease_stop` under strict = propose+notify unless human approve / owner ack. Profile never implies `hypermesh.*`. Elevated auto deferred to grants (slice 7). |
| C | Stale heartbeat: if `last_heartbeat_at` is older than `AIMMUNE_SELL_STATE_STALE_S` (default **300s**), posture is **unknown** → automated stop-only holds. |
| D | Explicit `device_id` / `lease_id` required. No omit / pick-active. |
| E | Separate preempt runner from IDS cycle (shared receipt/notify). |
| F | Tests: mock `#40`/`#41` + H4; H3 order; pause-fail; site_defense pause-fail exception; plane-down H4; schema-valid tools. |

## What this slice includes

| Piece | Module | Notes |
|-------|--------|--------|
| Site jobs | `aimmune.plane.jobs` | `POST`/`GET /api/v1/hypermesh/site/jobs`. `hm_site_`. `lease_id` required on `lease_stop` (422). No `reason_code` on the job. Enqueue ≠ apply. |
| Live posture | `aimmune.plane.posture` | `GET /api/v1/hypermesh/site/devices/{device_id}`. Copy Host `sell_state`. Brewnix decides staleness. |
| H4 owner | `aimmune.host.owner` | Unix socket `$HOST_STATE_DIR/owner.sock` + bearer `owner.token` **0600**. `POST /v0/sell_pause` · `/v0/lease_stop`. Plane-down only. |
| Matrix | `aimmune.preempt.policy` | Strict execute vs propose. Strip extras (1 pause + ≤8 stops). Rate limit 10 `lease_stop`s / hour / site. |
| H3 | `aimmune.preempt.h3` | Per device: await each `sell_pause` **result** before any `lease_stop`. |
| Hook | `aimmune.preempt.hook` | Flag-gated `site_defense` proposals into the runner. |
| Runner | `aimmune.preempt.runner` | Policy → receipt → H3 if execute-eligible. CLI + queue drain. |
| CLI | `aimmune preempt` | `sell-pause` / `lease-stop` / `drain` / `run`. |

## site_defense rules hook (exact trigger)

**Off by default.** Enable with `AIMMUNE_SITE_DEFENSE_PREEMPT=true`.

Fires only when **all** of the following hold:

1. The flag is on.
2. `AIMMUNE_HYPERMESH_DEVICE_IDS` lists at least one explicit `device_id` (comma-separated). No pick-active.
3. This IDS cycle **applied** a **critical** `firewall.block_ip` (rules path — today `port_scan_burst`).
4. Actor is `kind: rule`.

Then the hook emits **one envelope per configured device** into the preempt runner (propose+notify under strict):

- `hypermesh.sell_pause` with `reason_code: site_defense`
- `hypermesh.lease_stop` **only** when that device has an explicit lease in `AIMMUNE_HYPERMESH_LEASE_IDS` (`device_id:lease_id`, or a bare `lease_id` when exactly one device is configured)

Does **not** fire on high/propose contain, observe, expiry, or a SID match without an applied critical block. Does **not** await Host jobs. Policy matrix still applies (`lease_stop` execute under strict still needs human / owner ack). `preempt_mode` stays `drain`.

## H3 (locked)

Filter execute-eligible `hypermesh.*` (matrix already applied).

1. Sort: all `sell_pause` before any `lease_stop`. Device-scoped. Stable within each group.
2. Per device: await **each** pause **result** before enqueueing **any** stop for that device.
3. Different devices may run independently.
4. Prefer sync await of the pause result.

Pause success: Host `passed=true` **and** `sell_state` ∈ `{paused, draining, off}`. `selling` is not success. `passed=true` + `n/a` is invalid.

**Pause fail (default):** no automated stops; `hold_human` + notify; receipt records the pause failure.

**`site_defense` pause-fail exception:** `reason_code=site_defense` **and** automated **rules** actor **and** stops are execute-eligible → allow stops anyway. Still record the pause failure. Still `drain` (not `hard`).

Stop-only (no pause this cycle): automated stops only when last-known `sell_state` ∈ `{paused, off, n/a}` (or human). Stale heartbeat → unknown → hold. Stop-only while `selling` with a never-attempted pause is **not** the pause-fail exception.

Pause OK + stop fail: keep sell paused. No auto-resume. Continue other stops. Notify on any stop failure.

## Plane vs plane-down

| Plane up | Plane down |
|----------|------------|
| `#40` POST/GET site jobs (`hm_site_`) | Do **not** call site jobs / site GET |
| `#41` GET device `sell_state` | H4 `owner.sock` + `owner.token` |
| Poll until Host `passed` / `failed` | Copy `owner-effects.jsonl` onto the receipt |

Site still writes `fyber.receipt/v0`. Executor names: `panopticon:job:sell_pause` / `panopticon:job:lease_stop` / `hypermesh-host@site:owner`.

Receipt `posture.sell_state` maps Host `{selling, paused, draining, off, n/a}` → `{on, paused, paused, off, n/a}`. Do not invent `paused` from enqueue.

## Environment

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_RAILS_PROFILE` | `strict` | Ceiling only — not a Hypermesh grant |
| `AIMMUNE_ALLOW_SELL_PAUSE_EXECUTE` | `true` | Required (with rules + allowed reason) for auto `sell_pause` |
| `AIMMUNE_ALLOW_STOP_WHILE_SELLING` | `false` | Site flag; stop-only while `selling` |
| `AIMMUNE_SITE_DEFENSE_PREEMPT` | `false` | Thin rules hook |
| `AIMMUNE_HYPERMESH_DEVICE_IDS` | empty | Explicit device list for the hook |
| `AIMMUNE_HYPERMESH_LEASE_IDS` | empty | `device_id:lease_id` or bare id if one device |
| `AIMMUNE_SELL_STATE_STALE_S` | `300` | Heartbeat older than this → unknown |
| `AIMMUNE_LEASE_STOP_RATE` | `10` | `lease_stop`s / hour / site |
| `AIMMUNE_JOB_POLL_TIMEOUT_S` | `30` | Sync await of a site job |
| `AIMMUNE_HOST_STATE_DIR` / `HYPERMESH_STATE_DIR` | unset | Host dir with `owner.sock`, `owner.token`, `owner-effects.jsonl` |
| `PANOPTICON_BASE_URL` / `HM_SITE_TOKEN` / `SITE_ID` | (plane-up) | Same as slice 2. **WireGuard, not Tailscale.** |

## Run

```bash
export PANOPTICON_BASE_URL=https://panopticon.wg.example
export HM_SITE_TOKEN=hm_site_…
export SITE_ID=net-tn-cottage
export AIMMUNE_STATE_DIR=/tmp/aimmune-state

# Propose only (strict; notify queued)
python -m aimmune preempt sell-pause --device-id jetson-cottage-01 --reason-code health_evacuate
python -m aimmune preempt lease-stop --device-id jetson-cottage-01 --lease-id lease-203-0-113-50 --reason-code site_defense

# Owner-console ack → execute via #40 (plane-up) or H4 (plane-down)
python -m aimmune preempt drain --device-id jetson-cottage-01 --lease-id lease-203-0-113-50 --reason-code health_evacuate --execute

# After auditor approve of held hypermesh.* (slice 2 poll enqueues; does not await Host)
python -m aimmune preempt run

# IDS cycle may emit site_defense proposals when the hook flag is on — never Host RTT
export AIMMUNE_SITE_DEFENSE_PREEMPT=1
export AIMMUNE_HYPERMESH_DEVICE_IDS=jetson-cottage-01
python -m aimmune cycle
```

## Out of scope

Privilege grants / `tool_allowlist_add` (slice 7) · AImmune UI (slice 5) · model triage (slice 6) · SociACL · Tailscale · `schemas/` edits · `preempt_mode=hard` · Host mega-job · implying `hypermesh.*` from `rails_profile`.
