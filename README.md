# Log-RT-Sync

## Project Purpose

**Log-RT-Sync** synchronises Nginx access logs from multiple application servers (“sender” servers) to a central client-end SFTP server via an intermediate “receiver” server. Features include robust failover, log rotation handling, real-time monitoring, email alerting, and housekeeping for optimal reliability.

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
                             |    '--------------------^           |
                             |          |              |           |
+----------------------------+          |              |           |
| Log Monitoring & Email     |----------'              |           |
| Log-Monitoring-scripts-    |-- Monitors per server   |           |
| with-mail.py               |-- Sends alerts & hourly |           |
| SMTP alerts                |   summaries             |           |
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
  - Maintains offset file for reliability
- Sends log lines in chunks via HTTP POST to the receiver; skips health check lines

### 2. **Log-reciever.py** (middle receiver server)
- Runs on the middle server, accepts log streams via grouped TCP ports using Gunicorn for concurrency.
  - E.g. servers 1-5 → port 5001; 6-11 → port 5002, etc.
- Splits, groups, and saves incoming logs by IP and 20-minute batches.

### 3. **Log-sender-to-client-end.sh** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-sender-to-client-end.sh))
- On receiver server, periodically:
  - Searches for new log batches
  - Uses rsync+sshpass to securely send them to the client SFTP server
  - Handles retry and archives sent/failed files

### 4. **Log-Monitoring-scripts-with-mail.py** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Log-Monitoring-scripts-with-mail.py))
- Tracks latest log arrival time for each server/source directory
- If no log received from a server for >5 min, sends SMTP alert
- Notifies on server recovery, emails hourly log summaries

### 5. **Houskeep-log.sh** ([source](https://github.com/sajjadm624/Log-RT-Sync/blob/main/Houskeep-log.sh))
- Compresses logs older than 3 hours
- Deletes logs older than retention (default 4 hours), except failed logs for troubleshooting

---

## Setup & Installation: Service Files (systemd)

### **A. Sender End (Log Shipper) – Setup as a Service**

#### 1. **Create the service file:**
Save the following in `/etc/systemd/system/log-shipper.service`:

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

#### 2. **Enable and Start Service:**
```bash
sudo systemctl daemon-reload           # Reloads systemd unit files
sudo systemctl enable log-shipper      # Enables the service on boot
sudo systemctl start log-shipper       # Starts the service now
sudo systemctl status log-shipper      # Shows running status
```

**Failover Guarantee:**  
- The `log-shipper.py` maintains a persistent offset file. If the log rotates, or the server is patched/rebooted, it reads the new file, resets offset if needed, and resumes shipping from the correct line, ensuring no loss or duplication.

---

### **B. Receiver End (Log Receiver/Sender/Monitor) – Setup as a Service**

1. **Log-Receiver is typically run under Gunicorn** (for concurrency) and not always as a systemd service. But if you want to set it up as a service, create `/etc/systemd/system/log-receiver.service`:

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
*(Repeat for other ports as needed)*

2. **Enable and Start Service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable log-receiver
sudo systemctl start log-receiver
```

#### **Log Sender to SFTP (from receiver) as a service:**
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

#### **Monitoring and Housekeeping Scripts**
- These can be run:
  - As cron jobs executed periodically (`crontab -e`)
  - Or as services using similar systemd files

---

## Monitoring & Alerting

- **Log-Monitoring-scripts-with-mail.py** tracks all incoming directories for each server, sends email alerts if logs stop arriving (via SMTP), and summarizes hourly file/line counts.

---

## Housekeeping

- **Houskeep-log.sh** compresses old logs, deletes logs past retention, preserving failed transfers for troubleshooting.  
- Run manually, as a cron job, or systemd service.

---

## Prerequisites

- **Python 3** (with `watchdog`, `tenacity`, possibly others)
- **gunicorn** (for concurrent receivers)
- **Bash, rsync, sshpass, gzip**
- **Systemd** (for services)
- **SMTP server** (for email alerts)

---

## License

MIT License

---

### **Notes & Troubleshooting**
- After any change to a service file, always run `sudo systemctl daemon-reload`.
- To view logs, use `journalctl -u log-shipper` or `journalctl -u edw-rsync`.
- Restart services after significant changes: `sudo systemctl restart <service-name>`.

**For questions or contributions, open an issue or pull request on GitHub!**
