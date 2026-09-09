# Role: gateway-opnsense (USB stub)

Pointer only. This repo does **not** vendor OPNsense, Suricata, or a qcow. Thin installer: [`install.sh`](install.sh) (prints this pointer and exits 2).

## Owns

- Suricata `eve.json` (typically `/var/log/suricata/eve.json`)
- `ai_autoblock` + `alias_util` add/delete
- WireGuard overlay to Panopticon (**not Tailscale**)

## Source

- Image / role: [`Brewnix/proxmox-firewall`](https://github.com/Brewnix/proxmox-firewall)
- **Run that repo’s installer** — do not install the gateway from `auto-defense`
- AImmune consume: `AIMMUNE_EVE_PATH` · [`docs/slice-1-zero-llm.md`](../../../docs/slice-1-zero-llm.md) · [`docs/packaging-v0.md`](../../../docs/packaging-v0.md)

## Tarball (conceptual)

On a **built** gateway, archive operator notes — not the appliance disk:

```bash
tar czf gateway-opnsense-notes.tgz \
  README.md \
  # plus your Eve path / alias_util cheat-sheet
```

Copy that tarball into this directory on the stick. Lab offline smoke may skip the live gateway and use [`tests/fixtures/eve_port_scan.jsonl`](../../../tests/fixtures/eve_port_scan.jsonl) + [`tests/fixtures/eve_ssh_brute.jsonl`](../../../tests/fixtures/eve_ssh_brute.jsonl) with `AIMMUNE_EXEC_MOCK=1`.
