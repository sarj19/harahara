#!/usr/bin/env python3
"""Telegram Bot — entry point.

All logic lives in the botpkg/ package.
This file is the launch target for the launchd plist.
"""
import os
import signal
import sys
import time
from datetime import datetime

import telebot

from botpkg import bot, logger, AUTHORIZED_USER_ID
from botpkg.config import SPECIAL_COMMANDS
from botpkg.utils import load_commands
from settings import BOT_NAME, BOT_EMOJI, BOT_GREETING, PROJECT_DIR

# Import handlers to register the @bot.message_handler decorator
import botpkg.handlers  # noqa: F401
import botpkg.heartbeat
import botpkg.scheduler
import botpkg.digest
import botpkg.clipboard


def _time_greeting():
    """Return a time-of-day greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning ☀️"
    elif hour < 17:
        return "Good afternoon 🌤"
    elif hour < 21:
        return "Good evening 🌅"
    else:
        return "Good night 🌙"


def signal_handler(signum, frame):
    logger.info("Received termination signal. Stopping background services...")
    # Stop background threads gracefully
    try:
        from botpkg.heartbeat import stop_heartbeat
        from botpkg.scheduler import stop_scheduler
        from botpkg.digest import stop_digest
        from botpkg.clipboard import stop_clipboard_monitor
        stop_heartbeat()
        stop_scheduler()
        stop_digest()
        stop_clipboard_monitor()
    except Exception as e:
        logger.error(f"Failed to stop background services: {e}")
    # Force-save persistent data before shutdown
    try:
        from botpkg.persistence import save_history_now, save_stats_now, save_conversations_now
        from botpkg.handlers.meta import _command_history
        from botpkg.config import activity_stats
        save_history_now(_command_history)
        save_stats_now(activity_stats)
        from settings import PERSIST_CONVERSATIONS
        if PERSIST_CONVERSATIONS:
            from botpkg.brain import _chat_history
            save_conversations_now(_chat_history)
    except Exception as e:
        logger.error(f"Failed to save persistent data: {e}")
    try:
        bot.send_message(AUTHORIZED_USER_ID, f"{BOT_EMOJI} Goodbye!")
    except Exception as e:
        logger.error(f"Failed to send shutdown message: {e}")
    logger.info("Shutting down bot.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Bot is starting up...")
    botpkg.heartbeat.start_heartbeat()
    botpkg.scheduler.start_scheduler()
    botpkg.digest.start_digest()
    botpkg.clipboard.start_clipboard_monitor()

    greeting = BOT_GREETING if BOT_GREETING else _time_greeting()
    try:
        # Register command suggestions with Telegram (auto-complete when typing /)
        cmds = [telebot.types.BotCommand(c, d[:256]) for c, d in SPECIAL_COMMANDS.items()]
        # Add YAML commands (shared + personal)
        yaml_cmds = load_commands()
        for c, entry in yaml_cmds.items():
            desc = entry.get("desc", c) if isinstance(entry, dict) else c
            cmds.append(telebot.types.BotCommand(c, desc[:256]))
        bot.set_my_commands(cmds)
        logger.info(f"Registered {len(cmds)} command suggestions with Telegram.")
    except Exception as e:
        logger.warning(f"Failed to register commands: {e}")

    # Set the bot's display name in Telegram — only on first run
    _name_flag = os.path.join(PROJECT_DIR, "personal", ".bot_name_set")
    if not os.path.exists(_name_flag):
        try:
            bot.set_my_name(f"{BOT_EMOJI} {BOT_NAME}")
            os.makedirs(os.path.dirname(_name_flag), exist_ok=True)
            with open(_name_flag, "w") as f:
                f.write(f"{BOT_EMOJI} {BOT_NAME}\n")
            logger.info(f"Set bot display name to '{BOT_EMOJI} {BOT_NAME}'.")
        except Exception as e:
            logger.warning(f"Failed to set bot name: {e}")

    try:
        bot.send_message(AUTHORIZED_USER_ID, f"{BOT_EMOJI} {greeting}")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")

    logger.info("Bot is listening for commands...")
    backoff = 5
    while True:
        try:
            bot.polling(non_stop=True)
        except Exception as e:
            logger.error(f"Bot polling crashed: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        else:
            backoff = 5  # Reset on clean exit
