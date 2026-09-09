# Testing harden v0 — live cottage + plane staging

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this cut  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Cite:** [`docs/host-install-smoke.md`](host-install-smoke.md) · [`docs/synthetics-v0.md`](synthetics-v0.md) · [`docs/plane-client.md`](plane-client.md) · [`docs/slice-9-package.md`](slice-9-package.md)

Two **default-off** pytest markers plus a CI-less cottage script. Neither track folds into unmarked `pytest -q` or the existing PR pytest job. Offline vertical SoT and `plane_mocked` FakeAuditor / FakeGrants stay unchanged.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | Two markers + this doc: `live_cottage` and `plane_staging` (both **default-off**). Do **not** fold either into unmarked `pytest -q` / existing CI pytest job. |
| B | **Live cottage v0** scripts the [host-install checklist](host-install-smoke.md) through **offline contain**: install path → perms notes → env → service/status where practical in a CI-less script → cycle → verify-chain → `status --json` pass criteria. `AIMMUNE_EXEC_MOCK=1` is OK for v0. Live `alias_util` / real Eve is an opt-in follow-on citing the Brewnix gateway — not this cut. |
| C | **Plane staging E2E v0** is the site-token **safe** subset only: `site-tokens/me` → auditor create/GET → grant propose/GET → optional ack after local apply. **Assert** the site token **cannot** call resolve/revoke on tickets or grants (expect 401/403). No live `lease_stop` / preempt against rented boxes. Requires `PANOPTICON_BASE_URL`, `HM_SITE_TOKEN`, `SITE_ID`. Skip cleanly if unset. |
| D | CI: keep current iface-pin / pytest / UI jobs unchanged for PRs. Optional `workflow_dispatch` workflow runs plane_staging / live_cottage **only when secrets present** — never fail PR CI if secrets missing. |
| E | Keep `plane_mocked` FakeAuditor/FakeGrants and offline vertical SoT ([`docs/synthetics-v0.md`](synthetics-v0.md)) unchanged. No Playwright. UI stays Vitest. |
| F | Non-goals: ISO/USB bake, Tailscale, SIWE wallet in CI, site-side resolve, iface pin bump, vendoring Host/OPNsense, `schemas/` amend. |

Also locked: WireGuard not Tailscale; iface pin `3621849bbf7c368b1d709356c465883144300208`; no real tokens in the repo; MIT.

## Markers (default off)

| Marker | Gate | What |
|--------|------|------|
| *(unmarked)* | always | Offline vertical SoT + unit tests. Existing `pytest` CI job. |
| `plane_mocked` | `pytest -m plane_mocked` | In-process FakeAuditor / FakeGrants contrast. Unchanged. |
| `live_cottage` | `AIMMUNE_LIVE_COTTAGE=1` + `pytest -m live_cottage` | Cottage install-like prefix → offline contain. |
| `plane_staging` | `PANOPTICON_BASE_URL` + `HM_SITE_TOKEN` + `SITE_ID` + `pytest -m plane_staging` | Live WireGuard plane, site-token safe subset. |

Default `addopts` is `-m "not live_cottage and not plane_staging and not plane_mocked"`. Explicit `-m <marker>` overrides that exclude.

## Live cottage v0

Automates [host-install-smoke](host-install-smoke.md) steps 2–6 (pip assumed; role prereqs cited, not installed). **Offline contain only.** `AIMMUNE_EXEC_MOCK=1`. No live Suricata, OPNsense `alias_util`, WireGuard, or Panopticon.

```bash
# CI-less script (DEST_* prefix; no root, no systemd start by default)
./scripts/smoke-cottage-offline.sh

# pytest track (skipped unless the gate is set)
AIMMUNE_LIVE_COTTAGE=1 pytest -q -m live_cottage
```

The script stages [`deploy/install.sh`](../deploy/install.sh) into `$AIMMUNE_COTTAGE_PREFIX` (or a temp dir):

| Checklist step | What the script does |
|----------------|----------------------|
| 2. pip + `install.sh` | `DEST_SYSTEMD` / `DEST_ENV_DIR` / `DEST_STATE_DIR` overrides — does **not** write `/etc` unless you point them there |
| 3. Perms | State dir **0700**; env **0600**. `chown aimmune` is noted, not required without root |
| 4. Env | `AIMMUNE_EXEC_MOCK=1`, `AIMMUNE_PLANE_REACHABLE=0`, Eve fixture, plane URL/token **unset** |
| 5. Service / status | Units must exist and mention `aimmune loop` + `EnvironmentFile`. `systemctl` only if `AIMMUNE_LIVE_COTTAGE_SYSTEMD=1` on a real cottage |
| 6. Offline contain | Restamp [synthetics fixtures](synthetics-v0.md) → `aimmune cycle` → `verify-chain` → `status --json` |

