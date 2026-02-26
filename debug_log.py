"""
Simple debug logging that writes directly to a file.
No dependencies, always works.
"""

import os
import traceback
from datetime import datetime

DEBUG_LOG_FILE = os.path.join(os.getcwd(), 'debug_crash.log')

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
