# Configuration Guide for Log-RT-Sync

## Overview

Log-RT-Sync v5.0 introduces centralized configuration file support, allowing you to manage all settings from a single YAML file. This makes it easy to:
- Configure multiple servers from a central location
- Customize log batching timeframes
- Adjust retention policies
- Manage email alerts and monitoring thresholds
- Update SFTP credentials without editing code

## Configuration File Setup

### 1. Create Configuration File

Copy the example configuration to create your own:

```bash
cp config.example.yaml config.yaml
```

### 2. Edit Configuration

The configuration file is divided into sections for each component:

#### Log Shipper Configuration (Sender Servers)

```yaml
log_shipper:
  log_file: "/app/log/nginx/access.log"          # Log file to monitor
  offset_file: "/app/log/nginx/log-shipper/latest.offset"  # Offset tracker
  chunk_size: 10000                              # Lines per chunk
  receiver_url: "http://10.10.23.212:5000/upload"  # Receiver endpoint
  logging_file: "/app/log/nginx/log-shipper/log_shipper_status.log"
  debounce_delay: 1.0                            # Seconds to wait before processing
  retry_attempts: 600                            # Max retry attempts
  retry_wait_seconds: 6                          # Seconds between retries
```

#### Log Receiver Configuration (Middle Server)

```yaml
log_receiver:
  base_log_dir: "/app/log/access-log-reciever/"  # Base directory for logs
  port: 5000                                      # Listen port
  host: "0.0.0.0"                                 # Bind address
  
  # Customize time windows for log batching
  time_windows:
    - start: 0
      end: 19
      label: "00-19"
    - start: 20
      end: 39
      label: "20-39"
    - start: 40
      end: 59
      label: "40-59"
```

**Customizing Time Windows:**
You can configure different time windows to suit your needs. For example, for 10-minute windows:

```yaml
time_windows:
  - {start: 0, end: 9, label: "00-09"}
  - {start: 10, end: 19, label: "10-19"}
  - {start: 20, end: 29, label: "20-29"}
  - {start: 30, end: 39, label: "30-39"}
  - {start: 40, end: 49, label: "40-49"}
  - {start: 50, end: 59, label: "50-59"}
```

#### Log Sender Configuration (SFTP Transfer)

```yaml
log_sender:
  source_dir: "/app/log/access-log-reciever"
  
  destination:
    user: "mygp1"
    host: "10.12.3.3"
    port: 22022
    directory: "/cdrdata/oracle/ProdEDW/source_data/MYGP"
    password: "YOUR_PASSWORD_HERE"  # CHANGE THIS!
  
  archive_dir: "/app/log/access-log-reciever/sent"
  failed_dir: "/app/log/access-log-reciever/failed"
  sleep_seconds: 60                              # Seconds between cycles
  max_retries: 3                                 # Max transfer retries
  file_pattern: "MyGP_accessLog_*.log"          # File pattern to match
  min_file_age_minutes: 2                       # Don't transfer new files
```

#### Log Monitoring Configuration

```yaml
log_monitoring:
  log_base_dir: "/app/log/access-log-reciever/"
  threshold_minutes: 5                          # Inactivity threshold
  
  email:
    smtp_host: "192.168.207.212"
    smtp_port: 25
    from_address: "devops@example.com"
    recipients:
      - "admin@example.com"
      - "team@example.com"
    subject_prefix: "[Log Monitor]"
    timeout: 15
  
  hourly_summary:
    enabled: true
    send_after_minutes: 15                      # Send summary HH:15
```

#### Housekeeping Configuration

```yaml
housekeeping:
  base_dir: "/app/log/access-log-reciever"
  compress_after_hours: 3                       # Compress logs older than 3h
  delete_after_hours: 4                         # Delete logs older than 4h
```

### 3. Using Configuration with Services

#### Running Scripts Manually

All scripts now accept a `-c` or `--config` parameter:

```bash
# Log Shipper
python3 Log-shipper.py -c config.yaml

# Log Receiver
python3 Log-reciever.py -c config.yaml

# Log Monitoring
python3 Log-Monitoring-scripts-with-mail.py -c config.yaml

# Log Sender (bash)
./Log-sender-to-client-end.sh -c config.yaml

# Housekeeping (bash)
./Houskeep-log.sh -c config.yaml
```

