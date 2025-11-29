
import os
import time
import logging
import threading
import requests
import socket
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver as Observer  # Reliable in production
from tenacity import retry, stop_after_attempt, wait_fixed

# CONFIGURATION
LOG_FILE = "/app/log/nginx/access.log"
OFFSET_FILE = "/app/log/nginx/log-shipper/latest.offset"
CHUNK_SIZE = 10000
SEND_URL = "http://10.10.23.212:5000/upload"
LOGGING_FILE = "/app/log/nginx/log-shipper/log_shipper_status.log"
DEBOUNCE_DELAY = 1.0  # seconds

# SETUP LOGGING
logging.basicConfig(
    filename=LOGGING_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


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

@retry(stop=stop_after_attempt(600), wait=wait_fixed(6))
def send_chunk(lines, start_offset, end_offset):
    if not lines:
        return
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
    logging.info("Starting log shipper...")
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
