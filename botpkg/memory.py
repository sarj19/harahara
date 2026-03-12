"""Conversation memory — per-chat sliding window for NLP context.

Owns: _chat_history (dict of chat_id → deque of messages)
"""
import time
from collections import deque

from botpkg import logger

# ─── Configuration ───
try:
    from settings import NLP_CONTEXT_SIZE
except ImportError:
    NLP_CONTEXT_SIZE = 20

# ─── Per-chat conversation memory ───
# Owner: this module. Read by brain.py for prompt building.
_chat_history = {}  # chat_id → deque of {"role": "user"|"assistant", "text": str}

# Load persisted conversations if enabled
try:
    from settings import PERSIST_CONVERSATIONS
    if PERSIST_CONVERSATIONS:
        from botpkg.persistence import load_conversations
        _saved_convos = load_conversations()
        for cid, messages in _saved_convos.items():
            _chat_history[int(cid)] = deque(messages[-NLP_CONTEXT_SIZE:], maxlen=NLP_CONTEXT_SIZE)
except Exception:
    pass


def add_to_history(chat_id, role, text):
    """Add a message to conversation history."""
    if chat_id not in _chat_history:
        _chat_history[chat_id] = deque(maxlen=NLP_CONTEXT_SIZE)
    _chat_history[chat_id].append({
        "role": role,
        "text": text[:500],  # Truncate long messages
        "time": time.time(),
    })
    # Persist if enabled
    try:
        from settings import PERSIST_CONVERSATIONS
        if PERSIST_CONVERSATIONS:
            from botpkg.persistence import save_conversations
            save_conversations(_chat_history)
    except Exception:
        pass


def get_history(chat_id):
    """Get conversation history for a chat."""
    return list(_chat_history.get(chat_id, []))


def clear_history(chat_id):
    """Clear conversation history for a chat."""
    if chat_id in _chat_history:
        _chat_history[chat_id].clear()


def get_memory_stats(chat_id):
    """Get memory stats for /brain command."""
    history = _chat_history.get(chat_id, deque())
    return {
        "messages": len(history),
        "max_size": NLP_CONTEXT_SIZE,
        "oldest": history[0]["time"] if history else None,
    }
