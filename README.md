# AImmune — Brewnix `auto-defense`

**Product:** AImmune  
**Engineering repo:** [`Brewnix/auto-defense`](https://github.com/Brewnix/auto-defense) (this repo)  
**Status:** **slice 0 landed** (2026-09-08) — iface pin + inventory freeze; executor vertical not started  
**License:** [MIT](LICENSE)  
**Contracts:** pin [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208) in [`vendor/inference-iface`](vendor/inference-iface). Do **not** fork or weaken those locks here.  
**CI:** [iface pin](.github/workflows/iface-pin.yml) — checkout with submodules; fail if pin missing; validate `schemas/*.v0.json` + examples.

Site-local sense → decide → act → receipt. Policy + typed actuators execute. The LLM judges only. Offline-first when Panopticon is unreachable.

> Supersedes the short-lived [`Brewnix/site-defense`](https://github.com/Brewnix/site-defense) scaffold (same intent; renamed).

## Clone

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
# or, after a plain clone:
git submodule update --init --recursive
```

## What lives here

| Area | This repo | Elsewhere |
|------|-----------|-----------|
| Locked schemas / policy docs | Pin / submodule [`vendor/inference-iface`](vendor/inference-iface) | [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) |
| Site policy executor + receipt chain | **Here** (slice 1+) | — |
| OPNsense / Suricata actuators | **Here** (slice 1+) | Host image: [`Brewnix/proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall) |
| `notify.operator` → fyber.auditor client | **Here** (slice 2) | Plane: Panopticon `#39` |
| Hypermesh preempt client + H3 drain | **Here** (slice 4) | Host H1–H4; plane `#40` / `#41` |
| AImmune UI (digests / tickets / posture) | **Here** (slice 5; site SoT) | — |
| Plane doors (`hm_site_`, auditor, site jobs, sell_state) | Client only — [`docs/plane-client.md`](docs/plane-client.md) | [`FyberLabs/panopticon`](https://github.com/FyberLabs/panopticon) |
| Host actuators | Client / H4 owner path | [`FyberLabs/hypermesh-host`](https://github.com/FyberLabs/hypermesh-host) |

**Not this repo:** Panopticon SaaS gateway fork, Hypermesh-router IR chat UI, `schemas/` amends, market/renter surfaces, Tailscale-as-plane-transport.

## Locked axioms (pressure-test 2026-09-08)

- Plane reach: **WireGuard** (Panopticon/host) — not Tailscale  
- `Device.site_id`: operator bind once  
- UI SoT: site-local; tickets are intent  
- Vertical: UI (5) before privilege grants (7)  
- Model cottage v0: **local-only**  
- Auth: `hm_site_` machine + SociACL human (dual)  
- No `/v1/ir/chat` in AImmune UI  
- CI pins iface SHA **here**

Full table: [`docs/slice-0-inventory.md`](docs/slice-0-inventory.md). Roadmap: [`docs/roadmap.md`](docs/roadmap.md).

## Recommended vertical

`0 → 1 → 2 → 4 → 5` then package. **Slice 0 done.**

0. Pin iface + plane inventory freeze (docs) — **landed**  
1. Zero-LLM OPNsense loop + `fyber.receipt/v0`  
2. `notify.operator` auditor client  
3. Incident side index (parallel after 1)  
4. Preempt client + H3 (`/site/jobs`, `/site/devices`, H4 offline)  
5. AImmune UI v0  
6–8. Model triage, privilege grant, SociACL IR UX  
9. Package as one site daemon

## Plane doors (cite, don’t reimplement)

| Door | Panopticon |
|------|------------|
| Site token | `#38` — `hm_site_…` |
| fyber.auditor | `#39` — `/api/v1/auditor/v0/tickets` |
| Site jobs | `#40` — [`brewnix-executor-bridge-v0`](https://github.com/FyberLabs/panopticon/blob/main/products/hypermesh/docs/brewnix-executor-bridge-v0.md) |
| Live `sell_state` | `#41` — [`heartbeat-sell-state-v0`](https://github.com/FyberLabs/panopticon/blob/main/products/hypermesh/docs/heartbeat-sell-state-v0.md) |

How AImmune will call them over WireGuard: [`docs/plane-client.md`](docs/plane-client.md) (`PANOPTICON_BASE_URL`, `HM_SITE_TOKEN`, `SITE_ID`).
