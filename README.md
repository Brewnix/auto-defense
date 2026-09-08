# AImmune — Brewnix `auto-defense`

**Product:** AImmune  
**Engineering repo:** [`Brewnix/auto-defense`](https://github.com/Brewnix/auto-defense) (this repo)  
**Status:** **slice 9** — one site daemon + host wiring runbook on top of slices 1–7. See [`docs/slice-9-package.md`](docs/slice-9-package.md). SociACL (slice 8) is later.  
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
| Site policy executor + receipt chain | **Here** (slice 1) | — |
| OPNsense / Suricata actuators | **Here** (slice 1) | Host image: [`Brewnix/proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall) |
| `notify.operator` → fyber.auditor client | **Here** (slice 2) | Plane: Panopticon `#39` — intent ≠ actuation |
| Hypermesh preempt client + H3 drain | **Here** (slice 4) — [`docs/slice-4-preempt.md`](docs/slice-4-preempt.md) | Host H1–H4; plane `#40` / `#41` |
| AImmune UI (digests / tickets / posture) | **Here** (slice 5) — [`docs/slice-5-ui.md`](docs/slice-5-ui.md) · [`ui/`](ui/) | — |
| Privilege grant site client | **Here** (slice 7) — [`docs/slice-7-privilege-grant.md`](docs/slice-7-privilege-grant.md) | Plane: Panopticon `#50` — resolve is plane-only |
| Plane doors (`hm_site_`, auditor, site jobs, sell_state, grants) | Client only — [`docs/plane-client.md`](docs/plane-client.md) | [`FyberLabs/panopticon`](https://github.com/FyberLabs/panopticon) |
| Host actuators | Client / H4 owner path | [`FyberLabs/hypermesh-host`](https://github.com/FyberLabs/hypermesh-host) |
| Cottage package (systemd + env) | **Here** (slice 9) — [`docs/slice-9-package.md`](docs/slice-9-package.md) · [`deploy/`](deploy/) | Host image bake stays in proxmox-firewall / hypermesh-host |

**Not this repo:** Panopticon SaaS gateway fork, Hypermesh-router IR chat UI, `schemas/` amends, market/renter surfaces, Tailscale-as-plane-transport, `.deb`/`.rpm`.

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

`0 → 1 → 2 → 4 → 5` then package. **Slices 0–7 and 9 in this tree** (3 parallel after 1; 8 later).

```bash
python -m pip install -e '.[dev]'
AIMMUNE_STATE_DIR=/tmp/aimmune-state AIMMUNE_EXEC_MOCK=1 python -m aimmune cycle
python -m aimmune status --json
pytest
```

0. Pin iface + plane inventory freeze (docs) — **landed**  
1. Zero-LLM OPNsense loop + `fyber.receipt/v0` + expiry + notify queue stub — [`docs/slice-1-zero-llm.md`](docs/slice-1-zero-llm.md) — **landed**  
2. `notify.operator` auditor client — [`docs/slice-2-auditor.md`](docs/slice-2-auditor.md) — **landed**  
3. Incident side index — [`docs/slice-3-incident.md`](docs/slice-3-incident.md) — **this tree**  
4. Preempt client + H3 (`/site/jobs`, `/site/devices`, H4 offline, site_defense hook) — [`docs/slice-4-preempt.md`](docs/slice-4-preempt.md) — **landed**  
5. AImmune UI v0 — [`docs/slice-5-ui.md`](docs/slice-5-ui.md) — **landed**  
6. Model triage — [`docs/slice-6-model-triage.md`](docs/slice-6-model-triage.md) — **landed**  
7. Privilege grant — [`docs/slice-7-privilege-grant.md`](docs/slice-7-privilege-grant.md) — **landed**  
8. SociACL IR UX  
9. Package as one site daemon — [`docs/slice-9-package.md`](docs/slice-9-package.md) — **this tree**

## Plane doors (cite, don’t reimplement)

| Door | Panopticon |
|------|------------|
| Site token | `#38` — `hm_site_…` |
| fyber.auditor | `#39` — `/api/v1/auditor/v0/tickets` |
| Site jobs | `#40` — [`brewnix-executor-bridge-v0`](https://github.com/FyberLabs/panopticon/blob/main/products/hypermesh/docs/brewnix-executor-bridge-v0.md) |
| Live `sell_state` | `#41` — [`heartbeat-sell-state-v0`](https://github.com/FyberLabs/panopticon/blob/main/products/hypermesh/docs/heartbeat-sell-state-v0.md) |
| Privilege grants | `#50` — `/api/v1/grants/v0/grants` (propose / get / list; resolve is plane-only) |

How AImmune will call them over WireGuard: [`docs/plane-client.md`](docs/plane-client.md) (`PANOPTICON_BASE_URL`, `HM_SITE_TOKEN`, `SITE_ID`).

## Site UI (slice 5)

Loopback + bearer token. No IR chat.

```bash
export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_EXEC_MOCK=1
export AIMMUNE_UI_TOKEN=dev-token   # required; do not commit
export AIMMUNE_PLANE_REACHABLE=0

python -m aimmune cycle
python -m aimmune ui                # env checklist
cd ui && npm install && npm run dev # 127.0.0.1:3000
```

`AIMMUNE_UI_HOST=0.0.0.0` is an explicit opt-in only. Local approve/deny: `python -m aimmune owner approve --receipt-id …` (refused when a ticket exists and the plane is up).

## Cottage install (slice 9)

Python package + two systemd units. UI is a sibling `npm` tree (not in the pip wheel). No `.deb`/`.rpm`, no image bake.

```bash
python3 -m pip install -e .
sudo ./deploy/install.sh          # copies units + /etc/aimmune/aimmune.env
# edit /etc/aimmune/aimmune.env (chmod 0600); state dir 0700
sudo systemctl enable --now aimmune.service
aimmune status                    # always exits 0; --json for scripts
journalctl -u aimmune -f
```

Optional UI: `cd ui && npm ci && npm run build`, copy to `/usr/local/lib/aimmune/ui`, set `AIMMUNE_UI_TOKEN`, then `systemctl enable --now aimmune-ui.service` (127.0.0.1). Host wiring checklist (Eve, OPNsense `alias_util`, WireGuard, `#38` token, `Device.site_id`, H4 `owner.sock`): [`docs/slice-9-package.md`](docs/slice-9-package.md).