Live `alias_util` / real Eve (gateway role) is a documented follow-on: point `AIMMUNE_EVE_PATH` at `/var/log/suricata/eve.json` and leave `AIMMUNE_EXEC_MOCK` unset. Cite [`usb/roles/gateway-opnsense/README.md`](../usb/roles/gateway-opnsense/README.md) — not required for this PR.

### Pass criteria (`status --json`)

| Check | Expect |
|-------|--------|
| `site_id` | set (default `net-tn-cottage`) |
| `plane_reachable` | `false` |
| `exec_mock` | `true` |
| `state_dir_exists` | `true` |
| `receipts.count` | ≥ 1 after the cycle (grows vs pre-cycle) |
| `receipts.last.receipt_id` | present |
| `verify-chain` | `{"ok": true}` |

`status` always exits 0. Missing state is a field, not a failure — the script asserts the dir exists after install.

## Plane staging E2E v0

Site-token **safe** subset against a WireGuard-reachable Panopticon. **Not Tailscale.** Do **not** put tokens in the repo.

```bash
export PANOPTICON_BASE_URL=https://panopticon.wg.example   # no trailing slash
export HM_SITE_TOKEN=hm_site_…                            # 0600 on the box; never commit
export SITE_ID=net-tn-cottage                             # must equal the token site

pytest -q -m plane_staging
# unset any of the three → skip (not fail)
```

Sequence ([`docs/plane-client.md`](plane-client.md)):

1. `GET /api/v1/hypermesh/site-tokens/me` — token is a site machine token; `site_id` matches `SITE_ID`
2. Auditor `POST /api/v1/auditor/v0/tickets` + `GET …/tickets/{id}`
3. Grant `POST /api/v1/grants/v0/grants` (propose) + `GET …/grants/{id}`
4. Optional `POST …/tickets/{id}/ack` after a local apply receipt — **409** (ticket still open) is accepted; resolve is not
5. **Assert denied (401/403)** — site token `POST …/tickets/{id}/resolve`, `POST …/grants/{id}/resolve`, `POST …/grants/{id}/revoke`

No `POST /api/v1/hypermesh/site/jobs` (`lease_stop` / `sell_pause`). No preempt against rented boxes. Site-side resolve is not implemented here and must stay that way.

### Pass criteria

| Check | Expect |
|-------|--------|
| `/site-tokens/me` | 200; token `site_id` == `SITE_ID` |
| Auditor create + GET | 200; `ticket_id` round-trips |
| Grant propose + GET | 200; `grant_id` round-trips; status `proposed` (or plane-equivalent open) |
| Optional ack | 200 **or** 409 (still open / not yet resolved). Never treat as plane resolve |
| Site resolve/revoke | **401 or 403** on ticket resolve, grant resolve, and grant revoke |
| Skip | any of `PANOPTICON_BASE_URL` / `HM_SITE_TOKEN` / `SITE_ID` unset → skipped, not failed |

## How this relates to synthetics

| Track | Plane | Exec | Marker | CI |
|-------|-------|------|--------|----|
| Offline vertical SoT | down | mock | unmarked | existing `pytest` job |
| `plane_mocked` | FakeAuditor / FakeGrants | mock | `plane_mocked` | default-off |
| Live cottage v0 | down | mock | `live_cottage` | optional dispatch only |
| Plane staging v0 | live WireGuard | n/a (HTTP only) | `plane_staging` | optional dispatch + secrets |

Do not replace [`tests/test_synthetic_vertical_offline.py`](../tests/test_synthetic_vertical_offline.py). Do not attach FakeAuditor to the cottage script.

## CI

[`.github/workflows/iface-pin.yml`](../.github/workflows/iface-pin.yml) is **unchanged** (pin validate / `pytest -q` / UI Vitest). PRs never run these markers.

Optional: [`.github/workflows/testing-harden-optional.yml`](../.github/workflows/testing-harden-optional.yml) — `workflow_dispatch` only.

| Job | When it runs | If secrets missing |
|-----|----------------|--------------------|
| `live_cottage` | dispatch track `live_cottage` or `both` | N/A (no plane secrets). Sets `AIMMUNE_LIVE_COTTAGE=1` |
| `plane_staging` | dispatch track `plane_staging` or `both` | exit 0 (skip). Requires repo secrets `PANOPTICON_BASE_URL`, `HM_SITE_TOKEN`, `SITE_ID` |

Manual without GitHub:

```bash
AIMMUNE_LIVE_COTTAGE=1 pytest -q -m live_cottage
# and / or
PANOPTICON_BASE_URL=… HM_SITE_TOKEN=… SITE_ID=… pytest -q -m plane_staging
```

## Out of scope

ISO / USB bake · Tailscale · SIWE wallet in CI · Playwright · site-implemented resolve/revoke · live `lease_stop` / preempt · live `alias_util` / Eve (follow-on) · vendoring Host / OPNsense · iface pin bump · `schemas/` amend · folding these markers into unmarked `pytest -q`.