#### Systemd Service Configuration

Update your systemd service files to use the config file:

**Log Shipper Service** (`/etc/systemd/system/log-shipper.service`):
```ini
[Unit]
Description=Log Shipper (Nginx Access Log Sender)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/app/log/nginx/log-shipper
ExecStart=/usr/bin/python3 /app/log/nginx/log-shipper/Log-shipper.py -c /etc/log-rt-sync/config.yaml
Restart=always

[Install]
WantedBy=multi-user.target
```

**Log Receiver Service** (`/etc/systemd/system/log-receiver.service`):
```ini
[Unit]
Description=Log Receiver (Nginx Log Collector)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/log-rt-sync
# For production with gunicorn:
# ExecStart=/usr/local/bin/gunicorn --workers 4 --bind 0.0.0.0:5001 "Log-reciever:app"
# Or directly with Flask:
ExecStart=/usr/bin/python3 /opt/log-rt-sync/Log-reciever.py -c /etc/log-rt-sync/config.yaml
Restart=always

[Install]
WantedBy=multi-user.target
```

**Log Sender Service** (`/etc/systemd/system/log-sender.service`):
```ini
[Unit]
Description=Log Sender to SFTP
After=network.target

[Service]
Type=simple
User=mygpadmin
WorkingDirectory=/opt/log-rt-sync
ExecStart=/bin/bash /opt/log-rt-sync/Log-sender-to-client-end.sh -c /etc/log-rt-sync/config.yaml
Restart=always

[Install]
WantedBy=multi-user.target
```

### 4. Configuration File Locations

Scripts will search for configuration files in the following order:

1. Path specified with `-c` or `--config`
2. `/etc/log-rt-sync/config.yaml`
3. `/etc/log-rt-sync.yaml`
4. `./config.yaml` (current directory)
5. `~/.log-rt-sync.yaml` (user home)

If no config file is found, the scripts will use default values (backward compatible with hardcoded values).

## Testing Configuration

### Validate Configuration

Test that your configuration is loaded correctly:

```bash
# Test config loader
python3 config_loader.py -c config.yaml

# Test specific section
python3 config_loader.py -c config.yaml -s log_shipper
```

### Test Email Configuration

```bash
# Send test email
python3 Log-Monitoring-scripts-with-mail.py -c config.yaml --test-mail
```

## Migration from Hardcoded Configuration

If you're upgrading from an older version:

1. Create `config.yaml` from `config.example.yaml`
2. Copy your current settings into the config file
3. Update systemd service files to use `-c /path/to/config.yaml`
4. Reload and restart services:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart log-shipper
   sudo systemctl restart log-receiver
   sudo systemctl restart log-sender
   ```

## Security Considerations

- Store `config.yaml` in a secure location (e.g., `/etc/log-rt-sync/`)
- Set appropriate permissions: `chmod 600 config.yaml`
- Never commit `config.yaml` with passwords to version control
- Use `config.example.yaml` as a template with placeholder values

## Advanced Configuration

### Multiple Receiver Ports

You can run multiple receiver instances on different ports by:

1. Creating separate config files for each port
2. Running multiple instances with different configs:
   ```bash
   python3 Log-reciever.py -c config-port5001.yaml
   python3 Log-reciever.py -c config-port5002.yaml
   ```

### Custom Time Windows

Adjust time windows to match your analytics or storage needs:

```yaml
# Example: 15-minute windows
time_windows:
  - {start: 0, end: 14, label: "00-14"}
  - {start: 15, end: 29, label: "15-29"}
  - {start: 30, end: 44, label: "30-44"}
  - {start: 45, end: 59, label: "45-59"}
```

### Multiple Email Recipients

Add multiple recipients for alerts:

```yaml
email:
  recipients:
    - "devops-team@example.com"
    - "oncall@example.com"
    - "sre@example.com"
```

## Troubleshooting

**Config file not found:**
- Check file path and permissions
- Verify YAML syntax: `python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"`

**Changes not taking effect:**
- Restart the service after config changes
- Check logs: `journalctl -u log-shipper -f`

**YAML syntax errors:**
- Validate YAML online or with: `yamllint config.yaml`
- Check indentation (use spaces, not tabs)

## Configuration Reference

See `config.example.yaml` for a complete reference with all available options and their default values.
