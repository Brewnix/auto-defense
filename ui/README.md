# AImmune UI v0

Site-local operator console. See [`docs/slice-5-ui.md`](../docs/slice-5-ui.md).

```bash
export AIMMUNE_UI_TOKEN=…          # required
export AIMMUNE_STATE_DIR=/tmp/aimmune-state
export AIMMUNE_UI_HOST=127.0.0.1   # default; 0.0.0.0 is an explicit opt-in
cd ui && npm install && npm run dev
```

Production: `npm run build && npm run start` (still binds 127.0.0.1).

No IR chat. Writes are local approve/deny only.
