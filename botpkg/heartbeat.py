"""Periodic heartbeat — sends emoji pulse to confirm bot is alive.

Format: 💓BOT_EMOJI (e.g. 💓🐟)
If the previous message was also a heartbeat, edits it to increment a counter
(e.g. 💓🐟 → 💓🐟2 → 💓🐟3) instead of flooding the chat.
"""
import threading
import time
from datetime import datetime

from botpkg import bot, logger, AUTHORIZED_USER_ID
from settings import HEARTBEAT_INTERVAL, BOT_EMOJI, BOT_QUIET_START, BOT_QUIET_END

# Track the last heartbeat message so we can edit it
_last_hb_msg_id = None
_hb_count = 0
_stop_event = threading.Event()  # Graceful shutdown signal


def _is_quiet_hours():
    """Check if current time is within quiet hours."""
    if not BOT_QUIET_START or not BOT_QUIET_END:
        return False
    try:
        now = datetime.now().strftime("%H:%M")
        start, end = BOT_QUIET_START, BOT_QUIET_END
        if start <= end:
            return start <= now < end
        else:  # Wraps midnight, e.g. 23:00 - 07:00
            return now >= start or now < end
    except Exception:
        return False


def start_heartbeat():
    """Start the heartbeat background thread."""
    if HEARTBEAT_INTERVAL <= 0:
        logger.info("Heartbeat disabled (HEARTBEAT_INTERVAL = 0).")
        return
    _stop_event.clear()
    thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    thread.start()
    logger.info(f"Heartbeat thread started (every {HEARTBEAT_INTERVAL} min).")


def stop_heartbeat():
    """Signal the heartbeat thread to stop."""
    _stop_event.set()


def _heartbeat_loop():
    """Send a heartbeat every HEARTBEAT_INTERVAL minutes."""
    global _last_hb_msg_id, _hb_count

    interval_seconds = HEARTBEAT_INTERVAL * 60  # minutes → seconds

    while not _stop_event.wait(interval_seconds):

        # Skip during quiet hours
        if _is_quiet_hours():
            logger.debug("Heartbeat skipped (quiet hours).")
            continue
        try:
            if _last_hb_msg_id:
                # Increment counter and edit the existing message
                _hb_count += 1
                new_text = f"💓{BOT_EMOJI}{_hb_count}"
                try:
                    bot.edit_message_text(
                        new_text,
                        chat_id=AUTHORIZED_USER_ID,
                        message_id=_last_hb_msg_id,
                    )
                    logger.info(f"Edited heartbeat (count: {_hb_count}).")
                    continue
                except Exception:
                    # Edit failed (message too old, deleted, etc.) — send new
                    pass

            # Send a fresh heartbeat message
            pulse = f"💓{BOT_EMOJI}"
            msg = bot.send_message(AUTHORIZED_USER_ID, pulse)
            _last_hb_msg_id = msg.message_id
            _hb_count = 1
            logger.info(f"Sent heartbeat: {pulse}")

        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")


def reset_heartbeat_tracking():
    """Call when user sends a command — next heartbeat will be a new message."""
    global _last_hb_msg_id, _hb_count
    _last_hb_msg_id = None
    _hb_count = 0
