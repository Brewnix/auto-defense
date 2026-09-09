# AImmune roadmap

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Vertical (locked):** `0 → 1 → 2 → 4 → 5` then package. Slices **6** (model triage) and **7** (privilege grants) ride the same pipeline after the vertical.

Contracts stay in [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface). This repo pins that SHA and implements the site executor + UI. Do not fork or weaken schemas.

## Vertical

| Slice | Status | What |
|-------|--------|------|
| **0** | **done** | Pin iface + plane inventory freeze. Submodule, CI, docs. No executor. |
| **1** | **done** | Zero-LLM OPNsense detect → block → `fyber.receipt/v0` + TTL expiry unblock + local notify queue stub + minimal security incident side-record. Rules actor only. [`docs/slice-1-zero-llm.md`](slice-1-zero-llm.md). |
| **2** | **done** | `notify.operator` → fyber.auditor client (`#39` tickets; drain / poll / apply / ack; intent ≠ actuation). [`docs/slice-2-auditor.md`](slice-2-auditor.md). |
| **3** | **done** | Incident side index (`fyber.incident/v0` overlay). Close clocks, ops kind, `lease_stop` require-incident. Never gates contain. [`docs/slice-3-incident.md`](slice-3-incident.md). |
| **4** | **done** | Preempt client + H3 drain: `/site/jobs`, `/site/devices`, H4 offline, thin site_defense hook. `lease_id` required. Enqueue ≠ apply. [`docs/slice-4-preempt.md`](slice-4-preempt.md). |
| **5** | **done** | AImmune UI v0 (site SoT; tickets are intent; no `/v1/ir/chat`). [`docs/slice-5-ui.md`](slice-5-ui.md). |

Then package as one site daemon.

## After the vertical works

| Slice | When | What |
|-------|------|------|
| **6** | **done** | Model triage (`actor.kind: model`, local-only cottage v0). LLM judges; policy executes. [`docs/slice-6-model-triage.md`](slice-6-model-triage.md). |
| **7** | **done** | Privilege grant site client (`#50`). Plane mint / site cache / home offline mint. [`docs/slice-7-privilege-grant.md`](slice-7-privilege-grant.md). |
| **8** | **done** | SociACL IR UX (`Check` / `delegate` for human resolve / mint). Dual auth with `hm_site_`. [`docs/slice-8-sociacl-ir.md`](slice-8-sociacl-ir.md). SIWE v0: [`docs/siwe-v0.md`](siwe-v0.md). |
| **9** | **done** | Package: one site daemon + host wiring runbook (no image bake). [`docs/slice-9-package.md`](slice-9-package.md). |

Slice 3 may start as soon as slice 1 writes receipts. Do not block 2 / 4 / 5 on 3. Slice 8 stays off the critical path until grants exist. Slice 6 is judge-only; slice 7 mints / caches grants.

## Slice 0 exit (landed)

