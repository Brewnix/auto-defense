# Slice 3 — incident overlay (`fyber.incident/v0`)

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Spec (source of truth — do not fork):**  
[`incident-binding-v0.md`](../vendor/inference-iface/docs/incident-binding-v0.md)

Site-local overlay case that groups receipt cycles. A `trace_id` is one cycle. An `incident_id` is the multi-cycle case. Contain and `firewall.block_ip` **never** wait on this store. Binding is the **side index only** — no additive `incident_id` on receipts/tickets, no `schemas/` amend, no `schemas/incident.v0.json`. Privilege-grant mint is slice 7.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | Close clocks + ops kind + preempt `lease_stop` require-incident + UI enrich + acceptance tests 1–8. **Not** privilege_grant mint. |
| B | Ops join default **1h** from `opened_at`. Auto-close ops = **2h with no new linked receipts** (proxy for health clear until health-watch sensors exist). Do **not** invent Suricata/WAN polls. |
| C | Auto-close runner at the **end** of `aimmune cycle` (never blocks detect/contain) + CLI `aimmune incident sweep` / `aimmune incident close --id …`. |
| D | Grants: side index `grant_ids` + `flags.grant_active`. Refuse close while active. Until slice 7 only test-injected grants. Acceptance #4 = unit reject helper. |
| E | `lease_stop` **execute** requires an open `incident_id`; if missing → force propose/hold+notify. Do not silent-execute unscoped. `sell_pause` must not invent a security incident; ops preferred for health. |
| F | **Side index only.** No receipt/ticket schema amend. Do not bump the iface pin. |

## What this slice includes

| Piece | Module | Notes |
|-------|--------|--------|
| Store | `aimmune.incident.minimal.IncidentStore` | Security + ops open/join, human close, `auto_quiet` sweep, grant stub |
| Grant reject | `require_grant_incident_id` | Stub until slice 7 mint |
| Cycle | `aimmune.cycle` | Sweep after detect/expiry (and plane sync). Sweep failure never blocks contain |
| Preempt | `aimmune.preempt.policy` / `runner` | `lease_stop` execute needs an open incident; health `sell_pause` opens/joins ops |
| CLI | `aimmune incident` | `list` · `close --id` · `sweep` · `open-ops` (dev/tests) |
| UI | `/incidents` + `ui-snapshot` | Full fyber.incident/v0 fields + index counts; human close button |

## Kinds, join, close

Two kinds only: `security` and `ops`. Never join across that line. Status is `open` or `closed` only.

| Kind | Dominant subject `[0]` | Join window (from `opened_at`) | Auto-close quiet |
|------|------------------------|--------------------------------|------------------|
| `security` | `{kind: ip, value}` | **4h** | **24h** with no new linked receipts |
| `ops` | `node_unit {kind,node,unit}` or `health_class {kind,value}` | **1h** | **2h** with no new linked receipts (**proxy** for health-clear) |

Quiet is **per-incident linked receipts only**. Other IPs, other kinds, and unscoped observe do not reset the clock.

Reopen after close = **new** `incident_id`. Closed never joins. Severity is a rolling max while open.

### Ops quiet proxy (not health-clear)

The binding spec’s ops auto-close is “2h after health clear”. This slice has no Suricata / disk / WAN sensors. Until health-watch exists, ops `auto_quiet` is **2h with no new receipts linked to that incident**. Documented here so later slices can replace the proxy without changing the overlay object.

## Triggers

| Event | Action |
|-------|--------|
| Critical contain / hold / propose | open or join **security** (already slices 1–2) |
| Expiry | inherit parent only; never open new |
| Observe / unscoped | no incident |
| Health `sell_pause` | **ops** preferred; do not invent security |
| `lease_stop` execute | require existing **open** incident; else propose + notify |
| Cycle end | `sweep` (`auto_quiet`) after detect/expiry/plane sync |

Incident write failure (`fail_next_write` / `OSError`) returns `None`. Callers still act. Attach the receipt later via the side index when an id exists (axiom 3).

## Grants (stub)

Side index:

```json
{
  "incident_id": "<uuid>",
  "receipt_ids": [],
  "ticket_ids": [],
  "grant_ids": [],
  "grants": [{"grant_id": "<uuid>", "active_until": "…"}],
  "last_receipt_at": "…"
}
```

`flags.grant_active` or a grant `active_until` in the future blocks human close and auto-close. Helpers: `attach_grant`, `set_grant_active`. `require_grant_incident_id` rejects a grant body with missing / empty / null `incident_id`. No mint UX.

## State directory

Same paths as slice 1 (do not rename):

```
$AIMMUNE_STATE_DIR/
  incidents.jsonl
  incident_index.jsonl
```

## CLI

```bash
python -m aimmune incident list
python -m aimmune incident close --id <uuid>    # human; exit 2 if grant_active
python -m aimmune incident sweep                # auto_quiet
python -m aimmune incident open-ops --health-class health_disk --summary "…"
python -m aimmune cycle                         # detect + expiry + optional plane + sweep
```

Offline (`AIMMUNE_PLANE_REACHABLE=false`) open / close / sweep still works. Plane mirror is out of scope.

## UI

`/incidents` shows kind, status, subjects, severity, opening links, linked receipt/ticket counts from the snapshot. Human **Close** spawns `aimmune incident close --id`. Grant-active refuse is a clear error. Snapshot serializer includes full `fyber.incident/v0` fields plus the index summary and still strips prompts / EVE. No grant mint. No IR chat.

## Tests

`tests/test_incident.py` maps to binding acceptance 1–8, plus `auto_quiet` on `FrozenClock` and preempt `lease_stop` execute without an incident → no execute.

```bash
pytest -q
python scripts/validate-iface-pin.py
cd ui && npm ci && npm run lint && npm run typecheck && npm test
```

## Out of scope

`schemas/incident.v0.json` · required receipt `incident_id` · plane mirror · `contained` / `monitoring` · 24h **join** · `supersedes_incident_id` · EVE on the incident · grant mint · gating contain on incident write · bumping the iface pin · Suricata/WAN health polls.
