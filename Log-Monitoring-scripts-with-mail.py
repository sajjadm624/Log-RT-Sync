#!/usr/bin/env python3
import os
import re
import json
import time
import smtplib
import sys
import argparse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

# Import configuration loader
try:
    from config_loader import load_config
except ImportError:
    print("Error: config_loader module not found. Please ensure config_loader.py is in the same directory.")
    sys.exit(1)

# Global configuration - will be loaded from config file
CONFIG = None
LOG_BASE_DIR = None
STATUS_FILE = None
REPORT_FILE = None
LINECOUNT_FILE = None
HOUR_STATE_FILE = None
THRESHOLD_MINUTES = None
MAIL_HOST = None
MAIL_PORT = None
MAIL_FROM = None
MAIL_RECIPIENTS = None
MAIL_SUBJECT_PREFIX = None
MAIL_TIMEOUT = None
HOURLY_SUMMARY_ENABLED = None
HOURLY_SEND_AFTER_MINUTES = None

# --- Helper: HTML Email Sender ---
def send_html_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["From"] = MAIL_FROM
    msg["To"] = ", ".join(MAIL_RECIPIENTS)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = f"{MAIL_SUBJECT_PREFIX} {subject}"
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(MAIL_HOST, MAIL_PORT, timeout=MAIL_TIMEOUT) as s:
            s.ehlo()
            s.sendmail(MAIL_FROM, MAIL_RECIPIENTS, msg.as_string())
        print(f"[{datetime.now()}] Email sent: {subject}")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to send email: {e}")

# --- Logging Helper ---
def log_report(text):
    timestamped = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}"
    print(timestamped)
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, "a") as f:
        f.write(timestamped + "\n")

