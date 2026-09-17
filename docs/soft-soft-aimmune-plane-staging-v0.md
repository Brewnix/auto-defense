# Soft Soft — AImmune plane_staging v0

**Product:** AImmune  
**Owner:** AImmune Product (small-model harness productization)  
**Date:** 2026-09-17  
**Repo:** [`Brewnix/auto-defense`](https://github.com/Brewnix/auto-defense)  
**Status:** Soft Soft ask (this cut) — docs lock of already-landed `plane_staging` code. No new runtime.  
**License:** MIT

This Soft Soft productizes the **live WireGuard plane safe subset** that is already on `main` after [#16](https://github.com/Brewnix/auto-defense/pull/16). It does **not** add features, bump the iface pin, change schemas, or change CI.

It is a **separate Soft Soft** from [`docs/soft-soft-aimmune-testable-v0.md`](soft-soft-aimmune-testable-v0.md) (offline / MockEngine cottage). Do not collapse the two.

Hypermesh lease / rental is **out of scope**. Productization deploy / field install at scale is **Research’s lane** — this document does not claim it.

## 1. Source of truth

Do not fork these locks. This file only names the shippable Soft Soft slice.

| Kind | Pin |
|------|-----|
| Product code | [`Brewnix/auto-defense`](https://github.com/Brewnix/auto-defense) @ [`a2d3b7ec0a82fc93b53c1b4024995c4fde371587`](https://github.com/Brewnix/auto-defense/commit/a2d3b7ec0a82fc93b53c1b4024995c4fde371587) (`a2d3b7ec` — Soft Soft testable cottage v0 [#16](https://github.com/Brewnix/auto-defense/pull/16) merge) |
| Contracts | [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208) in [`vendor/inference-iface`](../vendor/inference-iface). **Do not bump.** |

Cite (do not fork their locks):

| Doc | What it already locks |
|-----|------------------------|
| [`docs/testing-harden-v0.md`](testing-harden-v0.md) | Default-off `plane_staging`; site-token **safe** subset; pass criteria; skip if secrets unset |
| [`docs/plane-client.md`](plane-client.md) | WireGuard-only reach; `PANOPTICON_BASE_URL` / `HM_SITE_TOKEN` / `SITE_ID`; auditor + grants doors; no Tailscale |
| [`docs/soft-soft-aimmune-testable-v0.md`](soft-soft-aimmune-testable-v0.md) | **Separate** Soft Soft: unmarked offline vertical SoT + MockEngine CI + cottage offline smoke. Already merged via [#16](https://github.com/Brewnix/auto-defense/pull/16). |

Also already on that tip (cite only): [`docs/roadmap.md`](roadmap.md) · [`docs/synthetics-v0.md`](synthetics-v0.md) · [`docs/slice-2-auditor.md`](slice-2-auditor.md) · [`docs/slice-7-privilege-grant.md`](slice-7-privilege-grant.md).

`plane_staging` code already exists: marker in [`pyproject.toml`](../pyproject.toml), test [`tests/test_plane_staging_e2e.py`](../tests/test_plane_staging_e2e.py), optional [`workflow_dispatch`](../.github/workflows/testing-harden-optional.yml) on GitHub-hosted `ubuntu-latest`. This Soft Soft does not re-ship them.

## 2. Relationship to Soft Soft #16

| Soft Soft | What it productizes | What it does not |
|-----------|---------------------|------------------|
| [#16](https://github.com/Brewnix/auto-defense/pull/16) — [`docs/soft-soft-aimmune-testable-v0.md`](soft-soft-aimmune-testable-v0.md) | Offline / MockEngine cottage: unmarked `pytest -q`, MockEngine triage in CI, `scripts/smoke-cottage-offline.sh` | Live WireGuard plane; live Eve contain |
| **This cut** | Live plane **safe** subset: `pytest -q -m plane_staging` from a **WireGuard-reachable** host | Offline cottage SoT (already Soft Soft’d); field deploy; Hypermesh lease |

#16’s HOLD row for `plane_staging` live WireGuard is **this** Soft Soft — not an expansion of that document.

## 3. Soft Soft slice (this Soft Soft)

Shippable definition. Product Soft Softs **this**, not live Eve contain and not Research deploy.

Run from a **WireGuard-reachable** host (cottage or operator box on the overlay):

```bash
export PANOPTICON_BASE_URL=https://panopticon.wg.example   # no trailing slash
export HM_SITE_TOKEN=hm_site_…                            # 0600 on the box; never commit
export SITE_ID=net-tn-cottage                             # must equal the token site

pytest -q -m plane_staging
```

Transport lock: **WireGuard only**, not Tailscale. Sequence and pass criteria are already locked in [`docs/testing-harden-v0.md`](testing-harden-v0.md) (cite, do not fork):

| Check | Expect |
|-------|--------|
| `/site-tokens/me` | 200; token `site_id` == `SITE_ID` |
| Auditor create + GET | 200; `ticket_id` round-trips |
| Grant propose + GET | 200; `grant_id` round-trips; status `proposed` (or plane-equivalent open) |
| Optional ack | 200 **or** 409 (still open / not yet resolved). Never treat as plane resolve |
| Site resolve/revoke | **401 or 403** on ticket resolve, grant resolve, and grant revoke |
| Skip | any of the three env vars unset → skipped, not failed — **not** a Soft Soft pass |

Safe subset only: `site-tokens/me`, auditor create/GET, grant propose/GET, optional ack. **Assert** the site token cannot resolve/revoke. No `lease_stop` / preempt against rented boxes.

This document does **not** claim those secrets exist, that a cottage is online, or that this pytest has already been run.

## 4. Critical Soft Soft note — GitHub-hosted runners

[`.github/workflows/testing-harden-optional.yml`](../.github/workflows/testing-harden-optional.yml) is `workflow_dispatch` only on GitHub-hosted **`ubuntu-latest`**. That runner **cannot Soft Soft-prove WireGuard reach by itself**.

| Surface | What it is | Soft Soft? |
|---------|------------|------------|
| Operator / cottage (or other box on the WG overlay) | `pytest -q -m plane_staging` with the three env vars against a WireGuard-reachable Panopticon | **Yes** — this is Soft Soft evidence |
| Future WG self-hosted runner | Same pytest, if/when a runner sits on the overlay | **Yes**, if it actually reaches the plane over WireGuard |
| GitHub-hosted `ubuntu-latest` dispatch | Optional; skip-ok if secrets missing | **No** — skip is not a Soft Soft pass. Even a green dispatch on `ubuntu-latest` does not prove WireGuard overlay reach |

Optional `workflow_dispatch` remains skip-ok if secrets are missing. That skip is **not** a Soft Soft pass. Do not treat a missing-secrets exit 0 as evidence.

## 5. Secrets

Name only. **Never commit values.**

| Name | Meaning |
|------|---------|
| `PANOPTICON_BASE_URL` | Gateway origin over WireGuard, no trailing slash |
| `HM_SITE_TOKEN` | Opaque site machine token (`hm_site_…`) |
| `SITE_ID` | Site identifier; must equal the token `site_id` |

On the box: store as env (or env file) **0600**. May also be set as repo Actions secrets so optional dispatch can run — that does **not** replace a WG-reachable Soft Soft run, and this document does not claim those Actions secrets are present.

## 6. Gaps / HOLD (explicit)

Follow-on or other owners. **Not this Soft Soft.**

| HOLD | Why it is not this Soft Soft |
|------|------------------------------|
| Live Eve / real `alias_util` contain | Testing-harden follow-on citing the Brewnix gateway. v0 cottage smoke stays `AIMMUNE_EXEC_MOCK=1`. [`docs/testing-harden-v0.md`](testing-harden-v0.md) |
| `lease_stop` Soft Soft / preempt against rented boxes | Forbidden on this cut. Safe subset only. |
| Productization deploy / field install at scale | **Research lane.** Do not claim field deploy Soft Soft. |
| Hypermesh remint / lease / Stripe lease P0 | Other owners. Lease / rental is out of scope for AImmune Product on this repo. |
| Tailscale | Plane transport is WireGuard only. Forever out. |
| Iface pin bump | Stays `3621849bbf7c368b1d709356c465883144300208`. |

Also not this Soft Soft: site-implemented ticket/grant resolve-revoke · live Ollama as Soft Soft-required · `schemas/` amends · folding `plane_staging` into unmarked `pytest -q` / PR CI.

## 7. Acceptance for Soft Soft

Product may Soft Soft when **all** of the following are true:

1. **This doc matches `main` after #16** — no claim that secrets exist, that Soft Soft already ran, that GH-hosted dispatch proves WireGuard, that field deploy shipped, or that Hypermesh lease is in scope. Locks stay in the cited design docs.
2. **WG-reachable evidence** — Product (or an operator they accept) runs `pytest -q -m plane_staging` from a WireGuard-reachable cottage or operator box and **pastes the output into Soft Soft notes**. Skip / missing-secrets / `ubuntu-latest`-only dispatch is not that evidence.
3. **Soft Soft is Product’s.** Hard OK only after Soft Soft **and** the Chris merge path. Do not treat this PR as Hard OK.

After Soft Soft + Hard OK, the live plane safe-subset definition above is the product lock for this cut. Later Soft Softs (live Eve contain, `lease_stop`, Research deploy) are new documents — do not silently expand this one.
