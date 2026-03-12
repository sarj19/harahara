"""Timer & Pomodoro handler — visual countdown with progress bar."""
import threading
import time

from botpkg import bot, logger
from botpkg.utils import parse_duration

# Active timers: chat_id → {"stop": Event, "thread": Thread, ...}
_active_timers = {}


def _progress_bar(remaining, total, width=10):
    """Build a visual progress bar."""
    filled = int(width * (1 - remaining / total)) if total > 0 else width
    bar = "▓" * filled + "░" * (width - filled)
    return bar


def _format_time(seconds):
    """Format seconds as MM:SS or HH:MM:SS."""
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}"
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


def handle_timer(message, chat_id, text):
    """Handle /timer <duration> [label] or /timer stop."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""

    if not args:
        bot.reply_to(
            message,
            "⏱ *Timer Usage:*\n"
            "  `/timer 25m Work sprint`\n"
            "  `/timer 5m Break`\n"
            "  `/timer stop` — cancel\n"
            "  `/pomodoro` — 25m work → 5m break",
            parse_mode="Markdown",
        )
        return

    if args.lower() == "stop":
        if chat_id in _active_timers:
            _active_timers[chat_id]["stop"].set()
            del _active_timers[chat_id]
            bot.reply_to(message, "⏹ Timer stopped.")
        else:
            bot.reply_to(message, "No active timer.")
        return

    # Parse duration + optional label
    parts = args.split(" ", 1)
    duration_secs, duration_label = parse_duration(parts[0])
    if not duration_secs:
        bot.reply_to(message, "❌ Invalid duration. Use e.g. `25m`, `1h`, `90s`.")
        return

    label = parts[1].strip() if len(parts) > 1 else "Timer"

    # Cancel any existing timer
    if chat_id in _active_timers:
        _active_timers[chat_id]["stop"].set()

    _start_countdown(chat_id, duration_secs, label)


def handle_pomodoro(message, chat_id, text):
    """Handle /pomodoro — 25m work → 5m break cycle."""
    if chat_id in _active_timers:
        _active_timers[chat_id]["stop"].set()

    label = "🍅 Pomodoro — Work"
    _start_countdown(chat_id, 25 * 60, label, pomodoro=True)


def _start_countdown(chat_id, total_secs, label, pomodoro=False):
    """Start a countdown timer with live message edits."""
    stop_event = threading.Event()

    # Send initial message
    bar = _progress_bar(total_secs, total_secs)
    msg = bot.send_message(
        chat_id,
        f"⏱ *{label}*\n{bar} {_format_time(total_secs)} remaining",
        parse_mode="Markdown",
    )
    msg_id = msg.message_id

    _active_timers[chat_id] = {"stop": stop_event, "label": label}

    def countdown():
        remaining = total_secs
        update_interval = 30 if total_secs > 120 else 10

        while remaining > 0 and not stop_event.is_set():
            wait = min(update_interval, remaining)
            stop_event.wait(wait)
            if stop_event.is_set():
                return
            remaining -= wait

            bar = _progress_bar(remaining, total_secs)
            warning = " ⚠️" if remaining <= 60 and remaining > 0 else ""
            try:
                bot.edit_message_text(
                    f"⏱ *{label}*\n{bar} {_format_time(remaining)} remaining{warning}",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        if stop_event.is_set():
            return

        # Timer complete!
        try:
            bot.edit_message_text(
                f"🔔 *{label}* — Complete!\n{'▓' * 10} 0:00 ✅",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="Markdown",
            )
            bot.send_message(chat_id, f"🔔 *Timer done!* {label}")
        except Exception:
            pass

        # Play sound
        try:
            import subprocess
            subprocess.run(
                ["say", "-v", "Samantha", f"Timer complete. {label}"],
                timeout=10,
            )
        except Exception:
            pass

        # Clean up
        _active_timers.pop(chat_id, None)

        # Pomodoro: start break after work
        if pomodoro and "Work" in label:
            time.sleep(2)
            bot.send_message(chat_id, "☕ *Break time!* Starting 5-minute break...", parse_mode="Markdown")
            _start_countdown(chat_id, 5 * 60, "🍅 Pomodoro — Break", pomodoro=False)

    t = threading.Thread(target=countdown, daemon=True)
    t.start()
