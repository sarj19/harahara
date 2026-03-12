"""Constants and mutable state for the bot.

Mutable state ownership:
  screenshot_sessions  — Owner: system.py, Read by: system.py
  pending_confirmations — Owner: __init__.py, Read by: __init__.py
  activity_stats       — Owner: __init__.py, Read by: meta.py, digest.py
  SPECIAL_COMMANDS     — Owner: utils.py (via load_special_from_yaml), Read by: many
  SPECIAL_COMMAND_ALIASES — Owner: utils.py, Read by: utils.py
"""
import time

# ─── Active screenshot sessions (chat_id → threading.Event for cancellation) ───
# Owner: system.py
screenshot_sessions = {}

# ─── Dangerous commands requiring confirmation ───
DANGEROUS_COMMANDS = {"restart", "shutdown", "trash"}
# Owner: handlers/__init__.py
pending_confirmations = {}  # chat_id → {"command": str, "time": float}

# ─── Activity tracking (persistent across restarts) ───
from botpkg.persistence import load_stats

_saved_stats = load_stats()
activity_stats = {
    "commands_run": _saved_stats.get("commands_run", 0) if _saved_stats else 0,
    "screenshots_taken": _saved_stats.get("screenshots_taken", 0) if _saved_stats else 0,
    "commands_by_name": _saved_stats.get("commands_by_name", {}) if _saved_stats else {},
    "start_time": time.time(),  # Always fresh per session
}

# Registry of specially-handled commands (not in bot_commands.yaml).
# Populated from the _special: section of bot_commands.yaml at load time.
SPECIAL_COMMANDS = {}

# Special command aliases — populated from _special: YAML aliases at load time.
SPECIAL_COMMAND_ALIASES = {}


def load_special_from_yaml(special_data):
    """Populate SPECIAL_COMMANDS and SPECIAL_COMMAND_ALIASES from YAML _special: section."""
    SPECIAL_COMMANDS.clear()
    SPECIAL_COMMAND_ALIASES.clear()
    if not special_data or not isinstance(special_data, dict):
        return
    for name, entry in special_data.items():
        if isinstance(entry, dict):
            SPECIAL_COMMANDS[name] = entry.get("desc", "")
            for alias in entry.get("aliases", []):
                SPECIAL_COMMAND_ALIASES[str(alias).strip().lower()] = name

# ─── Category emoji mapping (Feature 8: Themed Responses) ───
CATEGORY_EMOJIS = {
    "System Control": "🖥",
    "Clipboard": "📋",
    "Volume & Audio": "🔊",
    "Notifications": "💬",
    "Network": "🌐",
    "Cleanup": "🧹",
    "Dev & Automation": "🛠",
    "Capture": "📸",
    "Other": "📦",
}

# Modifier key names → AppleScript modifier syntax
MODIFIERS = {
    "cmd": "command down", "command": "command down",
    "alt": "option down", "option": "option down", "opt": "option down",
    "shift": "shift down",
    "ctrl": "control down", "control": "control down",
}

# Special key names → AppleScript key codes
KEY_CODES = {
    "enter": 36, "return": 36,
    "tab": 48,
    "escape": 53, "esc": 53,
    "space": 49,
    "delete": 51, "backspace": 51,
    "forwarddelete": 117,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}
