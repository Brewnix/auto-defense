# Synthetics v0 — offline vertical SoT

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this cut  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Cite:** [`docs/slice-9-package.md`](slice-9-package.md) · [`docs/slice-8-sociacl-ir.md`](slice-8-sociacl-ir.md) · [`docs/siwe-v0.md`](siwe-v0.md) · [`tests/conftest.py`](../tests/conftest.py) · [`tests/test_cycle.py`](../tests/test_cycle.py) · [`tests/test_owner_local.py`](../tests/test_owner_local.py) · [`tests/test_grant_mint_local.py`](../tests/test_grant_mint_local.py)

One composed pytest is the offline vertical source of truth. It does **not** replace unit tests. SIWE v0 is on main ([`docs/siwe-v0.md`](siwe-v0.md)); this suite still does **not** require SIWE crypto or a wallet. UI stays Vitest — no Playwright.

## Locked design

| | Rule |
|---|------|
| A | **Offline vertical SoT.** `plane_reachable=false` + `AIMMUNE_EXEC_MOCK=1` → Eve burst → rules **contain** (`port_scan_burst`) **and** **hold** (`ssh_brute`) → verify receipt chain → local resolve → `grant mint-local` → `status --json`. No live Suricata / OPNsense / WireGuard / Panopticon. |
| B | **Compose existing fixtures only.** [`tests/conftest.py`](../tests/conftest.py) bursts, `tmp_state` + `MockAliasStore`. `FakeAuditor` / `FakeGrants` only on the default-off plane-mocked marker. Default is **rules-only** — do not attach a second mock triage stack. |
| C | **Files.** This doc · [`tests/test_synthetic_vertical_offline.py`](../tests/test_synthetic_vertical_offline.py) · [`tests/fixtures/eve_ssh_brute.jsonl`](../tests/fixtures/eve_ssh_brute.jsonl) · [`tests/fixtures/synthetic_vertical/env.offline.sh`](../tests/fixtures/synthetic_vertical/env.offline.sh). Optional: [`scripts/run-synthetics-offline.sh`](../scripts/run-synthetics-offline.sh) · [`tests/test_synthetic_vertical_plane_mocked.py`](../tests/test_synthetic_vertical_plane_mocked.py) (`@pytest.mark.plane_mocked`, default off). |
| D | UI stays Vitest. No Playwright. No SIWE wallet round-trip in this suite (cottage SIWE is the optional host-install UI path). |
| E | Fold the **offline** synthetic into existing `pytest` CI. Iface-pin job and SHA stay unchanged. |
| F | Non-goals: live Eve replay, OPNsense integration tests, Tailscale, replacing the SIWE Vitest suite, replacing unit tests. |

Also locked: WireGuard not Tailscale; iface pin `3621849bbf7c368b1d709356c465883144300208`; no `schemas/` amend; MIT.

## Sequence (SoT)

Two source IPs in one Eve window so rules classify independently (scan SIDs win over brute on the same subject):

| Burst | Fixture / helper | IP | Rule | Policy |
|-------|------------------|----|------|--------|
| Port scan | [`eve_port_scan.jsonl`](../tests/fixtures/eve_port_scan.jsonl) · `port_scan_burst` | `203.0.113.50` | `port_scan_burst` (critical, auto) | **contain** — `execute` + `firewall.block_ip` applied |
| SSH brute | [`eve_ssh_brute.jsonl`](../tests/fixtures/eve_ssh_brute.jsonl) · `ssh_brute_burst` | `203.0.113.60` | `ssh_brute` (high) | **hold** — `propose` + `notify.operator` queued |

Then:

1. `verify-chain` on `$STATE_DIR/receipts.jsonl`
2. `aimmune owner approve --receipt-id <propose>` (plane down — [`docs/slice-5-ui.md`](slice-5-ui.md) / [`docs/slice-8-sociacl-ir.md`](slice-8-sociacl-ir.md) local path; no Check / SIWE required)
3. `aimmune grant mint-local` on the hold incident (site cache only — [`docs/slice-7-privilege-grant.md`](slice-7-privilege-grant.md))
4. `aimmune status --json` — `site_id`, `plane_reachable: false`, growing `receipts.count`, `active_grants >= 1`

`tmp_state` already sets `exec_mock=True` and `plane_reachable=False` with `MockAliasStore`. Do not flip `AIMMUNE_PLANE_REACHABLE` or attach engines.

## Run

```bash
python -m pip install -e '.[dev]'
pytest -q
# offline synthetic is unmarked — included in the default pytest job
```

Operator replay (optional; same fixtures). The script restamps Eve timestamps to now so the default 300s window still matches:

```bash
./scripts/run-synthetics-offline.sh
# or:
source tests/fixtures/synthetic_vertical/env.offline.sh
export AIMMUNE_STATE_DIR=/tmp/aimmune-synthetic
# concatenate Eve fixtures, then:
python -m aimmune cycle
python -m aimmune verify-chain
python -m aimmune owner approve --receipt-id …
python -m aimmune grant mint-local --incident-id … --notes "…" --reason "…" --tool notify.operator
python -m aimmune status --json
```

## Plane-mocked (default off)

[`tests/test_synthetic_vertical_plane_mocked.py`](../tests/test_synthetic_vertical_plane_mocked.py) is **not** the SoT. It contrasts the offline path with in-process `FakeAuditor` / `FakeGrants`:

- cycle-end drain opens a ticket
- `local_resolve` raises `WaitingOnPlaneError`
- `mint_local(..., plane_reachable=True)` raises `PlaneUpMintError`
- grant **propose** (not resolve) is allowed

```bash
pytest -q -m plane_mocked
```

Default `addopts` is `-m "not plane_mocked"` so CI `pytest -q` skips it. No httpx against a live Panopticon.

## CI

[`.github/workflows/iface-pin.yml`](../.github/workflows/iface-pin.yml) `pytest` job is unchanged (`pytest -q`). Offline synthetic rides along. Iface-pin validate job is unchanged. UI job stays lint / typecheck / Vitest.

## Out of scope

Live Suricata replay · OPNsense IT · Tailscale · SIWE wallet round-trip in this suite · Playwright · replacing `test_cycle` / `test_owner_local` / `test_grant_mint_local` · bumping the iface pin · `schemas/` amend · k8s.
