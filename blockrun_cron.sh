#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# blockrun_cron.sh  —  Scheduled BlockRun report generator
#
# Intended to be run by cron.  Scans LOG_DIR for usage-*.jsonl files,
# regenerates report.html, and optionally rotates old reports.
#
# Configuration: edit the variables in the CONFIG block below, or override
# them via environment variables before calling this script.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Directory that contains usage-YYYY-MM-DD.jsonl files
LOG_DIR="${BLOCKRUN_LOG_DIR:-/home/agent/.openclaw/blockrun/logs/}"

# Where to write the final report.html
OUTPUT_PATH="${BLOCKRUN_OUTPUT:-/home/agent/.openclaw/workspace/report.html}"

# Path to the generator script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GENERATOR="${BLOCKRUN_GENERATOR:-${SCRIPT_DIR}/generate_reports.py}"

# Python interpreter
PYTHON="${BLOCKRUN_PYTHON:-python3}"

# Optional: keep this many previous reports (set to 0 to disable rotation)
KEEP_REPORTS="${BLOCKRUN_KEEP:-21}"

# Optional: send a one-line summary to this log file (set to "" to disable)
CRON_LOG="${BLOCKRUN_CRON_LOG:-${LOG_DIR}/cron.log}"
# ── END CONFIG ────────────────────────────────────────────────────────────────

TS="$(date '+%Y-%m-%d %H:%M:%S')"

log() {
  if [[ -n "${CRON_LOG}" ]]; then
    echo "[${TS}] $*" >> "${CRON_LOG}"
  fi
  echo "[${TS}] $*" >&2
}

# Validate paths
if [[ ! -d "${LOG_DIR}" ]]; then
  log "ERROR: LOG_DIR '${LOG_DIR}' does not exist."
  exit 1
fi

if [[ ! -f "${GENERATOR}" ]]; then
  log "ERROR: Generator script not found at '${GENERATOR}'."
  exit 1
fi

if ! command -v "${PYTHON}" &>/dev/null; then
  log "ERROR: Python interpreter '${PYTHON}' not found."
  exit 1
fi

# Count available files
FILE_COUNT=$(find "${LOG_DIR}" -maxdepth 1 -name 'usage-*.jsonl' | wc -l | tr -d ' ')
if [[ "${FILE_COUNT}" -eq 0 ]]; then
  log "WARNING: No usage-*.jsonl files found in '${LOG_DIR}'. Skipping."
  exit 0
fi

log "Generating report from ${FILE_COUNT} file(s) in '${LOG_DIR}'..."

# Optional report rotation: rename current report.html → report.YYYY-MM-DD_HH-MM.html
if [[ "${KEEP_REPORTS}" -gt 0 && -f "${OUTPUT_PATH}" ]]; then
  STAMP="$(date '+%Y-%m-%d_%H-%M')"
  ARCHIVE_DIR="$(dirname "${OUTPUT_PATH}")/archive"
  mkdir -p "${ARCHIVE_DIR}"
  cp "${OUTPUT_PATH}" "${ARCHIVE_DIR}/report.${STAMP}.html"

  # Prune old archives beyond KEEP_REPORTS
  ARCHIVE_COUNT=$(find "${ARCHIVE_DIR}" -name 'report.*.html' | wc -l | tr -d ' ')
  if [[ "${ARCHIVE_COUNT}" -gt "${KEEP_REPORTS}" ]]; then
    EXCESS=$(( ARCHIVE_COUNT - KEEP_REPORTS ))
    find "${ARCHIVE_DIR}" -name 'report.*.html' | sort | head -n "${EXCESS}" | xargs rm -f
    log "Pruned ${EXCESS} old archive(s), kept ${KEEP_REPORTS}."
  fi
fi

# Run the generator
if "${PYTHON}" "${GENERATOR}" "${LOG_DIR}" "${OUTPUT_PATH}" 2>&1 | while IFS= read -r line; do
    log "${line}"
  done; then
  log "SUCCESS: Report written to '${OUTPUT_PATH}'."
else
  log "ERROR: Generator exited with an error."
  exit 1
fi
