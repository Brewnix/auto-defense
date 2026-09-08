# Slice 0 — pin + inventory freeze

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** pressure-test package **LOCKED 2026-09-08** (Chris)

## Pins

| Dependency | How | Notes |
|------------|-----|-------|
| [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) | git submodule or release SHA | No fork. CI pins SHA here (lock #10). |
| Panopticon plane | `PANOPTICON_BASE_URL` over **WireGuard** (existing host/plane path) | **Not** Tailscale (lock #2). Client only. |
| Host (optional plane-up) | via Panopticon site jobs | Offline: `$STATE_DIR/owner.sock` (H4). |

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

## Device bind checklist (plane)

1. Mint site machine token (`hm_site_…`) for this `site_id`.  
2. Operator `POST`/`PATCH` device with matching `Device.site_id`.  
3. Unbound / wrong site → **404**.

## Plane surfaces

| Method | Path | Auth |
|--------|------|------|
| `POST`/`GET` | `/api/v1/auditor/v0/tickets…` | `hm_site_…` |
| `POST`/`GET` | `/api/v1/hypermesh/site/jobs` | `hm_site_…` |
| `GET` | `/api/v1/hypermesh/site/devices/{device_id}` | `hm_site_…` |

`lease_stop` requires `lease_id` (no omit-for-active).

## Vertical (ready to greenlight)

`0 → 1 → 2 → 4 → 5` then package. Slice 3 parallel after 1. Slices 6–8 after the vertical works.
