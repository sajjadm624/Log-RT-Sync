#!/bin/bash
# -------------------------------------------------------------
# Log Housekeeping for MyGP access logs
# Compress old logs and delete logs older than retention period
# without touching the failed directory.
# -------------------------------------------------------------

BASE_DIR="/app/log/access-log-reciever"
LOG_RETENTION_HOURS=4

# --- Compress logs not written in last 3 hours (180 minutes) ---
find "$BASE_DIR" -type f -name "*.log" \
    ! -name "stat*.log" \
    ! -name "line*.log" \
    ! -path "$BASE_DIR/failed/*" \
    ! -name "*.gz" \
    -mmin +180 \
    -exec gzip {} \;

# --- Delete logs older than retention period ---
find "$BASE_DIR" -type f \
    ! -path "$BASE_DIR/failed/*" \
    -mmin +$((LOG_RETENTION_HOURS * 60)) \
    -delete
