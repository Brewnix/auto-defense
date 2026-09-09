#!/usr/bin/env bash
# Thin pointer. This repo does not install Hypermesh Host.
# Run the installer in FyberLabs/hypermesh-host.
set -euo pipefail

cat <<'EOF'
hypermesh-host is not installed from Brewnix/auto-defense.

AImmune does not vendor Host or a qcow. Run that repo's installer:

  FyberLabs/hypermesh-host

AImmune consumes H4 owner.sock via AIMMUNE_HOST_STATE_DIR after Host exists.
Offline contain (aimmune cycle + mock alias) does not require this role.

See:
  usb/roles/hypermesh-host/README.md
  docs/packaging-v0.md
  docs/usb-layout.md
  docs/slice-4-preempt.md
EOF
exit 2
