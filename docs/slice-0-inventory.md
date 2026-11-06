# Slice 0 — pin + inventory freeze

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** **LOCKED / slice 0 complete** (2026-09-08)  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**CI:** [`.github/workflows/iface-pin.yml`](../.github/workflows/iface-pin.yml) (checkout + submodules; fail if pin missing; `check-jsonschema` + examples)

Pressure-test package 1–10 remains locked (Chris, 2026-09-08). No policy executor, auditor client, preempt client, or UI in this slice.

## Pins

| Dependency | How | Notes |
|------------|-----|-------|
| [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ `3621849bbf7c368b1d709356c465883144300208` | git submodule `vendor/inference-iface` | No fork. CI pins SHA here (lock #10). |
| Hypermesh plane | `PANOPTICON_BASE_URL` + `HM_SITE_TOKEN` + `SITE_ID` over **WireGuard** (existing host/plane path) | **Not** Tailscale (lock #2). Client only. Live owners: [`docs/plane-client.md`](plane-client.md). `FyberLabs/panopticon` is archived (2026-11-05). |
| Host (optional plane-up) | via Hypermesh plane site jobs (`#40`) | Offline: `$STATE_DIR/owner.sock` (H4). |

## Locked decisions (1–10)

| # | Decision |
|---|----------|
| 1 | Code home: **`Brewnix/auto-defense`** (MIT). Contracts stay in `inference-iface`. |
| 2 | Plane reach: **WireGuard** via Panopticon/host — not Tailscale. |
| 3 | **`Device.site_id` bind:** operator / enroll once (`POST`/`PATCH`). Daemon does not auto-bind; unbound → 404. |
| 4 | **AImmune UI SoT:** site-local always. Plane tickets = intent. Optional plane mirror later. Never “blocked” from resolve alone. |
| 5 | **UI before grants:** vertical includes slice 5 before slice 7 privilege_grant plane store. |
| 6 | **Model path cottage v0:** local-only (`rules_primary` + local engine). No plane_ir / leased Host IR chat. |
| 7 | **Dual auth v0:** `hm_site_` for machine doors; SociACL Check/`delegate` for human resolve/mint when that UX lands. |
| 8 | **Naming:** product **AImmune**; engineering repo **`auto-defense`**. |
| 9 | **Router `/v1/ir/chat`:** Hypermesh-only. AImmune UI does **not** consume it. |
| 10 | **Acceptance CI:** pin iface SHA in **this** repo’s CI — do not pull Panopticon monolith. |

Rows 2 and 10 keep their 2026-09-08 wording. As of the 2026-11-05 lock, `FyberLabs/panopticon` is archived and live owners are the `hyperme-sh` map in [`docs/plane-client.md`](plane-client.md). WireGuard, not Tailscale, is unchanged. Door numbers stay historical labels. This note does not claim HTTP paths moved.

## Device bind runbook (plane)

Operator bind **once**. The site daemon never invents `Device.site_id`.

1. Mint a site machine token for this `SITE_ID` (`hm_site_…`): operator `POST /api/v1/hypermesh/site-tokens` (historical `#38`; [`controlplane-identity`](https://github.com/hyperme-sh/controlplane-identity) + [`api-keys-service`](https://github.com/hyperme-sh/api-keys-service); doc name `site-machine-token-v0`). Plaintext is shown once.
2. Store the secret as `HM_SITE_TOKEN` (0600) on the site. Set `PANOPTICON_BASE_URL` to the **WireGuard** gateway origin. Set `SITE_ID` to the same identifier (e.g. `net-tn-cottage`).
3. Confirm `GET ${PANOPTICON_BASE_URL}/api/v1/hypermesh/site-tokens/me` with `Authorization: Bearer ${HM_SITE_TOKEN}`.
4. Operator `POST /api/v1/hypermesh/devices` `{site_id?}` or `PATCH /api/v1/hypermesh/devices/{id}` `{site_id}` so `Device.site_id` matches the token (historical `#40`; public companions [`hypermesh-gateway`](https://github.com/hyperme-sh/hypermesh-gateway) and [`hypermesh-ticket`](https://github.com/hyperme-sh/hypermesh-ticket)).
5. Enqueue and site device GET require `device.site_id == token.site_id`. **Unbound / wrong site / cross-site id → 404** (no existence leak).
6. Revoke via `DELETE /api/v1/hypermesh/site-tokens/{id}`. Do not reuse `hm_dev_`, `hm_rtr_`, `hm1.`, or renter / `purpose: service` keys.

## Plane surfaces

Cite only. Do not reimplement the gateway. Paths are under `PANOPTICON_BASE_URL`. Auth is `hm_site_…` unless noted. **Enqueue ≠ apply.** `lease_stop` **requires** `lease_id` (no omit-for-active).

| Cite | Method | Path | Auth | Role |
|------|--------|------|------|------|
| `#38` `site-machine-token-v0` · [`controlplane-identity`](https://github.com/hyperme-sh/controlplane-identity) + [`api-keys-service`](https://github.com/hyperme-sh/api-keys-service) | `POST` / `GET` / `DELETE` | `/api/v1/hypermesh/site-tokens` · `GET …/site-tokens/me` | operator mint; site Bearer on `/me` | Mint / list / revoke / verify `hm_site_…` |
| `#39` `fyber-auditor-v0` · `hyperme-sh/aiuditor` (private, not linked) | `POST` / `GET` | `/api/v1/auditor/v0/tickets` · `…/{id}` · `…/{id}/resolve` · `…/{id}/ack` | `hm_site_…` on create / site GET / ack; plane operator on resolve | Auditor inbox. Tickets = intent. |
| `#40` `brewnix-executor-bridge-v0` · [`hypermesh-gateway`](https://github.com/hyperme-sh/hypermesh-gateway) · [`hypermesh-ticket`](https://github.com/hyperme-sh/hypermesh-ticket) | `POST` / `GET` | `/api/v1/hypermesh/site/jobs` · `…/{job_id}` | `hm_site_…` | Enqueue + poll `lease_stop` / `sell_pause`. Host applies. |
| `#41` `heartbeat-sell-state-v0` · same public companions | `GET` | `/api/v1/hypermesh/site/devices/{device_id}` | `hm_site_…` | Live last-known Host `sell_state`. Not a receipt write. |

Client notes: [`docs/plane-client.md`](plane-client.md).

## Vertical

`0 → 1 → 2 → 4 → 5` then package. **Slice 0 done.** Slice 3 parallel after 1. Slices 6–8 after the vertical works. Slice 9 packages the daemon ([`docs/slice-9-package.md`](slice-9-package.md)). Full table: [`docs/roadmap.md`](roadmap.md).
