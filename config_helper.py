#!/usr/bin/env python3
"""
Configuration helper for bash scripts
Exports configuration values as environment variables or shell script
"""

import sys
import argparse
import yaml
import os
from config_loader import load_config


def export_bash_env(config_path=None):
    """Export configuration as bash environment variables"""
    config = load_config(config_path)
    
    # Log sender configuration
    sender_config = config.get_section('log_sender')
    dest_config = sender_config.get('destination', {})
    
    print(f'export LOG_SENDER_SOURCE_DIR="{sender_config.get("source_dir", "")}"')
    print(f'export LOG_SENDER_DEST_USER="{dest_config.get("user", "")}"')
    print(f'export LOG_SENDER_DEST_HOST="{dest_config.get("host", "")}"')
    print(f'export LOG_SENDER_DEST_PORT="{dest_config.get("port", 22)}"')
    print(f'export LOG_SENDER_DEST_DIR="{dest_config.get("directory", "")}"')
    print(f'export LOG_SENDER_PASSWORD="{dest_config.get("password", "")}"')
    print(f'export LOG_SENDER_ARCHIVE_DIR="{sender_config.get("archive_dir", "")}"')
    print(f'export LOG_SENDER_FAILED_DIR="{sender_config.get("failed_dir", "")}"')
    print(f'export LOG_SENDER_SLEEP_SECS="{sender_config.get("sleep_seconds", 60)}"')
    print(f'export LOG_SENDER_MAX_RETRIES="{sender_config.get("max_retries", 3)}"')
    print(f'export LOG_SENDER_RSYNC_TIMEOUT="{sender_config.get("rsync_timeout", 60)}"')
    print(f'export LOG_SENDER_SSH_TIMEOUT="{sender_config.get("ssh_connect_timeout", 20)}"')
    print(f'export LOG_SENDER_FILE_PATTERN="{sender_config.get("file_pattern", "")}"')
    print(f'export LOG_SENDER_MIN_AGE_MIN="{sender_config.get("min_file_age_minutes", 2)}"')
    print(f'export LOG_SENDER_LINECOUNT_LOG="{sender_config.get("linecount_log", "")}"')
    print(f'export LOG_SENDER_LINECOUNT_FAIL="{sender_config.get("linecount_fail_log", "")}"')
    print(f'export LOG_SENDER_OUT_LOG="{sender_config.get("out_log", "")}"')
    print(f'export LOG_SENDER_ERR_LOG="{sender_config.get("err_log", "")}"')
    
    # Housekeeping configuration
    housekeep_config = config.get_section('housekeeping')
    print(f'export HOUSEKEEP_BASE_DIR="{housekeep_config.get("base_dir", "")}"')
    print(f'export HOUSEKEEP_COMPRESS_HOURS="{housekeep_config.get("compress_after_hours", 3)}"')
    print(f'export HOUSEKEEP_DELETE_HOURS="{housekeep_config.get("delete_after_hours", 4)}"')


def print_config_value(config_path, key_path):
    """Print a specific configuration value"""
    config = load_config(config_path)
    value = config.get(key_path)
    if value is not None:
        print(value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configuration helper for bash scripts")
    parser.add_argument("-c", "--config", help="Path to configuration file")
    parser.add_argument("-e", "--export", action="store_true", help="Export as bash environment variables")
    parser.add_argument("-g", "--get", help="Get specific config value (dot notation)")
    args = parser.parse_args()
    
    if args.export:
        export_bash_env(args.config)
    elif args.get:
        print_config_value(args.config, args.get)
    else:
        parser.print_help()
