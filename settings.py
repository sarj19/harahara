"""Settings loaded from environment variables or .env file.

All personal/deployment-specific values live here.
Copy .env.example to .env and fill in your values.
"""
import os
import logging

_settings_logger = logging.getLogger("bot.settings")

# ─── Load .env file if present ───
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value


# ─── Helpers for validated parsing ───

def _parse_int(name, default):
    """Parse an integer env var with validation."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _settings_logger.warning(f"Invalid integer for {name}={raw!r}, using default {default}")
        return default


def _parse_bool(name, default=False):
    """Parse a boolean env var (true/1/yes → True)."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.lower() in ("true", "1", "yes")


def _parse_str(name, default=""):
    """Parse a string env var with a default."""
    return os.environ.get(name, default)


# ─── Required ───
TELEGRAM_BOT_TOKEN = _parse_str("TELEGRAM_BOT_TOKEN")
TELEGRAM_AUTHORIZED_USER_ID = _parse_str("TELEGRAM_AUTHORIZED_USER_ID")

# ─── Paths (all relative to project root by default) ───
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = _parse_str("BOT_LOG_FILE", os.path.join(PROJECT_DIR, "logs", "harahara_bot.log"))
YAML_PATH = _parse_str("BOT_YAML_PATH", os.path.join(PROJECT_DIR, "bot_commands.yaml"))
PERSONAL_YAML_PATH = _parse_str("BOT_PERSONAL_YAML_PATH", os.path.join(PROJECT_DIR, "personal", "bot_commands.yaml"))
UNAUTHORIZED_ID_FILE = _parse_str("BOT_UNAUTHORIZED_ID_FILE", os.path.join(PROJECT_DIR, "logs", "latest_unauthorized_id.txt"))

# ─── Launchd service name (for /restartbot) ───
LAUNCHD_SERVICE = _parse_str("BOT_LAUNCHD_SERVICE", "com.harahara.bot")

# ─── Custom scripts directory ───
SCRIPTS_DIR = _parse_str("BOT_SCRIPTS_DIR", os.path.join(PROJECT_DIR, "personal"))

# ─── Heartbeat interval (in minutes, 0 = disabled) ───
HEARTBEAT_INTERVAL = _parse_int("BOT_HEARTBEAT_INTERVAL", 15)

# ─── Quiet hours (suppress heartbeat, e.g. "23:00" to "07:00") ───
BOT_QUIET_START = _parse_str("BOT_QUIET_START")
BOT_QUIET_END = _parse_str("BOT_QUIET_END")

# ─── NLP mode ───
NLP_ENABLED = _parse_bool("BOT_NLP_ENABLED")
PERSIST_CONVERSATIONS = _parse_bool("BOT_PERSIST_CONVERSATIONS")
NLP_CONTEXT_SIZE = _parse_int("BOT_NLP_CONTEXT_SIZE", 20)

# ─── AI backend ───
BOT_AI_BACKEND = _parse_str("BOT_AI_BACKEND", "auto")  # "auto" | "gemini" | "ollama"
BOT_OLLAMA_MODEL = _parse_str("BOT_OLLAMA_MODEL", "llama3.2:1b")

# ─── Bot identity ───
BOT_NAME = _parse_str("BOT_NAME", "harahara")
BOT_EMOJI = _parse_str("BOT_EMOJI", "🐟")

# ─── Custom messages ───
BOT_GREETING = _parse_str("BOT_GREETING")
BOT_STATUS_TAGLINE = _parse_str("BOT_STATUS_TAGLINE")

# ─── Custom voice for /say ───
BOT_VOICE = _parse_str("BOT_VOICE")

# ─── Daily digest time (24h format, e.g. "21:00") ───
BOT_DIGEST_TIME = _parse_str("BOT_DIGEST_TIME")

# ─── Paths ───
SCHEDULES_PATH = _parse_str("BOT_SCHEDULES_PATH",
    os.path.join(PROJECT_DIR, "personal", "schedules.yaml"))
BOT_KEYBOARD_COMMANDS = _parse_str("BOT_KEYBOARD_COMMANDS",
    "ping,screenshot,volume,status,help")
DOWNLOADS_DIR = _parse_str("BOT_DOWNLOADS_DIR",
    os.path.join(os.path.expanduser("~"), "Downloads", "harahara"))
NOTES_FILE = _parse_str("BOT_NOTES_FILE",
    os.path.join(PROJECT_DIR, "personal", "notes.json"))
NOTES_BACKEND = _parse_str("BOT_NOTES_BACKEND", "local")  # local | apple | google
MACROS_PATH = _parse_str("BOT_MACROS_PATH",
    os.path.join(PROJECT_DIR, "personal", "macros.yaml"))

# ─── Google Calendar & Gmail (OAuth2) ───
GOOGLE_CREDENTIALS_PATH = _parse_str("BOT_GOOGLE_CREDENTIALS",
    os.path.join(PROJECT_DIR, "personal", "google_credentials.json"))
GOOGLE_TOKEN_PATH = _parse_str("BOT_GOOGLE_TOKEN",
    os.path.join(PROJECT_DIR, "personal", "google_token.json"))
