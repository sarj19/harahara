"""Clipboard history monitor — background thread that polls pbpaste."""
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

from botpkg import logger

# Clipboard history store
# Owner: this module. Read by meta.py for /snippet.
_clipboard_history = deque(maxlen=50)
_last_clip = None
_monitor_running = False
_stop_event = threading.Event()  # Graceful shutdown signal


def start_clipboard_monitor():
    """Start the background clipboard monitor thread."""
    global _monitor_running
    if _monitor_running:
        return
    _monitor_running = True
    _stop_event.clear()
    thread = threading.Thread(target=_clipboard_loop, daemon=True)
    thread.start()
    logger.info("Clipboard monitor started.")


def stop_clipboard_monitor():
    """Signal the clipboard monitor thread to stop."""
    _stop_event.set()


def _clipboard_loop():
    """Poll pbpaste every 3 seconds and save new entries."""
    global _last_clip
    while not _stop_event.wait(3):
        try:
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=2,
            )
            text = result.stdout.strip()
            if text and text != _last_clip:
                _last_clip = text
                _clipboard_history.append({
                    "text": text[:500],  # Truncate very long clips
                    "time": time.time(),
                    "full_length": len(text),
                })
        except Exception:
            pass


def get_history(n=10):
    """Get last N clipboard entries (most recent first)."""
    entries = list(_clipboard_history)
    entries.reverse()
    return entries[:n]


def search_history(query):
    """Search clipboard history for matching entries."""
    query_lower = query.lower()
    results = []
    for entry in reversed(_clipboard_history):
        if query_lower in entry["text"].lower():
            results.append(entry)
    return results[:10]


def clear_history():
    """Clear clipboard history."""
    global _last_clip
    _clipboard_history.clear()
    _last_clip = None


def get_entry(index):
    """Get a specific entry by 1-based index (most recent = 1)."""
    entries = list(_clipboard_history)
    entries.reverse()
    if 1 <= index <= len(entries):
        return entries[index - 1]
    return None
