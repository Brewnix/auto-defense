# AImmune SIWE / MockCheck durability v0

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this cut  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**IR Check:** unchanged — [`docs/slice-8-sociacl-ir.md`](slice-8-sociacl-ir.md). Re-Check at act (`requireIrAct`) is unchanged.  
**SIWE verify:** unchanged EOA / injected-only — [`docs/siwe-v0.md`](siwe-v0.md).

Cottage session TTL plus a durable MockCheck file. Dual door stays. Do not `npm install sociacl`. Iface pin unchanged. No Playwright.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | SIWE signed cookie includes `exp`. Mint `v2.<addr>.<exp>.<hmac>` only. Read leftover `v1.<addr>.<hmac>` (no exp) during upgrade. Expired v2 → logged out (no SIWE principal). `AIMMUNE_SIWE_TTL_S` default **43200** (12h). `DELETE /api/session` clears the UI token and the SIWE principal cookie. |
| B | Prefer `AIMMUNE_SIWE_SECRET`. UI-token HMAC fallback is transitional. Settings shows source (`siwe` / `smoke`), SIWE expiry, and **Sign out**. |
| C | Durable store `$AIMMUNE_STATE_DIR/sociacl-mock.json` (mode **0600**). Load on boot / first Check. Persist on `stateDelegateGrant` / `unstateDelegateGrant` (apply / cancel / undelegate). `AIMMUNE_SOCIACL_FIXTURE` seeds **only when the store is empty or missing**. |
| D | `POST /api/sociacl/undelegate` requires owner on the object. Settings lists live grants on `site:{id}` / `:ir`. Re-Check at act unchanged. |
| E | Vitest: expired cookie denied; persist → reload survives; cancel / undelegate → next Check denies; SIWE verify still EOA / injected-only. Existing SIWE + MockCheck tests stay green. |
| F | Out of scope: WalletConnect, ERC-1271, SociACL WASM / crate / npm, `:host`, plane resolve SociACL, Playwright, iface pin bump, `schemas/` amend. |

## Cookie

| Version | Value | Read |
|---------|-------|------|
| **v2** (mint) | `v2.<addr>.<exp>.<hmac>` | HMAC + `now < exp`. Expired → no SIWE principal. |
| **v1** (legacy) | `v1.<addr>.<hmac>` | HMAC only (unexpired-less). Not minted. |

`source: "siwe"` remains only an HMAC-verified cookie from `POST /api/siwe/verify`. Paste / `X-AImmune-Principal` stay smoke.

## Durable MockCheck

UI resolves `AIMMUNE_STATE_DIR` the same way other UI routes do (`configuredStateDir` — `AIMMUNE_STATE_DIR`, else the `AIMIMUNE_STATE_DIR` typo). When unset, the ACL stays process-local (no file). Cottage systemd env always sets the state dir.

```
$AIMMUNE_STATE_DIR/sociacl-mock.json
```

```json
{
  "objects": [{ "object": "site:net-tn-cottage:ir", "owner": "0xaaa…aaa" }],
  "grants": [
    {
      "principal": "0xbbb…bbb",
      "object": "site:net-tn-cottage:ir",
      "mask": "execute"
    }
  ]
}
```

Restart must not replace a populated store with the fixture. Privilege-down is still immediate: cancel / undelegate deletes the row, persists, and the next Check denies.

## Endpoints

| Method | Path | Result |
|--------|------|--------|
| `GET` | `/api/session` | Adds `exp` (unix seconds, or `null` for smoke / legacy v1). |
| `DELETE` | `/api/session` | Clears `aimmune_ui`, `aimmune_principal` (SIWE v2 / v1), and the nonce cookie. |
| `GET` | `/api/sociacl` | Live grants on `site:{id}` and `:ir`. Principal required. |
| `POST` | `/api/sociacl/undelegate` | Body `{ accessor, object }`. Owner-only. Next Check denies. |

## Environment

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_SIWE_TTL_S` | `43200` | Signed-cookie lifetime (seconds) |
| `AIMMUNE_SIWE_SECRET` | `AIMMUNE_UI_TOKEN` | HMAC key. Dedicated secret preferred; UI-token fallback is transitional |
| `AIMMUNE_STATE_DIR` | unset in UI (Python default `/var/lib/aimmune`) | Durable `sociacl-mock.json` directory |
| `AIMMUNE_SOCIACL_FIXTURE` | unset | Seed JSON **only** when the store is empty / missing |

## Cottage flow

```bash
export AIMMUNE_UI_TOKEN=dev-token
export AIMMUNE_SIWE_SECRET=dev-siwe-secret   # preferred; token fallback still works
export AIMMUNE_SIWE_TTL_S=43200
export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export SITE_ID=net-tn-cottage
export AIMMUNE_OWNER_PRINCIPALS=0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266
```

1. Settings → store UI token → **Connect wallet** (injected `window.ethereum` only).
2. Session card shows `source: siwe`, expiry, **Sign out**.
3. Live MockCheck grants appear under Settings. Owner **Undelegate** calls `POST /api/sociacl/undelegate`.
4. Human acts still re-Check at act (`requireIrAct`).

## Tests

```bash
cd ui && npm ci && npm run lint && npm run typecheck && npm test
```

- Expired v2 cookie → `resolvePrincipal` has no SIWE principal  
- Persist → `resetProcessAcl` → reload still allows  
- Cancel / undelegate → next Check denies (including after reload)  
- Verify remains EOA (`viem.verifyMessage`); Connect remains injected-only  

Iface-pin / pytest unchanged.

## Out of scope

WalletConnect · ERC-1271 · SociACL WASM / crate / npm · `:host` · plane SociACL resolve · Playwright · iface pin bump · `schemas/` amend · IR chat.
