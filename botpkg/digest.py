"""Daily activity digest — sends a summary of bot usage at a configured time."""
import threading
import time
from datetime import datetime

from botpkg import bot, logger, AUTHORIZED_USER_ID
from botpkg.config import activity_stats
from settings import BOT_DIGEST_TIME, BOT_NAME, BOT_EMOJI

_stop_event = threading.Event()  # Graceful shutdown signal


def start_digest():
    """Start the daily digest background thread."""
    if not BOT_DIGEST_TIME:
        logger.info("Daily digest disabled (BOT_DIGEST_TIME not set).")
        return
    _stop_event.clear()
    thread = threading.Thread(target=_digest_loop, daemon=True)
    thread.start()
    logger.info(f"Digest thread started — will send daily at {BOT_DIGEST_TIME}.")


def stop_digest():
    """Signal the digest thread to stop."""
    _stop_event.set()


def _digest_loop():
    """Check every 60s if it's time to send the daily digest."""
    last_sent_date = None

    while not _stop_event.wait(60):
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")

            # Don't send more than once per day
            if today == last_sent_date:
                continue

            # Parse target time
            try:
                target_hour, target_min = map(int, BOT_DIGEST_TIME.split(":"))
            except (ValueError, AttributeError):
                continue

            # Check if we're within 1 minute of the target time
            if now.hour == target_hour and now.minute == target_min:
                _send_digest()
                last_sent_date = today
        except Exception as e:
            logger.error(f"Digest loop error: {e}")


def _send_digest():
    """Format and send the daily activity digest."""
    try:
        uptime_secs = int(time.time() - activity_stats["start_time"])
        hours = uptime_secs // 3600
        mins = (uptime_secs % 3600) // 60

        commands_run = activity_stats["commands_run"]
        screenshots = activity_stats["screenshots_taken"]

        # Top 5 commands
        top_cmds = sorted(
            activity_stats["commands_by_name"].items(),
            key=lambda x: x[1], reverse=True
        )[:5]

        digest = f"{BOT_EMOJI} *{BOT_NAME} Daily Digest*\n\n"
        digest += f"  📊 Commands run: *{commands_run}*\n"
        digest += f"  📸 Screenshots taken: *{screenshots}*\n"
        digest += f"  ⏱ Bot uptime: *{hours}h {mins}m*\n"

        if top_cmds:
            digest += "\n  🏆 *Top commands:*\n"
            for cmd_name, count in top_cmds:
                digest += f"    `/{cmd_name}` — {count}×\n"

        if commands_run == 0 and screenshots == 0:
            digest += "\n  💤 _Quiet day — no commands used._"

        bot.send_message(AUTHORIZED_USER_ID, digest, parse_mode="Markdown")
        logger.info("Sent daily digest.")

        # Reset daily counters (keep start_time for cumulative uptime)
        activity_stats["commands_run"] = 0
        activity_stats["screenshots_taken"] = 0
        activity_stats["commands_by_name"] = {}

    except Exception as e:
        logger.error(f"Failed to send digest: {e}")
