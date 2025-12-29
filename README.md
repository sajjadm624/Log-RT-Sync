# Log-RT-Sync

## Project Purpose

**Log-RT-Sync** synchronizes Nginx access logs from multiple application servers (“sender” servers) to a central client-end SFTP server via an intermediate “receiver” server. Features include robust failover, log rotation handling, real-time monitoring, email alerting, and housekeeping for optimal reliability.

---

## Quick Start

1. **Clone the repo to each relevant server:**
   ```bash
   git clone https://github.com/sajjadm624/Log-RT-Sync.git
   cd Log-RT-Sync
   ```

2. **Install required dependencies:**
   - Python 3
   - [gunicorn](https://gunicorn.org/) (for receiver concurrency)
   - rsync, sshpass, gzip (for log sending and housekeeping)

3. **Service Setup (systemd):**
   - Configure and copy the example service files (see below).
   - Reload systemd and enable/start the service:
     ```bash
     sudo systemctl daemon-reload
     sudo systemctl enable log-shipper
     sudo systemctl start log-shipper
     sudo systemctl status log-shipper
     ```
     *(Repeat for receiver and log-sender services)*

4. **Verify log sync:**
   - Sender-end: log-shipper actively ships logs.
   - Receiver-end: logs written to `/app/log/access-log-reciever/<server_ip>/`
   - Logs are periodically transferred to SFTP server.

5. **Monitor services and log flow:**
   ```bash
   sudo journalctl -u log-shipper   # or -u edw-rsync, -u log-receiver
   ```

---

## Configuration (NEW in v5.0!)

**Log-RT-Sync now supports centralized configuration via YAML files!**

### Quick Configuration Setup

1. **Copy the example configuration:**
   ```bash
   cp config.example.yaml config.yaml
   ```

2. **Edit the configuration file:**
   ```bash
   nano config.yaml
   ```
   
   Key settings to configure:
   - **Server addresses and ports:** Update receiver URLs, SFTP endpoints
   - **Log paths:** Customize log file locations for your environment
   - **SFTP credentials:** Set username, password, and destination paths
   - **Email settings:** Configure SMTP server and alert recipients
   - **Time windows:** Customize log batching timeframes (20-min, 10-min, etc.)
   - **Retention policies:** Set compression and deletion timeframes

3. **Use configuration with services:**
   ```bash
   # All scripts support -c/--config parameter
   python3 Log-shipper.py -c config.yaml
   python3 Log-reciever.py -c config.yaml
   python3 Log-Monitoring-scripts-with-mail.py -c config.yaml
   ./Log-sender-to-client-end.sh -c config.yaml
   ./Houskeep-log.sh -c config.yaml
   ```

### Configuration Features

- **Centralized Management:** Single file controls all components
- **Customizable Time Windows:** Change from 20-minute to 10-minute or 15-minute batches
- **Multiple Servers:** Easy to manage settings for multiple shippers/receivers
- **Environment-specific:** Maintain different configs for dev/staging/production
- **Backward Compatible:** Works with or without config file (uses defaults)

📖 **[Full Configuration Guide →](CONFIG.md)** - Detailed documentation with examples

---

## Architecture & Workflow

```
+------------------+       +-------------------+       +-------------------------+
| Nginx App Server |  ---> | Middle Receiver   | --->  | Client-End SFTP Server  |
| Log-shipper.py   |  TCP  | Log-reciever.py   | RSYNC | Log-sender-to-client-   |
| (Sender, per srv)|       |   (Gunicorn)      |       | end.sh (Receiver)       |
+------------------+       +-------------------+       +-------------------------+
         |                        |                                 |
         |-- Watches log          |-- Accepts logs via group ports  |-- Receives logs for
         |   (chunked HTTP)       |   (5001, 5002...), saves        |   each 20-min batch
         |-- Handles failover     |   by time/IP                    |
         |   (rotation, reboot)   |-- Multiple gunicorn workers     |
         '-------------------^    |   for concurrency               |
                             |    |-- Monitored & summarized       |
+----------------------------+    '--------------------^           |
| Log Monitoring & Email     |--------- Monitors per server        |
| Log-Monitoring-scripts-    |--------- Sends alerts & hourly      |
| with-mail.py               |--------- summaries                  |
+----------------------------+-------------------------'           |
         |                                                      |
         v                                                      v
+------------------+                                    +------------------+
| Housekeeping     |                                    | SFTP             |
| Houskeep-log.sh  |                                    | Client log store |
| Compress+delete  |                                    +------------------+
+------------------+
```

---

## Components

**All components now support centralized configuration via YAML files!** Use `-c config.yaml` to specify your configuration file, or place it in a default location. See [CONFIG.md](CONFIG.md) for details.

### 1. **Log-shipper.py** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-shipper.py))
- **Runs on each sender/server (Nginx host)**
- Watches nginx access logs (configurable path)
- **Failover features:**
  - Handles log rotation (detects inode change, resets offset)
  - Restarts from the correct offset after server reboot or patching
  - Maintains persistent offset file for reliability
- Sends log lines in chunks via HTTP POST to the receiver; skips health check lines
- **Configuration:** Customize log path, receiver URL, chunk size, retry settings

### 2. **Log-reciever.py** (middle receiver server)
- Listens on TCP ports with Flask/Gunicorn (configurable)
- Saves incoming logs by server IP and time-based batch files
- **Configuration:** Customize time windows (20-min, 10-min, 15-min, etc.), ports, directories

### 3. **Log-sender-to-client-end.sh** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-sender-to-client-end.sh))
- Periodically scans for new log batches
- Uses rsync+sshpass to securely send logs to SFTP server
- Handles retries and archives sent/failed files
- **Configuration:** SFTP credentials, paths, retry settings, file patterns

### 4. **Log-Monitoring-scripts-with-mail.py** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-Monitoring-scripts-with-mail.py))
- Tracks latest log arrivals per server/source directory
- Sends SMTP alerts if log missing/inactive (configurable threshold)
- Notifies on server recovery, emails hourly summaries
- **Configuration:** Email settings, alert thresholds, monitoring paths

### 5. **Houskeep-log.sh** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Houskeep-log.sh))
- Compresses logs older than N hours (configurable)
- Deletes logs older than retention period (configurable), except failed logs
- **Configuration:** Retention policies, paths, exclusion patterns

### 6. **config_loader.py** & **config_helper.py** (NEW)
- Configuration loading and parsing utilities
- Supports Python and Bash script integration
- Validates configuration and provides defaults

---

## Sample Log Directory Structure

```
/app/log/access-log-reciever/
├── 10.10.21.181/
│   ├── MyGP_accessLog_20251129_10-20.log
│   ├── MyGP_accessLog_20251129_10-40.log
│   └── ...
├── 10.10.21.182/
│   ├── MyGP_accessLog_20251129_10-20.log
│   └── ...
├── failed/
│   └── MyGP_accessLog_20251129_09-40.log
└── sent/
    └── MyGP_accessLog_20251129_08-00.log
```
- Each server’s logs are saved in a separate directory.
- Logs are named with date and time, representing 20-minute batches.  
- Failed and sent logs are archived separately for traceability.

---

## Setup & Installation: Service Files (systemd)

### **A. Sender End (Log Shipper) – Setup as a Service**
#### 1. Create the service file `/etc/systemd/system/log-shipper.service`:
```ini
[Unit]
Description=Log Shipper (Chunked Nginx Access Log Sender)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/app/log/nginx/log-shipper
# With configuration file (recommended):
ExecStart=/usr/bin/python3 /app/log/nginx/log-shipper/Log-shipper.py -c /etc/log-rt-sync/config.yaml
# Or without config file (uses defaults):
# ExecStart=/usr/bin/python3 /app/log/nginx/log-shipper/Log-shipper.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
#### 2. Enable and Start Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable log-shipper
sudo systemctl start log-shipper
sudo systemctl status log-shipper
```
**Failover Guarantee:**  
- Maintains offset file and automatically resumes after rotation/reboot with no log loss.

---

### **B. Receiver End (Log Receiver/Sender/Monitor) – Setup as a Service**

#### 1. Log Receiver Service `/etc/systemd/system/log-receiver.service`:
```ini
[Unit]
Description=Log Receiver (Nginx Log Collector)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/log-rt-sync
# With configuration file (recommended):
ExecStart=/usr/bin/python3 /opt/log-rt-sync/Log-reciever.py -c /etc/log-rt-sync/config.yaml
# Or with Gunicorn for production (higher concurrency):
# ExecStart=/usr/local/bin/gunicorn --workers 4 --bind 0.0.0.0:5001 "Log-reciever:app"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
*(Repeat for each port as needed)*

#### 2. Enable and Start Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable log-receiver
sudo systemctl start log-receiver
sudo systemctl status log-receiver
```

#### 3. Log Sender to SFTP Service `/etc/systemd/system/log-sender.service`:
```ini
[Unit]
Description=Log Sender to SFTP (EDW Rsync)
After=network.target

[Service]
Type=simple
User=mygpadmin
WorkingDirectory=/opt/log-rt-sync
# With configuration file (recommended):
ExecStart=/bin/bash /opt/log-rt-sync/Log-sender-to-client-end.sh -c /etc/log-rt-sync/config.yaml
# Or without config file (uses defaults):
# ExecStart=/bin/bash /opt/log-rt-sync/Log-sender-to-client-end.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable log-sender
sudo systemctl start log-sender
sudo systemctl status log-sender
```

#### 4. Monitoring Service (Optional - can also run as cron)
Create `/etc/systemd/system/log-monitor.timer` and `/etc/systemd/system/log-monitor.service`:

**Timer file** (`log-monitor.timer`):
```ini
[Unit]
Description=Log Monitoring Timer (runs every 5 minutes)

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
```

**Service file** (`log-monitor.service`):
```ini
[Unit]
Description=Log Monitoring and Email Alerts

[Service]
Type=oneshot
User=mygpadmin
WorkingDirectory=/opt/log-rt-sync
ExecStart=/usr/bin/python3 /opt/log-rt-sync/Log-Monitoring-scripts-with-mail.py -c /etc/log-rt-sync/config.yaml
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable log-monitor.timer
sudo systemctl start log-monitor.timer
```

#### 5. Housekeeping Script (Cron Job)
Add to crontab (`crontab -e`):
```bash
# Run housekeeping every hour
0 * * * * /bin/bash /opt/log-rt-sync/Houskeep-log.sh -c /etc/log-rt-sync/config.yaml >> /var/log/housekeep.log 2>&1
```

---

## Troubleshooting & FAQ

**Q: The systemd service failed to start or is inactive. What should I do?**  
A: Run:
```bash
sudo journalctl -u log-shipper  # or -u edw-rsync
```
Check for errors (file not found, permissions, dependencies).

**Q: Why did log shipping suddenly stop?**  
A:
- Network connectivity issues
- Log rotation/offset file problems
- Ports/firewall blocks
- Dependency issues

**Q: I changed a service file but nothing happened.**  
A: Always run:
```bash
sudo systemctl daemon-reload
sudo systemctl restart <service-name>
```

**Q: How can I change the log retention period?**  
A: Edit the `housekeeping` section in `config.yaml`:
```yaml
housekeeping:
  compress_after_hours: 3  # Change this value
  delete_after_hours: 4    # Change this value
```
Then restart the housekeeping service or cron job.

**Q: How do I update email alert recipients?**  
A: Edit the `log_monitoring.email.recipients` section in `config.yaml`:
```yaml
log_monitoring:
  email:
    recipients:
      - "new-email@example.com"
      - "another@example.com"
```
Then restart the monitoring service.

**Q: How do I change log batching timeframes (e.g., from 20-min to 10-min windows)?**  
A: Edit the `log_receiver.time_windows` section in `config.yaml`:
```yaml
log_receiver:
  time_windows:
    - {start: 0, end: 9, label: "00-09"}
    - {start: 10, end: 19, label: "10-19"}
    # ... add more windows
```
See [CONFIG.md](CONFIG.md) for detailed examples.

**Q: Can I use the services without a config file?**  
A: Yes! All scripts are backward compatible. If no config file is specified or found, they use default hardcoded values.

---

## Prerequisites

### System Requirements
- **Python 3.6+** with pip
- **Bash 4.0+**
- **systemd** (for service management)

### Python Packages
Install via pip:
```bash
pip3 install -r requirements.txt
```

Or manually:
- `PyYAML>=6.0` - Configuration file parsing
- `flask>=2.0.0` - Log receiver web service
- `requests>=2.25.0` - HTTP client for log shipping
- `watchdog>=2.0.0` - File system monitoring
- `tenacity>=8.0.0` - Retry logic
- `gunicorn>=20.0.0` - Production WSGI server (optional)

### System Packages
- **rsync** - Log file transfer
- **sshpass** - Non-interactive SSH authentication
- **gzip** - Log compression
- **SMTP server** - For email alerts (can be remote)

---

## License

MIT License

---

### Notes & Troubleshooting

- After any change to a service file, always run `sudo systemctl daemon-reload`.
- To view logs, use `journalctl -u log-shipper` or `journalctl -u edw-rsync`.
- Restart services after significant changes: `sudo systemctl restart <service-name>`.

**For questions or contributions, open an issue or pull request on GitHub!**
