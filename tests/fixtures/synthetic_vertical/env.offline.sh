# Offline vertical synthetic — plane down, mock alias, rules-only.
# Source from the repo root (or any cwd). Then set AIMMUNE_STATE_DIR + AIMMUNE_EVE_PATH.
# No live Suricata, OPNsense, WireGuard, or Panopticon. No SIWE.

export AIMMUNE_EXEC_MOCK=1
export AIMMUNE_PLANE_REACHABLE=0
export SITE_ID="${SITE_ID:-net-tn-cottage}"
export AIMMUNE_SITE_ID="${AIMMUNE_SITE_ID:-$SITE_ID}"

# Rules-only default. Do not attach a second mock triage stack.
unset AIMMUNE_TRIAGE_ENGINES || true
unset AIMMUNE_TRIAGE_MODE || true
unset AIMMUNE_MOCK_ENGINE_SCENARIO || true

# Plane doors stay unset so cycle-end never POSTs.
unset PANOPTICON_BASE_URL || true
# Leave HM_SITE_TOKEN alone if the operator already has one; offline path
# does not read it when PANOPTICON_BASE_URL is unset.

_SYNTHETIC_ROOT="${AIMMUNE_REPO_ROOT:-}"
if [[ -z "${_SYNTHETIC_ROOT}" ]]; then
  if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    _SYNTHETIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
  else
    _SYNTHETIC_ROOT="$(pwd)"
  fi
fi
export AIMMUNE_REPO_ROOT="${_SYNTHETIC_ROOT}"
export AIMMUNE_SYNTHETIC_SCAN_FIXTURE="${AIMMUNE_SYNTHETIC_SCAN_FIXTURE:-${_SYNTHETIC_ROOT}/tests/fixtures/eve_port_scan.jsonl}"
export AIMMUNE_SYNTHETIC_BRUTE_FIXTURE="${AIMMUNE_SYNTHETIC_BRUTE_FIXTURE:-${_SYNTHETIC_ROOT}/tests/fixtures/eve_ssh_brute.jsonl}"
unset _SYNTHETIC_ROOT
