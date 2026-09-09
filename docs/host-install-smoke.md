# Host-install smoke (conceptual)

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** doc + optional offline script ([`scripts/smoke-cottage-offline.sh`](../scripts/smoke-cottage-offline.sh); default-off `live_cottage` — [`docs/testing-harden-v0.md`](testing-harden-v0.md))  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Extends:** [`docs/slice-9-package.md`](slice-9-package.md)  
**USB layout:** [`docs/usb-layout.md`](usb-layout.md)

Cottage install smoke for one site daemon. **No ISO bake. No `.deb` / `.rpm`.** Brewnix roles own the gateway, Eve, WireGuard, and Host. AImmune ships pip + systemd + env + docs + optional UI.

## Locked design

| | Rule |
|---|------|
| A | **Doc-only.** This file + USB role stubs. No image bake, no package artifacts. |
| B | **USB is conceptual.** `usb/roles/gateway-opnsense/`, `usb/roles/hypermesh-host/`, `usb/roles/aimmune-cottage/` — pointers and tarball notes, not qcow. |
| C | **Checklist extends slice 9:** role prereqs → `pip` + `deploy/install.sh` → perms → env → `aimmune.service` + `status` → offline contain → optional UI loopback + SIWE/smoke → plane-up **only** after WireGuard + `HM_SITE_TOKEN` + `Device.site_id`. |
| D | **Role split.** Brewnix / Host / OPNsense stay out of this repo. Never vendor [`Brewnix/proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall) or [`FyberLabs/hypermesh-host`](https://github.com/FyberLabs/hypermesh-host). |
| E | **Pass criteria.** `aimmune status --json` reports `site_id` / `plane_reachable` / `receipts`; journald has `aimmune` lines; UI **fail-closed** without `AIMMUNE_UI_TOKEN`. |
| F | Non-goals: ISO/USB bake, Tailscale, public UI default, k8s, embedding Next in Python, iface pin bump. |

Also locked: WireGuard not Tailscale; UI loopback (`AIMMUNE_UI_HOST=0.0.0.0` opt-in only); state `/var/lib/aimmune` **0700**; secrets **0600**; iface pin unchanged; MIT.

## Who owns what

| Role | Owner | This repo ships |
|------|-------|-----------------|
| Gateway / Suricata Eve / `alias_util` | Brewnix OPNsense / [`proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall) | `AIMMUNE_EVE_PATH` + `aimmune.exec.opnsense_alias` (or `AIMMUNE_EXEC_MOCK=1`) |
| WireGuard overlay | Existing Panopticon / host path | [`docs/plane-client.md`](plane-client.md) cite only |
| Hypermesh Host / H4 `owner.sock` | [`hypermesh-host`](https://github.com/FyberLabs/hypermesh-host) | `AIMMUNE_HOST_STATE_DIR` cite — [`docs/slice-4-preempt.md`](slice-4-preempt.md) |
| AImmune cottage | **This repo** | `pip install` · [`deploy/install.sh`](../deploy/install.sh) · `deploy/systemd/*.service` · [`deploy/aimmune.env.example`](../deploy/aimmune.env.example) · optional `ui/` |

Do not copy Host or OPNsense trees into `auto-defense`.

## Checklist (extends slice 9)

Work these in order. Lab boxes may stop after **offline contain**. Plane-up is last on purpose.

### 1. Role prereqs (cite, don’t install from here)

Confirm the other USB roles exist **or** the equivalent lab stubs:

- Gateway: Eve JSONL path you can point `AIMMUNE_EVE_PATH` at (live `/var/log/suricata/eve.json` **or** the offline fixtures in [`docs/synthetics-v0.md`](synthetics-v0.md)).
- Host: not required for offline contain. H4 `owner.sock` only if you will exercise preempt later.
- Identity: chosen `SITE_ID` (example `net-tn-cottage`). Do **not** auto-bind `Device.site_id` from the daemon.

Pointers: [`usb/roles/gateway-opnsense/README.md`](../usb/roles/gateway-opnsense/README.md) · [`usb/roles/hypermesh-host/README.md`](../usb/roles/hypermesh-host/README.md) · [`usb/roles/aimmune-cottage/README.md`](../usb/roles/aimmune-cottage/README.md).

### 2. pip + `install.sh`

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
cd auto-defense
python3 -m pip install -e .
sudo ./deploy/install.sh
```

`install.sh` copies units + `/etc/aimmune/aimmune.env` (0600 if new). It does **not** enable units or invent a user. Confirm `command -v aimmune`. If `ExecStart=` is not `/usr/local/bin/aimmune`, edit the unit (venv or `python -m aimmune loop`). See [`docs/slice-9-package.md`](slice-9-package.md).

### 3. Perms

```bash
sudo useradd --system --home /var/lib/aimmune --shell /usr/sbin/nologin aimmune || true
sudo chown aimmune:aimmune /var/lib/aimmune /etc/aimmune/aimmune.env
sudo chmod 0700 /var/lib/aimmune
sudo chmod 0600 /etc/aimmune/aimmune.env
```

### 4. Env

Edit `/etc/aimmune/aimmune.env`. For this smoke (offline-first):

```bash
SITE_ID=net-tn-cottage
AIMMUNE_STATE_DIR=/var/lib/aimmune
AIMMUNE_EXEC_MOCK=1
AIMMUNE_PLANE_REACHABLE=0
AIMMUNE_EVE_PATH=/var/log/suricata/eve.json   # or a fixture file
# leave PANOPTICON_BASE_URL / HM_SITE_TOKEN unset
# leave AIMMUNE_UI_TOKEN empty until the optional UI step
# SIWE v0 (landed): AIMMUNE_SIWE_DOMAIN / AIMMUNE_OWNER_PRINCIPALS
# smoke principal is the no-wallet loopback path — see docs/siwe-v0.md
```

Do not set `AIMMUNE_UI_HOST=0.0.0.0`. Do not set Tailscale env. Critical knobs: [`deploy/aimmune.env.example`](../deploy/aimmune.env.example).

### 5. `aimmune.service` + status

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aimmune.service
journalctl -u aimmune -n 50 --no-pager
aimmune status
aimmune status --json
```

`status` always exits 0. Missing state is a field (`state_dir_exists: false`), not a failure.

### 6. Offline contain

Plane down, mock alias — one tick must still write receipts. Prefer the composed synthetic ([`docs/synthetics-v0.md`](synthetics-v0.md)):

```bash
AIMMUNE_STATE_DIR=/var/lib/aimmune AIMMUNE_EXEC_MOCK=1 AIMMUNE_PLANE_REACHABLE=0 \
  aimmune cycle
aimmune verify-chain
aimmune status --json
```

Expect `plane_reachable: false`, a growing `receipts.count`, and journal lines from `aimmune.service` only. No public port. No SaaS.

Automated v0 (prefix dir, no root, `AIMMUNE_EXEC_MOCK=1`): [`scripts/smoke-cottage-offline.sh`](../scripts/smoke-cottage-offline.sh). Pytest marker `live_cottage` is default-off — [`docs/testing-harden-v0.md`](testing-harden-v0.md).

### 7. Optional UI (loopback + SIWE/smoke)

Sibling tree — not in the pip wheel. **Fail-closed without `AIMMUNE_UI_TOKEN`:**

- [`deploy/systemd/aimmune-ui.service`](../deploy/systemd/aimmune-ui.service) `ExecStartPre` is `test -n "${AIMMUNE_UI_TOKEN-}"`
- `aimmune ui` exits 1 and prints `MISSING` when the token is unset
- Next [`ui/proxy.ts`](../ui/proxy.ts) / session API refuse to serve without the token

```bash
cd ui && npm ci && npm run build
sudo mkdir -p /usr/local/lib/aimmune && sudo cp -a . /usr/local/lib/aimmune/ui
# set AIMMUNE_UI_TOKEN in /etc/aimmune/aimmune.env (do not commit)
sudo systemctl enable --now aimmune-ui.service
# 127.0.0.1:3000 — SSH tunnel if you are off-box
```

Optional UI path is **SIWE or smoke principal** — both are on main ([`docs/siwe-v0.md`](siwe-v0.md)):

- **SIWE (production human door):** Settings **Connect wallet** (injected `window.ethereum`) → `GET /api/siwe/nonce` + `POST /api/siwe/verify` → signed httpOnly `aimmune_principal` (`v2.<addr>.<exp>.<hmac>`). `resolvePrincipal` source `"siwe"` only after verify. Set `AIMMUNE_SIWE_DOMAIN` (loopback default), `AIMMUNE_OWNER_PRINCIPALS`, optional `AIMMUNE_SIWE_SECRET` / `AIMMUNE_SIWE_TTL_S`, and keep `AIMMUNE_UI_TOKEN`. Durability: [`docs/siwe-mockcheck-durability-v0.md`](siwe-mockcheck-durability-v0.md).
- **Smoke (loopback, no wallet):** `AIMMUNE_OWNER_PRINCIPALS` + `AIMMUNE_UI_SMOKE_PRINCIPAL`. `POST /api/session` `{ principal }` is smoke-only; production fails closed unless `AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL=1`. Source is `"smoke"`, never `"siwe"`.

MockCheck / `requireIrAct` are unchanged ([`docs/slice-8-sociacl-ir.md`](slice-8-sociacl-ir.md)). UI tests stay Vitest. The offline synthetic does **not** require a wallet.

### 8. Plane-up only after WireGuard + token + `Device.site_id`

Do **not** set `AIMMUNE_PLANE_REACHABLE=1` until all three exist:

1. WireGuard path to the Panopticon origin (`PANOPTICON_BASE_URL`) — **not Tailscale**
2. `HM_SITE_TOKEN` (`hm_site_…`, **0600**) minted via operator `POST /api/v1/hypermesh/site-tokens` ([Panopticon #38](https://github.com/FyberLabs/panopticon/pull/38)); confirm `GET …/site-tokens/me`
3. Operator `Device.site_id` bind once — daemon does not auto-bind ([`docs/slice-0-inventory.md`](slice-0-inventory.md#device-bind-runbook-plane))

`SITE_ID` / `AIMMUNE_SITE_ID` must equal the token site and every `Device.site_id` this daemon talks about. Then cycle-end auditor + grant poll may run. Host job RTT stays off the IDS loop (`aimmune preempt run` is on-demand).

## Pass criteria

| Check | Expect |
|-------|--------|
| `aimmune status --json` | `site_id` set; `plane_reachable` matches env; `receipts.count` / `receipts.last` present after a cycle |
| journald | `journalctl -u aimmune` shows loop/cycle lines; no SaaS exporter |
| UI fail-closed | Empty `AIMMUNE_UI_TOKEN` → unit `ExecStartPre` fails; `aimmune ui` exits 1; Next does not serve |

Optional: `verify-chain` ok; offline synthetic contain+hold ([`docs/synthetics-v0.md`](synthetics-v0.md)).

## Out of scope

ISO / USB bake · `.deb` / `.rpm` · Tailscale · public UI default · k8s · embedding Next in the Python process · vendoring Host / OPNsense · iface pin change · `schemas/` amend · ERC-1271 / WalletConnect (SIWE v0 stays injected EOA).
