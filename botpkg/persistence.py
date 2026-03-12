"""Persistence layer — save/load command history, activity stats, and NLP conversations.

Data files (all in personal/):
  history.json     — last 100 commands (cmd, time, exit_code)
  stats.json       — cumulative activity stats (commands_run, screenshots_taken, etc.)
  conversations.json — NLP chat history (optional, controlled by BOT_PERSIST_CONVERSATIONS)
"""
import json
import os
import time

from settings import PROJECT_DIR

_HISTORY_FILE = os.path.join(PROJECT_DIR, "personal", "history.json")
_STATS_FILE = os.path.join(PROJECT_DIR, "personal", "stats.json")
_CONVERSATIONS_FILE = os.path.join(PROJECT_DIR, "personal", "conversations.json")

# Debounce: save at most once every N seconds to avoid I/O thrashing
_SAVE_INTERVAL = 30
_last_save_time = {"history": 0, "stats": 0, "conversations": 0}


def _ensure_dir():
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)


# ═══════════════════════════════════════════════════════════════════
# Command history
# ═══════════════════════════════════════════════════════════════════

def load_history():
    """Load command history from disk. Returns a list of dicts."""
    try:
        if os.path.exists(_HISTORY_FILE):
            with open(_HISTORY_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_history(history_deque):
    """Save command history to disk (debounced)."""
    now = time.time()
    if now - _last_save_time["history"] < _SAVE_INTERVAL:
        return
    _last_save_time["history"] = now
    try:
        _ensure_dir()
        with open(_HISTORY_FILE, "w") as f:
            json.dump(list(history_deque), f)
    except Exception:
        pass


def save_history_now(history_deque):
    """Force-save history (used at shutdown)."""
    try:
        _ensure_dir()
        with open(_HISTORY_FILE, "w") as f:
            json.dump(list(history_deque), f)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# Activity stats
# ═══════════════════════════════════════════════════════════════════

def load_stats():
    """Load cumulative activity stats from disk. Returns a dict."""
    try:
        if os.path.exists(_STATS_FILE):
            with open(_STATS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def save_stats(stats_dict):
    """Save activity stats to disk (debounced)."""
    now = time.time()
    if now - _last_save_time["stats"] < _SAVE_INTERVAL:
        return
    _last_save_time["stats"] = now
    try:
        _ensure_dir()
        # Don't save start_time — it's session-specific
        data = {k: v for k, v in stats_dict.items() if k != "start_time"}
        with open(_STATS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def save_stats_now(stats_dict):
    """Force-save stats (used at shutdown)."""
    try:
        _ensure_dir()
        data = {k: v for k, v in stats_dict.items() if k != "start_time"}
        with open(_STATS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# NLP conversation history (optional)
# ═══════════════════════════════════════════════════════════════════

def load_conversations():
    """Load NLP conversation history. Returns dict of chat_id → list of messages."""
    try:
        if os.path.exists(_CONVERSATIONS_FILE):
            with open(_CONVERSATIONS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_conversations(chat_history_dict):
    """Save NLP conversations to disk (debounced)."""
    now = time.time()
    if now - _last_save_time["conversations"] < _SAVE_INTERVAL:
        return
    _last_save_time["conversations"] = now
    try:
        _ensure_dir()
        # Convert deques to lists, stringify chat_id keys
        data = {}
        for chat_id, messages in chat_history_dict.items():
            data[str(chat_id)] = list(messages)
        with open(_CONVERSATIONS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def save_conversations_now(chat_history_dict):
    """Force-save conversations (used at shutdown)."""
    try:
        _ensure_dir()
        data = {}
        for chat_id, messages in chat_history_dict.items():
            data[str(chat_id)] = list(messages)
        with open(_CONVERSATIONS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass
