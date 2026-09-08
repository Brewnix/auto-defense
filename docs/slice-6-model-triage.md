# Slice 6 — model triage (judge only)

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** this slice  
**Pin:** [`vendor/inference-iface`](../vendor/inference-iface) → [`Brewnix/inference-iface`](https://github.com/Brewnix/inference-iface) @ [`3621849bbf7c368b1d709356c465883144300208`](https://github.com/Brewnix/inference-iface/commit/3621849bbf7c368b1d709356c465883144300208)  
**Specs (source of truth — do not fork):**  
[`model-triage-v0.md`](../vendor/inference-iface/docs/model-triage-v0.md) · [`privilege-grant-v0.md`](../vendor/inference-iface/docs/privilege-grant-v0.md) (cite only — no grant mint) · [`zero-llm-opnsense-loop.md`](../vendor/inference-iface/docs/zero-llm-opnsense-loop.md)

A **judge-only** local model on the same pipeline as the zero-LLM loop: `feature_bundle` → envelope → policy → executor → receipt. The LLM never sits in the executor path. Critical auto-contain stays rule-deterministic with **no** model process. Prompts never leave the site box.

**Iface pin is not bumped.** `schemas/` are not amended.

## Locked design (Chris 2026-09-08)

| | Rule |
|---|------|
| A | Full judge path under **strict** (model propose/hold/notify only). Elevated execute is grant-gated (slice 7). A **deprecated rails stub** remains as a test-only injector. |
| B | CI uses **MockEngine + fixture envelopes**. Optional Ollama HTTP adapter is behind config and is skipped when unreachable. |
| C | `model_assist` is implemented and tested. **Default off.** Home default = `rules_only` (no engines) or `rules_primary` (engines configured). `model_primary` is rejected. |
| D | Eval harness is offline **pytest replay** (schema rate, subject-bind, strict dry-run over-execute=0, offline contain). No eval service. |
| E | Cycle placement: after rules emit / before policy. Decide call → engine → **single winner** → policy → exec. Auto-execute never reaches an engine. |
| F | Under strict, model `hypermesh.*` stay propose/hold. Profile never implies execute. |

Also locked from model-triage-v0: single envelope winner (never merge); ≤1 schema repair then fallback; `allow_model_execute` derived (not an envelope field); θ=0.6; unknown tools stripped; no `needs_model`; no ChatOps; no `fail_open_execute`; PAIR stub returns `engine_unavailable`; cottage tiers are local-only.

## What this slice includes

| Piece | Module | Notes |
|-------|--------|--------|
| Settings | `aimmune.triage.settings` | `triage_mode`, engines[], θ, enrich, rails stub. Env + optional yaml. |
| Call / winner | `aimmune.triage.decide` | `should_call_model`, `select_winner`, strip, subject-bind, `allow_model_execute` |
| Engines | `aimmune.triage.engines` | `MockEngine` (CI), `OllamaEngine` (optional HTTP), `PairEngine` (always unavailable) |
| Runner | `aimmune.triage.runner` | Ordered `engines[]` walk; ≤1 no-op repair; eval-log pointer |
| Policy gates | `aimmune.policy._decide_model` | Model critical ≠ auto-rule critical. Strict → propose. Elevated → allowlist + θ + whitelist/rate/bind |
| Cycle | `aimmune.cycle` | Triage between rules emit and `decide`. Instruments `policy_inputs` |
| Eval log | `$STATE_DIR/triage_eval.jsonl` | winner / engine id / failure / digests. **No prompts** |
| UI | `/receipts` | Shows `actor.kind` / `actor.id` when the model wins. No eval-log bodies. No IR chat |

## Rails stub vs slice 7

Slice 7 is the SoT. `allow_model_execute` is derived from an **active privilege grant** first. No grant → strict.

`AIMMUNE_RAILS_GRANT_*` / `RailsStub` remain a **deprecated test-only override** (pytest fixtures). Profile alone does **not** elevate. After `active_until` the stub is expired (strict). Production must not rely on these env knobs.

`hypermesh.*` are never implied by profile. They execute from a model only if an explicit `tool_allowlist_add` (or the empty emergency pack, which adds nothing) lists them.

## Engines

| Kind | CI | Behavior |
|------|----|----------|
| `mock` | **required for green CI** | Returns fixture envelopes keyed by scenario: `propose` (strict), `execute` (elevated tests), `schema_fail`, `unavailable`, `low_confidence`, `unbound` |
| `ollama` | optional | Short-timeout HTTP to local Ollama (`/api/chat`). Failure → next engine / fallback. Live test is skipped if unreachable. |
| `pair` | stub | Always `engine_unavailable`. No PAIR install. |

Walk `engines[]` in order. PAIR-down is not `fail_open_execute`.

## `triage_mode`

| Mode | Default? | Behavior |
|------|----------|----------|
| `rules_only` | Yes when `engines` is empty | Never call a model |
| `rules_primary` | Yes when at least one engine is configured | Call on non-auto severity ≥ high (not whitelist / `noise_ignore`). Optional `enrich` for propose/hold |
| `model_assist` | **Never** the home default | Same never-on-auto-execute gate; may fill other non-auto gaps |

`model_primary` → config error.

## Cycle

```
feature_bundle → rules envelopes
               → should_call_model? (never if auto-execute rule id)
               → engine walk → ≤1 repair → strip unknown tools → subject-bind
               → single winner envelope
               → policy (model gates) → exec → receipt
```

Auto-execute rule ids (`port_scan_burst`, …) short-circuit **before** any engine call, regardless of profile.

When the model wins, the receipt `actor.kind` is `model`. Incidents are still opened by policy/automation (`opened_by.kind` ∈ `rule|automation|human`) — the LLM does not write the incident.

## State directory (addition)

```
$AIMMUNE_STATE_DIR/
  triage_eval.jsonl    # redacted pointer only
```

## Environment

Same as slices 1–5, plus:

| Name | Default | Meaning |
|------|---------|---------|
| `AIMMUNE_TRIAGE_MODE` | derived | `rules_only` / `rules_primary` / `model_assist` |
| `AIMMUNE_TRIAGE_ENGINES` | empty | CSV: `mock`, `mock:propose`, `ollama`, `pair` |
| `AIMMUNE_TRIAGE_ENRICH` | `false` | Call on propose/hold under `rules_primary` |
| `AIMMUNE_TRIAGE_THETA` | `0.6` | Execute eligibility when `allow_model_execute` |
| `AIMMUNE_TRIAGE_DEFAULT_TIER` | `local_small` | `plane_ir` / `host_leased` require an active elevated stub |
| `AIMMUNE_TRIAGE_ON_FAILURE` | `fallback` | Only `fallback`. `fail_open_execute` is rejected |
| `AIMMUNE_TRIAGE_FILE` | unset | Optional yaml (`triage:` block) |
| `AIMMUNE_MOCK_ENGINE_SCENARIO` | `propose` | Fixture key for `kind: mock` |
| `AIMMUNE_OLLAMA_URL` | `http://127.0.0.1:11434` | Optional adapter |
| `AIMMUNE_OLLAMA_MODEL` | engine id | Ollama model name |
| `AIMMUNE_OLLAMA_TIMEOUT_S` | `3` | Short HTTP timeout |
| `AIMMUNE_RAILS_PROFILE` | `strict` | Resting profile |
| `AIMMUNE_RAILS_GRANT_ACTIVE` | `false` | **Deprecated** test-only override (slice 7 grants are SoT) |
| `AIMMUNE_RAILS_GRANT_UNTIL` | unset | Stub expiry |
| `AIMMUNE_RAILS_TOOL_ALLOWLIST` | empty | Stub execute allowlist |

Conceptual yaml (also accepted via `AIMMUNE_TRIAGE_FILE`):

```yaml
triage:
  triage_mode: rules_primary
  default_tier: local_small
  enrich: false
  confidence_theta: 0.6
  engines:
    - kind: mock
      id: mock-engine
      scenario: propose
    - kind: ollama
      id: qwen2.5-7b-q4
      tier: local_small
    - kind: pair
      id: pair-local
  on_model_failure: fallback
```

## Run

```bash
git clone --recurse-submodules https://github.com/Brewnix/auto-defense.git
python -m pip install -e '.[dev]'

export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_EXEC_MOCK=1
export AIMMUNE_TRIAGE_ENGINES=mock
# default mode becomes rules_primary

python -m aimmune cycle
pytest tests/test_triage.py tests/test_triage_acceptance.py tests/test_triage_eval.py
cd ui && npm ci && npm run lint && npm run typecheck && npm test
```

Ollama is not required. To try it on a cottage box: `AIMMUNE_TRIAGE_ENGINES=ollama` and a local daemon. CI stays on MockEngine.

## Acceptance (mapped)

1. Engines stopped / `rules_only` → critical rules still block  
2. Auto-execute match → MockEngine call count = 0  
3. Model schema fail → fallback; no model-attributed companion execute  
4. strict / no grant → model propose only  
5. Injected `ir_elevated` / `break_glass` stub → model execute only for allowlisted tools + gates; after stub expiry back to #4  
6. PAIR unavailable → next engine or fallback; never `fail_open_execute`  
7. Winner is exactly one envelope (`CycleResult.policy_inputs`)  
8. Receipt / ticket / incident / eval-log bodies contain no prompt text  

Also: subject-bind stripped/rejected; θ below → propose; `model_assist` works but is not default; `model_primary` rejected.

## Out of scope

`plane_ir` / `host_leased` without grant · ChatOps / `/v1/ir/chat` · grant mint · merge envelopes · `fail_open_execute` · prompts on receipts · schema amend · requiring Jetson/PAIR · `needs_model` · bumping the iface pin
