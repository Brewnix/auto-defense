# Slice 0 — pin + inventory freeze

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** draft checklist (2026-09-08)

## Pins

| Dependency | How | Notes |
|------------|-----|-------|
| [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) | git submodule or release SHA | No fork. |
| Panopticon plane | `PANOPTICON_BASE_URL` over **WireGuard** (existing host/plane path) | **Not** Tailscale. Client only. |
| Host (optional plane-up) | via Panopticon site jobs | Offline: `$STATE_DIR/owner.sock` (H4). |

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

## Locked so far

- Repo / product: **AImmune** product, **`auto-defense`** engineering repo  
- Plane reach: **WireGuard** (Panopticon/host) — not Tailscale  

## Still open (Chris)

3 operator bind · 4 UI SoT · 5 grants vs UI · 6 local model · 7 dual auth · 9 IR chat · 10 CI pin