# --- JSON Helpers ---
def load_json(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# --- Directory / File Helpers ---
def is_valid_ip_folder(name):
    return re.match(r"^\d{1,3}(\.\d{1,3}){3}$", name) is not None

def get_latest_file_info(server_dir):
    latest_file, latest_mtime = None, 0
    try:
        for fname in os.listdir(server_dir):
            fpath = os.path.join(server_dir, fname)
            if os.path.isfile(fpath):
                mtime = os.path.getmtime(fpath)
                if mtime > latest_mtime:
                    latest_file, latest_mtime = fname, mtime
    except Exception as e:
        log_report(f"Error reading directory {server_dir}: {e}")
    return (latest_file, latest_mtime) if latest_file else (None, None)

# --- 5-min Monitoring Logic ---
def monitor_receivers():
    now = time.time()
    prev_status = load_json(STATUS_FILE)
    new_status = {}
    inactive_alerts = []
    recovered_servers = []
    missing_servers = []

    for server_ip in sorted(os.listdir(LOG_BASE_DIR)):
        if not is_valid_ip_folder(server_ip):
            continue

        server_path = os.path.join(LOG_BASE_DIR, server_ip)
        if not os.path.isdir(server_path):
            continue

        latest_file, mtime = get_latest_file_info(server_path)

        if not latest_file:
            status = "missing"
            missing_servers.append(server_ip)
            log_report(f"No log files found for server {server_ip}")
            new_status[server_ip] = {"latest_file": None, "last_seen": None, "status": status}
            inactive_alerts.append((server_ip, "No log files", "-", "-"))
            continue

        last_seen = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        age_min = (now - mtime) / 60
        prev_state = prev_status.get(server_ip, {}).get("status", "unknown")

        if age_min > THRESHOLD_MINUTES:
            status = "inactive"
            if prev_state != "inactive":
                inactive_alerts.append((server_ip, latest_file, last_seen, round(age_min, 1)))
        else:
            status = "active"
            if prev_state in ["inactive", "missing"]:
                recovered_servers.append(server_ip)

        new_status[server_ip] = {
            "latest_file": latest_file,
            "last_seen": last_seen,
            "status": status
        }

    total_inactive = sum(1 for s in new_status.values() if s["status"] in ["inactive", "missing"])
    log_report(f"Scanned {len(new_status)} servers | Inactive: {total_inactive}")

    # --- Inactive / Missing Alert ---
    if inactive_alerts:
        html = """
        <html><body style="font-family:Arial, sans-serif;">
        <h3>⚠️ Inactive / Missing Servers</h3>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
        <thead style="background-color:#f2f2f2;">
            <tr><th>Server</th><th>Last File</th><th>Last Seen</th><th>Age (min)</th></tr>
        </thead><tbody>
        """
        for ip, f, t, age in inactive_alerts:
            html += f"<tr><td>{ip}</td><td>{f}</td><td>{t}</td><td align='center'>{age}</td></tr>"
        html += "</tbody></table>"

        if missing_servers:
            html += "<p><b>Missing servers (no logs at all):</b><br>" + "<br>".join(missing_servers) + "</p>"

        html += f"<p>Generated at: {datetime.now():%Y-%m-%d %H:%M:%S}</p></body></html>"
        subject = f"ALERT: {len(inactive_alerts)} server(s) inactive/missing >{THRESHOLD_MINUTES} min"
        send_html_email(subject, html)
        log_report(f"ALERT: {len(inactive_alerts)} inactive/missing servers. Email sent.")

    # --- Recovery Notice ---
    if recovered_servers:
        html = """
        <html><body style="font-family:Arial, sans-serif;">
        <h3>Recovered Servers</h3><ul>
        """
        for ip in recovered_servers:
            html += f"<li>{ip}</li>"
        html += f"</ul><p>Generated at: {datetime.now():%Y-%m-%d %H:%M:%S}</p></body></html>"
        subject = f"RECOVERY: {len(recovered_servers)} server(s) active again"
        send_html_email(subject, html)
        log_report(f"INFO: {len(recovered_servers)} servers recovered. Email sent.")

    save_json(STATUS_FILE, new_status)

# --- Hourly Summary Logic ---
def hourly_summary():
    if not HOURLY_SUMMARY_ENABLED:
        return
    
    now = datetime.now()
    if now.minute < HOURLY_SEND_AFTER_MINUTES:
        return

    last_state = load_json(HOUR_STATE_FILE)
    target_dt = now - timedelta(hours=1)
    target_hour_str = target_dt.strftime("%y%m%d%H")  # YYMMDDHH
    last_reported = last_state.get("last_reported_hour")

    if last_reported == target_hour_str:
        return

    if not os.path.exists(LINECOUNT_FILE):
        log_report("No linecount log found. Skipping hourly summary.")
        return

    with open(LINECOUNT_FILE) as f:
        lines = f.readlines()

    hourly_entries = []
    total_lines = 0

    pattern = re.compile(r"MyGP_accessLog_(\d{8})_\d{2}-\d{2}_")

    for line in lines:
        m = pattern.search(line)
        if not m:
            continue
        file_hour = m.group(1)  # YYMMDDHH
        if file_hour != target_hour_str:
            continue

        hourly_entries.append(line.strip())
        m_count = re.search(r"lines?\s*[:=]\s*(\d+)", line, re.IGNORECASE)
        if m_count:
            try:
                total_lines += int(m_count.group(1))
            except:
                pass

    if not hourly_entries:
        log_report(f"No linecount entries found for hour {target_hour_str}")
        return

    html = f"""
    <html><body style="font-family:Arial, sans-serif;">
    <h3>Hourly Summary for {target_hour_str}</h3>

    <p><b>Total files:</b> {len(hourly_entries)}<br>
    <b>Total lines:</b> {total_lines}<br>
    🕒 Generated at: {datetime.now():%Y-%m-%d %H:%M:%S}</p>

    </tbody></table>
    </body></html>

    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
    <thead style="background-color:#f2f2f2;">
        <tr><th>Timestamp</th><th>Log File / Info</th><th>Line Count</th></tr>
    </thead><tbody>
    """
    for line in hourly_entries:
        parts = [p.strip() for p in line.split("|")]
        ts = parts[0] if len(parts) > 0 else "-"
        rest = " | ".join(parts[1:]) if len(parts) > 1 else "-"
        m_count = re.search(r"lines?\s*[:=]\s*(\d+)", line, re.IGNORECASE)
        count = m_count.group(1) if m_count else "-"
        html += f"<tr><td>{ts}</td><td>{rest}</td><td align='center'>{count}</td></tr>"

    subject = f"HOURLY SUMMARY {target_hour_str}: {len(hourly_entries)} files, {total_lines} lines"
    send_html_email(subject, html)
    log_report(f"Hourly summary sent for {target_hour_str} | Files: {len(hourly_entries)} | Lines: {total_lines}")

    last_state["last_reported_hour"] = target_hour_str
    save_json(HOUR_STATE_FILE, last_state)

# --- Test SMTP ---
def test_mail():
    html = "<html><body><p>This is a test email from check_active_sources_v2.py</p></body></html>"
    subject = "TEST SMTP from Server Log Monitor"
    send_html_email(subject, html)

# --- Entrypoint ---
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Log Monitoring - Monitor log activity and send alerts")
    parser.add_argument("-c", "--config", help="Path to configuration file")
    parser.add_argument("--test-mail", action="store_true", help="Send a test email")
    args = parser.parse_args()
    
    # Load configuration
    CONFIG = load_config(args.config)
    
    # Get configuration values
    monitoring_config = CONFIG.get_section('log_monitoring')
    LOG_BASE_DIR = monitoring_config.get('log_base_dir', '/app/log/access-log-reciever/')
    STATUS_FILE = monitoring_config.get('status_file', '/tmp/receiver_status.json')
    REPORT_FILE = monitoring_config.get('report_file', '/tmp/receiver_status_report.log')
    LINECOUNT_FILE = monitoring_config.get('linecount_file', '/tmp/linecount-report.log')
    HOUR_STATE_FILE = monitoring_config.get('hour_state_file', '/tmp/last_hour_state.json')
    THRESHOLD_MINUTES = monitoring_config.get('threshold_minutes', 5)
    
    # Email configuration
    email_config = monitoring_config.get('email', {})
    MAIL_HOST = email_config.get('smtp_host', 'localhost')
    MAIL_PORT = email_config.get('smtp_port', 25)
    MAIL_FROM = email_config.get('from_address', 'noreply@localhost')
    MAIL_RECIPIENTS = email_config.get('recipients', ['admin@localhost'])
    MAIL_SUBJECT_PREFIX = email_config.get('subject_prefix', '[Log Monitor]')
    MAIL_TIMEOUT = email_config.get('timeout', 15)
    
    # Hourly summary configuration
    hourly_config = monitoring_config.get('hourly_summary', {})
    HOURLY_SUMMARY_ENABLED = hourly_config.get('enabled', True)
    HOURLY_SEND_AFTER_MINUTES = hourly_config.get('send_after_minutes', 15)
    
    if args.test_mail:
        test_mail()
        sys.exit(0)

    monitor_receivers()  # 5-minute monitoring
    hourly_summary()     # hourly summary after HH:15
