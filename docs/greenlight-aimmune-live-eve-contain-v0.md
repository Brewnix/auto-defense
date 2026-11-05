# Greenlight — AImmune live Eve / real alias_util contain v0

| Field | Value |
| --- | --- |
| **Product** | AImmune |
| **Owner** | AImmune Product (small-model harness productization) |
| **Date** | 2026-09-17 |
| **Repo** | Brewnix/auto-defense |
| **Status** | Greenlight ask (this cut) — docs lock of already-landed live Eve / real alias_util path. No new runtime. |
| **License** | MIT |

## Product code pin

| Pin | Ref |
| --- | --- |
| **Product code** | Brewnix/auto-defense @ `4eb7524db8cfb058957a08fab5b09bb321e8cf85` (`4eb7524` — plane_staging #19 merge) |
| **Contracts** | Brewnix/inference-iface @ `3621849bbf7c368b1d709356c465883144300208` — **do not bump** |

## Cite (do not fork)

| Doc / path | Role for this Greenlight cut |
| --- | --- |
| `docs/testing-harden-v0.md` | Live alias_util / real Eve is opt-in follow-on; `live_cottage` v0 stays `AIMMUNE_EXEC_MOCK=1` |
| `usb/roles/gateway-opnsense/README.md` | Suricata `eve.json` typically `/var/log/suricata/eve.json`; `ai_autoblock` + `alias_util`; image in Brewnix/proxmox-firewall |
| `docs/slice-1-zero-llm.md` | `AIMMUNE_EVE_PATH`, `AIMMUNE_EXEC_MOCK`, OPNsense URL/key/secret, alias `ai_autoblock`, critical `port_scan_burst` auto-execute |
| `deploy/aimmune.env.example` | Cottage env contract |
| `docs/soft-soft-aimmune-testable-v0.md` (#16) | Separate Greenlight — offline / MockEngine (legacy path name) |
| `docs/soft-soft-aimmune-plane-staging-v0.md` (#17/#19) | Separate Greenlight — WireGuard plane safe subset (legacy path name) |

## Relationship table

| Cut | What it productizes | What it does not |
| --- | --- | --- |
| #16 testable cottage | Offline MockEngine + `EXEC_MOCK=1` | Live Eve contain |
| plane_staging #17/#19 | Live WG site-token safe subset | Live Eve contain |
| **THIS cut (Greenlight)** | Live Suricata Eve + real OPNsense `alias_util` contain | Offline mock contain; plane_staging; `lease_stop` |

## Greenlight slice — operator evidence (real cottage / gateway)

Operator runs on a cottage with Suricata + OPNsense gateway role (cite Brewnix/proxmox-firewall; **not vendored here**).

```bash
# /etc/aimmune/aimmune.env 0600:
# AIMMUNE_EVE_PATH=/var/log/suricata/eve.json
# AIMMUNE_EXEC_MOCK=0   # or unset
# AIMMUNE_OPNSENSE_URL=… AIMMUNE_OPNSENSE_KEY=… AIMMUNE_OPNSENSE_SECRET=…
# AIMMUNE_ALIAS=ai_autoblock
# AIMMUNE_PLANE_REACHABLE=0 is OK — plane not required for this cut
# SITE_ID=net-tn-cottage
# AIMMUNE_STATE_DIR=/var/lib/aimmune

aimmune cycle   # or wait for loop after a port_scan_burst Eve window
aimmune verify-chain
aimmune status --json
```

### Pass criteria

Cautious wording: field names below match styles already used in `docs/testing-harden-v0.md` (`exec_mock`, `site_id`, `state_dir` / `state_dir_exists`). Do not invent further status JSON keys.

Checked against `build_status` in `src/aimmune/status.py` on `4eb7524`. This cut does not add status keys. `eve_path` and `eve_path_exists` are already returned (`eve_path` is `null` when unset; `eve_path_exists` is true only when that path is a file).

| Check | Expect |
| --- | --- |
| `AIMMUNE_EXEC_MOCK` | unset or `0` (not lab mock) |
| `AIMMUNE_EVE_PATH` | live Suricata eve JSONL on the box |
| OPNsense | URL + key + secret set; alias `ai_autoblock` exists |
| Contain | At least one receipt whose `execution` includes `tool` `firewall.block_ip` with `status` `applied`, and `actor.kind` `rule`, after Eve-driven `port_scan_burst` (or equivalent critical auto rule) |
| `verify-chain` | ok |
| `status --json` | `state_dir_exists` true; `site_id` set; `exec_mock` false; `eve_path` set and `eve_path_exists` true |
| Plane | **NOT** required; may be down. This cut is plane-independent |

### Not Sign-off evidence for this cut

- `live_cottage` / `smoke-cottage-offline.sh` with `AIMMUNE_EXEC_MOCK=1`
- GitHub-hosted CI

Those remain evidence for #16 (testable / offline), not for live Eve contain.

## Secrets

Name only — `AIMMUNE_OPNSENSE_KEY` / `AIMMUNE_OPNSENSE_SECRET` (or `OPNSENSE_*`). **Never commit** values. Operator paste into Sign-off notes must redact secrets.

## HOLD (unchanged by this cut)

- Live Ollama judge Greenlight
- remint / `lease_stop` Cut hold; `device.site_id` follow-on under that hold
- Research productization deploy
- Hypermesh remint / lease / Stripe P0
- Tailscale; iface pin bump; folding live Eve into unmarked pytest; site resolve / revoke; `lease_stop` against rented boxes

## Acceptance

1. **Doc matches main** after branch from `4eb7524`.
2. **Cottage evidence:** Product accepts operator paste of `cycle` / `verify-chain` / `status` summary (**no secrets**) into Sign-off notes.
3. **Greenlight** is Product's; **Sign-off** after Greenlight + Chris merge + clean cottage evidence.

## Sign-off

| Role | Action | Status |
| --- | --- | --- |
| Product | Greenlight this docs-lock ask | pending |
| Chris | Merge after Greenlight | pending |
| Operator | Cottage evidence paste (no secrets) | pending |
