#!/usr/bin/env bash
# Copy AImmune systemd units + env example. Non-interactive and idempotent.
# Does not enable/start units, create users, or overwrite an existing env file.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
DEST_SYSTEMD="${DEST_SYSTEMD:-/etc/systemd/system}"
DEST_ENV_DIR="${DEST_ENV_DIR:-/etc/aimmune}"
DEST_STATE_DIR="${DEST_STATE_DIR:-/var/lib/aimmune}"

echo "AImmune slice 9 installer (units + env example only)"
echo "  repo:          ${REPO_ROOT}"
echo "  systemd dest:  ${DEST_SYSTEMD}"
echo "  env dest:      ${DEST_ENV_DIR}"
echo "  state dest:    ${DEST_STATE_DIR}"

if [[ ! -f "${SCRIPT_DIR}/systemd/aimmune.service" ]]; then
  echo "ERROR: missing ${SCRIPT_DIR}/systemd/aimmune.service" >&2
  exit 1
fi

if [[ ! -w "$(dirname "${DEST_SYSTEMD}")" && ! -w "${DEST_SYSTEMD}" ]]; then
  echo "ERROR: cannot write ${DEST_SYSTEMD} — re-run as root or set DEST_SYSTEMD=" >&2
  exit 1
fi

mkdir -p "${DEST_SYSTEMD}" "${DEST_ENV_DIR}"
install -m 0644 "${SCRIPT_DIR}/systemd/aimmune.service" \
  "${DEST_SYSTEMD}/aimmune.service"
install -m 0644 "${SCRIPT_DIR}/systemd/aimmune-ui.service" \
  "${DEST_SYSTEMD}/aimmune-ui.service"
install -m 0644 "${SCRIPT_DIR}/aimmune.env.example" \
  "${DEST_ENV_DIR}/aimmune.env.example"

if [[ ! -e "${DEST_ENV_DIR}/aimmune.env" ]]; then
  install -m 0600 "${SCRIPT_DIR}/aimmune.env.example" \
    "${DEST_ENV_DIR}/aimmune.env"
  echo "  wrote ${DEST_ENV_DIR}/aimmune.env (0600) from example — edit before start"
else
  echo "  left existing ${DEST_ENV_DIR}/aimmune.env untouched"
fi

if [[ ! -d "${DEST_STATE_DIR}" ]]; then
  if mkdir -p "${DEST_STATE_DIR}" 2>/dev/null; then
    chmod 0700 "${DEST_STATE_DIR}" || true
    echo "  created ${DEST_STATE_DIR} (0700)"
  else
    echo "  skipped ${DEST_STATE_DIR} (not writable from this user)"
  fi
fi

cat <<'EOF'

Next steps (not run by this script):

  1. pip install the console script (venv or system):
       python3 -m pip install -e /path/to/auto-defense
       # confirm: command -v aimmune && aimmune status
       # if the unit's ExecStart path differs, edit aimmune.service

  2. Cottage user (preferred over root):
       useradd --system --home /var/lib/aimmune --shell /usr/sbin/nologin aimmune
       chown aimmune:aimmune /var/lib/aimmune /etc/aimmune/aimmune.env
       chmod 0700 /var/lib/aimmune
       chmod 0600 /etc/aimmune/aimmune.env

  3. Edit /etc/aimmune/aimmune.env (SITE_ID, EVE path, mock vs OPNsense, WireGuard plane).

  4. systemctl daemon-reload
     systemctl enable --now aimmune.service
     journalctl -u aimmune -f
     aimmune status

  5. Optional UI (sibling tree — not in the pip wheel):
       cd /path/to/auto-defense/ui && npm ci && npm run build
       mkdir -p /usr/local/lib/aimmune && cp -a ui /usr/local/lib/aimmune/ui
       # set AIMMUNE_UI_TOKEN in the env file, then:
       systemctl enable --now aimmune-ui.service

No .deb/.rpm. No image bake. No Tailscale. UI stays on 127.0.0.1 unless you
opt in with AIMMUNE_UI_HOST=0.0.0.0. Host wiring: docs/slice-9-package.md
EOF
