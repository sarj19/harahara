"""Tests for usability handlers: onboarding, menu, pins, streak, focus, suggestions."""
import os
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open

from botpkg.handlers.usability import (
    handle_start, handle_menu, handle_pin, handle_pins,
    handle_streak, handle_pretty_status, handle_focus,
    suggest_command, try_natural_shortcut, update_streak,
    _similarity, _load_streak, _save_streak, _load_pins, _save_pins,
    handle_tour_callback, handle_menu_callback,
    NATURAL_SHORTCUTS,
)


class TestOnboarding(unittest.TestCase):
    @patch("botpkg.handlers.usability.bot")
    def test_start_sends_welcome(self, mock_bot):
        msg = MagicMock()
        handle_start(msg, 100, "/start")
        mock_bot.send_message.assert_called_once()
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Welcome", text)

    @patch("botpkg.handlers.usability.bot")
    def test_tour_callback_screenshot(self, mock_bot):
        handle_tour_callback(100, "screenshot")
        mock_bot.send_message.assert_called()
        self.assertIn("Screenshot", mock_bot.send_message.call_args[0][1])

    @patch("botpkg.handlers.usability.bot")
    def test_tour_callback_help(self, mock_bot):
        with patch("botpkg.handlers.meta.handle_help") as mock_help:
            handle_tour_callback(100, "help")
            mock_help.assert_called_with(100)


class TestMenu(unittest.TestCase):
    @patch("botpkg.handlers.usability.bot")
    def test_menu_shows_categories(self, mock_bot):
        msg = MagicMock()
        handle_menu(msg, 100, "/menu")
        mock_bot.send_message.assert_called()
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Quick Menu", text)

    @patch("botpkg.handlers.usability.bot")
    def test_menu_callback(self, mock_bot):
        handle_menu_callback(100, "screen")
        mock_bot.send_message.assert_called()


class TestPins(unittest.TestCase):
    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_pins", return_value=[])
    @patch("botpkg.handlers.usability._save_pins")
    def test_pin_text(self, mock_save, mock_load, mock_bot):
        msg = MagicMock()
        msg.reply_to_message = None
        handle_pin(msg, 100, "/pin remember this")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        self.assertEqual(len(saved), 1)
        self.assertIn("remember this", saved[0]["text"])

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_pins", return_value=[])
    def test_pins_empty(self, mock_load, mock_bot):
        msg = MagicMock()
        handle_pins(msg, 100, "/pins")
        text = mock_bot.reply_to.call_args[0][1]
        self.assertIn("No pins", text)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_pins", return_value=[
        {"text": "test pin", "time": 1700000000}
    ])
    def test_pins_list(self, mock_load, mock_bot):
        msg = MagicMock()
        handle_pins(msg, 100, "/pins")
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Pinned Items", text)
        self.assertIn("test pin", text)


class TestStreak(unittest.TestCase):
    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_streak", return_value={
        "current": 5, "best": 10, "total_days": 30, "last_date": ""
    })
    def test_streak_display(self, mock_load, mock_bot):
        msg = MagicMock()
        handle_streak(msg, 100, "/streak")
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Streak", text)
        self.assertIn("🔥", text)

    @patch("botpkg.handlers.usability._load_streak", return_value={
        "current": 0, "best": 0, "total_days": 0, "last_date": ""
    })
    @patch("botpkg.handlers.usability._save_streak")
    def test_update_streak_new_day(self, mock_save, mock_load):
        update_streak()
        mock_save.assert_called_once()
        data = mock_save.call_args[0][0]
        self.assertEqual(data["current"], 1)
        self.assertEqual(data["total_days"], 1)


class TestPrettyStatus(unittest.TestCase):
    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability.subprocess")
    @patch("botpkg.handlers.usability._load_streak", return_value={"current": 3})
    def test_pretty_status(self, mock_streak, mock_subprocess, mock_bot):
        mock_subprocess.run.return_value = MagicMock(stdout="Now drawing from 'AC Power'\n -InternalBattery-0 (id=123)\t85%")
        msg = MagicMock()
        handle_pretty_status(msg, 100, "/status")
        # Status now sends a photo (image card) or falls back to text
        self.assertTrue(
            mock_bot.send_photo.called or mock_bot.send_message.called,
            "Expected send_photo or send_message for status"
        )


class TestSuggestions(unittest.TestCase):
    def test_similarity_exact(self):
        self.assertEqual(_similarity("screenshot", "screenshot"), 1.0)

    def test_similarity_partial(self):
        score = _similarity("screen", "screenshot")
        self.assertGreater(score, 0.5)

    def test_similarity_unrelated(self):
        score = _similarity("xyz", "screenshot")
        self.assertLess(score, 0.4)

    @patch("botpkg.handlers.usability.bot")
    def test_suggest_command(self, mock_bot):
        result = suggest_command(100, "screensht")
        self.assertTrue(result)
        mock_bot.send_message.assert_called()

    @patch("botpkg.handlers.usability.bot")
    def test_suggest_no_match(self, mock_bot):
        result = suggest_command(100, "zzzzzzzzz")
        self.assertTrue(result)
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Unknown", text)


class TestNaturalShortcuts(unittest.TestCase):
    @patch("botpkg.handlers.usability.bot")
    def test_screenshot_shortcut(self, mock_bot):
        result = try_natural_shortcut(100, "take a screenshot")
        self.assertTrue(result)
        mock_bot.send_message.assert_called()
        self.assertIn("/screenshot", mock_bot.send_message.call_args[0][1])

    @patch("botpkg.handlers.usability.bot")
    def test_no_match(self, mock_bot):
        result = try_natural_shortcut(100, "random sentence about cooking")
        self.assertFalse(result)

    def test_shortcuts_all_have_commands(self):
        for phrase, cmd in NATURAL_SHORTCUTS.items():
            self.assertTrue(cmd.startswith("/") or cmd == "briefing",
                            f"Shortcut '{phrase}' maps to invalid command '{cmd}'")


class TestFocus(unittest.TestCase):
    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability.subprocess")
    @patch("botpkg.handlers.timer.handle_timer")
    @patch("botpkg.handlers.usability.threading")
    def test_focus_start(self, mock_thread, mock_timer, mock_subprocess, mock_bot):
        msg = MagicMock()
        handle_focus(msg, 100, "/focus 25m Deep work")
        mock_bot.send_message.assert_called()
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Focus Mode", text)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability.subprocess")
    def test_focus_stop(self, mock_subprocess, mock_bot):
        msg = MagicMock()
        handle_focus(msg, 100, "/focus stop")
        mock_bot.reply_to.assert_called()
        self.assertIn("ended", mock_bot.reply_to.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
