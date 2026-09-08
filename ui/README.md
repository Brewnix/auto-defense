# AImmune UI v0

Site-local operator console. See [`docs/slice-5-ui.md`](../docs/slice-5-ui.md) and [`docs/slice-8-sociacl-ir.md`](../docs/slice-8-sociacl-ir.md).

```bash
export AIMMUNE_UI_TOKEN=…          # required (loopback smoke)
export AIMMUNE_OWNER_PRINCIPALS=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export AIMMUNE_UI_SMOKE_PRINCIPAL=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export AIMMUNE_SIWE_DOMAIN=127.0.0.1
# AIMMUNE_SIWE_CHAIN_ID=1
export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_UI_HOST=127.0.0.1   # default; 0.0.0.0 is an explicit opt-in
cd ui && npm install && npm run dev
```

Production: `npm run build && npm run start` (still binds 127.0.0.1). Human acts re-Check a verified SIWE address ([`docs/siwe-v0.md`](../docs/siwe-v0.md)). Paste-principal is smoke-only.

No IR chat. Local resolve / mint-local are Check-gated. Machine doors stay `hm_site_`.
