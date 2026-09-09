#!/usr/bin/env bash
# Thin pointer. This repo does not install the gateway.
# Run the installer in Brewnix/proxmox-firewall (or your gateway image bake).
set -euo pipefail

cat <<'EOF'
gateway-opnsense is not installed from Brewnix/auto-defense.

AImmune does not vendor OPNsense, Suricata, or a qcow. Run that repo's installer:

  Brewnix/proxmox-firewall

AImmune consumes Eve at AIMMUNE_EVE_PATH and alias_util via the cottage env
contract after the gateway exists. Lab smoke may skip this role and use
tests/fixtures/eve_*.jsonl with AIMMUNE_EXEC_MOCK=1.

See:
  usb/roles/gateway-opnsense/README.md
  docs/packaging-v0.md
  docs/usb-layout.md
EOF
exit 2
