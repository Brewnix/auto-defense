# Slice 1 — zero-LLM OPNsense detect → block → receipt

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Specs (source of truth — do not fork):**  
[`zero-llm-opnsense-loop.md`](../vendor/inference-iface/docs/zero-llm-opnsense-loop.md) · [`expiry-unblock-loop.md`](../vendor/inference-iface/docs/expiry-unblock-loop.md) · [`schemas/*.v0.json`](../vendor/inference-iface/schemas)

Site-local Suricata EVE → redacted `fyber.feature_bundle/v0` → `brewnix-rules/v0.1` → `brewnix-policy/v0` → OPNsense `ai_autoblock` alias add/remove → append-only `fyber.receipt/v0` hash chain. Actor is `kind: rule` only. No model, no health-watch, no preempt, no plane auditor client, no UI.

## What this slice includes

| Piece | Module | Notes |
|-------|--------|--------|
| Sensor | `aimmune.sensors.eve_to_bundle` | EVE window → redacted bundle (no payloads) |
| Rules | `aimmune.rules` + `rules/v0.1.yaml` | `port_scan_burst`, `ssh_brute`, `noise_ignore`; N=10, M=20, K=15 |
| Expiry | `aimmune.rules.expiry` + `aimmune.ledger.ttl` | `brewnix-rules/expiry` emits `firewall.unblock_ip` |
| Policy | `aimmune.policy` | whitelist, alias+TTL dedupe, B=30/hour, critical auto, **high → propose** (not observe) |
| Exec | `aimmune.exec.opnsense_alias` | `firewall/alias_util` add/delete; mockable |
| Receipts | `aimmune.receipt.chain` | JSONL; `body_hash` = SHA-256 of canonical JSON with `integrity` omitted |
| Incident | `aimmune.incident.minimal` | Best-effort `{id, kind=security, open}` side-record; **never** gates the block |
| Notify | `aimmune.notify.queue` | Durable local queue for `propose` / `hold_human`; slice 2 drains to fyber.auditor |
| Cycle | `aimmune.cycle` / `python -m aimmune` | One cycle or loop (default **120s**) |

## State directory

Default **`/var/lib/aimmune/`**. Override with `AIMMUNE_STATE_DIR`. This is an env/runtime path, **not** a schema field.

```
$AIMMUNE_STATE_DIR/
  receipts.jsonl
  ttl_ledger.jsonl
  notify_queue.jsonl
  incidents.jsonl
  incident_index.jsonl
  rate_limit.jsonl
```

## Environment

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_STATE_DIR` | `/var/lib/aimmune` | Durable site state |
| `SITE_ID` / `AIMMUNE_SITE_ID` | `net-tn-cottage` | Envelope / receipt `site_id` |
| `AIMMUNE_EVE_PATH` | unset | Suricata `eve.json` (JSONL) |
| `AIMMUNE_WINDOW_S` | `300` | Feature-bundle window |
| `AIMMUNE_CYCLE_SECONDS` | `120` | Loop interval |
| `AIMMUNE_WHITELIST_FILE` | unset | One IP or CIDR per line (`#` comments) |
| `AIMMUNE_RULES_FILE` | packaged `v0.1.yaml` | Override rule pack |
| `AIMMUNE_ALIAS` | `ai_autoblock` | OPNsense alias name |
| `AIMMUNE_RATE_LIMIT_B` | `30` | Max new blocks / hour / site |
| `AIMMUNE_BLOCK_TTL_S` | pack `86400` | Override block TTL |
| `AIMMUNE_PLANE_REACHABLE` | `false` | Receipt posture only (no plane client) |
| `AIMMUNE_WAN_UP` | `true` | Receipt posture / bundle health stub |
| `AIMMUNE_SELL_STATE` | `off` | Receipt posture |
| `AIMMUNE_EXEC_MOCK` | `false` | In-memory alias (tests / no OPNsense) |
| `AIMMUNE_OPNSENSE_URL` / `OPNSENSE_URL` | unset | e.g. `https://opnsense.local` |
| `AIMMUNE_OPNSENSE_KEY` / `OPNSENSE_KEY` | unset | API key (HTTP basic user) |
| `AIMMUNE_OPNSENSE_SECRET` / `OPNSENSE_SECRET` | unset | API secret |
| `AIMMUNE_OPNSENSE_VERIFY` | `true` | TLS verify |
| `AIMMUNE_IFACE_PIN` | `vendor/inference-iface` | Schema pin path |

`PANOPTICON_BASE_URL` / `HM_SITE_TOKEN` stay documented for later slices ([`plane-client.md`](plane-client.md)). Slice 1 does not call the plane.

## Run

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
python -m pip install -e '.[dev]'

export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_EVE_PATH=/var/log/suricata/eve.json
export AIMMUNE_EXEC_MOCK=1          # or set OPNsense URL/key/secret
export SITE_ID=net-tn-cottage

python -m aimmune cycle             # one detect + expiry tick
python -m aimmune loop              # every 120s
python -m aimmune verify-chain
pytest
```

OPNsense one-time: Host(s) alias `ai_autoblock`, WAN block-source rule (created once), API user with `firewall/alias_util` add/delete. Executor does **not** reload the full ruleset.

## Policy (v0.1)

1. Reject unknown tools / extra args (pin JSON Schema).  
2. Whitelist IP → `observe`.  
3. Already in `ai_autoblock` → `observe` (dedupe).  
4. Rate limit B=30 new blocks / hour → `hold_human` + queue `notify.operator` (`channel: fyber.auditor`).  
5. `severity: critical` and rule in auto set (`port_scan_burst`) → `execute` `firewall.block_ip`. Open a **minimal** local security incident; **do not** wait on that write.  
6. `severity: high` (`ssh_brute`) → **`propose` only** + notify queue. Do **not** downgrade high → observe.

Expiry (`brewnix-rules/expiry`): rate limits do not apply; whitelist does not stick the ledger; already-gone alias member → `observe` + advance ledger. Inherits parent incident only.

Each `cycle` runs **detect then expiry**. A still-hot EVE window dedupes against the live alias before this tick removes an expired member. New alerts after `expire_at` may re-block on a later cycle (no sliding TTL).

## Out of scope (slice 2+)

Plane fyber.auditor client · health-watch · `actor.kind: model` · Hypermesh preempt · full incident join/close clocks · AImmune UI · Tailscale.

## Locked design (Chris 2026-09-08)

A. Propose / `hold_human` write the local notify queue + receipt; slice 2 drains.  
B. Critical execute opens a minimal local incident side-record; never gates the block.  
C. Expiry (TTL ledger + expiry actor) is in this slice.  
D. State dir default `/var/lib/aimmune/` (env override).  
E. `rules/v0.1.yaml` placeholder SIDs + N=10, M=20, K=15.  
F. Thin `exec/opnsense_alias.py`; mock in tests; `alias_util` add/delete.
