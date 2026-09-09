# Role: aimmune-cottage (USB)

This slot is the **only** AImmune payload on a Brewnix multi-role stick. Adapter → Linux SoT ([`deploy/install.sh`](../../../deploy/install.sh)). No `.deb` / `.rpm`. No ISO.

Pin + checksums: [`VERSION`](VERSION) · [`SHA256SUMS`](SHA256SUMS). Installer: [`install.sh`](install.sh). Matrix: [`docs/packaging-v0.md`](../../../docs/packaging-v0.md).

## Owns

- `python3 -m pip install -e .` (or a source tarball of this checkout)
- [`deploy/install.sh`](../../../deploy/install.sh) · [`deploy/systemd/`](../../../deploy/systemd/) · [`deploy/aimmune.env.example`](../../../deploy/aimmune.env.example)
- Optional sibling `ui/` (`npm ci && npm run build`) — not in the pip wheel
- Offline synthetic fixtures — [`docs/synthetics-v0.md`](../../../docs/synthetics-v0.md)

Orin / Jetson: same path on JetPack Ubuntu (native systemd). Compose is not the AImmune runtime.

## Does not own

Gateway Eve / OPNsense · WireGuard · Hypermesh Host · Panopticon · secrets

## Install (callable)

From a clone of this repo:

```bash
./usb/roles/aimmune-cottage/install.sh --verify
sudo ./usb/roles/aimmune-cottage/install.sh
```

`install.sh` verifies `VERSION` + `SHA256SUMS`, finds the checkout (or unpacks `aimmune-cottage.tgz`), then calls `deploy/install.sh`. It does **not** enable units or invent a user. Pip stays a next step (`AIMMUNE_USB_SKIP_PIP=1` by default) — same as the Linux SoT.

## Tarball (optional on the stick)

```bash
git submodule update --init --recursive
git archive --format=tar.gz --prefix=auto-defense/ HEAD > aimmune-cottage.tgz
# attach vendor/inference-iface at the pinned SHA separately, or
# clone --recurse-submodules on the box instead of the stick
./usb/roles/aimmune-cottage/install.sh --write-sums
```

Place `aimmune-cottage.tgz` here. Prefer `git clone --recurse-submodules` on the box so [`vendor/inference-iface`](../../../vendor/inference-iface) is at pin `3621849bbf7c368b1d709356c465883144300208`.

Then: [`docs/host-install-smoke.md`](../../../docs/host-install-smoke.md) — prereqs → pip + `install.sh` → perms → env → `aimmune.service` → offline contain → optional UI (token required) → plane-up last.

Do not put `HM_SITE_TOKEN` or `AIMMUNE_UI_TOKEN` on the stick.
