"""Scheduled command runner — execute commands on a timer from schedules.yaml."""
import os
import threading
import time

import yaml

from botpkg import bot, logger, AUTHORIZED_USER_ID
from botpkg.config import DANGEROUS_COMMANDS
from botpkg.utils import parse_duration
from botpkg.runner import run_command_with_screenshots
from settings import SCHEDULES_PATH

# ─── Schedule Cache ───
_schedules_cache = {}
_schedules_mtime = 0
_last_run = {}  # schedule_name → timestamp of last execution
_stop_event = threading.Event()  # Graceful shutdown signal


def _load_schedules():
    """Load schedules from YAML with mtime caching."""
    global _schedules_cache, _schedules_mtime
    if not os.path.exists(SCHEDULES_PATH):
        return {}
    try:
        mtime = os.path.getmtime(SCHEDULES_PATH)
        if mtime == _schedules_mtime and _schedules_cache:
            return _schedules_cache
        with open(SCHEDULES_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        _schedules_cache = data
        _schedules_mtime = mtime
        logger.info(f"Loaded {len(data)} schedule(s) from {SCHEDULES_PATH}")
        return _schedules_cache
    except Exception as e:
        logger.error(f"Error loading schedules: {e}")
        return _schedules_cache if _schedules_cache else {}


def start_scheduler():
    """Start the scheduler background thread."""
    if not os.path.exists(SCHEDULES_PATH):
        logger.info(f"No schedules file at {SCHEDULES_PATH} — scheduler disabled.")
        return
    _stop_event.clear()
    thread = threading.Thread(target=_scheduler_loop, daemon=True)
    thread.start()
    logger.info("Scheduler thread started.")


def stop_scheduler():
    """Signal the scheduler thread to stop."""
    _stop_event.set()


def _scheduler_loop():
    """Check every 60s if any scheduled commands are due."""
    while not _stop_event.wait(60):
        try:
            schedules = _load_schedules()
            now = time.time()
            for name, entry in schedules.items():
                if not isinstance(entry, dict) or "cmd" not in entry:
                    continue
                interval_str = entry.get("interval", "1h")
                interval_secs, _ = parse_duration(interval_str)
                if interval_secs is None or interval_secs <= 0:
                    continue

                cmd = entry["cmd"]
                desc = entry.get("desc", name)

                # Safety: skip dangerous commands
                cmd_name = cmd.lstrip("/").split()[0].lower() if cmd.startswith("/") else ""
                if cmd_name in DANGEROUS_COMMANDS:
                    logger.warning(f"Scheduler: skipping dangerous command '{name}' ({cmd})")
                    continue

                last = _last_run.get(name, 0)
                if now - last >= interval_secs:
                    _last_run[name] = now
                    if last == 0:
                        # First run — don't execute on startup, just mark as "run"
                        continue
                    logger.info(f"Scheduler: executing '{name}' ({desc})")
                    _execute_scheduled(name, entry)
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")


def _execute_scheduled(name, entry):
    """Execute a scheduled command and send output to the authorized user."""
    cmd = entry["cmd"]
    timeout = entry.get("timeout", 300)
    desc = entry.get("desc", name)

    try:
        if cmd.startswith("/"):
            # Bot command reference — run the underlying shell command
            from botpkg.utils import load_commands
            bot_cmd_name = cmd.lstrip("/").split()[0].lower()
            commands = load_commands()
            if bot_cmd_name in commands:
                bot_entry = commands[bot_cmd_name]
                shell_cmd = bot_entry["cmd"] if isinstance(bot_entry, dict) else bot_entry
            else:
                bot.send_message(AUTHORIZED_USER_ID, f"⏰ Schedule '{name}': unknown command {cmd}")
                return
        else:
            shell_cmd = cmd

        output, returncode = run_command_with_screenshots(
            AUTHORIZED_USER_ID, shell_cmd, timeout, name
        )
        if not output.strip():
            output = "(No output)"
        if len(output) > 4000:
            output = output[:4000] + "\n...[Output truncated]"

        bot.send_message(
            AUTHORIZED_USER_ID,
            f"⏰ *Scheduled: {desc}*\n```\n{output}\n```\nExit code: {returncode}",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.send_message(AUTHORIZED_USER_ID, f"⏰ Schedule '{name}' failed: {e}")
        logger.error(f"Scheduled command '{name}' error: {e}")
