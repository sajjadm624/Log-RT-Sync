
#!/bin/bash
# -------------------------------------------------------------
# EDW Log Shipper v5 (Config-Enabled Version)
# Sends MyGP log files to remote host with retry and verification.
# Tracks line counts separately for Sent and Failed files.
# Failed files are retried each cycle until success.
# Stdout -> .out, Errors -> .err
#
# Usage: ./Log-sender-to-client-end.sh [-c CONFIG_FILE]
# -------------------------------------------------------------

set -u

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

# --- Configuration (with fallbacks to defaults) ---
SRC_DIR="${LOG_SENDER_SOURCE_DIR:-/app/log/access-log-reciever}"
DEST_USER="${LOG_SENDER_DEST_USER:-mygp1}"
DEST_HOST="${LOG_SENDER_DEST_HOST:-10.12.3.3}"
DEST_DIR="${LOG_SENDER_DEST_DIR:-/cdrdata/oracle/ProdEDW/source_data/MYGP}"
SSHPASS="${LOG_SENDER_PASSWORD:-9Z@pfKV}3y!v}"
SSH_PORT="${LOG_SENDER_DEST_PORT:-22022}"
SLEEP_SECS="${LOG_SENDER_SLEEP_SECS:-60}"
MAX_RETRIES="${LOG_SENDER_MAX_RETRIES:-3}"
RSYNC_TIMEOUT="${LOG_SENDER_RSYNC_TIMEOUT:-60}"
SSH_TIMEOUT="${LOG_SENDER_SSH_TIMEOUT:-20}"
FILE_PATTERN="${LOG_SENDER_FILE_PATTERN:-MyGP_accessLog_*.log}"
MIN_FILE_AGE="${LOG_SENDER_MIN_AGE_MIN:-2}"

ARCHIVE_DIR="${LOG_SENDER_ARCHIVE_DIR:-$SRC_DIR/sent}"
FAILED_DIR="${LOG_SENDER_FAILED_DIR:-$SRC_DIR/failed}"
mkdir -p "$ARCHIVE_DIR" "$FAILED_DIR"

# --- Linecount logs ---
LINECOUNT_LOG="${LOG_SENDER_LINECOUNT_LOG:-/home/mygpadmin/LogTerminal-rtSync/edw-rsync/linecount-report/linecount-report.log}"
LINECOUNT_FAIL_LOG="${LOG_SENDER_LINECOUNT_FAIL:-/home/mygpadmin/LogTerminal-rtSync/edw-rsync/linecount-report/linecount-report.fail}"
mkdir -p "$(dirname "$LINECOUNT_LOG")"
touch "$LINECOUNT_LOG" "$LINECOUNT_FAIL_LOG"

# --- Logging ---
OUT_LOG="${LOG_SENDER_OUT_LOG:-/home/mygpadmin/LogTerminal-rtSync/edw-rsync/log/edw-rsync_v4.out}"
ERR_LOG="${LOG_SENDER_ERR_LOG:-/home/mygpadmin/LogTerminal-rtSync/edw-rsync/log/edw-rsync_v4.err}"
mkdir -p "$(dirname "$OUT_LOG")"
touch "$OUT_LOG" "$ERR_LOG"

log() { echo "$(date '+%F %T') | $*" >> "$OUT_LOG"; }
log_err() { echo "$(date '+%F %T') | $*" >> "$ERR_LOG"; }

# --- Transfer function ---
transfer_file() {
    local file="$1"
    local fname="$(basename "$file")"
    local tmpname="${fname}.tmp"
    local retries=0

    while (( retries < MAX_RETRIES )); do
        log "Attempting transfer for $fname (try $((retries + 1))/$MAX_RETRIES)"

        if sshpass -p "$SSHPASS" rsync --timeout="$RSYNC_TIMEOUT" -avz \
            -e "ssh -p $SSH_PORT -o StrictHostKeyChecking=no -o ConnectTimeout=$SSH_TIMEOUT" \
            "$file" "${DEST_USER}@${DEST_HOST}:${DEST_DIR}/${tmpname}" >>"$OUT_LOG" 2>>"$ERR_LOG"; then

            if sshpass -p "$SSHPASS" ssh -p "$SSH_PORT" \
                -o StrictHostKeyChecking=no \
                "${DEST_USER}@${DEST_HOST}" \
                "mv ${DEST_DIR}/${tmpname} ${DEST_DIR}/${fname}" >>"$OUT_LOG" 2>>"$ERR_LOG"; then
                return 0
            else
                log_err "Failed to rename remote file ${tmpname}"
            fi
        else
            log_err "Rsync failed for $fname (attempt $((retries + 1)))"
        fi

        ((retries++))
        sleep 5
    done

    return 1
}

# --- Record line count ---
record_linecount() {
    local file="$1"
    local status="$2"
    local linecount
    linecount=$(wc -l < "$file" 2>/dev/null || echo 0)
    local log_file

    if [ "$status" == "Sent" ]; then
        log_file="$LINECOUNT_LOG"
    else
        log_file="$LINECOUNT_FAIL_LOG"
    fi

    echo "$(date '+%F %T') | $(basename "$file") | lines=$linecount | status=$status" >> "$log_file"
}

# --- Process files ---
process_files() {
    local file_list=("$@")
    for file in "${file_list[@]}"; do
        [ -f "$file" ] || continue
        local fname="$(basename "$file")"

        # Skip if file modified recently (still being written)
        if [ "$(find "$file" -mmin -"$MIN_FILE_AGE" | wc -l)" -gt 0 ]; then
            log "Skipping $fname (still updating)"
            continue
        fi

        if transfer_file "$file"; then
            mv "$file" "$ARCHIVE_DIR/"
            record_linecount "$ARCHIVE_DIR/$fname" "Sent"
            log "$fname sent successfully."
        else
            mv "$file" "$FAILED_DIR/"
            record_linecount "$FAILED_DIR/$fname" "Failed"
            log_err "Failed after $MAX_RETRIES retries: $fname -> moved to failed/"
        fi
    done
}

# --- Main loop ---
log "EDW log shipper started. Source=$SRC_DIR -> $DEST_HOST:$DEST_DIR"

while true; do
    mapfile -t new_files < <(
        find "$SRC_DIR" -type f -name "$FILE_PATTERN" \
            ! -name "stats*.log" ! -path "*/sent/*" ! -path "*/failed/*"
    )

    mapfile -t failed_files < <(
        find "$FAILED_DIR" -type f -name "$FILE_PATTERN"
    )

    if [ ${#new_files[@]} -eq 0 ] && [ ${#failed_files[@]} -eq 0 ]; then
        log "No files to process this cycle."
    fi

    process_files "${new_files[@]}"
    process_files "${failed_files[@]}"

    log "Cycle complete. Sleeping ${SLEEP_SECS}s..."
    sleep "$SLEEP_SECS"
done
