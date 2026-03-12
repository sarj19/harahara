"""Tests for NLP Brain module: fuzzy matching, conversation memory, command parsing,
system prompt building, and brain handler dispatch."""
import os
import unittest
from unittest.mock import patch, MagicMock
from collections import deque

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN-FOR-TESTING")
os.environ.setdefault("TELEGRAM_AUTHORIZED_USER_ID", "12345")


# ═══════════════════════════════════════════════════════════════════
# Conversation Memory
# ═══════════════════════════════════════════════════════════════════

class TestConversationMemory(unittest.TestCase):
    """Test per-chat conversation memory."""

    def setUp(self):
        from botpkg.brain import _chat_history
        _chat_history.clear()

    def test_add_and_get_history(self):
        from botpkg.brain import add_to_history, get_history
        add_to_history(99, "user", "hello")
        add_to_history(99, "assistant", "hi there")
        history = get_history(99)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["text"], "hello")
        self.assertEqual(history[1]["role"], "assistant")

    def test_per_chat_isolation(self):
        from botpkg.brain import add_to_history, get_history
        add_to_history(1, "user", "chat 1")
        add_to_history(2, "user", "chat 2")
        self.assertEqual(len(get_history(1)), 1)
        self.assertEqual(len(get_history(2)), 1)
        self.assertEqual(get_history(1)[0]["text"], "chat 1")

    def test_memory_size_limit(self):
        from botpkg.brain import add_to_history, get_history, NLP_CONTEXT_SIZE
        for i in range(NLP_CONTEXT_SIZE + 10):
            add_to_history(99, "user", f"message {i}")
        history = get_history(99)
        self.assertEqual(len(history), NLP_CONTEXT_SIZE)
        # Oldest messages should have been dropped
        self.assertIn(str(NLP_CONTEXT_SIZE + 9), history[-1]["text"])

    def test_clear_history(self):
        from botpkg.brain import add_to_history, clear_history, get_history
        add_to_history(99, "user", "hello")
        add_to_history(99, "assistant", "hi")
        clear_history(99)
        self.assertEqual(len(get_history(99)), 0)

    def test_memory_stats(self):
        from botpkg.brain import add_to_history, get_memory_stats
        add_to_history(99, "user", "hello")
        add_to_history(99, "assistant", "hi")
        stats = get_memory_stats(99)
        self.assertEqual(stats["messages"], 2)
        self.assertIsNotNone(stats["oldest"])

    def test_memory_stats_empty(self):
        from botpkg.brain import get_memory_stats
        stats = get_memory_stats(999)
        self.assertEqual(stats["messages"], 0)
        self.assertIsNone(stats["oldest"])

    def test_long_message_truncated(self):
        from botpkg.brain import add_to_history, get_history
        long_msg = "x" * 1000
        add_to_history(99, "user", long_msg)
        self.assertEqual(len(get_history(99)[0]["text"]), 500)


# ═══════════════════════════════════════════════════════════════════
# Fuzzy Matching
# ═══════════════════════════════════════════════════════════════════

class TestFuzzyMatch(unittest.TestCase):
    """Test fuzzy command matching."""

    def test_exact_match(self):
        from botpkg.brain import _fuzzy_match
        matches = _fuzzy_match("screenshot")
        self.assertTrue(len(matches) > 0)
        self.assertEqual(matches[0][0], "screenshot")
        self.assertGreaterEqual(matches[0][1], 0.8)

    def test_close_match(self):
        from botpkg.brain import _fuzzy_match
        matches = _fuzzy_match("screensho")
        self.assertTrue(len(matches) > 0)
        # Should suggest screenshot
        names = [m[0] for m in matches]
        self.assertIn("screenshot", names)

    def test_no_match(self):
        from botpkg.brain import _fuzzy_match
        matches = _fuzzy_match("xyzzy_nonexistent_foobar")
        # Should return empty or very low scores
        high_matches = [m for m in matches if m[1] >= 0.5]
        self.assertEqual(len(high_matches), 0)

    def test_keyword_match(self):
        from botpkg.brain import _fuzzy_match
        matches = _fuzzy_match("volume")
        self.assertTrue(len(matches) > 0)
        names = [m[0] for m in matches]
        # Should match volume-related commands
        self.assertTrue(any("volume" in n or "vol" in n for n in names))

    def test_returns_max_3(self):
        from botpkg.brain import _fuzzy_match
        matches = _fuzzy_match("help")
        self.assertLessEqual(len(matches), 3)


# ═══════════════════════════════════════════════════════════════════
# Command Parsing
# ═══════════════════════════════════════════════════════════════════

