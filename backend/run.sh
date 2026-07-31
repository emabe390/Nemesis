#!/usr/bin/env bash
# EVE Nemesis Tracker — Run Script
#
# Usage:
#   ./run.sh init [start_date]    # First-time database build
#   ./run.sh weekly               # Weekly update + export + git push
#   ./run.sh export               # Export only (from existing DB)
#   ./run.sh stats                # Show database statistics
#
# Environment:
#   NEMESIS_DB      — SQLite database path (default: ./nemesis.db)
#   NEMESIS_OUTPUT  — JSON export directory (default: ../site/data)
#   NEMESIS_MIN_LOSSES — Min losses to include character (default: 3)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DB="${NEMESIS_DB:-./nemesis.db}"
OUTPUT="${NEMESIS_OUTPUT:-../site/data}"
MIN_LOSSES="${NEMESIS_MIN_LOSSES:-3}"
PYTHON="${PYTHON:-python3}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

check_python() {
    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        die "Python not found: $PYTHON. Set PYTHON env var or install python3."
    fi
    log "Using $($PYTHON --version)"
}

cmd_init() {
    local start_date="${1:-}"
    check_python
    log "=== Initial database build ==="
    log "Database: $DB"
    log "Output: $OUTPUT"

    if [[ -f "$DB" ]]; then
        log "Database already exists: $DB"
        read -rp "Delete and rebuild? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || die "Aborted"
        rm -f "$DB"
    fi

    local args=("--init-db" "--db" "$DB")
    [[ -n "$start_date" ]] && args+=("--start" "$start_date")

    "$PYTHON" build_nemesis.py "${args[@]}"

    log "=== Exporting JSON ==="
    "$PYTHON" build_nemesis.py --db "$DB" --export "$OUTPUT" --min-losses "$MIN_LOSSES"

    log "=== Done ==="
    log "Database: $DB"
    log "Output: $OUTPUT"
    "$PYTHON" build_nemesis.py --db "$DB" --stats
}

cmd_weekly() {
    check_python
    log "=== Weekly update ==="

    if [[ ! -f "$DB" ]]; then
        die "Database not found: $DB. Run: $0 init"
    fi

    log "Updating database..."
    "$PYTHON" build_nemesis.py --db "$DB" --update

    log "Exporting JSON..."
    "$PYTHON" build_nemesis.py --db "$DB" --export "$OUTPUT" --min-losses "$MIN_LOSSES"

    log "Git commit and push..."
    cd "$(dirname "$OUTPUT")"
    if [[ -d .git ]]; then
        git add data/
        git diff --cached --quiet || {
            git commit -m "weekly nemesis update $(date +%Y-%m-%d)"
            git push
        }
        log "Pushed to git"
    else
        log "No git repo found at $(pwd), skipping push"
    fi

    log "=== Done ==="
    "$PYTHON" build_nemesis.py --db "$DB" --stats
}

cmd_export() {
    check_python
    log "=== Export only ==="
    [[ -f "$DB" ]] || die "Database not found: $DB"
    "$PYTHON" build_nemesis.py --db "$DB" --export "$OUTPUT" --min-losses "$MIN_LOSSES"
    log "Done"
}

cmd_stats() {
    check_python
    [[ -f "$DB" ]] || die "Database not found: $DB"
    "$PYTHON" build_nemesis.py --db "$DB" --stats
}

cmd_help() {
    cat <<'EOF'
EVE Nemesis Tracker — Run Script

Usage: ./run.sh <command> [options]

Commands:
  init [START_DATE]   First-time build. Optional START_DATE as YYYYMMDD.
  weekly              Update DB, export JSON, git commit+push.
  export              Export JSON from existing DB (no update).
  stats               Show database statistics.
  help                Show this message.

Environment Variables:
  NEMESIS_DB          SQLite database path (default: ./nemesis.db)
  NEMESIS_OUTPUT      JSON export directory (default: ../site/data)
  NEMESIS_MIN_LOSSES  Minimum losses to include character (default: 3)
  PYTHON              Python executable (default: python3)

Examples:
  ./run.sh init                    # Full history build
  ./run.sh init 20240101          # Build from 2024-01-01 onward
  NEMESIS_MIN_LOSSES=5 ./run.sh weekly
  NEMESIS_DB=/mnt/usb/nemesis.db ./run.sh weekly

Cron (weekly Monday 3am):
  0 3 * * 1 cd /path/to/nemesis/backend && ./run.sh weekly >> cron.log 2>&1
EOF
}

case "${1:-help}" in
    init)       shift; cmd_init "$@" ;;
    weekly)     cmd_weekly ;;
    export)     cmd_export ;;
    stats)      cmd_stats ;;
    help|--help|-h) cmd_help ;;
    *)          die "Unknown command: $1. Run: $0 help" ;;
esac
