#!/usr/bin/env bash
# Live cottage v0 — host-install checklist through offline contain.
# AIMMUNE_EXEC_MOCK=1. No live alias_util / Eve / WireGuard / Panopticon.
# Not folded into unmarked pytest. See docs/testing-harden-v0.md
#
# Override DEST_* to write /etc + /var (real cottage). Default is a prefix
# dir so the script is CI-less and does not need root.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
# shellcheck source=tests/fixtures/synthetic_vertical/env.offline.sh
source "${REPO_ROOT}/tests/fixtures/synthetic_vertical/env.offline.sh"

PREFIX="${AIMMUNE_COTTAGE_PREFIX:-$(mktemp -d /tmp/aimmune-cottage-XXXXXX)}"
export DEST_SYSTEMD="${DEST_SYSTEMD:-${PREFIX}/systemd}"
export DEST_ENV_DIR="${DEST_ENV_DIR:-${PREFIX}/etc/aimmune}"
export DEST_STATE_DIR="${DEST_STATE_DIR:-${PREFIX}/var/lib/aimmune}"
export AIMMUNE_STATE_DIR="${AIMMUNE_STATE_DIR:-${DEST_STATE_DIR}}"
EVE_PATH="${AIMMUNE_EVE_PATH:-${PREFIX}/eve.jsonl}"
export AIMMUNE_EVE_PATH="${EVE_PATH}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
PYTHON="${PYTHON:-python3}"
SITE="${SITE_ID:-net-tn-cottage}"
export SITE_ID="${SITE}"
export AIMMUNE_SITE_ID="${AIMMUNE_SITE_ID:-${SITE}}"
export AIMMUNE_EXEC_MOCK=1
export AIMMUNE_PLANE_REACHABLE=0
unset PANOPTICON_BASE_URL || true
unset AIMMUNE_UI_TOKEN || true

mkdir -p "${DEST_SYSTEMD}" "${DEST_ENV_DIR}" "${DEST_STATE_DIR}"

echo "live cottage v0 (offline contain)"
echo "  repo:    ${REPO_ROOT}"
echo "  prefix:  ${PREFIX}"
echo "  systemd: ${DEST_SYSTEMD}"
echo "  env:     ${DEST_ENV_DIR}"
echo "  state:   ${DEST_STATE_DIR}"
echo "  eve:     ${EVE_PATH}"
echo "  site:    ${SITE}"

# --- 1. Role prereqs (cite, don't install) --------------------------------
echo
echo "== 1. role prereqs (cite) =="
echo "  gateway Eve: fixture ${AIMMUNE_SYNTHETIC_SCAN_FIXTURE} + brute"
echo "  live alias_util / real Eve: follow-on — usb/roles/gateway-opnsense (not this cut)"
echo "  Host H4 / WireGuard: not required for offline contain"

# --- 2. pip + install.sh --------------------------------------------------
echo
echo "== 2. pip + install.sh =="
if ! "${PYTHON}" -c "import aimmune" 2>/dev/null; then
  echo "  pip install -e ${REPO_ROOT}"
  "${PYTHON}" -m pip install -e "${REPO_ROOT}"
fi
command -v aimmune >/dev/null 2>&1 || true
DEST_SYSTEMD="${DEST_SYSTEMD}" DEST_ENV_DIR="${DEST_ENV_DIR}" \
  DEST_STATE_DIR="${DEST_STATE_DIR}" \
  "${REPO_ROOT}/deploy/install.sh"
test -f "${DEST_SYSTEMD}/aimmune.service"
test -f "${DEST_SYSTEMD}/aimmune-ui.service"
test -f "${DEST_ENV_DIR}/aimmune.env.example"
test -d "${DEST_STATE_DIR}"

# --- 3. Perms -------------------------------------------------------------
echo
echo "== 3. perms =="
# On a real cottage (root): useradd aimmune; chown aimmune:aimmune state + env.
# This CI-less path only asserts modes. chown is documented, not required.
chmod 0700 "${DEST_STATE_DIR}"
chmod 0600 "${DEST_ENV_DIR}/aimmune.env"
STATE_MODE=$(stat -c '%a' "${DEST_STATE_DIR}")
ENV_MODE=$(stat -c '%a' "${DEST_ENV_DIR}/aimmune.env")
echo "  state ${DEST_STATE_DIR} mode=${STATE_MODE} (want 700)"
echo "  env   ${DEST_ENV_DIR}/aimmune.env mode=${ENV_MODE} (want 600)"
[[ "${STATE_MODE}" == "700" ]]
[[ "${ENV_MODE}" == "600" ]]
echo "  note: chown aimmune:aimmune is a cottage-box step (skipped without root)"

