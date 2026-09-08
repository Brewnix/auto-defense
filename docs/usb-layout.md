# USB layout (conceptual)

**Product:** AImmune  
**Repo:** `Brewnix/auto-defense`  
**Status:** pointers + tarball notes — **not** an image  
**Companion:** [`docs/host-install-smoke.md`](host-install-smoke.md)

AImmune does **not** bake an ISO, qcow, or installer USB. If an operator stages a stick for cottage bring-up, use this role split so Host / OPNsense stay outside this repo.

```
usb/
  roles/
    gateway-opnsense/     # Eve, alias_util, WireGuard — Brewnix / proxmox-firewall
    hypermesh-host/       # H4 owner.sock, site jobs — FyberLabs/hypermesh-host
    aimmune-cottage/      # pip wheel / checkout + systemd + env + optional UI tarball
```

Stubs: [`usb/roles/gateway-opnsense/README.md`](../usb/roles/gateway-opnsense/README.md) · [`usb/roles/hypermesh-host/README.md`](../usb/roles/hypermesh-host/README.md) · [`usb/roles/aimmune-cottage/README.md`](../usb/roles/aimmune-cottage/README.md).

## What belongs on the stick

| Slot | Put here | Do not put here |
|------|----------|-----------------|
| `gateway-opnsense` | Notes + tarball of **your** gateway config / Eve path cheat-sheet | qcow2, OPNsense ISO, this repo’s Python tree |
| `hypermesh-host` | Notes + tarball of Host state-dir layout (`owner.sock` parent) | Host git checkout vendored into auto-defense |
| `aimmune-cottage` | `git archive` / source tarball of **this** repo (with submodule pin) + `deploy/` | Live `HM_SITE_TOKEN`, `AIMMUNE_UI_TOKEN`, or a baked `.deb` |

Tarball example (cottage slot only):

```bash
git submodule update --init --recursive
git archive --format=tar.gz --prefix=auto-defense/ HEAD \
  > aimmune-cottage.tgz
# attach vendor/inference-iface at the pinned SHA separately, or
# clone --recurse-submodules on the box instead of the stick
```

Copy `aimmune-cottage.tgz` onto `usb/roles/aimmune-cottage/`. Secrets stay off the stick (0600 on the box). Then follow [`docs/host-install-smoke.md`](host-install-smoke.md).

## Out of scope

ISO bake · USB image CI · qcow · Tailscale · public UI default · k8s.