- [`vendor/inference-iface`](../vendor/inference-iface) pins [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ `3621849bbf7c368b1d709356c465883144300208`
- CI: [`.github/workflows/iface-pin.yml`](../.github/workflows/iface-pin.yml) — submodule checkout, fail if pin missing, validate `schemas/*.v0.json` + examples
- Inventory: [`docs/slice-0-inventory.md`](slice-0-inventory.md)
- Plane client: [`docs/plane-client.md`](plane-client.md)

## Slice 1 exit (landed)

- Python package `aimmune` — EVE → bundle → `brewnix-rules/v0.1` → policy → `alias_util` add/delete → receipt hash chain
- Expiry: TTL ledger + `brewnix-rules/expiry` (`execution.status: expired`)
- `propose` / `hold_human` → durable `notify_queue.jsonl` (no plane POST)
- Minimal local `fyber.incident/v0` side-record; contain is not gated on that write
- Tests + pytest CI job; iface-pin CI unchanged
- Runbook: [`docs/slice-1-zero-llm.md`](slice-1-zero-llm.md)

## Slice 2 exit (landed)

- Held companion snapshot on enqueue; old rows fall back to the held receipt
- `aimmune.auditor.client` — create / get / ack with `HM_SITE_TOKEN` (no resolve)
- Drain queue → `POST /api/v1/auditor/v0/tickets`; `auditor_watch.jsonl`
- Poll watches every cycle (no long-poll); apply approved / denied / timed_out / amended; child receipt; ack
- Cycle-end sync only when `plane_reachable` (3s default timeout); CLI `drain` / `poll-tickets`
- Phase A only; incident open/join on propose/hold; never wait on plane
- Tests (httpx mock) + iface-pin CI unchanged
- Runbook: [`docs/slice-2-auditor.md`](slice-2-auditor.md)

## Slice 4 exit (landed)

- `aimmune.plane.jobs` — `#40` POST/GET site jobs (`hm_site_`); `lease_id` required on `lease_stop`
- `aimmune.plane.posture` — `#41` GET `sell_state` + `AIMMUNE_SELL_STATE_STALE_S` (default 300s)
- `aimmune.host.owner` — H4 unix socket for plane-down
- `aimmune.preempt.policy` — strict matrix; profile never grants `hypermesh.*`
- `aimmune.preempt.h3` — pause result before stops; site_defense pause-fail exception; never `hard`
- Thin `site_defense` hook (`AIMMUNE_SITE_DEFENSE_PREEMPT`) — propose into the runner; no Host RTT on the IDS cycle
- CLI `aimmune preempt` (`sell-pause` / `lease-stop` / `drain` / `run`)
- Tests (mock `#40`/`#41`/H4) + iface-pin CI unchanged
- Runbook: [`docs/slice-4-preempt.md`](slice-4-preempt.md)

## Slice 3 exit (landed)

- `IncidentStore` — security 4h join + ops 1h join; human close; `auto_quiet` (security 24h / ops 2h linked-receipt proxy)
- `lease_stop` execute requires an open incident (else propose+notify). Health `sell_pause` prefers ops; never invents security
- Cycle-end sweep after detect/expiry/plane sync; CLI `aimmune incident list|close|sweep`
- UI `/incidents` enrich + human close; snapshot includes full fyber.incident/v0 + index counts
- Grant stub (`grant_ids` / `grant_active` / `require_grant_incident_id`) — no mint
- Tests map to binding acceptance 1–8; iface-pin CI unchanged
- Runbook: [`docs/slice-3-incident.md`](slice-3-incident.md)

## Slice 6 exit (landed)

- `aimmune.triage` — call gate, single winner, MockEngine + optional Ollama + PAIR stub
- Policy forces model companion tools to propose under strict / no grant; elevated execute is grant-gated (`ir_elevated` / `break_glass` + allowlist + θ)
- Cycle wires triage after rules emit / before policy; auto-execute never calls an engine
- `$STATE_DIR/triage_eval.jsonl` redacted pointer (no prompts)
- UI `/receipts` shows `actor.kind` / `actor.id`
- Tests map to model-triage-v0 acceptance 1–8 + eval replay; iface-pin + UI CI unchanged
- Runbook: [`docs/slice-6-model-triage.md`](slice-6-model-triage.md)
- Iface pin stays `3621849bbf7c368b1d709356c465883144300208`

## Slice 7 exit (landed)

- `aimmune.grants` — #50 propose / get / list (no resolve/revoke); local ladder validate; `$STATE_DIR/grants.jsonl`
- Plane mint SoT when up; cache `active_until` if plane drops; home `mint-local` is site-local only
- Cycle-end grant poll after auditor sync; never blocks contain
- Active grant drives `allow_model_execute` / catalog / tier / budget; rails env is a deprecated test override
- CLI `aimmune grant propose|get|list|poll|mint-local|status`
- UI `/grants` + redacted snapshot (no prompts); ticket approve ≠ elevation
- Empty `packs/emergency-v0` + tiny prompt_route registry
- Tests (httpx mock) + iface-pin + UI CI unchanged
- Runbook: [`docs/slice-7-privilege-grant.md`](slice-7-privilege-grant.md)
- Iface pin stays `3621849bbf7c368b1d709356c465883144300208`

## Slice 9 exit (landed)

- Two systemd units: `aimmune.service` (`aimmune loop`) required; `aimmune-ui.service` optional (`next start` on 127.0.0.1). Next is **not** embedded in Python
- In-repo artifact: pip `aimmune` + `deploy/systemd/*.service` + `deploy/aimmune.env.example` + `deploy/install.sh`. No `.deb`/`.rpm`
- Host wiring is a runbook + env contract (Eve, alias_util, WireGuard, `#38` token, `Device.site_id`, H4 sock). No image bake, no vendored Host/OPNsense
- Cycle-end already covers auditor / grant / incident / site_defense hook. No second preempt daemon
- `aimmune status` / `--json` — journald companion; always exits 0; `$STATE_DIR/last_cycle.json`
- UI remains a sibling `npm ci && npm run build`. Iface-pin CI unchanged
- Runbook: [`docs/slice-9-package.md`](slice-9-package.md)
- Iface pin stays `3621849bbf7c368b1d709356c465883144300208`

## Slice 8 exit (landed)

- `ui/lib/sociacl-light` — copied IR light contract from SociACL **master** (`docs/aimmune-ir-check.d.ts` @ `4218cd4022b452d6329007a37b39ee16457facf4` / `.md` @ `38fb1a5b20c05f429af5283f95226d2360aee2c8`; landed via #14) + in-memory MockCheck
- Dual auth: `AIMMUNE_UI_TOKEN` loopback smoke; human acts re-Check a SIWE / cottage principal
- SIWE v0 (follow-on): EIP-4361 nonce → `personal_sign` → verify; signed httpOnly cookie; paste-principal is smoke-only. [`docs/siwe-v0.md`](siwe-v0.md)
- `AIMMUNE_OWNER_PRINCIPALS` owner gate; `break_glass` = execute on `:ir` **and** owner (not a SociACL verb)
- `/holds` local resolve gated `execute`; annotate gated `write`; redacted view `see`/`read`
- `/grants` Check-gates slice 7 plane `#50` propose (when up) and `GrantStore` `mint-local` (plane down). Body stays Brewnix `fyber.privilege_grant/v0` (≠ delegate)
- `:host` / per-incident objects fail closed. Contain / expiry never import Check
- Plane `POST …/resolve` remains JWT — documented gap
- Tests: MockCheck binding 1–6 + annotate pytest; iface pin unchanged
- Runbook: [`docs/slice-8-sociacl-ir.md`](slice-8-sociacl-ir.md)

## SIWE v0 (cottage session)

- `GET /api/siwe/nonce` + `POST /api/siwe/verify` with viem (`verifyMessage`). EOA only.
- Settings Connect uses injected `window.ethereum` (`personal_sign`). No WalletConnect / Wagmi.
- Signed httpOnly `aimmune_principal` (`v1.<addr>.<hmac>`). `source: "siwe"` only after verify.
- Paste-principal / `POST /api/session` `{ principal }` is smoke-only; production fails closed unless `AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL=1`.
- Env: `AIMMUNE_SIWE_DOMAIN` (loopback default), statement binds `site:{SITE_ID}`, optional `AIMMUNE_SIWE_CHAIN_ID`.
- MockCheck / `requireIrAct` unchanged. Iface pin unchanged. [`docs/siwe-v0.md`](siwe-v0.md).

## Synthetics v0 + host-install smoke (landed)

- Offline vertical SoT: plane-down + `AIMMUNE_EXEC_MOCK=1` → Eve burst → rules contain (`port_scan`) **and** hold (`ssh_brute`) → verify-chain → local resolve → `grant mint-local` → `status --json`. No live Suricata / OPNsense / WG / Panopticon. Does not require SIWE crypto.
- Compose existing fixtures (`conftest`, `MockAlias`). Rules-only default. Plane-mocked marker is default-off (`FakeAuditor` / `FakeGrants` only)
- Folded into existing `pytest` CI. Iface-pin unchanged. UI stays Vitest
- Host-install smoke started **doc-only** (extends slice 9). USB roles are pointers + tarball notes, not qcow. Cottage offline script + `live_cottage` landed in testing harden v0
- Optional UI path on cottage: SIWE Connect (landed) or smoke principal — [`docs/siwe-v0.md`](siwe-v0.md)
- Runbook: [`docs/synthetics-v0.md`](synthetics-v0.md) · [`docs/host-install-smoke.md`](host-install-smoke.md) · [`docs/usb-layout.md`](usb-layout.md)

## Testing harden v0 (this cut)

- Two **default-off** markers: `live_cottage` (cottage install path → offline contain, `AIMMUNE_EXEC_MOCK=1`) and `plane_staging` (live WireGuard site-token **safe** subset + deny resolve/revoke). Neither folds into unmarked `pytest -q` / PR pytest
- Script: [`scripts/smoke-cottage-offline.sh`](../scripts/smoke-cottage-offline.sh). Optional `workflow_dispatch` only — [`.github/workflows/testing-harden-optional.yml`](../.github/workflows/testing-harden-optional.yml). Secrets missing → skip, not fail
- `plane_mocked` FakeAuditor/FakeGrants and offline vertical SoT unchanged. No Playwright. UI stays Vitest. Iface pin unchanged
- Runbook: [`docs/testing-harden-v0.md`](testing-harden-v0.md)

## Slice 5 exit (landed)

- `aimmune.ui.status` — display enums; never blocked from resolve alone
- `aimmune.owner.local` — local approve/deny via the same apply path as poll
- CLI `aimmune owner approve|deny`, `ui-snapshot`, `ui`
- Next.js + shadcn console in `ui/` (loopback + `AIMMUNE_UI_TOKEN`)
- Tests: pytest copy/apply + UI lint/typecheck/vitest; iface-pin CI unchanged
- Runbook: [`docs/slice-5-ui.md`](slice-5-ui.md)

## Not this repo

Panopticon SaaS gateway fork · Hypermesh-router IR chat UI · `schemas/` amends · market / renter surfaces · Tailscale-as-plane-transport.
