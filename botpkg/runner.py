"""Async command runner with live output streaming and periodic auto-screenshots."""
import io
import subprocess
import threading
import time

from botpkg import bot, logger
from botpkg.utils import take_and_send_screenshot
from botpkg.rate_limiter import throttle

import telebot

# ─── Output limits ───
MAX_VISIBLE_LINES = 20
MAX_MSG_CHARS = 3500


def run_command_with_screenshots(chat_id, shell_command, timeout, command_name=""):
    """Run a shell command. If timeout > 60s, send periodic screenshots while it runs.

    For short commands (timeout <= 60), runs synchronously via subprocess.run.
    For long commands, uses Popen + a background thread that sends a screenshot
    every 60 seconds until the process finishes.

    Returns (stdout+stderr output string, return_code) or raises on timeout.
    """
    if timeout <= 60:
        # Short command — blocking run, no screenshots
        result = subprocess.run(
            shell_command, shell=True,
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout + result.stderr, result.returncode

    # Long command — non-blocking with periodic screenshots
    proc = subprocess.Popen(
        shell_command, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    stop_event = threading.Event()

    def screenshot_loop():
        """Send a screenshot every 60s while the command is running."""
        while not stop_event.wait(60):
            if proc.poll() is not None:
                return
            try:
                take_and_send_screenshot(chat_id)
            except Exception as e:
                logger.error(f"Auto-screenshot failed: {e}")

    screenshotter = threading.Thread(target=screenshot_loop, daemon=True)
    screenshotter.start()

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        stop_event.set()
        return (stdout or "") + (stderr or ""), proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        stop_event.set()
        raise
    finally:
        stop_event.set()


def _format_elapsed(seconds):
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s}s"


def _truncated_output(lines, max_lines=MAX_VISIBLE_LINES):
    """Return visible lines and a truncation note if needed."""
    total = len(lines)
    if total <= max_lines:
        return "\n".join(lines) if lines else "(No output)", False, total
    visible = lines[-max_lines:]
    text = "\n".join(visible)
    return text, True, total


def run_command_streaming(chat_id, shell_command, timeout, command_name="", reply_to_message_id=None):
    """Run a shell command with live output streaming via Telegram message edits.

    Sends an initial '⏳ Running...' message, then edits it every 10s with
    accumulated stdout. On completion, sends final output with exit code.
    Truncates to MAX_VISIBLE_LINES and offers full output as document.

    Returns (full_output, return_code).
    """
    cmd_label = command_name or shell_command[:40]
    start_time = time.time()

    # Send initial message
    status_msg = bot.send_message(
        chat_id,
        f"⏳ Running `{cmd_label}`...",
        parse_mode="Markdown",
        reply_to_message_id=reply_to_message_id
    )

    proc = subprocess.Popen(
        shell_command, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    lines = []
    stop_event = threading.Event()

    def reader_thread():
        """Read stdout line by line."""
        try:
            for line in proc.stdout:
                lines.append(line.rstrip("\n"))
        except Exception:
            pass

    reader = threading.Thread(target=reader_thread, daemon=True)
    reader.start()

    def updater_thread():
        """Edit the message every 10s with latest output + elapsed time."""
        while not stop_event.wait(10):
            if not lines:
                # Show elapsed even with no output yet
                elapsed = _format_elapsed(time.time() - start_time)
                try:
                    throttle(chat_id)
                    bot.edit_message_text(
                        f"⏳ `{cmd_label}` — running {elapsed}...",
                        chat_id=chat_id,
                        message_id=msg_id,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
                continue
            try:
                visible_text, truncated, total = _truncated_output(lines)
                if len(visible_text) > MAX_MSG_CHARS:
                    visible_text = visible_text[-MAX_MSG_CHARS:]

                elapsed = _format_elapsed(time.time() - start_time)
                trunc_note = f" ({total} lines)" if truncated else f" ({total} lines)"
                progress = f"⏳ `{cmd_label}` — {elapsed}{trunc_note}\n```\n{visible_text}\n```"
                throttle(chat_id)
                bot.edit_message_text(
                    progress,
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="Markdown",
                )
            except Exception:
                pass  # Rate limited or message unchanged

    updater = threading.Thread(target=updater_thread, daemon=True)
    updater.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stop_event.set()
        reader.join(timeout=2)
        bot.edit_message_text(
            f"⏰ Timed out after {timeout}s.\n```\n{''.join(lines[-10:])}\n```",
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="Markdown",
        )
        raise

    stop_event.set()
    reader.join(timeout=2)

    full_output = "\n".join(lines) if lines else "(No output)"
    returncode = proc.returncode

    # Final edit with truncated output
    try:
        visible_text, truncated, total = _truncated_output(lines)
        if len(visible_text) > MAX_MSG_CHARS:
            visible_text = visible_text[-MAX_MSG_CHARS:]

        status_icon = "✅" if returncode == 0 else "❌"
        # Quieter success: hide exit code when 0
        exit_info = "" if returncode == 0 else f" — exit {returncode}"
        trunc_note = f"\n↕️ _{total - MAX_VISIBLE_LINES} more lines (sent as doc)_" if truncated else ""
        bot.edit_message_text(
            f"{status_icon} `{cmd_label}`{exit_info}\n```\n{visible_text}\n```{trunc_note}",
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="Markdown",
        )
    except Exception:
        pass

    # Send full output as document if truncated
    if truncated:
        try:
            doc = io.BytesIO(full_output.encode("utf-8"))
            doc.name = f"{command_name or 'output'}.txt"
            bot.send_document(chat_id, doc, caption=f"📄 Full output ({total} lines)")
        except Exception as e:
            logger.error(f"Failed to send full output document: {e}")

    return full_output, returncode
