
import os
import sys
import time
import logging
import threading
import requests
import socket
import argparse
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver as Observer  # Reliable in production
from tenacity import retry, stop_after_attempt, wait_fixed

# Import configuration loader
try:
    from config_loader import load_config
except ImportError:
    print("Error: config_loader module not found. Please ensure config_loader.py is in the same directory.")
    sys.exit(1)

# Global configuration - will be loaded from config file
CONFIG = None
LOG_FILE = None
OFFSET_FILE = None
CHUNK_SIZE = None
SEND_URL = None
LOGGING_FILE = None
DEBOUNCE_DELAY = None
RETRY_ATTEMPTS = None
RETRY_WAIT_SECONDS = None



# ========== UTILITIES ==========

def get_file_id(path):
    try:
        st = os.stat(path)
        return (st.st_dev, st.st_ino)
    except FileNotFoundError:
        logging.error(f"File not found: {path}")
        return None

def get_last_offset():
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE, "r") as f:
            offset = int(f.read().strip())
            logging.info(f"Loaded last offset: {offset}")
            return offset
    logging.info("Offset file not found. Starting from offset 0.")
    return 0

def save_offset(offset):
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))
    logging.info(f"Saved new offset: {offset}")

def should_skip_line(line):
    return (
        "/health.php" in line and
        "nginx/" in line and
        "health check" in line
    )

def send_chunk(lines, start_offset, end_offset):
    """Send log chunk with retry logic"""
    if not lines:
        return
    
    # Create retry decorator dynamically based on config
    @retry(stop=stop_after_attempt(RETRY_ATTEMPTS), wait=wait_fixed(RETRY_WAIT_SECONDS))
    def _send():
        data = "\n".join(lines)
        host_ip = socket.gethostbyname(socket.gethostname())

        try:
            logging.info(f"Sending {len(lines)} lines (offset {start_offset}-{end_offset}) to server.")
            response = requests.post(SEND_URL, json={"log": data, "host": host_ip})
            response.raise_for_status()
            logging.info(f"Successfully sent {len(lines)} lines (offset {start_offset}-{end_offset}).")
        except Exception as e:
            logging.error(f"Failed to send lines (offset {start_offset}-{end_offset}): {e}")
            logging.error(f"Last line (offset {end_offset}): {lines[-1]}")
            raise
    
    _send()


# ========== HANDLER ==========

class LogHandler(FileSystemEventHandler):
    def __init__(self):
        self.offset = get_last_offset()
        self.last_file_id = get_file_id(LOG_FILE)
        self._lock = threading.Lock()
        self._timer = None

    def on_modified(self, event):
        if os.path.realpath(event.src_path) != os.path.realpath(LOG_FILE):
            return
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_DELAY, self._process_logs)
            self._timer.start()

    def _process_logs(self):
        with self._lock:
            current_file_id = get_file_id(LOG_FILE)
            if current_file_id != self.last_file_id:
                logging.info("Detected file rotation. Resetting offset.")
                self.offset = 0
                save_offset(self.offset)
                self.last_file_id = current_file_id

            lines = []
            with open(LOG_FILE, "r") as f:
                f.seek(self.offset)
                start_offset = self.offset

                for _ in range(CHUNK_SIZE):
                    line = f.readline()
                    if not line:
                        break
                    if should_skip_line(line):
                        continue
                    lines.append(line)

                end_offset = f.tell()

            if lines:
                try:
                    send_chunk(lines, start_offset, end_offset)
                    self.offset = end_offset
                    save_offset(self.offset)
                except Exception:
                    logging.error("Error during sending chunk.")


# ========== MAIN ==========

def drain_backlog(handler: LogHandler):
    logging.info("Draining backlog from log file...")

    with open(LOG_FILE, "r") as f:
        f.seek(handler.offset)
        start_offset = handler.offset
        lines = []

        while True:
            line = f.readline()
            if not line:
                break
            if should_skip_line(line):
                continue
            lines.append(line)

            if len(lines) >= CHUNK_SIZE:
                end_offset = f.tell()
                send_chunk(lines, start_offset, end_offset)
                handler.offset = end_offset
                save_offset(end_offset)
                lines = []
                start_offset = end_offset

        if lines:
            end_offset = f.tell()
            send_chunk(lines, start_offset, end_offset)
            handler.offset = end_offset
            save_offset(end_offset)

    logging.info("Finished draining backlog.")


def main():
    """Main entry point with configuration support"""
    global CONFIG, LOG_FILE, OFFSET_FILE, CHUNK_SIZE, SEND_URL, LOGGING_FILE, DEBOUNCE_DELAY
    global RETRY_ATTEMPTS, RETRY_WAIT_SECONDS
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Log Shipper - Ship nginx logs to receiver")
    parser.add_argument("-c", "--config", help="Path to configuration file")
    args = parser.parse_args()
    
    # Load configuration
    CONFIG = load_config(args.config)
    
    # Get configuration values
    shipper_config = CONFIG.get_section('log_shipper')
    LOG_FILE = shipper_config.get('log_file', '/app/log/nginx/access.log')
    OFFSET_FILE = shipper_config.get('offset_file', '/app/log/nginx/log-shipper/latest.offset')
    CHUNK_SIZE = shipper_config.get('chunk_size', 10000)
    SEND_URL = shipper_config.get('receiver_url', 'http://10.10.23.212:5000/upload')
    LOGGING_FILE = shipper_config.get('logging_file', '/app/log/nginx/log-shipper/log_shipper_status.log')
    DEBOUNCE_DELAY = shipper_config.get('debounce_delay', 1.0)
    RETRY_ATTEMPTS = shipper_config.get('retry_attempts', 600)
    RETRY_WAIT_SECONDS = shipper_config.get('retry_wait_seconds', 6)
    
    # Ensure directories exist
    os.makedirs(os.path.dirname(OFFSET_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(LOGGING_FILE), exist_ok=True)
    
    # Re-configure logging with the loaded config
    logging.basicConfig(
        filename=LOGGING_FILE,
        level=logging.DEBUG if CONFIG.get('global.debug', False) else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        force=True,  # Force reconfiguration
    )
    
    logging.info(f"Starting log shipper with config file...")
    logging.info(f"  Log file: {LOG_FILE}")
    logging.info(f"  Receiver URL: {SEND_URL}")
    logging.info(f"  Chunk size: {CHUNK_SIZE}")
    
    handler = LogHandler()
    drain_backlog(handler)

    observer = Observer()
    observer.schedule(handler, path=os.path.dirname(LOG_FILE), recursive=False)
    observer.start()

    logging.info(f"Watching {LOG_FILE} for changes.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("Log shipper interrupted by user.")
    observer.join()
    logging.info("Shutting down log shipper.")


if __name__ == "__main__":
    main()
