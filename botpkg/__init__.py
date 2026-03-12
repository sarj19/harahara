"""Telegram Bot Package — shared state and initialization."""
import os
import sys
import logging
import time
import warnings

import telebot

# Load settings first (reads .env file)
from settings import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_AUTHORIZED_USER_ID, LOG_FILE,
)

try:
    from urllib3.exceptions import NotOpenSSLWarning
    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except ImportError:
    pass

# ─── Logging ───
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bot")

# ─── Bot instance ───
if not TELEGRAM_BOT_TOKEN:
    logger.critical("TELEGRAM_BOT_TOKEN is not set. Exiting.")
    sys.exit(1)

if not TELEGRAM_AUTHORIZED_USER_ID:
    logger.critical("TELEGRAM_AUTHORIZED_USER_ID is not set. Exiting.")
    sys.exit(1)

AUTHORIZED_USER_ID = int(TELEGRAM_AUTHORIZED_USER_ID)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Mutable shared state: updated by handlers.py on every message,
# read by heartbeat.py to delay heartbeat after recent interaction.
last_interaction_time = time.time()
