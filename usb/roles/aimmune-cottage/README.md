# Role: aimmune-cottage (USB stub)

This slot is the **only** AImmune payload on a conceptual USB. Pip + systemd + env + docs + optional UI. No `.deb` / `.rpm`. No ISO.

## Owns

- `python3 -m pip install -e .` (or a source tarball of this checkout)
- [`deploy/install.sh`](../../../deploy/install.sh) · [`deploy/systemd/`](../../../deploy/systemd/) · [`deploy/aimmune.env.example`](../../../deploy/aimmune.env.example)
- Optional sibling `ui/` (`npm ci && npm run build`) — not in the pip wheel
- Offline synthetic fixtures — [`docs/synthetics-v0.md`](../../../docs/synthetics-v0.md)

## Does not own

Gateway Eve / OPNsense · WireGuard · Hypermesh Host · Panopticon · secrets

## Tarball

```bash
git submodule update --init --recursive
git archive --format=tar.gz --prefix=auto-defense/ HEAD > aimmune-cottage.tgz
```

Place `aimmune-cottage.tgz` here. Prefer `git clone --recurse-submodules` on the box so [`vendor/inference-iface`](../../../vendor/inference-iface) is at pin `3621849bbf7c368b1d709356c465883144300208`.

Then: [`docs/host-install-smoke.md`](../../../docs/host-install-smoke.md) — prereqs → pip + `install.sh` → perms → env → `aimmune.service` → offline contain → optional UI (token required) → plane-up last.

Do not put `HM_SITE_TOKEN` or `AIMMUNE_UI_TOKEN` on the stick.
