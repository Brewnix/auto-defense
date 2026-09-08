# Slice 7 — privilege grant site client

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Specs (source of truth — do not fork):**  
[`privilege-grant-v0.md`](../vendor/inference-iface/docs/privilege-grant-v0.md) · plane integrator: [Panopticon privilege-grant-v0](https://github.com/FyberLabs/panopticon/blob/main/products/hypermesh/docs/privilege-grant-v0.md) · [`fyber-auditor-api-v0.md`](../vendor/inference-iface/docs/fyber-auditor-api-v0.md) · [`incident-binding-v0.md`](../vendor/inference-iface/docs/incident-binding-v0.md)

Site client for Panopticon **#50** (`/api/v1/grants/v0/grants`). Automations propose. A human (or home owner, plane-down) mints. Policy hot-reloads `allow_model_execute` / catalogs / tier / budget from the **active grant**. The LLM never executes and is never `resolved_by`.

**Iface pin is not bumped.** `schemas/` are not amended.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | Plane mint when up; site cache `active_until` if the plane drops; home offline mint is **site-local only**. |
| B | Cycle-end `GET /api/v1/grants/v0/grants?status=approved&incident_id=` (and/or watch open proposes) — short timeout; never block contain. |
| C | Grants replace `AIMMUNE_RAILS_GRANT_*` / `RailsStub` as SoT. Test-only fixture injector kept; rails env is a **deprecated override**. |
| D | CLI + library first (`aimmune grant propose\|get\|list\|poll\|mint-local\|status`). Thin auto-propose is optional — no ChatOps escalate. |
| E | `break_glass` home: local mint requires open incident + auditor ticket id (or local ticket stub) + notes; clamp TTL ≤3600 prefer 1800. Plane-up BG is plane-resolved — site **never** `POST …/resolve`. |
| F | [`docs/plane-client.md`](plane-client.md) cites #50 doors like #39 / #40 / #41. |

Also locked from privilege-grant-v0: five ask kinds only; empty asks → refuse (use a ticket); profile ladder strict / `ir_elevated`≤8h / `break_glass`≤60m; `incident_id` required; `hypermesh.*` never implied by profile; LLM never `resolved_by`; no prompts in the grant body; ticket approved ≠ elevation; grant approved ≠ firewall apply; no SociACL on the grant body (slice 8 Check-gates the existing UI/API; plane when up, home mint-local when down); no Phase B cooldown; no home→plane sync door.

## SoT

1. **Plane up** — `POST /grants` propose; poll approved / proposed into `$STATE_DIR/grants.jsonl`.
2. **Plane drops** — cached `approved` + `active_until` remains SoT until that clock.
3. **Plane down home mint** — `aimmune grant mint-local` writes the cache only. No later sync door.

No grant → **strict**. `AIMMUNE_RAILS_GRANT_ACTIVE` may still inject an elevation for pytest; it is not production SoT.

## Plane doors (site token `hm_site_`)

Same env as auditor: `PANOPTICON_BASE_URL`, `HM_SITE_TOKEN`, `SITE_ID`, timeout ~3s.

| Method | Path | Site role |
|--------|------|-----------|
| `POST` | `/api/v1/grants/v0/grants` | propose (idempotent `(site_id,incident_id,trace_id)` or `Idempotency-Key`) |
| `GET` | `/api/v1/grants/v0/grants/{id}` | read incl. terminal |
| `GET` | `/api/v1/grants/v0/grants?status=proposed\|approved` + optional `incident_id` | narrow list |
| `POST` | `…/resolve` · `…/revoke` | **DO NOT CALL** from site |

## What this slice includes

| Piece | Module | Notes |
|-------|--------|--------|
| Client | `aimmune.grants.client` | propose / get / list. No resolve/revoke methods. |
| Validate | `aimmune.grants.validate` | Ladder before POST / mint (empty/CUT asks, budget+tier, hypermesh, TTL clamps) |
| Cache | `aimmune.grants.store` | `$STATE_DIR/grants.jsonl`; `active_for_incident`; local expire |
| Home mint | `aimmune.grants.home` | Offline approved row; plane-up refused |
| Hot-reload | `aimmune.grants.hotreload` | `allow_model_execute` / allowlist / tier / budget from active grant |
| Poll | `aimmune.grants.poll` | Cycle-end; fail-open; wires `attach_grant` / `set_grant_active` |
| CLI | `aimmune grant …` | Resolve is plane-only (documented; not implemented) |
| UI | `/grants` | Snapshot list + minimal propose / mint-local form |
| Registries | `packs/emergency-v0.json` (empty) · `ir.triage.v0` / `emergency.contain.v0` | Stub only |

## Ask kinds (v0 ONLY — five)

`tool_allowlist_add` · `rate_limit_raise` · `budget_tokens` (+ sibling `model_tier`) · `model_tier` · `prompt_route`. Unknown / CUT kinds (`shell_unrestricted`, `mcp_allowlist`, `rails_profile` as an ask, …) are rejected. Empty `asks` → refuse; use a ticket.

`packs/emergency-v0` ships **empty** and adds nothing. `hypermesh.*` is never implied by profile.

## Cycle

```
detect → expiry → auditor drain/poll (if plane up)
       → grant poll (approved + proposed for open incidents; expire local)
       → incident sweep
```

Grant poll failure never blocks contain. Sweep sees current `grant_active` so auto_quiet will not close under an active grant.

## CLI

```bash
python -m aimmune grant propose --incident-id … --profile ir_elevated --ttl 14400 \
  --reason "…" --tool health.restart_service --tool notify.operator
python -m aimmune grant get --id …
python -m aimmune grant list --status approved --incident-id …
python -m aimmune grant poll
python -m aimmune grant mint-local --incident-id … --notes "…" --reason "…" --profile break_glass
python -m aimmune grant status --incident-id …
```

Resolve / revoke are **plane-only**. This CLI does not implement them.

## Environment

Same as slices 1–6, plus:

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_RAILS_GRANT_ACTIVE` | `false` | **Deprecated** test-only override. Warns. Prefer a grant fixture. |
| `AIMMUNE_RAILS_GRANT_UNTIL` | unset | Deprecated stub expiry |
| `AIMMUNE_RAILS_TOOL_ALLOWLIST` | empty | Deprecated stub allowlist |
| `AIMMUNE_RAILS_PROFILE` | `strict` | Resting profile when no grant |

## Run

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
python -m pip install -e '.[dev]'

export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_EXEC_MOCK=1

python -m aimmune cycle
pytest tests/test_grants.py tests/test_triage.py tests/test_triage_acceptance.py
cd ui && npm ci && npm run lint && npm run typecheck && npm test
```

## Acceptance (mapped)

1. Propose is idempotent on `(site_id, incident_id, trace_id)` / Idempotency-Key  
2. List by incident; GET includes terminal  
3. Site client has no resolve/revoke; never POSTs those doors  
4. Poll → cache → `allow_model_execute` true under approved `ir_elevated` / `break_glass`  
5. After `active_until` → strict  
6. Empty asks / CUT kinds / budget without tier / hypermesh on `ir_elevated` rejected  
7. `break_glass` TTL 7200 clamps to 1800; offline mint; plane-up mint refused  
8. Incident close refused while grant active  
9. Elevated model execute uses the grant, not rails env  
10. Snapshot / UI strips prompts  

## Out of scope

Site resolve/revoke · home→plane sync · SociACL · Phase B cooldown · schema amend · ChatOps · sixth ask kind · bumping the iface pin
