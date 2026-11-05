# Plane client — AImmune → Hypermesh plane over WireGuard

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** slice 7 — fyber.auditor `#39` + Hypermesh `#40` / `#41` + privilege grants `#50`. Resolve (tickets and grants) is plane-only.  
**Transport:** **WireGuard** via the existing Hypermesh plane / host path. **Not Tailscale.**

AImmune is a **client** of the plane. This repo does not fork the gateway, mint tokens, or implement Host jobs. Contracts stay in [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface).

**Plane owner citation (Chris lock 2026-11-05).** [`FyberLabs/panopticon`](https://github.com/FyberLabs/panopticon) is archived. Live owners are the `hyperme-sh` microservices (hyphen). Door numbers `#38` `#39` `#40` `#41` `#50` stay historical labels. Product-lock SoT: [`hyperme-sh/hypermesh-docs`](https://github.com/hyperme-sh/hypermesh-docs). Public plane templates that lived in spanopticon: [`hyperme-sh/spanopticon`](https://github.com/hyperme-sh/spanopticon). Primary plane: [`hyperme-sh/hypermesh-plane`](https://github.com/hyperme-sh/hypermesh-plane). Companions: [`hyperme-sh/hypermesh-gateway`](https://github.com/hyperme-sh/hypermesh-gateway), [`hyperme-sh/hypermesh-ticket`](https://github.com/hyperme-sh/hypermesh-ticket).

| Door | Historical label | Live owner | Extracted doc on `hypermesh-plane` |
|------|------------------|------------|-------------------------------------|
| Site token `hm_site_` | `#38` | [`controlplane-identity`](https://github.com/hyperme-sh/controlplane-identity) + [`api-keys-service`](https://github.com/hyperme-sh/api-keys-service) | [`site-machine-token-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/site-machine-token-v0.md) |
| fyber.auditor | `#39` | [`aiuditor`](https://github.com/hyperme-sh/aiuditor) | [`fyber-auditor-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/fyber-auditor-v0.md) |
| Site jobs | `#40` | [`hypermesh-plane`](https://github.com/hyperme-sh/hypermesh-plane) | [`brewnix-executor-bridge-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/brewnix-executor-bridge-v0.md) |
| Live `sell_state` | `#41` | [`hypermesh-plane`](https://github.com/hyperme-sh/hypermesh-plane) | [`heartbeat-sell-state-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/heartbeat-sell-state-v0.md) |
| Privilege grants | `#50` | [`acl-service`](https://github.com/hyperme-sh/acl-service) (+ [`controlplane-tenancy`](https://github.com/hyperme-sh/controlplane-tenancy) for tenant membership) | [`privilege-grant-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/privilege-grant-v0.md) |

These are owner citations. They do **not** claim the HTTP paths below already moved off `PANOPTICON_BASE_URL`, and they do **not** claim AGX `plane_staging` was re-run against `hyperme-sh`.

## Reach

Site daemons call the gateway at a **WireGuard-reachable** origin. Same overlay the host already uses for plane-up. Offline-first still applies: local `fyber.receipt/v0` always; queue plane POSTs when unreachable. Plane-down owner actuators stay on Host H4 (`$STATE_DIR/owner.sock`) — not this client.

Do **not** add Tailscale (or any second overlay) as plane transport.

## Environment

| Name | Required (plane-up) | Meaning |
|------|---------------------|---------|
| `PANOPTICON_BASE_URL` | yes | Gateway origin over WireGuard, no trailing slash. Example: `https://panopticon.wg.example`. |
| `HM_SITE_TOKEN` | yes | Opaque site machine token (`hm_site_…`). Shown once at mint. Not `hm_dev_`, `hm_rtr_`, `hm1.`, or a renter / `purpose: service` key. |
| `SITE_ID` | yes | This site’s identifier (e.g. `net-tn-cottage`). Must equal the token `site_id` and every `Device.site_id` this daemon talks about. |

Host H4 (plane-down): `AIMMUNE_HOST_STATE_DIR` / `HYPERMESH_STATE_DIR` for `owner.sock` + `owner.token` (**0600**). Do not require the site GET / `/site/jobs` doors when `plane_reachable: false`.

```http
Authorization: Bearer ${HM_SITE_TOKEN}
```

Unknown / expired / revoked token → reject (no leak). Body `site_id`, when present, must equal the token site.

## `site_id` bind (operator, once)

The daemon **does not** auto-bind boxes. Unbound or wrong-site devices 404 on site doors.

1. Operator mints a site token for this `SITE_ID` (historical `#38`; [`controlplane-identity`](https://github.com/hyperme-sh/controlplane-identity) + [`api-keys-service`](https://github.com/hyperme-sh/api-keys-service); [`site-machine-token-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/site-machine-token-v0.md)).
2. Store plaintext as `HM_SITE_TOKEN` on the site (0600). Confirm `GET ${PANOPTICON_BASE_URL}/api/v1/hypermesh/site-tokens/me`.
3. Operator `POST` / `PATCH` each Host device with `Device.site_id` = `SITE_ID` (historical `#40`; [`hypermesh-plane`](https://github.com/hyperme-sh/hypermesh-plane)).
4. Enqueue / device GET require `device.site_id == token.site_id`. Cross-site ids → **404**.

Runbook: [`docs/slice-0-inventory.md`](slice-0-inventory.md#device-bind-runbook-plane).

## Doors this client calls

All paths are under `PANOPTICON_BASE_URL`. Auth is `HM_SITE_TOKEN` unless noted.

### Auditor — historical `#39` ([`hyperme-sh/aiuditor`](https://github.com/hyperme-sh/aiuditor))

Contract: [fyber.auditor API v0](https://github.com/Brewnix/inference-iface/blob/main/docs/fyber-auditor-api-v0.md) · plane doc: [`fyber-auditor-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/fyber-auditor-v0.md)

| Method | Path | Who | Role |
|--------|------|-----|------|
| `POST` | `/api/v1/auditor/v0/tickets` | site | Create (idempotent upsert) |
| `GET` | `/api/v1/auditor/v0/tickets/{id}` | site or plane operator | Read one |
| `POST` | `/api/v1/auditor/v0/tickets/{id}/resolve` | plane operator only | Resolution **intent** (site token rejected) |
| `POST` | `/api/v1/auditor/v0/tickets/{id}/ack` | site | Site wrote apply / observe receipt |

Tickets are intent. Actuation SoT is the site receipt. UI must not claim blocked from resolve alone.

Site implementation: [`aimmune.auditor.client`](../src/aimmune/auditor/client.py) (`POST` create, `GET`, `POST` ack). Drain / poll: [`docs/slice-2-auditor.md`](slice-2-auditor.md). Default timeout **3s**. This repo does **not** implement resolve.

### Site jobs — historical `#40` ([`hyperme-sh/hypermesh-plane`](https://github.com/hyperme-sh/hypermesh-plane))

Contract: [`brewnix-executor-bridge-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/brewnix-executor-bridge-v0.md)

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/v1/hypermesh/site/jobs` | Enqueue existing kinds `lease_stop` / `sell_pause` |
| `GET` | `/api/v1/hypermesh/site/jobs/{job_id}` | Poll until Host reports `passed` or `failed` |

```http
POST ${PANOPTICON_BASE_URL}/api/v1/hypermesh/site/jobs
Authorization: Bearer ${HM_SITE_TOKEN}
{"kind": "sell_pause", "device_id": "<uuid>", "until": "optional-rfc3339"}
```

```http
POST ${PANOPTICON_BASE_URL}/api/v1/hypermesh/site/jobs
Authorization: Bearer ${HM_SITE_TOKEN}
{"kind": "lease_stop", "device_id": "<uuid>", "lease_id": "<uuid>"}
```

### Site devices (live `sell_state`) — historical `#41` ([`hyperme-sh/hypermesh-plane`](https://github.com/hyperme-sh/hypermesh-plane))

Contract: [`heartbeat-sell-state-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/heartbeat-sell-state-v0.md)

| Method | Path | Role |
|--------|------|------|
| `GET` | `/api/v1/hypermesh/site/devices/{device_id}` | Last Host-reported `{device_id, site_id, sell_state, last_heartbeat_at}` |

Not a `fyber.receipt/v0` write. Copy Host-reported `sell_state`. Do not invent `paused` from enqueue.

## Locks the client must not weaken

**Enqueue ≠ apply.** `POST /site/jobs` writes a CP job. Host pulls it and posts the result. Poll `GET` until `status` is `passed` or `failed`. `passed=true` with `sell_state=n/a` is invalid on the Host result door. This client copies that report; it does not treat enqueue as paused / stopped.

**`lease_id` required on `lease_stop`.** Missing or empty → **422**. No omit-for-active. No 409 single-lease fallback. Matches `hypermesh.lease_stop` on the iface pin. Unknown `lease_id` or a lease on another box → **404**.

**H3 drain is Brewnix-side.** Two jobs (`sell_pause` then `lease_stop`), not a Host mega-job. Await pause **result** before enqueueing stops for that device.

**Plane-down.** Do not require these doors when `plane_reachable: false`. Host H4 unix socket is the owner path.

Site implementation: [`aimmune.plane.jobs`](../src/aimmune/plane/jobs.py) · [`aimmune.plane.posture`](../src/aimmune/plane/posture.py). H3 sequencing: [`aimmune.preempt.h3`](../src/aimmune/preempt/h3.py). Plane-down: [`aimmune.host.owner`](../src/aimmune/host/owner.py). Runbook: [`docs/slice-4-preempt.md`](slice-4-preempt.md).

Stale heartbeat: if `last_heartbeat_at` is older than `AIMMUNE_SELL_STATE_STALE_S` (default 300s), treat posture as unknown. Automated stop-only holds.

### Privilege grants — historical `#50` ([`hyperme-sh/acl-service`](https://github.com/hyperme-sh/acl-service))

Tenant membership: [`hyperme-sh/controlplane-tenancy`](https://github.com/hyperme-sh/controlplane-tenancy). Contract: [privilege-grant-v0](https://github.com/Brewnix/inference-iface/blob/3621849bbf7c368b1d709356c465883144300208/docs/privilege-grant-v0.md) · plane doc: [`privilege-grant-v0`](https://github.com/hyperme-sh/hypermesh-plane/blob/main/products/hypermesh/docs/privilege-grant-v0.md)

Same env and timeout as auditor (`PANOPTICON_BASE_URL`, `HM_SITE_TOKEN`, `SITE_ID`, ~3s).

| Method | Path | Who | Role |
|--------|------|-----|------|
| `POST` | `/api/v1/grants/v0/grants` | site | Propose (idempotent `(site_id,incident_id,trace_id)` or `Idempotency-Key`) |
| `GET` | `/api/v1/grants/v0/grants/{id}` | site or plane operator | Read one (incl. terminal) |
| `GET` | `/api/v1/grants/v0/grants?status=proposed\|approved` + optional `incident_id` | site | Narrow list |
| `POST` | `/api/v1/grants/v0/grants/{id}/resolve` | plane operator only | Mint / deny. **Site token must not call this.** |
| `POST` | `/api/v1/grants/v0/grants/{id}/revoke` | plane operator only | Revoke. **Site token must not call this.** |

Plane mint is SoT when reachable. The site cache (`$STATE_DIR/grants.jsonl`) is SoT for `active_until` if the plane drops. Home offline mint is site-local only — no home→plane sync door. Site implementation: [`aimmune.grants.client`](../src/aimmune/grants/client.py). Runbook: [`docs/slice-7-privilege-grant.md`](slice-7-privilege-grant.md). This repo does **not** implement resolve or revoke.

Ticket `approved` is not an elevation. Grant `approved` is not a firewall apply.

## Out of slice 7

SociACL, Phase B cooldown, home→plane grant sync, Tailscale, site-implemented resolve/revoke, `preempt_mode=hard`, `schemas/` edits, iface pin bump.
