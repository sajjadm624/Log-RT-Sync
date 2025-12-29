# Quick Start Guide - Configuration System

## 🚀 Getting Started in 3 Steps

### Step 1: Copy the Configuration Template
```bash
cp config.example.yaml config.yaml
```

### Step 2: Edit Your Settings
```bash
nano config.yaml  # or your favorite editor
```

**Essential settings to configure:**
- `log_receiver.base_log_dir` - Where to store logs
- `log_sender.destination` - SFTP server details and credentials
- `log_monitoring.email` - Email settings for alerts

### Step 3: Run with Configuration
```bash
# On sender servers (where logs are generated)
python3 Log-shipper.py -c config.yaml

# On receiver server (middle server)
python3 Log-reciever.py -c config.yaml

# On receiver server (transfer to SFTP)
./Log-sender-to-client-end.sh -c config.yaml

# Optional: Monitoring and housekeeping
python3 Log-Monitoring-scripts-with-mail.py -c config.yaml
./Houskeep-log.sh -c config.yaml
```

## 📋 Common Configuration Tasks

### Change Log Batching Timeframe

**Default: 20-minute windows**
```yaml
time_windows:
  - {start: 0, end: 19, label: "00-19"}
  - {start: 20, end: 39, label: "20-39"}
  - {start: 40, end: 59, label: "40-59"}
```

**Change to 10-minute windows:**
```yaml
time_windows:
  - {start: 0, end: 9, label: "00-09"}
  - {start: 10, end: 19, label: "10-19"}
  - {start: 20, end: 29, label: "20-29"}
  - {start: 30, end: 39, label: "30-39"}
  - {start: 40, end: 49, label: "40-49"}
  - {start: 50, end: 59, label: "50-59"}
```

### Update SFTP Credentials
```yaml
log_sender:
  destination:
    user: "your_username"
    host: "sftp.example.com"
    port: 22
    directory: "/path/to/destination"
    password: "your_secure_password"
```

### Configure Email Alerts
```yaml
log_monitoring:
  email:
    smtp_host: "smtp.example.com"
    smtp_port: 25
    from_address: "alerts@example.com"
    recipients:
      - "admin@example.com"
      - "team@example.com"
```

### Adjust Log Retention
```yaml
housekeeping:
  compress_after_hours: 3    # Compress logs older than 3 hours
  delete_after_hours: 4      # Delete logs older than 4 hours
```

### Port Grouping for Multiple Servers (Production Setup)

For handling many servers with real-time syncing, use **port grouping** with Gunicorn workers:

**Example: 20 servers grouped across 5 ports**
- Servers 1-4 → Port 5000 (4 workers)
- Servers 5-8 → Port 5001 (4 workers)
- Servers 9-12 → Port 5002 (4 workers)
- Servers 13-16 → Port 5003 (4 workers)
- Servers 17-20 → Port 5004 (4 workers)

**Result**: 20 concurrent workers = true parallel processing

```bash
# Start each port with Gunicorn (4 workers each)
gunicorn --workers 4 --bind 0.0.0.0:5000 Log-reciever:app &
gunicorn --workers 4 --bind 0.0.0.0:5001 Log-reciever:app &
gunicorn --workers 4 --bind 0.0.0.0:5002 Log-reciever:app &
gunicorn --workers 4 --bind 0.0.0.0:5003 Log-reciever:app &
gunicorn --workers 4 --bind 0.0.0.0:5004 Log-reciever:app &
```

See [CONFIG.md](CONFIG.md) section "Port Grouping for Server Groups" for detailed setup.

## 🔧 Systemd Service Setup

### Create Service File
```bash
sudo nano /etc/systemd/system/log-shipper.service
```

### Service Configuration
```ini
[Unit]
Description=Log Shipper
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/log-rt-sync
ExecStart=/usr/bin/python3 /opt/log-rt-sync/Log-shipper.py -c /etc/log-rt-sync/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Enable and Start
```bash
sudo systemctl daemon-reload
sudo systemctl enable log-shipper
sudo systemctl start log-shipper
sudo systemctl status log-shipper
```

## 📝 Configuration File Locations

Scripts search for config files in this order:
1. Path specified with `-c` parameter
2. `/etc/log-rt-sync/config.yaml`
3. `/etc/log-rt-sync.yaml`
4. `./config.yaml` (current directory)
5. `~/.log-rt-sync.yaml` (user home)

**Recommended:** `/etc/log-rt-sync/config.yaml`

## 🧪 Testing Your Configuration

Run the test suite:
```bash
./test-config.sh
```

Expected output: All 11 tests passing ✓

Test individual component:
```bash
# Test config loading
python3 config_loader.py -c config.yaml

# Test specific section
python3 config_loader.py -c config.yaml -s log_shipper
```

## 🔍 Troubleshooting

### Configuration not loading?
```bash
# Check file exists and is readable
ls -la config.yaml

# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

### Service not starting?
```bash
# Check service logs
sudo journalctl -u log-shipper -n 50

# Test manually
python3 Log-shipper.py -c config.yaml
```

### Need to verify settings?
```bash
# View entire config
python3 config_loader.py -c config.yaml

# View specific section
python3 config_loader.py -c config.yaml -s log_receiver
```

## 📚 More Information

- **Comprehensive Guide:** See [CONFIG.md](CONFIG.md)
- **Full Documentation:** See [README.md](README.md)
- **Implementation Details:** See [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

## 💡 Tips

1. **Always backup** your config before changes
2. **Use version control** for config files (without passwords)
3. **Test in dev** before deploying to production
4. **Set proper permissions**: `chmod 600 config.yaml`
5. **Document changes** in config file comments

## ⚠️ Security

- Never commit `config.yaml` with real passwords to git
- Store production configs in `/etc/log-rt-sync/`
- Use restrictive permissions: `chmod 600`
- Rotate credentials regularly

---

**Need Help?** Check [CONFIG.md](CONFIG.md) for detailed documentation or open an issue on GitHub.
