from flask import Flask, request
import os
import logging
import json
import codecs
from datetime import datetime
import re

app = Flask(__name__)

BASE_LOG_DIR = "/app/log/access-log-reciever/"
os.makedirs(BASE_LOG_DIR, exist_ok=True)

META_LOG_FILE = os.path.join(BASE_LOG_DIR, "stats.log")

# Logging setup
logging.basicConfig(
    filename=META_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Regex pattern to extract JSON-like payload in double quotes
json_log_pattern = re.compile(r'"({.*?})"')

# Regex pattern to extract NGINX timestamp
nginx_ts_pattern = re.compile(r"\[(\d{2}/[A-Za-z]+/\d{4}:\d{2}:\d{2}:\d{2})")


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

            # --- Determine 20-minute bucket ---
            minute = dt.minute
            if minute < 20:
                minute_window = "00-19"
            elif minute < 40:
                minute_window = "20-39"
            else:
                minute_window = "40-59"

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
    app.run(host="0.0.0.0", port=5000)
