# AImmune SIWE v0 — EIP-4361 cottage session

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this cut  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**IR Check:** unchanged — [`docs/slice-8-sociacl-ir.md`](slice-8-sociacl-ir.md). SIWE address is the SociACL `AccessorId`.

Cottage operator session. Server verifies EIP-4361 with **viem** (`parseSiweMessage` + `verifyMessage`). No WalletConnect / Wagmi / Web3Modal. No ERC-1271. Do not `npm install sociacl`. Iface pin unchanged.

Cookie TTL + durable MockCheck: [`siwe-mockcheck-durability-v0.md`](siwe-mockcheck-durability-v0.md).

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | `GET /api/siwe/nonce` + `POST /api/siwe/verify` `{ message, signature }`. httpOnly `aimmune_principal` is set **only** after verify. Freeform `POST /api/session` `{ principal }` is smoke-only — not SIWE in production. |
| B | Injected `window.ethereum` only (MetaMask / Brave). Settings: Connect → `personal_sign` → verify. |
| C | Dual door: `AIMMUNE_UI_TOKEN` still required to serve (proxy). SIWE address is Check `AccessorId`. Production without SIWE fails closed unless `AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL=1`. |
| D | `AIMMUNE_SIWE_DOMAIN` (loopback default). Statement binds `site:{SITE_ID}`. Optional `AIMMUNE_SIWE_CHAIN_ID`. |
| E | Out of scope: ERC-1271, WalletConnect, Gun SEA, WebAuthn PRF, Panopticon OIDC, plane SociACL resolve. |
| F | Tests: one-time nonce; bad sig → 401; address lowercase `0x`; httpOnly cookie; smoke in non-prod; MockCheck / `requireIrAct` unchanged. |

## Endpoints

| Method | Path | Result |
|--------|------|--------|
| `GET` | `/api/siwe/nonce` | `{ nonce, domain, uri, statement, version, chainId, issuedAt, expirationTime, site_id }` + httpOnly `aimmune_siwe_nonce` (TTL 10m, one-time) |
| `POST` | `/api/siwe/verify` | Body `{ message, signature }`. 200 + signed httpOnly `aimmune_principal` (`v2.<addr>.<exp>.<hmac>`). Bad sig / nonce / domain / statement → **401**. |
| `POST` | `/api/session` | Token cookie unchanged. `{ principal }` only when smoke is allowed; `resolvePrincipal` labels that **`smoke`**, never `siwe`. Production → **403**. |
| `DELETE` | `/api/session` | Clears UI token + SIWE principal + nonce cookies (Sign out). |
| `GET` | `/api/session` | `{ principal, source, exp, … }`. `exp` is set for SIWE v2. |

`resolvePrincipal` source `"siwe"` is only the HMAC-verified cookie from `/api/siwe/verify`. Unsigned paste / `X-AImmune-Principal` cannot claim SIWE in production.

## Environment

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_SIWE_DOMAIN` | `127.0.0.1` | EIP-4361 domain (RFC 3986 authority) |
| `AIMMUNE_SIWE_CHAIN_ID` | unset (client sends `1`; server accepts any) | Optional required chain |
| `AIMMUNE_SIWE_URI` | `http://{domain}:{AIMMUNE_UI_PORT}` | Optional URI override |
| `AIMMUNE_SIWE_SECRET` | `AIMMUNE_UI_TOKEN` | HMAC key for the signed principal cookie. Dedicated secret preferred; UI-token fallback is transitional |
| `AIMMUNE_SIWE_TTL_S` | `43200` | Signed-cookie lifetime (seconds). Expired v2 → logged out |
| `AIMMUNE_OWNER_PRINCIPALS` | unset | Comma-separated SIWE addresses (slice 8 owner list) |
| `AIMMUNE_UI_SMOKE_PRINCIPAL` | unset | Loopback Check principal when no SIWE cookie |
| `AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL` | unset | Opt-in paste/smoke principal in production |

`AIMMUNE_UI_TOKEN` remains required to serve. Statement always includes `site:{SITE_ID}`.

## Cottage flow

```bash
export AIMMUNE_UI_TOKEN=dev-token
export SITE_ID=net-tn-cottage
export AIMMUNE_SIWE_DOMAIN=127.0.0.1
export AIMMUNE_OWNER_PRINCIPALS=0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266
# loopback without a wallet:
export AIMMUNE_UI_SMOKE_PRINCIPAL=0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266

cd ui && npm install && npm run dev
```

1. Open `/settings`, store the UI token.
2. **Connect wallet** (injected Ethereum) → sign the SIWE message → v2 cookie is set (`exp` = now + `AIMMUNE_SIWE_TTL_S`).
3. Human acts re-Check that address on `site:{SITE_ID}:ir` (slice 8). MockCheck / `requireIrAct` are unchanged.
4. Settings shows source / SIWE expiry / **Sign out**. Durable MockCheck + owner undelegate: [`siwe-mockcheck-durability-v0.md`](siwe-mockcheck-durability-v0.md).

Loopback without a wallet: leave smoke env set and skip Connect. `GET /api/session` reports `source: "smoke"`.

## Out of scope

ERC-1271 · WalletConnect · Wagmi / Web3Modal · Gun SEA · WebAuthn PRF · Panopticon OIDC · plane SociACL resolve · `npm install sociacl` · iface pin bump · IR chat.
