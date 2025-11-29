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

### 1. **Log-shipper.py** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-shipper.py))
- **Runs on each sender/server (Nginx host)**
- Watches `/app/log/nginx/access.log`
- **Failover features:**
  - Handles log rotation (detects inode change, resets offset)
  - Restarts from the correct offset after server reboot or patching
  - Maintains persistent offset file for reliability
- Sends log lines in chunks via HTTP POST to the receiver; skips health check lines

### 2. **Log-reciever.py** (middle receiver server)
- Listens on grouped TCP ports with Gunicorn (e.g. servers 1-5 → port 5001; 6-11 → port 5002, etc.)
- Saves incoming logs by server IP and 20-minute batch files

### 3. **Log-sender-to-client-end.sh** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-sender-to-client-end.sh))
- Periodically scans for new log batches
- Uses rsync+sshpass to securely send logs to SFTP server
- Handles retries and archives sent/failed files

### 4. **Log-Monitoring-scripts-with-mail.py** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-Monitoring-scripts-with-mail.py))
- Tracks latest log arrivals per server/source directory
- Sends SMTP alerts if log missing/inactive for >5 min
- Notifies on server recovery, emails hourly summaries

### 5. **Houskeep-log.sh** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Houskeep-log.sh))
- Compresses logs older than 3 hours
- Deletes logs older than 4 hours (default), except failed logs

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
ExecStart=/usr/bin/python3 /app/log/nginx/log-shipper/log-shipper.py
Restart=always

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

#### 1. Optional Service File `/etc/systemd/system/log-receiver.service`:
```ini
[Unit]
Description=Gunicorn Log Receiver (Nginx Log Collector)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/log-rt-sync
ExecStart=/usr/local/bin/gunicorn --workers 4 --bind 0.0.0.0:5001 log-reciever:app
Restart=always

[Install]
WantedBy=multi-user.target
```
*(Repeat for each port as needed)*

#### 2. Enable and Start Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable log-receiver
sudo systemctl start log-receiver
```

#### Log Sender to SFTP (from receiver) as a service:
Create `/etc/systemd/system/edw-rsync.service`:
```ini
[Unit]
Description=EDW Log Rsync Shipper
After=network.target

[Service]
Type=simple
User=mygpadmin
ExecStart=/bin/bash /home/mygpadmin/LogTerminal-rtSync/edw-rsync/edw-rsync_v4.sh
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable edw-rsync
sudo systemctl start edw-rsync
```

#### Monitoring & Housekeeping Scripts
- Can be run as cron jobs (`crontab -e`) or as additional systemd services.

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
A: Edit `LOG_RETENTION_HOURS` in `Houskeep-log.sh` and restart job/service.

**Q: How do I update email alert recipients?**  
A: Edit `MAIL_RECIPIENTS` variable in `Log-Monitoring-scripts-with-mail.py`.

---

## Prerequisites

- Python 3 (`watchdog`, `tenacity`)
- gunicorn
- Bash, rsync, sshpass, gzip
- Systemd (for service management)
- SMTP server (for email alerts)

---

## License

MIT License

---

### Notes & Troubleshooting

- After any change to a service file, always run `sudo systemctl daemon-reload`.
- To view logs, use `journalctl -u log-shipper` or `journalctl -u edw-rsync`.
- Restart services after significant changes: `sudo systemctl restart <service-name>`.

**For questions or contributions, open an issue or pull request on GitHub!**
