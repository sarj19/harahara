"""Tests for the /build wizard — command, schedule, and macro creation."""
import os
import unittest
from unittest.mock import patch, MagicMock, mock_open

from botpkg.handlers.build import (
    handle_build, process_build_step, pending_build, _save_command,
    _save_schedule, _save_macro,
)


class TestBuildWizard(unittest.TestCase):
    def setUp(self):
        pending_build.clear()

    @patch("botpkg.handlers.build.bot")
    def test_build_shows_mode_picker(self, mock_bot):
        msg = MagicMock()
        msg.chat.id = 100
        handle_build(msg, 100, "/build")
        self.assertIn(100, pending_build)
        self.assertIsNone(pending_build[100]["mode"])
        sent_text = mock_bot.send_message.call_args[0][1]
        self.assertIn("command", sent_text)
        self.assertIn("schedule", sent_text.lower())
        self.assertIn("macro", sent_text.lower())

    @patch("botpkg.handlers.build.bot")
    def test_cancel_aborts(self, mock_bot):
        pending_build[100] = {"mode": None, "step": -1}
        msg = MagicMock()
        msg.chat.id = 100
        result = process_build_step(msg, 100, "cancel")
        self.assertTrue(result)
        self.assertNotIn(100, pending_build)

    @patch("botpkg.handlers.build.bot")
    def test_mode_1_selects_command(self, mock_bot):
        pending_build[100] = {"mode": None, "step": -1}
        msg = MagicMock()
        result = process_build_step(msg, 100, "1")
        self.assertTrue(result)
        self.assertEqual(pending_build[100]["mode"], "command")

    @patch("botpkg.handlers.build.bot")
    def test_mode_2_selects_schedule(self, mock_bot):
        pending_build[100] = {"mode": None, "step": -1}
        msg = MagicMock()
        result = process_build_step(msg, 100, "2")
        self.assertTrue(result)
        self.assertEqual(pending_build[100]["mode"], "schedule")

    @patch("botpkg.handlers.build.bot")
    def test_mode_3_selects_macro(self, mock_bot):
        pending_build[100] = {"mode": None, "step": -1}
        msg = MagicMock()
        result = process_build_step(msg, 100, "3")
        self.assertTrue(result)
        self.assertEqual(pending_build[100]["mode"], "macro")
        self.assertEqual(pending_build[100].get("steps"), [])

    @patch("botpkg.handlers.build.bot")
    def test_command_wizard_name_step(self, mock_bot):
        pending_build[100] = {"mode": "command", "step": 0}
        msg = MagicMock()
        process_build_step(msg, 100, "mytest")
        self.assertEqual(pending_build[100]["name"], "mytest")
        self.assertEqual(pending_build[100]["step"], 1)

    @patch("botpkg.handlers.build.bot")
    @patch("botpkg.config.SPECIAL_COMMANDS", {"screenshot": "Take screenshot", "help": "Show help"})
    def test_command_rejects_builtin_name(self, mock_bot):
        pending_build[100] = {"mode": "command", "step": 0}
        msg = MagicMock()
        process_build_step(msg, 100, "screenshot")
        self.assertEqual(pending_build[100]["step"], 0)  # Still on step 0

    @patch("botpkg.handlers.build.bot")
    def test_command_wizard_full_flow(self, mock_bot):
        pending_build[100] = {"mode": "command", "step": 0}
        msg = MagicMock()
        # Name
        process_build_step(msg, 100, "weather")
        # Command
        process_build_step(msg, 100, "curl wttr.in")
        # Description
        process_build_step(msg, 100, "Show weather")
        # Aliases
        process_build_step(msg, 100, "w, wttr")
        # Timeout
        process_build_step(msg, 100, "skip")

        self.assertEqual(pending_build[100]["step"], 5)
        self.assertEqual(pending_build[100]["name"], "weather")
        self.assertEqual(pending_build[100]["cmd"], "curl wttr.in")
        self.assertEqual(pending_build[100]["aliases"], ["w", "wttr"])

    @patch("botpkg.handlers.build.bot")
    def test_schedule_wizard_full_flow(self, mock_bot):
        pending_build[100] = {"mode": "schedule", "step": 0}
        msg = MagicMock()
        # Name
        process_build_step(msg, 100, "battery_check")
        # Command
        process_build_step(msg, 100, "pmset -g batt")
        # Interval
        process_build_step(msg, 100, "2h")
        # Description
        process_build_step(msg, 100, "Check battery")

        self.assertEqual(pending_build[100]["step"], 4)
        self.assertEqual(pending_build[100]["name"], "battery_check")
        self.assertEqual(pending_build[100]["interval"], "2h")

    @patch("botpkg.handlers.build.bot")
    def test_schedule_rejects_bad_interval(self, mock_bot):
        pending_build[100] = {"mode": "schedule", "step": 2}
        pending_build[100]["name"] = "test"
        pending_build[100]["cmd"] = "echo hi"
        msg = MagicMock()
        process_build_step(msg, 100, "banana")
        self.assertEqual(pending_build[100]["step"], 2)  # Still on step 2

    @patch("botpkg.handlers.build.bot")
    def test_macro_wizard_add_steps(self, mock_bot):
        pending_build[100] = {"mode": "macro", "step": 2, "steps": [], "name": "test", "desc": ""}
        msg = MagicMock()
        # Add step 1
        process_build_step(msg, 100, "echo hello | Say hello")
        self.assertEqual(len(pending_build[100]["steps"]), 1)
        self.assertEqual(pending_build[100]["steps"][0]["cmd"], "echo hello")
        self.assertEqual(pending_build[100]["steps"][0]["desc"], "Say hello")
        # Add step 2
        process_build_step(msg, 100, "uptime")
        self.assertEqual(len(pending_build[100]["steps"]), 2)
        self.assertEqual(pending_build[100]["steps"][1]["desc"], "Step 2")

    @patch("botpkg.handlers.build.bot")
    def test_macro_done_with_no_steps_rejected(self, mock_bot):
        pending_build[100] = {"mode": "macro", "step": 2, "steps": [], "name": "test", "desc": ""}
        msg = MagicMock()
        process_build_step(msg, 100, "done")
        self.assertEqual(pending_build[100]["step"], 2)  # Still on step 2

    @patch("botpkg.handlers.build.bot")
    @patch("botpkg.handlers.build.os.path.exists", return_value=False)
    @patch("builtins.open", new_callable=mock_open)
    def test_save_command_writes_yaml(self, mock_file, mock_exists, mock_bot):
        session = {"name": "test", "cmd": "echo hi", "desc": "Test cmd", "aliases": [], "timeout": 300}
        _save_command(100, session)
        mock_bot.send_message.assert_called()
        self.assertIn("saved", mock_bot.send_message.call_args[0][1].lower())

    @patch("botpkg.handlers.build.bot")
    @patch("botpkg.handlers.build.os.path.exists", return_value=False)
    @patch("builtins.open", new_callable=mock_open)
    def test_save_schedule_writes_yaml(self, mock_file, mock_exists, mock_bot):
        session = {"name": "batt", "cmd": "pmset -g batt", "interval": "2h", "desc": "Battery"}
        _save_schedule(100, session)
        mock_bot.send_message.assert_called()
        self.assertIn("saved", mock_bot.send_message.call_args[0][1].lower())

    @patch("botpkg.handlers.build.bot")
    @patch("botpkg.handlers.build.os.path.exists", return_value=False)
    @patch("builtins.open", new_callable=mock_open)
    def test_save_macro_writes_yaml(self, mock_file, mock_exists, mock_bot):
        session = {"name": "morning", "desc": "Morning", "steps": [{"cmd": "uptime", "desc": "Up"}]}
        _save_macro(100, session)
        mock_bot.send_message.assert_called()
        self.assertIn("saved", mock_bot.send_message.call_args[0][1].lower())

    @patch("botpkg.handlers.build.bot")
    def test_quick_build(self, mock_bot):
        msg = MagicMock()
        msg.chat.id = 100
        with patch("botpkg.handlers.build.os.path.exists", return_value=False), \
             patch("builtins.open", new_callable=mock_open):
            handle_build(msg, 100, "/build mytest echo hello world")
        mock_bot.send_message.assert_called()
        self.assertIn("saved", mock_bot.send_message.call_args[0][1].lower())

    def test_returns_false_when_no_session(self):
        msg = MagicMock()
        result = process_build_step(msg, 999, "anything")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
