"""Telegram API rate limiter — prevents 429 errors on rapid message edits.

Owner: this module. Used by runner.py and any code making rapid API calls.
"""
import threading
import time

from botpkg import logger

# Telegram allows ~30 msg/sec per chat, but message edits are more restricted.
# Conservative: at most 1 API call per _MIN_INTERVAL seconds per chat.
_MIN_INTERVAL = 0.5  # 500ms between calls to the same chat
_last_call = {}  # chat_id → timestamp of last API call
_lock = threading.Lock()


def throttle(chat_id):
    """Block until it's safe to make a Telegram API call to this chat.

    Call this before bot.edit_message_text() or similar rapid-fire calls.
    Returns immediately if enough time has passed since the last call.
    """
    with _lock:
        now = time.time()
        last = _last_call.get(chat_id, 0)
        wait = _MIN_INTERVAL - (now - last)
        if wait > 0:
            time.sleep(wait)
        _last_call[chat_id] = time.time()
