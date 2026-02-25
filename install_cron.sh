#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install_cron.sh  —  Installs the BlockRun report cron job
#
# Usage:
#   ./install_cron.sh                        # runs every hour at :00
#   CRON_SCHEDULE="30 6 * * *" ./install_cron.sh   # runs daily at 06:30
#   ./install_cron.sh --remove               # removes the cron job
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_SCRIPT="${SCRIPT_DIR}/blockrun_cron.sh"
CRON_TAG="# blockrun-report-generator"

# Default: every hour on the hour
CRON_SCHEDULE="${CRON_SCHEDULE:-0 * * * *}"

remove_cron() {
  echo "Removing BlockRun cron job..."
  ( crontab -l 2>/dev/null | grep -v "${CRON_TAG}" ) | crontab -
  echo "Done."
}

install_cron() {
  if [[ ! -x "${CRON_SCRIPT}" ]]; then
    chmod +x "${CRON_SCRIPT}"
    echo "Made '${CRON_SCRIPT}' executable."
  fi

  # Remove any existing entry first
  ( crontab -l 2>/dev/null | grep -v "${CRON_TAG}" ) | crontab - || true

  # Add fresh entry
  CRON_LINE="${CRON_SCHEDULE} ${CRON_SCRIPT} ${CRON_TAG}"
  ( crontab -l 2>/dev/null; echo "${CRON_LINE}" ) | crontab -

  echo "Cron job installed:"
  echo "  ${CRON_LINE}"
  echo ""
  echo "Override schedule with:"
  echo "  CRON_SCHEDULE='30 6 * * *' ./install_cron.sh   # daily at 06:30"
  echo "  CRON_SCHEDULE='*/15 * * * *' ./install_cron.sh # every 15 minutes"
  echo ""
  echo "Current crontab:"
  crontab -l
}

if [[ "${1:-}" == "--remove" ]]; then
  remove_cron
else
  install_cron
fi
