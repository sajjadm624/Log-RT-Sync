#!/bin/bash
# Test script for Log-RT-Sync configuration system
# Validates that all components can load and use configuration files

set -e  # Exit on error

echo "======================================"
echo "Log-RT-Sync Configuration Test Suite"
echo "======================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

info() {
    echo -e "${YELLOW}→${NC} $1"
}

# Test 1: Configuration files exist
echo "Test 1: Configuration files"
info "Checking for config files..."
[ -f "config.example.yaml" ] && success "config.example.yaml exists" || error "config.example.yaml not found"
[ -f "config.test.yaml" ] && success "config.test.yaml exists" || error "config.test.yaml not found"
[ -f "CONFIG.md" ] && success "CONFIG.md exists" || error "CONFIG.md not found"
echo ""

# Test 2: Python dependencies
echo "Test 2: Python dependencies"
info "Checking Python modules..."
python3 -c "import yaml" && success "PyYAML installed" || error "PyYAML not installed"
python3 -c "import flask" && success "Flask installed" || error "Flask not installed"
python3 -c "import requests" && success "Requests installed" || error "Requests not installed"
python3 -c "import watchdog" && success "Watchdog installed" || error "Watchdog not installed"
python3 -c "import tenacity" && success "Tenacity installed" || error "Tenacity not installed"
echo ""

# Test 3: Config loader module
echo "Test 3: Configuration loader"
info "Testing config_loader.py..."
python3 -m py_compile config_loader.py && success "config_loader.py syntax valid" || error "config_loader.py has syntax errors"
python3 config_loader.py -c config.test.yaml > /dev/null && success "Config loads successfully" || error "Failed to load config"
echo ""

# Test 4: Config helper for bash
echo "Test 4: Configuration helper for bash"
info "Testing config_helper.py..."
python3 -m py_compile config_helper.py && success "config_helper.py syntax valid" || error "config_helper.py has syntax errors"
python3 config_helper.py -c config.test.yaml --export > /dev/null && success "Config exports for bash" || error "Failed to export config"
echo ""

# Test 5: Log shipper config
echo "Test 5: Log shipper configuration"
info "Testing Log-shipper.py config loading..."
python3 -c "
import sys
sys.path.insert(0, '.')
from config_loader import load_config
config = load_config('config.test.yaml')
shipper = config.get_section('log_shipper')
assert shipper['chunk_size'] == 100, 'chunk_size mismatch'
assert shipper['receiver_url'] == 'http://localhost:5555/upload', 'receiver_url mismatch'
print('OK')
" && success "Log-shipper config valid" || error "Log-shipper config failed"
echo ""

# Test 6: Log receiver config
echo "Test 6: Log receiver configuration"
info "Testing Log-reciever.py config loading..."
python3 -c "
import sys
sys.path.insert(0, '.')
from config_loader import load_config
config = load_config('config.test.yaml')
receiver = config.get_section('log_receiver')
assert receiver['port'] == 5555, 'port mismatch'
assert len(receiver['time_windows']) == 3, 'time_windows count mismatch'
print('OK')
" && success "Log-reciever config valid" || error "Log-reciever config failed"
echo ""

# Test 7: Log monitoring config
echo "Test 7: Log monitoring configuration"
info "Testing Log-Monitoring-scripts-with-mail.py config loading..."
python3 -c "
import sys
sys.path.insert(0, '.')
from config_loader import load_config
config = load_config('config.test.yaml')
monitoring = config.get_section('log_monitoring')
email = monitoring.get('email', {})
assert monitoring['threshold_minutes'] == 2, 'threshold_minutes mismatch'
assert email['smtp_host'] == 'localhost', 'smtp_host mismatch'
print('OK')
" && success "Log-Monitoring config valid" || error "Log-Monitoring config failed"
echo ""

# Test 8: Bash scripts config
echo "Test 8: Bash scripts configuration"
info "Testing bash script config loading..."
bash -c '
eval "$(python3 config_helper.py -c config.test.yaml --export 2>/dev/null)"
[ "$HOUSEKEEP_BASE_DIR" = "/tmp/test-receiver" ] || exit 1
[ "$HOUSEKEEP_COMPRESS_HOURS" = "1" ] || exit 1
[ "$LOG_SENDER_DEST_HOST" = "localhost" ] || exit 1
echo "OK"
' && success "Bash config loading works" || error "Bash config loading failed"
echo ""

# Test 9: Bash script syntax
echo "Test 9: Bash scripts syntax"
info "Checking bash scripts..."
bash -n Log-sender-to-client-end.sh && success "Log-sender-to-client-end.sh syntax valid" || error "Log-sender-to-client-end.sh has syntax errors"
bash -n Houskeep-log.sh && success "Houskeep-log.sh syntax valid" || error "Houskeep-log.sh has syntax errors"
echo ""

# Test 10: Python scripts syntax
echo "Test 10: Python scripts syntax"
info "Checking Python scripts..."
python3 -m py_compile Log-shipper.py && success "Log-shipper.py syntax valid" || error "Log-shipper.py has syntax errors"
python3 -m py_compile Log-reciever.py && success "Log-reciever.py syntax valid" || error "Log-reciever.py has syntax errors"
python3 -m py_compile Log-Monitoring-scripts-with-mail.py && success "Log-Monitoring-scripts-with-mail.py syntax valid" || error "Log-Monitoring-scripts-with-mail.py has syntax errors"
echo ""

# Test 11: Default config (no config file)
echo "Test 11: Default configuration fallback"
info "Testing default config when no file exists..."
python3 -c "
import sys
sys.path.insert(0, '.')
from config_loader import load_config
config = load_config('/nonexistent/config.yaml')
shipper = config.get_section('log_shipper')
assert 'log_file' in shipper, 'Default config missing log_file'
assert 'chunk_size' in shipper, 'Default config missing chunk_size'
print('OK')
" 2>/dev/null && success "Default config works" || error "Default config failed"
echo ""

# Summary
echo "======================================"
echo -e "${GREEN}All tests passed!${NC}"
echo "======================================"
echo ""
echo "Configuration system is working correctly."
echo "You can now use config files with all components:"
echo "  python3 Log-shipper.py -c config.yaml"
echo "  python3 Log-reciever.py -c config.yaml"
echo "  python3 Log-Monitoring-scripts-with-mail.py -c config.yaml"
echo "  ./Log-sender-to-client-end.sh -c config.yaml"
echo "  ./Houskeep-log.sh -c config.yaml"
echo ""