# --- 4. Env (offline-first) -----------------------------------------------
echo
echo "== 4. env =="
cat > "${DEST_ENV_DIR}/aimmune.env" <<EOF
SITE_ID=${SITE}
AIMMUNE_SITE_ID=${SITE}
AIMMUNE_STATE_DIR=${DEST_STATE_DIR}
AIMMUNE_EXEC_MOCK=1
AIMMUNE_PLANE_REACHABLE=0
AIMMUNE_EVE_PATH=${EVE_PATH}
AIMMUNE_UI_HOST=127.0.0.1
AIMMUNE_UI_TOKEN=
EOF
chmod 0600 "${DEST_ENV_DIR}/aimmune.env"
# Re-read for the rest of the script (install example had EXEC_MOCK=0).
set -a
# shellcheck disable=SC1091
source "${DEST_ENV_DIR}/aimmune.env"
set +a
export AIMMUNE_EXEC_MOCK=1
export AIMMUNE_PLANE_REACHABLE=0
unset PANOPTICON_BASE_URL || true
echo "  wrote ${DEST_ENV_DIR}/aimmune.env (0600) EXEC_MOCK=1 plane down"

# --- 5. service + status (where practical) --------------------------------
echo
echo "== 5. service / status =="
grep -q 'aimmune loop' "${DEST_SYSTEMD}/aimmune.service"
grep -q 'EnvironmentFile=-/etc/aimmune/aimmune.env' "${DEST_SYSTEMD}/aimmune.service"
grep -q 'test -n "${AIMMUNE_UI_TOKEN-}"' "${DEST_SYSTEMD}/aimmune-ui.service"
echo "  units staged: aimmune.service + aimmune-ui.service"
if [[ "${AIMMUNE_LIVE_COTTAGE_SYSTEMD:-0}" == "1" ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
  systemctl is-system-running --quiet && echo "  systemd is running" || echo "  systemd not in a running state"
  systemctl status aimmune.service --no-pager -n 0 || true
  if command -v journalctl >/dev/null 2>&1; then
    journalctl -u aimmune -n 20 --no-pager || true
  fi
else
  echo "  CI-less: not starting systemd (set AIMMUNE_LIVE_COTTAGE_SYSTEMD=1 on a cottage box)"
fi

echo "  pre-cycle status (always exit 0):"
PRE_STATUS=$("${PYTHON}" -m aimmune status --json --state-dir "${DEST_STATE_DIR}" --site-id "${SITE}")
echo "${PRE_STATUS}"
PRE_COUNT=$("${PYTHON}" -c "import json,sys; print(json.loads(sys.argv[1])['receipts']['count'])" "${PRE_STATUS}")

# --- 6. Offline contain ---------------------------------------------------
echo
echo "== 6. offline contain =="
# Fixture timestamps match FrozenClock tests. Restamp so the 300s window matches.
"${PYTHON}" - "${AIMMUNE_SYNTHETIC_SCAN_FIXTURE}" "${AIMMUNE_SYNTHETIC_BRUTE_FIXTURE}" "${EVE_PATH}" <<'PY'
import json
import sys
from datetime import datetime, timezone

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
out = sys.argv[3]
rows: list[str] = []
for path in sys.argv[1:3]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            ev["timestamp"] = now
            rows.append(json.dumps(ev, separators=(",", ":")))
with open(out, "w", encoding="utf-8") as fh:
    fh.write("\n".join(rows) + "\n")
PY

"${PYTHON}" -m aimmune cycle --state-dir "${DEST_STATE_DIR}" --eve "${EVE_PATH}" --site-id "${SITE}"
VERIFY=$("${PYTHON}" -m aimmune verify-chain --state-dir "${DEST_STATE_DIR}" --site-id "${SITE}")
echo "${VERIFY}"
"${PYTHON}" -c "import json,sys; d=json.loads(sys.argv[1]); assert d['ok'] is True and d['count']>=1" "${VERIFY}"

STATUS=$("${PYTHON}" -m aimmune status --json --state-dir "${DEST_STATE_DIR}" --site-id "${SITE}")
echo "${STATUS}"
"${PYTHON}" - "${STATUS}" "${PRE_COUNT}" "${SITE}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
pre = int(sys.argv[2])
site = sys.argv[3]
assert payload["site_id"] == site, payload.get("site_id")
assert payload["plane_reachable"] is False
assert payload["exec_mock"] is True
assert payload["state_dir_exists"] is True
assert payload["receipts"]["count"] >= 1
assert payload["receipts"]["count"] > pre
assert payload["receipts"]["last"] and payload["receipts"]["last"].get("receipt_id")
print("status --json pass criteria ok")
PY

# UI fail-closed without token (checklist E; no Next / Playwright).
UI_RC=0
"${PYTHON}" -m aimmune ui --state-dir "${DEST_STATE_DIR}" --site-id "${SITE}" >/dev/null || UI_RC=$?
if [[ "${UI_RC}" -ne 1 ]]; then
  echo "ERROR: aimmune ui should exit 1 when AIMMUNE_UI_TOKEN is empty (got ${UI_RC})" >&2
  exit 1
fi
echo "  ui fail-closed (no token) ok"

echo
echo "live cottage offline contain ok"
echo "  prefix: ${PREFIX}"