class TestCommandParsing(unittest.TestCase):
    """Test AI response parsing for /commands."""

    def test_single_command(self):
        from botpkg.brain import _parse_commands
        cmds, text = _parse_commands("/screenshot")
        self.assertEqual(cmds, ["/screenshot"])
        self.assertEqual(text, "")

    def test_multiple_commands(self):
        from botpkg.brain import _parse_commands
        cmds, text = _parse_commands("/battery\n/screenshot\n/notify low battery")
        self.assertEqual(len(cmds), 3)
        self.assertEqual(cmds[0], "/battery")
        self.assertEqual(cmds[2], "/notify low battery")

    def test_mixed_text_and_commands(self):
        from botpkg.brain import _parse_commands
        response = "Here's what I'll do:\n/battery\nThen check the screen\n/screenshot"
        cmds, text = _parse_commands(response)
        self.assertEqual(len(cmds), 2)
        self.assertIn("Here's what I'll do:", text)

    def test_no_commands(self):
        from botpkg.brain import _parse_commands
        cmds, text = _parse_commands("I don't know how to do that.")
        self.assertEqual(cmds, [])
        self.assertEqual(text, "I don't know how to do that.")

    def test_empty_response(self):
        from botpkg.brain import _parse_commands
        cmds, text = _parse_commands("")
        self.assertEqual(cmds, [])
        self.assertEqual(text, "")

    def test_none_response(self):
        from botpkg.brain import _parse_commands
        cmds, text = _parse_commands(None)
        self.assertEqual(cmds, [])
        self.assertEqual(text, "")

    def test_command_with_args(self):
        from botpkg.brain import _parse_commands
        cmds, text = _parse_commands("/say hello world")
        self.assertEqual(cmds, ["/say hello world"])


# ═══════════════════════════════════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════════════════════════════════

class TestSystemPrompt(unittest.TestCase):
    """Test system prompt builder."""

    def test_prompt_includes_commands(self):
        from botpkg.brain import _build_system_prompt
        prompt = _build_system_prompt(99)
        self.assertIn("/help", prompt)
        self.assertIn("/screenshot", prompt)
        self.assertIn("AVAILABLE COMMANDS", prompt)
        self.assertIn("INSTRUCTIONS", prompt)

    def test_prompt_includes_history(self):
        from botpkg.brain import _build_system_prompt, add_to_history, _chat_history
        _chat_history.clear()
        add_to_history(99, "user", "what is the battery")
        add_to_history(99, "assistant", "checking...")
        prompt = _build_system_prompt(99)
        self.assertIn("what is the battery", prompt)
        self.assertIn("RECENT CONVERSATION", prompt)

    def test_prompt_without_history(self):
        from botpkg.brain import _build_system_prompt, _chat_history
        _chat_history.clear()
        prompt = _build_system_prompt(999)
        self.assertNotIn("RECENT CONVERSATION", prompt)


# ═══════════════════════════════════════════════════════════════════
# Brain Handler
# ═══════════════════════════════════════════════════════════════════

class TestBrainHandler(unittest.TestCase):
    """Test /brain handler."""

    def setUp(self):
        from botpkg.handlers import _last_command
        _last_command.clear()

    @patch("botpkg.handlers.meta.bot")
    @patch("botpkg.handlers.bot")
    def test_brain_status(self, mock_bot, mock_meta_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/brain"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        mock_meta_bot.send_message.assert_called()
        text = mock_meta_bot.send_message.call_args[0][1]
        self.assertIn("NLP Brain Status", text)

    @patch("botpkg.handlers.meta.bot")
    @patch("botpkg.handlers.bot")
    def test_brain_clear(self, mock_bot, mock_meta_bot):
        from botpkg.handlers import handle_all_messages
        from botpkg.brain import add_to_history, get_history, _chat_history
        _chat_history.clear()
        add_to_history(99, "user", "test message")
        self.assertEqual(len(get_history(99)), 1)

        msg = MagicMock()
        msg.text = "/brain clear"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        self.assertEqual(len(get_history(99)), 0)


# ═══════════════════════════════════════════════════════════════════
# Brain Callback Handlers
# ═══════════════════════════════════════════════════════════════════

class TestBrainCallbacks(unittest.TestCase):
    """Test brain inline button callbacks."""

    @patch("botpkg.handlers.bot")
    def test_brain_cancel_callback(self, mock_bot):
        from botpkg.handlers import handle_callback_query
        call = MagicMock()
        call.from_user.id = 12345
        call.message.chat.id = 99
        call.data = "brain_cancel:"
        handle_callback_query(call)
        mock_bot.send_message.assert_called()
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Cancelled", text)

    @patch("botpkg.brain.bot")
    @patch("botpkg.handlers.bot")
    def test_brain_plan_expired(self, mock_bot, mock_brain_bot):
        from botpkg.handlers import handle_callback_query
        call = MagicMock()
        call.from_user.id = 12345
        call.message.chat.id = 99
        call.data = "brain_plan:nonexistent_plan_id"
        handle_callback_query(call)
        mock_brain_bot.send_message.assert_called()


# ═══════════════════════════════════════════════════════════════════
# Config Registration
# ═══════════════════════════════════════════════════════════════════

class TestBrainConfig(unittest.TestCase):
    """Test brain is registered in config."""

    @classmethod
    def setUpClass(cls):
        from botpkg.utils import load_commands
        load_commands()  # Populates SPECIAL_COMMANDS and aliases

    def test_brain_in_special_commands(self):
        from botpkg.config import SPECIAL_COMMANDS
        self.assertIn("brain", SPECIAL_COMMANDS)

    def test_ai_alias(self):
        from botpkg.utils import resolve_alias
        # 'ask' is an alias for the standalone 'ai' command
        self.assertEqual(resolve_alias("ask"), "ai")


if __name__ == "__main__":
    unittest.main()
