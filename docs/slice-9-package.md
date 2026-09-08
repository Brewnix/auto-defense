# Slice 9 — package one site daemon + host wiring runbook

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Does not wait on slice 8.** UI token / local owner paths stay valid. SociACL is later.

Ship the existing `aimmune` Python package plus in-repo systemd units and an env contract. **No** `.deb` / `.rpm` in v0. **No** host image bake. Cite OPNsense / Eve / alias_util / WireGuard / `HM_SITE_TOKEN` / H4 `owner.sock` — do **not** vendor [`Brewnix/proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall) or [`FyberLabs/hypermesh-host`](https://github.com/FyberLabs/hypermesh-host).

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | **Two systemd units.** `aimmune.service` required (`aimmune loop`). `aimmune-ui.service` optional (`next start` on 127.0.0.1, `After=aimmune`). Do **not** embed Next inside the Python process. |
| B | Ship before SociACL. Packaging does not wait on slice 8. |
| C | Artifact: pip-installable `aimmune` + `deploy/systemd/*.service` + `deploy/aimmune.env.example`. No `.deb`/`.rpm`. |
| D | Host image: **runbook + env contract only.** Cite Eve, alias_util, WireGuard, `#38` token mint, `Device.site_id`, H4 sock. |
| E | Existing `loop` / cycle-end path covers grant poll, auditor drain/poll, incident sweep, and the thin site_defense hook. **No** second long-running preempt daemon. `aimmune preempt run` stays on-demand CLI (Host job RTT stays off the IDS loop). |
| F | Observability: **journald** + `aimmune status`. No SaaS telemetry. No public bind. |

Also locked: WireGuard not Tailscale; UI loopback by default (`AIMMUNE_UI_HOST=0.0.0.0` opt-in only); state `/var/lib/aimmune` (**0700**); secrets **0600**; iface pin `3621849bbf7c368b1d709356c465883144300208` unchanged; no `schemas/` amend; no IR chat; MIT.

## What this slice includes

| Piece | Path | Notes |
|-------|------|--------|
| Daemon unit | [`deploy/systemd/aimmune.service`](../deploy/systemd/aimmune.service) | `EnvironmentFile=-/etc/aimmune/aimmune.env`; `ExecStart=aimmune loop`; `Restart=on-failure` |
| UI unit | [`deploy/systemd/aimmune-ui.service`](../deploy/systemd/aimmune-ui.service) | Optional; `ConditionPathExists` on the sibling UI; token required |
| Env contract | [`deploy/aimmune.env.example`](../deploy/aimmune.env.example) | Critical knobs documented |
| Install helper | [`deploy/install.sh`](../deploy/install.sh) | Copies units + env example; prints next steps; non-interactive |
| Status | `aimmune status` / `aimmune status --json` | Read-only; **always exits 0** |
| Last cycle | `$STATE_DIR/last_cycle.json` | Written at cycle end for the status summary |

## Install on a cottage box

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
cd auto-defense
python3 -m pip install -e .

# units + /etc/aimmune/aimmune.env (0600 if new)
sudo ./deploy/install.sh

sudo useradd --system --home /var/lib/aimmune --shell /usr/sbin/nologin aimmune || true
sudo chown aimmune:aimmune /var/lib/aimmune /etc/aimmune/aimmune.env
sudo chmod 0700 /var/lib/aimmune
sudo chmod 0600 /etc/aimmune/aimmune.env
```

Edit `/etc/aimmune/aimmune.env`. Lab:

```bash
AIMMUNE_EXEC_MOCK=1
AIMMUNE_PLANE_REACHABLE=0
AIMMUNE_EVE_PATH=/var/log/suricata/eve.json   # or a fixture file
```

If `command -v aimmune` is not `/usr/local/bin/aimmune`, point `ExecStart=` at the venv (or `python -m aimmune loop` with `PYTHONPATH=src` and a checkout `WorkingDirectory`). Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aimmune.service
journalctl -u aimmune -n 50 --no-pager
aimmune status
```

`ProtectSystem` is **off** by default so Suricata EVE and H4 `owner.sock` keep working. Tighten later with `ReadOnlyPaths=` / `ReadWritePaths=/var/lib/aimmune` if you want.

### Verify offline contain

```bash
# plane down, mock alias — one tick must still write receipts
AIMMUNE_STATE_DIR=/var/lib/aimmune AIMMUNE_EXEC_MOCK=1 AIMMUNE_PLANE_REACHABLE=0 \
  aimmune cycle
aimmune verify-chain
aimmune status --json
```

Expect `plane_reachable: false`, a growing `receipts.count`, and journal lines from `aimmune.service` only. No public port. No SaaS.

### Optional UI (sibling install — not in the pip wheel)

```bash
cd ui
npm ci
npm run build
sudo mkdir -p /usr/local/lib/aimmune
sudo cp -a . /usr/local/lib/aimmune/ui
# set AIMMUNE_UI_TOKEN in /etc/aimmune/aimmune.env (do not commit)
sudo systemctl enable --now aimmune-ui.service
# 127.0.0.1:3000 — SSH tunnel if you are off-box
```

`AIMMUNE_UI_HOST=0.0.0.0` is documented only as an explicit opt-in. Next stays a **separate** process (`npm run start` / `npx next start -H 127.0.0.1`). Local approve/deny and the UI token remain valid without SociACL.

The UI spawns `python -m aimmune` (`AIMMUNE_PYTHON`, optional `AIMMUNE_REPO_ROOT`). After `pip install`, any `python3` that sees the package works.

## `aimmune status`

Read-only. Does **not** create `/var/lib/aimmune`, call the plane, or mutate JSONL.

**Exit 0 always** (informational). Missing state dir is a field (`state_dir_exists: false`), not a failure. Use `--json` for scripts.

Reports: `site_id`, configured `plane_reachable`, state paths, receipt count + last receipt id/time, `last_cycle` (or inferred from the last receipt), pending notify / preempt counts, open incidents, active / proposed grants, cheap `sell_state` (last receipt / env; stale unknown OK).

```bash
aimmune status
aimmune status --json
python -m aimmune status --json --state-dir /tmp/aimmune-state
```

No SaaS telemetry. Pair with `journalctl -u aimmune`.

## Cycle-end (no mega-timer)

One loop. Cycle-end already:

1. Auditor drain + poll when `AIMMUNE_PLANE_REACHABLE` (slice 2)
2. Grant poll + local expire (slice 7)
3. Incident `auto_quiet` sweep (slice 3)
4. Thin `site_defense` preempt **propose** hook when flagged (slice 4)

Do **not** add `aimmune-preempt.service`. `aimmune preempt run` drains the execute queue on demand; the IDS cycle never awaits Host job RTT.

## Host wiring checklist (cite, don’t vendor)

Pointers only. This repo does not bake OPNsense, Suricata, WireGuard, or Hypermesh Host.

| Item | Where | This repo |
|------|--------|-----------|
| Suricata `eve.json` | Host / OPNsense image — typically `/var/log/suricata/eve.json`. Image: [`Brewnix/proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall) | `AIMMUNE_EVE_PATH` — [`docs/slice-1-zero-llm.md`](slice-1-zero-llm.md) |
| `ai_autoblock` + `alias_util` add/delete | OPNsense API (or `AIMMUNE_EXEC_MOCK=1` in lab) | [`aimmune.exec.opnsense_alias`](../src/aimmune/exec/opnsense_alias.py) |
| WireGuard overlay | Existing Panopticon / host path. **Not Tailscale.** | [`docs/plane-client.md`](plane-client.md) |
| `HM_SITE_TOKEN` mint | Operator `POST /api/v1/hypermesh/site-tokens` ([Panopticon #38](https://github.com/FyberLabs/panopticon/pull/38)) | Store in `aimmune.env` **0600**. Confirm `GET …/site-tokens/me` |
| `Device.site_id` bind | Operator once (`POST`/`PATCH`). Daemon does not auto-bind | [`docs/slice-0-inventory.md`](slice-0-inventory.md#device-bind-runbook-plane) |
| H4 `owner.sock` | [`FyberLabs/hypermesh-host`](https://github.com/FyberLabs/hypermesh-host) `$STATE_DIR/owner.sock` + `owner.token` **0600** | `AIMMUNE_HOST_STATE_DIR` / `HYPERMESH_STATE_DIR` — [`docs/slice-4-preempt.md`](slice-4-preempt.md) |
| Grants / auditor | Cycle-end poll; resolve is plane-only | [`docs/slice-7-privilege-grant.md`](slice-7-privilege-grant.md) · [`docs/slice-2-auditor.md`](slice-2-auditor.md) |

`SITE_ID` / `AIMMUNE_SITE_ID` must equal the token site and every `Device.site_id` this daemon talks about.

## Environment (critical knobs)

Full list lives in [`deploy/aimmune.env.example`](../deploy/aimmune.env.example). Loaded by both units via `EnvironmentFile=-/etc/aimmune/aimmune.env`.

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_STATE_DIR` | `/var/lib/aimmune` | Durable site state (**0700**) |
| `SITE_ID` / `AIMMUNE_SITE_ID` | `net-tn-cottage` | Envelope / receipt / token site |
| `AIMMUNE_EVE_PATH` | unset | Suricata Eve JSONL |
| `AIMMUNE_CYCLE_SECONDS` | `120` | `aimmune loop` interval |
| `AIMMUNE_EXEC_MOCK` | `false` | Lab in-memory alias |
| `AIMMUNE_OPNSENSE_*` / `OPNSENSE_*` | unset | Live `alias_util` |
| `AIMMUNE_PLANE_REACHABLE` | `false` | Cycle-end auditor + grant poll |
| `PANOPTICON_BASE_URL` | unset | WireGuard gateway origin |
| `HM_SITE_TOKEN` | unset | `hm_site_…` (**0600**) |
| `AIMMUNE_HOST_STATE_DIR` | unset | H4 `owner.sock` parent |
| `AIMMUNE_UI_TOKEN` | unset | Required to serve the UI |
| `AIMMUNE_UI_HOST` | `127.0.0.1` | `0.0.0.0` is opt-in only |
| `AIMMUNE_UI_PORT` | `3000` | UI port |

## Out of scope

Tailscale · public UI default · Panopticon in this package · IR chat · baking OPNsense/Host into this repo · `.deb`/`.rpm` · waiting on SociACL · k8s · SaaS telemetry · embedding Next in Python · iface pin change · `schemas/` amend.
