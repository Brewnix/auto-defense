# Slice 8 — SociACL IR UX

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Consume contract (SociACL master — copy / re-type only):**  
[`docs/aimmune-ir-check.d.ts`](https://github.com/FyberLabs/SociACL/blob/master/docs/aimmune-ir-check.d.ts) (`4218cd4022b452d6329007a37b39ee16457facf4`) · [`docs/aimmune-ir-check.md`](https://github.com/FyberLabs/SociACL/blob/master/docs/aimmune-ir-check.md) (`38fb1a5b20c05f429af5283f95226d2360aee2c8`)  
Landed on master via [SociACL #14](https://github.com/FyberLabs/SociACL/pull/14). Pin these master blobs — not the PR branch. Do not `npm install sociacl`. No crate / NAPI / WASM.  
**Binding:** [`sociacl-ir-binding-v0.md`](https://github.com/Brewnix/inference-iface/blob/main/docs/sociacl-ir-binding-v0.md) (do not fork)

Site UI + home-offline human acts. MockCheck-first. Do **not** `npm install sociacl`. No Rust / NAPI / WASM on the Next light path. Do **not** block on Panopticon adopting SociACL for plane resolve.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | Site UI + home-offline human acts only. Do not wait on plane SociACL. |
| B | MockCheck-first. Copy / re-type the IR light contract from **SociACL master** (not the #14 PR branch). Types + MockCheck live in [`ui/lib/sociacl-light/`](../ui/lib/sociacl-light/). |
| C | Dual tokens during transition. `AIMMUNE_UI_TOKEN` stays for loopback smoke. Production human path requires Check (SIWE / cottage session principal). Machine doors stay `hm_site_`. |
| D | Owner list is `AIMMUNE_OWNER_PRINCIPALS` (SIWE addresses). `break_glass` = Check `execute` on `:ir` **and** principal ∈ owners — not a SociACL verb. |
| E | Objects this cut: `site:{site_id}` and `site:{site_id}:ir` only. `:host` and per-incident ACL objects fail closed. |
| F | Auditor / grant `POST …/resolve` remains plane JWT. Documented gap. Out of this PR. |

Also locked: contain / expiry **never** Calls Check; write without execute = annotate-only; re-Check at act time (no cached allow across undelegate / `until`); privilege_grant body stays Brewnix; hop / hint never sets `allowed`; hopcap 1; iface pin unchanged; no `schemas/` amend; no IR chat; MIT.

## Consume names (copied)

From [SociACL master](https://github.com/FyberLabs/SociACL/blob/master/docs/aimmune-ir-check.d.ts) (names unchanged from the #14 land):

- `SiteObjectId`, `AccessorId` (cottage = SIWE address), `ActionMask` `read` \| `write` \| `execute`
- `DelegateGrant`, `DelegateGraph` / `DelegateAcl`
- `checkDelegate`, `applyDelegate`, `cancelDelegate` / `undelegate`, `remintCapability` stub
- `mapAction` (`see` → `read`), `acceptHint` never allows, `until` exclusive

MockCheck in-memory rows: `principal`, `object`, `mask`, `from?`, `until?`, `owner?`.

Rules: object owner → allow; else a matching live grant with `now ∈ [from, until)`; cancel deletes the row → next Check denies.

## Wire into the existing UI

| Surface | Gate |
|---------|------|
| Redacted view (`/holds`, `/receipts`, `/incidents`) | `see` / `read` on `site:{SITE_ID}:ir` |
| Annotate (`/api/annotate`, note on resolve) | `write` only — must not imply execute |
| Local resolve (`/holds` approve/deny → `/api/owner`) | `checkDelegate(..., 'execute')` at act |
| Non-`break_glass` propose / mint (`/grants` → `/api/grant`) | `execute` on `:ir` at act |
| `break_glass` propose / mint | `execute` **and** principal ∈ `AIMMUNE_OWNER_PRINCIPALS` |

Session principal comes from the cottage SIWE address cookie (`aimmune_principal` / `X-AImmune-Principal`) when set. Loopback smoke may use `AIMMUNE_UI_SMOKE_PRINCIPAL` after the UI token is accepted. Re-Check every act — do not cache allow.

Dual grant SoT (slice 7 + this Check gate):

1. **Plane up** — existing `/api/grant` propose uses the slice 7 plane client (`#50`). Check authorizes the human act; the stored object is still `fyber.privilege_grant/v0` via `GrantStore`.
2. **Plane down** — home `mint_local` / `aimmune grant mint-local` writes the same site cache. Check-gated in the UI. Offline path only — no home-only mint SoT, no parallel `owner.grant` writer.
3. The privilege_grant body is **not** a SociACL `delegate`. Plane `POST …/resolve` stays JWT.

## Dual token

| Door | Who | Slice 8 |
|------|-----|---------|
| `AIMMUNE_UI_TOKEN` | Loopback console / smoke | Still required to serve |
| SIWE / cottage principal | Human acts | Required for Check. Production fails closed without it (unless smoke principal is explicitly allowed). |
| `hm_site_` | Machine auditor / jobs / sell_state | Unchanged. Not a SociACL type. |

## Documented gap

Auditor and grant **`POST …/resolve` on the plane remain plane JWT**. Panopticon has not adopted SociACL for plane resolve. This PR does not implement site-side plane resolve and does not wait on that adoption.

## Environment

| Name | Meaning |
|------|---------|
| `AIMMUNE_UI_TOKEN` | Required to serve (loopback smoke) |
| `AIMMUNE_UI_SMOKE_PRINCIPAL` | Loopback Check principal when no SIWE cookie |
| `AIMMUNE_OWNER_PRINCIPALS` | Comma-separated SIWE addresses. First address owns `site:{id}` and `site:{id}:ir` when no fixture objects exist. |
| `AIMMUNE_SOCIACL_FIXTURE` | Optional JSON `{ objects, grants }` for MockCheck rows |
| `AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL` | Opt-in smoke principal in production |
| `SITE_ID` / `AIMMUNE_SITE_ID` | Same token as envelopes / grants / auditor scope |
| `HM_SITE_TOKEN` | Machine door — unchanged |

## Smoke local approve with MockCheck fixtures

```bash
export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_EXEC_MOCK=1
export SITE_ID=net-tn-cottage
export AIMMUNE_PLANE_REACHABLE=0
export AIMMUNE_UI_TOKEN=dev-token
export AIMMUNE_OWNER_PRINCIPALS=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export AIMMUNE_UI_SMOKE_PRINCIPAL=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

python -m pip install -e '.[dev]'
python -m aimmune cycle

cd ui && npm install && npm run dev   # 127.0.0.1:3000
```

1. Open `http://127.0.0.1:3000/settings`, store the UI token (principal optional — smoke principal is used).
2. Open `/holds`. Owner MockCheck allows `execute` on `site:net-tn-cottage:ir`.
3. **Approve locally**. The API re-Checks `execute` at act, then spawns `aimmune owner approve`.

Delegated (non-owner) fixture:

```json
{
  "objects": [
    { "object": "site:net-tn-cottage:ir", "owner": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  ],
  "grants": [
    {
      "principal": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "object": "site:net-tn-cottage:ir",
      "mask": "execute"
    },
    {
      "principal": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "object": "site:net-tn-cottage:ir",
      "mask": "write"
    },
    {
      "principal": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "object": "site:net-tn-cottage:ir",
      "mask": "read"
    }
  ]
}
```

`export AIMMUNE_SOCIACL_FIXTURE=/path/to/fixture.json` and set the cottage principal cookie to `0xbb…`. That principal can resolve / mint but **cannot** `break_glass`.

Write-only: seed `mask: "write"` only — Annotate only is offered; approve/deny is hidden and `/api/owner` returns 403.

Cancel: `cancelDelegate` / `undelegate` deletes the row. The next resolve is denied (binding 4).

## Tests

```bash
cd ui && npm ci && npm run lint && npm run typecheck && npm test
pytest -q tests/test_contain_no_check.py tests/test_owner_annotate.py tests/test_grant_mint_local.py tests/test_grants.py
```

Vitest `ui/lib/sociacl-light/mock-check.test.ts` maps binding acceptance 1–6:

1. `execute` on `:ir` can resolve / mint; same principal cannot `break_glass` without the owner list  
2. `write` ≠ resolve / mint (annotate-only)  
3. Re-Check at act; `until` exclusive; `from` inclusive  
4. Cancel clears — next Check denies  
5. Contain / expiry / alias / cycle never import Check  
6. `fyber.privilege_grant/v0` body ≠ SociACL `delegate`

Iface-pin CI is unchanged. Pin stays `3621849bbf7c368b1d709356c465883144300208`.

## Out of scope

Rust / NAPI / WASM in Next · Elect / wills · per-incident ACL · Check on contain · hop as grant · replacing `hm_site_` · plane SociACL · `:host` · `schemas/` amend · IR chat · site-implemented plane `POST …/resolve`.
