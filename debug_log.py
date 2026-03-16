"""
Simple debug logging that writes directly to a file.
No dependencies, always works.
"""

import os
import sys
import traceback
from datetime import datetime


def _get_log_directory() -> str:
    """Return a user-writable directory for log files."""
    try:
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        elif sys.platform == "darwin":
            base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
        else:
            base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
        log_dir = os.path.join(base, "SceneWrite")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir
    except Exception:
        return os.getcwd()


DEBUG_LOG_FILE = os.path.join(_get_log_directory(), 'debug_crash.log')

def debug_log(message):
    """Write a debug message to the log file."""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()
    except:
        pass  # Silently fail if logging doesn't work

def debug_exception(message, exc=None):
    """Log an exception with full traceback."""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] EXCEPTION: {message}\n")
            if exc:
                f.write(f"Exception: {exc}\n")
            f.write(f"Traceback:\n{traceback.format_exc()}\n")
            f.write("-" * 80 + "\n")
            f.flush()
    except:
        pass
