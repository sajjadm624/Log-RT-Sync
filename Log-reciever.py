from flask import Flask, request
import os
import sys
import logging
import json
import codecs
import argparse
from datetime import datetime
import re

# Import configuration loader
try:
    from config_loader import load_config
except ImportError:
    print("Error: config_loader module not found. Please ensure config_loader.py is in the same directory.")
    sys.exit(1)

app = Flask(__name__)

# Global configuration - will be loaded from config file
CONFIG = None
BASE_LOG_DIR = None
TIME_WINDOWS = None
META_LOG_FILE = None

# Regex pattern to extract JSON-like payload in double quotes
json_log_pattern = re.compile(r'"({.*?})"')

# Regex pattern to extract NGINX timestamp
nginx_ts_pattern = re.compile(r"\[(\d{2}/[A-Za-z]+/\d{4}:\d{2}:\d{2}:\d{2})")


def get_time_window_label(minute):
    """Determine time window label based on minute and configured windows"""
    for window in TIME_WINDOWS:
        if window['start'] <= minute <= window['end']:
            return window['label']
    # Default fallback
    return "00-59"


@app.route('/upload', methods=['POST'])
def upload():
    if not request.is_json:
        logging.warning("Received non-JSON payload.")
        return "Invalid content-type, expected JSON", 400

    log_data = request.json.get('log')
    hostname = request.json.get('host')
    source_ip = request.remote_addr.replace(".", "-")

    if not log_data or not hostname:
        logging.warning(f"Incomplete upload from {source_ip}. Missing hostname or log.")
        return "Missing data", 400

    host_dir = os.path.join(BASE_LOG_DIR, hostname.strip())
    os.makedirs(host_dir, exist_ok=True)

    saved = 0

    for line in log_data.strip().splitlines():
        try:
            # --- Extract NGINX timestamp ---
            ts_match = nginx_ts_pattern.search(line)
            if not ts_match:
                logging.warning(f"No NGINX timestamp found in line from {source_ip}. Skipped.")
                continue

            try:
                dt = datetime.strptime(ts_match.group(1), "%d/%b/%Y:%H:%M:%S")
            except ValueError:
                logging.error(f"Invalid timestamp format in line from {source_ip}. Skipped.")
                continue

            # --- Determine time window based on config ---
            minute = dt.minute
            minute_window = get_time_window_label(minute)

            time_part = dt.strftime("%y%m%d%H")  # YYMMDDHH

            # --- Build log file path ---
            filename = f"MyGP_accessLog_{time_part}_{minute_window}_{source_ip}.log"
            filepath = os.path.join(host_dir, filename)

            # --- Optional JSON parsing (not used for bucketing) ---
            matches = json_log_pattern.findall(line)
            log_json = None
            for candidate in matches:
                try:
                    decoded_json = codecs.decode(candidate, 'unicode_escape')
                    log_json = json.loads(decoded_json)
                    break
                except json.JSONDecodeError:
                    continue
            # (log_json can be used later if needed, but not required here)

            # --- Write log line ---
            with open(filepath, "a") as f:
                f.write(line + "\n")

            saved += 1

        except Exception as e:
            logging.error(f"Error processing line from {source_ip}: {e}")

    logging.info(f"{saved} lines written to {hostname}/ for IP {source_ip}")
    return f"OK - {saved} lines", 200

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Log Receiver - Receive logs from shippers")
    parser.add_argument("-c", "--config", help="Path to configuration file")
    parser.add_argument("-p", "--port", type=int, help="Port to listen on (overrides config)")
    parser.add_argument("--host", help="Host to bind to (overrides config)")
    args = parser.parse_args()
    
    # Load configuration
    CONFIG = load_config(args.config)
    
    # Get configuration values
    receiver_config = CONFIG.get_section('log_receiver')
    BASE_LOG_DIR = receiver_config.get('base_log_dir', '/app/log/access-log-reciever/')
    TIME_WINDOWS = receiver_config.get('time_windows', [
        {'start': 0, 'end': 19, 'label': '00-19'},
        {'start': 20, 'end': 39, 'label': '20-39'},
        {'start': 40, 'end': 59, 'label': '40-59'},
    ])
    
    # Ensure base directory exists
    os.makedirs(BASE_LOG_DIR, exist_ok=True)
    
    META_LOG_FILE = os.path.join(BASE_LOG_DIR, "stats.log")
    
    # Setup logging
    logging.basicConfig(
        filename=META_LOG_FILE,
        level=logging.DEBUG if CONFIG.get('global.debug', False) else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    
    # Determine host and port
    host = args.host if args.host else receiver_config.get('host', '0.0.0.0')
    port = args.port if args.port else receiver_config.get('port', 5000)
    
    logging.info(f"Starting log receiver on {host}:{port}")
    logging.info(f"Base log directory: {BASE_LOG_DIR}")
    logging.info(f"Time windows: {TIME_WINDOWS}")
    
    app.run(host=host, port=port)
