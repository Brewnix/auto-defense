# USB layout (conceptual)

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** role adapters + cottage installer — **not** an image  
**Companion:** [`docs/host-install-smoke.md`](host-install-smoke.md)  
**Packaging matrix:** [`docs/packaging-v0.md`](packaging-v0.md)

AImmune does **not** bake an ISO, qcow, or installer USB. If an operator stages a stick for cottage bring-up, use this role split so Host / OPNsense stay outside this repo. Orin / Jetson uses the cottage role on JetPack Ubuntu (native systemd), not Compose.

```
usb/
  roles/
    gateway-opnsense/     # pointer + install.sh stub — run proxmox-firewall
    hypermesh-host/       # pointer + install.sh stub — run hypermesh-host
    aimmune-cottage/      # VERSION + SHA256SUMS + install.sh → deploy/install.sh
```

Stubs: [`usb/roles/gateway-opnsense/README.md`](../usb/roles/gateway-opnsense/README.md) · [`usb/roles/hypermesh-host/README.md`](../usb/roles/hypermesh-host/README.md) · cottage: [`usb/roles/aimmune-cottage/README.md`](../usb/roles/aimmune-cottage/README.md) · [`install.sh`](../usb/roles/aimmune-cottage/install.sh).

## What belongs on the stick

| Slot | Put here | Do not put here |
|------|----------|-----------------|
| `gateway-opnsense` | Notes + tarball of **your** gateway config / Eve path cheat-sheet | qcow2, OPNsense ISO, this repo’s Python tree |
| `hypermesh-host` | Notes + tarball of Host state-dir layout (`owner.sock` parent) | Host git checkout vendored into auto-defense |
| `aimmune-cottage` | `git archive` / source tarball of **this** repo (with submodule pin) + `deploy/` + `VERSION` / `SHA256SUMS` / `install.sh` | Live `HM_SITE_TOKEN`, `AIMMUNE_UI_TOKEN`, or a baked `.deb` |

Tarball example (cottage slot only):

```bash
git submodule update --init --recursive
git archive --format=tar.gz --prefix=auto-defense/ HEAD \
  > aimmune-cottage.tgz
# attach vendor/inference-iface at the pinned SHA separately, or
# clone --recurse-submodules on the box instead of the stick
```

Copy `aimmune-cottage.tgz` onto `usb/roles/aimmune-cottage/` and refresh sums (`./install.sh --write-sums`). Secrets stay off the stick (0600 on the box). Then `./usb/roles/aimmune-cottage/install.sh` (calls [`deploy/install.sh`](../deploy/install.sh)) and follow [`docs/host-install-smoke.md`](host-install-smoke.md).

## Out of scope

ISO bake · USB image CI · qcow · Compose-primary · Tailscale · public UI default · k8s · Playwright. Matrix: [`docs/packaging-v0.md`](packaging-v0.md).
