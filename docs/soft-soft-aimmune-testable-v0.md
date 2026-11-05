# Greenlight — AImmune testable cottage v0

**Product:** AImmune  
**Owner:** AImmune Product (small-model harness productization)  
**Date:** 2026-09-17  
**Repo:** [`Brewnix/auto-defense`](https://github.com/Brewnix/auto-defense)  
**Status:** Greenlight ask (this cut) — docs lock of already-landed, already-testable code. No new runtime.  
**License:** MIT

Filename [`docs/soft-soft-aimmune-testable-v0.md`](soft-soft-aimmune-testable-v0.md) is a legacy path name. Review vocab is **Greenlight**, then **Sign-off**.

This Greenlight productizes what is already on `main`. It does **not** add features, bump the iface pin, change schemas, or change CI.

Hypermesh lease / rental is **out of scope**. Productization deploy / field install at scale is **Research’s lane** — this document does not claim it.

## 1. Source of truth

Do not fork these locks. This file only names the shippable Greenlight slice.

| Kind | Pin |
|------|-----|
| Product code | [`Brewnix/auto-defense`](https://github.com/Brewnix/auto-defense) @ [`2c9d139353a9cdedc8af13c0b53d31e049c63d79`](https://github.com/Brewnix/auto-defense/commit/2c9d139353a9cdedc8af13c0b53d31e049c63d79) (`2c9d139` — packaging v0 [#15](https://github.com/Brewnix/auto-defense/pull/15)) |
| Contracts | [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208) in [`vendor/inference-iface`](../vendor/inference-iface). **Do not bump.** |

Cite (do not fork their locks):

| Doc | What it already locks |
|-----|------------------------|
| [`docs/roadmap.md`](roadmap.md) | Slice 0–9 exits + follow-on cuts (SIWE, synthetics, testing harden, packaging) |
| [`docs/packaging-v0.md`](packaging-v0.md) | One code SoT; Linux/Orin systemd; Mac Homebrew mock; USB cottage adapter; out-of-scope matrix |
| [`docs/synthetics-v0.md`](synthetics-v0.md) | Unmarked offline vertical SoT (`plane_reachable=false` + `AIMMUNE_EXEC_MOCK=1`) |
| [`docs/testing-harden-v0.md`](testing-harden-v0.md) | Default-off `live_cottage` / `plane_staging`; cottage smoke script; optional dispatch only |
| [`docs/slice-6-model-triage.md`](slice-6-model-triage.md) | MockEngine required for green CI; optional Ollama skipped when unreachable |

Also already on that tip (cite only): [`docs/siwe-v0.md`](siwe-v0.md) · [`docs/siwe-mockcheck-durability-v0.md`](siwe-mockcheck-durability-v0.md) · [`docs/host-install-smoke.md`](host-install-smoke.md) · [`docs/slice-9-package.md`](slice-9-package.md).

## 2. Exists (landed)

Already merged on the product-code SHA above. This Greenlight does not re-ship them.

- **Slices 0–9** — inventory → zero-LLM loop → auditor → incident → preempt → UI → model triage → grants → SociACL IR UX → site daemon package. See [`docs/roadmap.md`](roadmap.md).
- **SIWE + durability** — EIP-4361 cottage session (cookie v2 TTL) + durable MockCheck ACL. [`docs/siwe-v0.md`](siwe-v0.md) · [`docs/siwe-mockcheck-durability-v0.md`](siwe-mockcheck-durability-v0.md).
- **Offline vertical synthetics** — unmarked pytest SoT; plane-down + `AIMMUNE_EXEC_MOCK=1`. [`docs/synthetics-v0.md`](synthetics-v0.md).
- **Packaging v0 adapters** — Linux/Orin systemd SoT; Mac Homebrew mock; USB cottage calls `deploy/install.sh`. [`docs/packaging-v0.md`](packaging-v0.md).
- **Testing harden markers (default-off)** — `live_cottage` / `plane_staging` (and existing `plane_mocked`) stay out of unmarked `pytest -q`. [`docs/testing-harden-v0.md`](testing-harden-v0.md).

## 3. Testable Greenlight slice v0 (this Greenlight)

Shippable definition. Product Greenlights **this**, not live field contain and not Research deploy.

| Evidence | What “done” means | Cite |
|----------|-------------------|------|
| Unmarked offline vertical SoT | `pytest -q` on a plane-down box with `AIMMUNE_EXEC_MOCK=1` includes [`tests/test_synthetic_vertical_offline.py`](../tests/test_synthetic_vertical_offline.py): Eve burst → rules contain (`port_scan`) **and** hold (`ssh_brute`) → verify-chain → local resolve → `grant mint-local` → `status --json`. No live Suricata / OPNsense / WireGuard / Hypermesh plane. | [`docs/synthetics-v0.md`](synthetics-v0.md) |
| MockEngine triage path green in CI | Slice 6 judge path stays green on MockEngine + fixture envelopes. Optional Ollama HTTP adapter is **not** required (live test skips if unreachable). | [`docs/slice-6-model-triage.md`](slice-6-model-triage.md) |
| Cottage offline smoke (operator evidence) | [`scripts/smoke-cottage-offline.sh`](../scripts/smoke-cottage-offline.sh) stages `deploy/install.sh` into a prefix (no root by default), asserts 0700/0600, restamps synthetics fixtures, `aimmune cycle` → `verify-chain` → `status --json`. Documented operator evidence — not folded into unmarked pytest. | [`docs/testing-harden-v0.md`](testing-harden-v0.md) · [`docs/host-install-smoke.md`](host-install-smoke.md) |
| Packaging matrix documented | Linux cottage + Orin/Jetson = systemd SoT (`deploy/`). Mac = Homebrew formula + `brew services`, mock/offline, **no** live OPNsense contain. USB `aimmune-cottage` adapter verifies `VERSION` + `SHA256SUMS` then calls `deploy/install.sh`. | [`docs/packaging-v0.md`](packaging-v0.md) |

How Product (or CI) checks the first two rows:

```bash
python -m pip install -e '.[dev]'
pytest -q
# unmarked offline synthetic rides along; live_cottage / plane_staging / plane_mocked stay deselected
```

Operator cottage evidence (optional; CI-less):

```bash
./scripts/smoke-cottage-offline.sh
```

CI jobs that must stay green — **do not change them**: [`.github/workflows/iface-pin.yml`](../.github/workflows/iface-pin.yml)

| Job | What it already runs |
|-----|----------------------|
| `validate-pin` | Submodule present; `schemas/*.v0.json` + examples at the iface pin |
| `pytest` | `pytest -q` (offline vertical SoT + MockEngine triage; default-off markers excluded) |
| `ui` | `npm run lint` / `typecheck` / `npm test` (Vitest; no Playwright) |

`live_cottage` / `plane_staging` remain `workflow_dispatch` only ([`.github/workflows/testing-harden-optional.yml`](../.github/workflows/testing-harden-optional.yml)). Missing secrets skip, not fail. That is **not** Greenlight-required.

## 4. Gaps / HOLD (explicit)

Follow-on or other owners. **Not this Greenlight.**

| HOLD | Why it is not this Greenlight |
|------|------------------------------|
| Live Eve / real `alias_util` contain | Deferred to Greenlight [`docs/greenlight-aimmune-live-eve-contain-v0.md`](greenlight-aimmune-live-eve-contain-v0.md). v0 smoke stays `AIMMUNE_EXEC_MOCK=1`. [`docs/testing-harden-v0.md`](testing-harden-v0.md) |
| `plane_staging` live WireGuard | Needs secrets + a cottage on the overlay. Greenlight later when Research / productization deploy **and** secrets exist. Default-off; skip if unset. |
| Live Ollama judge on cottage | Optional adapter exists; skipped when unreachable. Greenlight requires MockEngine in CI only. [`docs/slice-6-model-triage.md`](slice-6-model-triage.md) |
| Productization deploy / field install at scale | **Research lane.** This repo ships pip + systemd + adapters + runbooks. Do not claim field rollout. |
| Hypermesh remint / lease / Stripe lease P0 | Other owners. Lease / rental is out of scope for AImmune Product on this repo. |
| Out of scope **forever** for this repo | Cite [`docs/packaging-v0.md`](packaging-v0.md) (and README axioms): `.deb` / `.rpm` · ISO bake · Compose-primary · notarized Mac app · Tailscale · iface pin bump · Playwright · IR chat UI (`/v1/ir/chat`) |

Also not this Greenlight (already documented elsewhere): site-implemented ticket/grant resolve-revoke · live `lease_stop` / preempt against rented boxes · `schemas/` amends · k8s.

## 5. Acceptance for Greenlight

Product may Greenlight when **all** of the following are true:

1. **CI green on `main`** — existing `validate-pin` / `pytest` / `ui` jobs in [`.github/workflows/iface-pin.yml`](../.github/workflows/iface-pin.yml). Do **not** add jobs or fold default-off markers into PR CI.
2. **This doc matches `main`** — no claim of live Eve contain, live WireGuard staging, live Ollama, field deploy, or Hypermesh lease. Locks stay in the cited design docs.
3. **Greenlight is Product’s.** Sign-off only after Greenlight **and** the Chris merge path. Do not treat this PR as Sign-off.

After Greenlight + Sign-off, the testable cottage v0 definition above is the product lock. Live Eve / real `alias_util` contain is deferred to [`docs/greenlight-aimmune-live-eve-contain-v0.md`](greenlight-aimmune-live-eve-contain-v0.md). Do not silently expand this document.
