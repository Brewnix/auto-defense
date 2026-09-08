#!/usr/bin/env bash
# Operator replay of the offline vertical synthetic (plane down, mock alias).
# CI SoT is pytest tests/test_synthetic_vertical_offline.py — this script is optional.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
# shellcheck source=tests/fixtures/synthetic_vertical/env.offline.sh
source "${REPO_ROOT}/tests/fixtures/synthetic_vertical/env.offline.sh"

STATE_DIR="${AIMMUNE_STATE_DIR:-$(mktemp -d /tmp/aimmune-synthetic-XXXXXX)}"
EVE_PATH="${AIMMUNE_EVE_PATH:-${STATE_DIR}/eve.jsonl}"
export AIMMUNE_STATE_DIR="${STATE_DIR}"
export AIMMUNE_EVE_PATH="${EVE_PATH}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

mkdir -p "${STATE_DIR}"
cat "${AIMMUNE_SYNTHETIC_SCAN_FIXTURE}" "${AIMMUNE_SYNTHETIC_BRUTE_FIXTURE}" > "${EVE_PATH}"

echo "offline synthetic"
echo "  state: ${STATE_DIR}"
echo "  eve:   ${EVE_PATH}"
echo "  site:  ${SITE_ID}"

python -m aimmune cycle --state-dir "${STATE_DIR}" --eve "${EVE_PATH}" --site-id "${SITE_ID}"
python -m aimmune verify-chain --state-dir "${STATE_DIR}" --site-id "${SITE_ID}"

python - <<'PY'
import json
import os
import sys
from pathlib import Path

from aimmune.cli import main
from aimmune.config import load_config
from aimmune.cycle import build_runtime
from aimmune.store import read_jsonl

state = Path(os.environ["AIMMUNE_STATE_DIR"])
site = os.environ.get("SITE_ID") or os.environ.get("AIMMUNE_SITE_ID") or "net-tn-cottage"
cfg = load_config(state_dir=state, site_id=site)
rt = build_runtime(cfg)
propose = None
for rec in read_jsonl(cfg.receipts_path):
    if (rec.get("policy") or {}).get("decision") == "propose":
        propose = rec
if propose is None:
    print("ERROR: no propose receipt — ssh_brute hold missing", file=sys.stderr)
    sys.exit(1)
incident_id = rt.incidents.find_by_receipt(propose["receipt_id"])
if not incident_id:
    print("ERROR: propose receipt has no incident", file=sys.stderr)
    sys.exit(1)
rc = main(
    [
        "owner",
        "approve",
        "--receipt-id",
        propose["receipt_id"],
        "--state-dir",
        str(state),
        "--site-id",
        site,
    ]
)
if rc != 0:
    sys.exit(rc)
rc = main(
    [
        "grant",
        "mint-local",
        "--state-dir",
        str(state),
        "--incident-id",
        incident_id,
        "--reason",
        "offline synthetic elevate",
        "--notes",
        "cottage owner mint after local resolve",
        "--tool",
        "notify.operator",
        "--profile",
        "break_glass",
        "--ttl",
        "1800",
    ]
)
if rc != 0:
    sys.exit(rc)
print(json.dumps({"resolved": propose["receipt_id"], "incident_id": incident_id}))
PY

python -m aimmune status --json --state-dir "${STATE_DIR}" --site-id "${SITE_ID}"
echo "offline synthetic ok"
