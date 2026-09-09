# Role: hypermesh-host (USB stub)

Pointer only. This repo does **not** vendor Hypermesh Host or a qcow. Thin installer: [`install.sh`](install.sh) (prints this pointer and exits 2).

## Owns

- H4 `$STATE_DIR/owner.sock` + `owner.token` (**0600**)
- Site jobs / device lease actuators (plane `#40` / `#41`)
- Host image bake (stays in that project)

## Source

- [`FyberLabs/hypermesh-host`](https://github.com/FyberLabs/hypermesh-host)
- **Run that repo’s installer** — do not install Host from `auto-defense`
- AImmune consume: `AIMMUNE_HOST_STATE_DIR` / `HYPERMESH_STATE_DIR` — [`docs/slice-4-preempt.md`](../../../docs/slice-4-preempt.md)

## Tarball (conceptual)

```bash
tar czf hypermesh-host-notes.tgz README.md
# plus your owner.sock parent-dir layout notes — never the live token
```

Copy into this directory on the stick. Offline contain (`aimmune cycle` + mock alias) does **not** require Host. Do not enable plane-up preempt until WireGuard + `HM_SITE_TOKEN` + `Device.site_id` are bound ([`docs/host-install-smoke.md`](../../../docs/host-install-smoke.md)).
