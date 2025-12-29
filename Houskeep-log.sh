#!/bin/bash
# -------------------------------------------------------------
# Log Housekeeping for MyGP access logs
# Compress old logs and delete logs older than retention period
# without touching the failed directory.
#
# Usage: ./Houskeep-log.sh [-c CONFIG_FILE]
# -------------------------------------------------------------

# --- Parse command line arguments ---
CONFIG_FILE=""
while getopts "c:" opt; do
    case $opt in
        c) CONFIG_FILE="$OPTARG" ;;
        *) echo "Usage: $0 [-c config_file]" >&2; exit 1 ;;
    esac
done

# --- Load configuration from file or use defaults ---
if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
    echo "Loading configuration from: $CONFIG_FILE"
    
    # Use config_helper to export environment variables
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/config_helper.py" ]; then
        eval "$(python3 "$SCRIPT_DIR/config_helper.py" -c "$CONFIG_FILE" --export)"
    else
        echo "Warning: config_helper.py not found, using default values"
    fi
fi

BASE_DIR="${HOUSEKEEP_BASE_DIR:-/app/log/access-log-reciever}"
COMPRESS_AFTER_HOURS="${HOUSEKEEP_COMPRESS_HOURS:-3}"
DELETE_AFTER_HOURS="${HOUSEKEEP_DELETE_HOURS:-4}"

# Calculate minutes
COMPRESS_AFTER_MIN=$((COMPRESS_AFTER_HOURS * 60))
DELETE_AFTER_MIN=$((DELETE_AFTER_HOURS * 60))

echo "Housekeeping: Base=$BASE_DIR, Compress>${COMPRESS_AFTER_HOURS}h, Delete>${DELETE_AFTER_HOURS}h"

# --- Compress logs not written in last N hours ---
find "$BASE_DIR" -type f -name "*.log" \
    ! -name "stat*.log" \
    ! -name "line*.log" \
    ! -path "$BASE_DIR/failed/*" \
    ! -name "*.gz" \
    -mmin +"$COMPRESS_AFTER_MIN" \
    -exec gzip {} \;

# --- Delete logs older than retention period ---
find "$BASE_DIR" -type f \
    ! -path "$BASE_DIR/failed/*" \
    -mmin +"$DELETE_AFTER_MIN" \
    -delete
