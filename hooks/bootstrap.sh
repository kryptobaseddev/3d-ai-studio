#!/usr/bin/env bash
# SessionStart bootstrap for the 3d-studio plugin.
#
# Idempotently provisions a Python venv with the studio3d harness dependencies in
# the plugin-DATA dir (NOT the ephemeral plugin-root, which changes each update).
# Skips all work when the venv already matches the bundled requirements hash, so
# it adds negligible latency to session start.
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REQ="${PLUGIN_ROOT}/harness/requirements.txt"
DATA_DIR="${HOME}/.local/share/studio3d"
VENV="${DATA_DIR}/venv"
STAMP="${DATA_DIR}/requirements.sha256"

# If a dev .venv exists at the plugin root, prefer it and skip provisioning.
if [ -x "${PLUGIN_ROOT}/.venv/bin/python" ]; then
  echo "[3d-studio] using dev venv at ${PLUGIN_ROOT}/.venv" >&2
  exit 0
fi

[ -f "${REQ}" ] || { echo "[3d-studio] no requirements.txt; skipping bootstrap" >&2; exit 0; }

mkdir -p "${DATA_DIR}"
NEW_HASH="$(sha256sum "${REQ}" | awk '{print $1}')"
OLD_HASH="$(cat "${STAMP}" 2>/dev/null || echo none)"

if [ -x "${VENV}/bin/python" ] && [ "${NEW_HASH}" = "${OLD_HASH}" ]; then
  exit 0  # already current — fast path
fi

echo "[3d-studio] provisioning Python harness venv (one-time)…" >&2
python3 -m venv "${VENV}" 2>/dev/null || true
"${VENV}/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
if "${VENV}/bin/pip" install --quiet -r "${REQ}" >&2; then
  echo "${NEW_HASH}" > "${STAMP}"
  echo "[3d-studio] harness ready." >&2
else
  echo "[3d-studio] WARNING: dependency install failed; run 'studio3d doctor' to diagnose." >&2
fi
