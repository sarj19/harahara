"""Exhaustive tests for the Telegram bot.

Tests cover real logic in utils, config, runner, and handlers.
Uses unittest.mock to avoid actual Telegram API calls or shell execution.

Run: python3 -m pytest tests/ -v
"""
import os
import sys
import time
import tempfile
import textwrap
import subprocess
import threading
import unittest
from unittest.mock import patch, MagicMock, call

# Set required env vars BEFORE importing botpkg
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:FAKE-TOKEN-FOR-TESTING"
os.environ["TELEGRAM_AUTHORIZED_USER_ID"] = "12345"

from botpkg.utils import parse_duration, get_cmd_name, load_commands, send_file_smart
import botpkg.utils as _utils

_NONEXISTENT = "/nonexistent/personal.yaml"
from botpkg.config import (
    SPECIAL_COMMANDS, MODIFIERS, KEY_CODES,
    DANGEROUS_COMMANDS, screenshot_sessions, pending_confirmations,
)
from botpkg.runner import run_command_with_screenshots


# ═══════════════════════════════════════════════════════════════════
# parse_duration tests
# ═══════════════════════════════════════════════════════════════════

class TestParseDuration(unittest.TestCase):
    """Test duration parsing with various formats and edge cases."""

    def test_plain_number_defaults_to_seconds(self):
        seconds, label = parse_duration("90")
        self.assertEqual(seconds, 90)
        self.assertEqual(label, "90 seconds")

    def test_seconds_suffix(self):
        for suffix in ("s", "sec", "secs"):
            seconds, label = parse_duration(f"30{suffix}")
            self.assertEqual(seconds, 30, f"Failed for suffix '{suffix}'")

    def test_minutes_suffix(self):
        for suffix in ("m", "min", "mins"):
            seconds, label = parse_duration(f"5{suffix}")
            self.assertEqual(seconds, 300, f"Failed for suffix '{suffix}'")
            self.assertEqual(label, "5 minutes")

    def test_hours_suffix(self):
        for suffix in ("h", "hr", "hrs", "hour", "hours"):
            seconds, label = parse_duration(f"2{suffix}")
            self.assertEqual(seconds, 7200, f"Failed for suffix '{suffix}'")
            self.assertEqual(label, "2 hours")

    def test_singular_labels(self):
        _, label = parse_duration("1m")
        self.assertEqual(label, "1 minute")
        _, label = parse_duration("1h")
        self.assertEqual(label, "1 hour")
        _, label = parse_duration("1s")
        self.assertEqual(label, "1 second")

    def test_whitespace_is_stripped(self):
        seconds, _ = parse_duration("  10m  ")
        self.assertEqual(seconds, 600)

    def test_case_insensitive(self):
        seconds, _ = parse_duration("5M")
        self.assertEqual(seconds, 300)
        seconds, _ = parse_duration("2H")
        self.assertEqual(seconds, 7200)

    def test_invalid_returns_none(self):
        for invalid in ("", "abc", "5x", "-1", "3.5m", "m5", "hello world"):
            seconds, label = parse_duration(invalid)
            self.assertIsNone(seconds, f"Expected None for '{invalid}', got {seconds}")
            self.assertIsNone(label, f"Expected None label for '{invalid}'")

    def test_zero_is_valid(self):
        seconds, label = parse_duration("0")
        self.assertEqual(seconds, 0)
        self.assertEqual(label, "0 seconds")


# ═══════════════════════════════════════════════════════════════════
# get_cmd_name tests
# ═══════════════════════════════════════════════════════════════════

class TestGetCmdName(unittest.TestCase):
    """Test command name extraction from message text."""

    def test_simple_command(self):
        self.assertEqual(get_cmd_name("/help"), "/help")

    def test_command_with_args(self):
        self.assertEqual(get_cmd_name("/screenshot 5"), "/screenshot")

    def test_command_with_bot_mention(self):
        self.assertEqual(get_cmd_name("/help@MyBot"), "/help")

    def test_command_with_mention_and_args(self):
        self.assertEqual(get_cmd_name("/remind@MyBot 5m hello"), "/remind")

    def test_case_insensitive(self):
        self.assertEqual(get_cmd_name("/HELP"), "/help")
        self.assertEqual(get_cmd_name("/Screenshot"), "/screenshot")


# ═══════════════════════════════════════════════════════════════════
# load_commands tests
# ═══════════════════════════════════════════════════════════════════

class TestLoadCommands(unittest.TestCase):
    """Test YAML command loading, caching, and section parsing."""

    def _write_yaml(self, content):
        """Write YAML to a temp file and return its path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        f.write(textwrap.dedent(content))
        f.close()
        return f.name

    def test_loads_commands_from_yaml(self):
        path = self._write_yaml("""
            ping:
              cmd: "echo pong"
              desc: "Test command"
            volume:
              cmd: "echo 50"
              desc: "Volume"
        """)
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}

            commands = load_commands()
            self.assertIn("ping", commands)
            self.assertIn("volume", commands)
            self.assertEqual(commands["ping"]["cmd"], "echo pong")
            self.assertEqual(commands["ping"]["desc"], "Test command")
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path)

    def test_caches_by_mtime(self):
        path = self._write_yaml("""
            test:
              cmd: "echo test"
              desc: "Test"
        """)
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}

            commands1 = load_commands()
            # Second call should return cached version (same mtime)
            commands2 = load_commands()
            self.assertIs(commands1, commands2)
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path)

    def test_reloads_on_mtime_change(self):
        path = self._write_yaml("""
            original:
              cmd: "echo 1"
              desc: "Original"
        """)
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}

            commands1 = load_commands()
            self.assertIn("original", commands1)

            # Overwrite with new content and bump mtime
            time.sleep(0.1)
            with open(path, 'w') as f:
                f.write("updated:\n  cmd: 'echo 2'\n  desc: 'Updated'\n")

            commands2 = load_commands()
            self.assertIn("updated", commands2)
            self.assertNotIn("original", commands2)
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path)

    def test_section_parsing(self):
        path = self._write_yaml("""
            # ─── System Control ───
            ping:
              cmd: "echo pong"
              desc: "Ping"
            lock:
              cmd: "echo lock"
              desc: "Lock"
            # ─── Audio ───
            volume:
              cmd: "echo 50"
              desc: "Volume"
        """)
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}
            _utils.commands_sections = []

            load_commands()
            sections = _utils.commands_sections
            self.assertEqual(len(sections), 2)
            self.assertEqual(sections[0][0], "System Control")
            self.assertIn("ping", sections[0][1])
            self.assertIn("lock", sections[0][1])
            self.assertEqual(sections[1][0], "Audio")
            self.assertIn("volume", sections[1][1])
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path)

    def test_handles_missing_file_gracefully(self):
        old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
        _utils.YAML_PATH = "/nonexistent/path.yaml"
        _utils.PERSONAL_YAML_PATH = _NONEXISTENT
        _utils._commands_mtime = (0, 0)
        _utils._commands_cache = {}
        try:
            commands = load_commands()
            self.assertEqual(commands, {})
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal

    def test_command_names_are_lowercased(self):
        path = self._write_yaml("""
            MyCommand:
              cmd: "echo hi"
              desc: "Test"
        """)
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}

            commands = load_commands()
            self.assertIn("mycommand", commands)
            self.assertNotIn("MyCommand", commands)
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# send_file_smart tests
# ═══════════════════════════════════════════════════════════════════

class TestSendFileSmart(unittest.TestCase):
    """Test file sending logic (photo vs document threshold)."""

    def test_nonexistent_file_returns_false(self):
        result = send_file_smart(123, "/nonexistent/file.jpg")
        self.assertFalse(result)

    @patch("botpkg.utils.bot")
    def test_small_file_sent_as_photo(self, mock_bot):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"x" * 100)
            path = f.name
        try:
            result = send_file_smart(123, path)
            self.assertTrue(result)
            mock_bot.send_photo.assert_called_once()
            mock_bot.send_document.assert_not_called()
        finally:
            os.unlink(path)

    @patch("botpkg.utils.bot")
    def test_large_file_sent_as_document(self, mock_bot):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            # Write 11MB
            f.write(b"x" * (11 * 1024 * 1024))
            path = f.name
        try:
            result = send_file_smart(123, path)
            self.assertTrue(result)
            mock_bot.send_document.assert_called_once()
            mock_bot.send_photo.assert_not_called()
        finally:
            os.unlink(path)

    @patch("botpkg.utils.bot")
    def test_caption_passed_through(self, mock_bot):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"x" * 100)
            path = f.name
        try:
            send_file_smart(123, path, caption="2/5")
            args, kwargs = mock_bot.send_photo.call_args
            self.assertEqual(kwargs.get("caption") or args[2] if len(args) > 2 else kwargs.get("caption"), "2/5")
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# run_command_with_screenshots tests
# ═══════════════════════════════════════════════════════════════════

class TestRunCommandWithScreenshots(unittest.TestCase):
    """Test the async command runner with auto-screenshots."""

    def test_short_command_runs_blocking(self):
        """Commands with timeout <= 60 should run via subprocess.run (blocking)."""
        output, returncode = run_command_with_screenshots(123, "echo hello", timeout=10)
        self.assertIn("hello", output)
        self.assertEqual(returncode, 0)

    def test_short_command_captures_stderr(self):
        output, returncode = run_command_with_screenshots(
            123, "echo error >&2", timeout=10
        )
        self.assertIn("error", output)

    def test_short_command_timeout_raises(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            run_command_with_screenshots(123, "sleep 10", timeout=1)

    @patch("botpkg.runner.take_and_send_screenshot")
    def test_long_command_uses_popen(self, mock_screenshot):
        """Commands with timeout > 60 should use Popen (non-blocking)."""
        output, returncode = run_command_with_screenshots(
            123, "echo long_output", timeout=120
        )
        self.assertIn("long_output", output)
        self.assertEqual(returncode, 0)

    @unittest.skip("Blocks for 62s waiting for real process timeout — run manually")
    @patch("botpkg.runner.take_and_send_screenshot")
    def test_long_command_timeout_kills_process(self, mock_screenshot):
        with self.assertRaises(subprocess.TimeoutExpired):
            run_command_with_screenshots(123, "sleep 300", timeout=62)


# ═══════════════════════════════════════════════════════════════════
# Config sanity tests
# ═══════════════════════════════════════════════════════════════════

class TestConfig(unittest.TestCase):
    """Verify config constants are sane and consistent."""

    def test_special_commands_all_have_descriptions(self):
        for cmd, desc in SPECIAL_COMMANDS.items():
            self.assertIsInstance(desc, str)
            self.assertTrue(len(desc) > 0, f"/{cmd} has empty description")

    def test_modifiers_map_to_applescript_syntax(self):
        for alias, value in MODIFIERS.items():
            self.assertTrue(value.endswith(" down"), f"Modifier '{alias}' -> '{value}' is not valid AppleScript")

    def test_key_codes_are_integers(self):
        for name, code in KEY_CODES.items():
            self.assertIsInstance(code, int, f"Key '{name}' has non-int code: {code}")

    def test_dangerous_commands_is_a_set(self):
        self.assertIsInstance(DANGEROUS_COMMANDS, set)
        self.assertTrue(len(DANGEROUS_COMMANDS) > 0)

    def test_common_dangerous_commands_present(self):
        for cmd in ("restart", "shutdown", "trash"):
            self.assertIn(cmd, DANGEROUS_COMMANDS)


# ═══════════════════════════════════════════════════════════════════
# Handler logic tests (mocked bot interactions)
# ═══════════════════════════════════════════════════════════════════

class TestHandlerLogic(unittest.TestCase):
    """Test handler dispatch and argument parsing logic via mocked messages."""

    def setUp(self):
        # Clear throttle state to prevent test bleed
        from botpkg.handlers import _last_command
        _last_command.clear()

    def _make_message(self, text, user_id=12345, chat_id=99):
        msg = MagicMock()
        msg.text = text
        msg.from_user.id = user_id
        msg.chat.id = chat_id
        return msg

    @patch("botpkg.handlers.bot")
    def test_unauthorized_user_rejected(self, mock_bot):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("/help", user_id=99999)
        handle_all_messages(msg)
        # After split: unauthorized users are silently ignored (logged only)
        mock_bot.send_message.assert_not_called()

    @patch("settings.NLP_ENABLED", False)
    @patch("botpkg.handlers.bot")
    def test_non_command_text_ignored(self, mock_bot):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("just a normal message")
        handle_all_messages(msg)
        mock_bot.reply_to.assert_not_called()

    @patch("botpkg.handlers.meta.load_commands", return_value={})
    @patch("botpkg.handlers.meta.bot")
    @patch("botpkg.handlers.bot")
    def test_help_command_sends_message(self, mock_bot, mock_meta_bot, mock_load):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("/help")
        handle_all_messages(msg)
        mock_meta_bot.send_message.assert_called_once()
        help_text = mock_meta_bot.send_message.call_args[0][1]
        self.assertIn("Help", help_text)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.commands.bot")
    @patch("botpkg.handlers.bot")
    def test_unknown_yaml_command(self, mock_bot, mock_cmd_bot, mock_usability_bot):
        from botpkg.handlers import handle_all_messages
        with patch("botpkg.handlers.commands.load_commands", return_value={}):
            msg = self._make_message("/nonexistent")
            handle_all_messages(msg)
            # Now suggests similar commands instead of plain "Unknown" error
            mock_usability_bot.send_message.assert_called()
            text = mock_usability_bot.send_message.call_args[0][1]
            self.assertIn("not found", text.lower())

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.commands.bot")
    @patch("botpkg.handlers.bot")
    def test_dangerous_command_asks_confirmation(self, mock_bot, mock_cmd_bot, mock_usability_bot):
        from botpkg.handlers import handle_all_messages
        from botpkg.config import pending_confirmations
        pending_confirmations.clear()
        fake_commands = {"restart": {"cmd": "echo restarting", "desc": "Restart"}}
        with patch("botpkg.handlers.commands.load_commands", return_value=fake_commands):
            msg = self._make_message("/restart", chat_id=555)
            handle_all_messages(msg)
            mock_cmd_bot.reply_to.assert_called()
            confirm_text = mock_cmd_bot.reply_to.call_args[0][1]
            self.assertIn("Run", confirm_text)
            self.assertIn(555, pending_confirmations)
        pending_confirmations.clear()

    @patch("botpkg.handlers.bot")
    def test_confirmation_yes_executes(self, mock_bot):
        from botpkg.handlers import handle_all_messages
        from botpkg.config import pending_confirmations
        pending_confirmations[555] = {"command": "restart", "time": time.time()}
        fake_commands = {"restart": {"cmd": "echo done", "desc": "Restart"}}
        with patch("botpkg.handlers.load_commands", return_value=fake_commands), \
             patch("botpkg.handlers.commands.run_command_with_screenshots", return_value=("done", 0)):
            msg = self._make_message("yes", chat_id=555)
            handle_all_messages(msg)
            self.assertNotIn(555, pending_confirmations)

    @patch("botpkg.handlers.bot")
    def test_confirmation_cancel(self, mock_bot):
        from botpkg.handlers import handle_all_messages
        from botpkg.config import pending_confirmations
        pending_confirmations[555] = {"command": "restart", "time": time.time()}
        msg = self._make_message("no", chat_id=555)
        handle_all_messages(msg)
        mock_bot.reply_to.assert_called()
        self.assertIn("Cancelled", mock_bot.reply_to.call_args[0][1])
        self.assertNotIn(555, pending_confirmations)

    @patch("botpkg.handlers.bot")
    def test_confirmation_expired(self, mock_bot):
        from botpkg.handlers import handle_all_messages
        from botpkg.config import pending_confirmations
        pending_confirmations[555] = {"command": "restart", "time": time.time() - 120}
        msg = self._make_message("yes", chat_id=555)
        handle_all_messages(msg)
        # Now uses _execute_confirmed_command which calls bot.send_message for expired
        mock_bot.send_message.assert_called()
        expired_text = mock_bot.send_message.call_args[0][1]
        self.assertIn("expired", expired_text)

    @patch("botpkg.handlers.system.subprocess")
    @patch("botpkg.handlers.system.bot")
    @patch("botpkg.handlers.bot")
    def test_type_command_builds_applescript(self, mock_bot, mock_sys_bot, mock_subproc):
        from botpkg.handlers import handle_all_messages
        mock_subproc.run.return_value = MagicMock(returncode=0)
        msg = self._make_message('/type hello world')
        handle_all_messages(msg)
        calls = mock_subproc.run.call_args_list
        script_call = [c for c in calls if "osascript" in str(c)]
        self.assertTrue(len(script_call) > 0, "osascript not called for /type")

    @patch("botpkg.handlers.system.subprocess")
    @patch("botpkg.handlers.system.bot")
    @patch("botpkg.handlers.bot")
    def test_url_command_opens_url(self, mock_bot, mock_sys_bot, mock_subproc):
        from botpkg.handlers import handle_all_messages
        mock_subproc.run.return_value = MagicMock(returncode=0)
        msg = self._make_message('/url https://example.com')
        handle_all_messages(msg)
        open_call = mock_subproc.run.call_args_list[0]
        self.assertEqual(open_call[0][0], ["open", "https://example.com"])

    @patch("botpkg.handlers.system.bot")
    @patch("botpkg.handlers.bot")
    def test_screenshot_invalid_arg(self, mock_bot, mock_sys_bot):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("/screenshot abc")
        handle_all_messages(msg)
        reply_text = mock_sys_bot.reply_to.call_args[0][1]
        self.assertIn("positive integer", reply_text)

    @patch("botpkg.handlers.remind.bot")
    @patch("botpkg.handlers.bot")
    def test_remind_invalid_duration(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("/remind xyz do something")
        handle_all_messages(msg)
        reply_text = mock_prod_bot.reply_to.call_args[0][1]
        self.assertIn("Invalid duration", reply_text)

    @patch("botpkg.handlers.remind.bot")
    @patch("botpkg.handlers.bot")
    def test_remind_missing_message(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("/remind 5m")
        handle_all_messages(msg)
        reply_text = mock_prod_bot.reply_to.call_args[0][1]
        self.assertIn("What's the reminder for", reply_text)

    @patch("botpkg.handlers.system.bot")
    @patch("botpkg.handlers.bot")
    def test_kill_no_args(self, mock_bot, mock_sys_bot):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("/kill")
        handle_all_messages(msg)
        reply_text = mock_sys_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply_text)

    @patch("botpkg.handlers.system.bot")
    @patch("botpkg.handlers.bot")
    def test_open_no_args(self, mock_bot, mock_sys_bot):
        from botpkg.handlers import handle_all_messages
        msg = self._make_message("/open")
        handle_all_messages(msg)
        reply_text = mock_sys_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply_text)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.commands.subprocess.run")
    @patch("botpkg.handlers.commands.bot")
    @patch("botpkg.handlers.bot")
    def test_yaml_command_inline_timeout(self, mock_bot, mock_cmd_bot, mock_subproc_run, mock_usability_bot):
        from botpkg.handlers import handle_all_messages
        mock_subproc_run.return_value = MagicMock(stdout="hi", stderr="", returncode=0)
        fake_commands = {"gemini": {"cmd": "echo hi", "desc": "Gemini", "timeout": 300}}
        with patch("botpkg.handlers.commands.load_commands", return_value=fake_commands):
            msg = self._make_message("/gemini -t 30m what is 1+1")
            handle_all_messages(msg)
            call_kwargs = mock_subproc_run.call_args[1]
            self.assertEqual(call_kwargs["timeout"], 1800)  # timeout arg

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.commands.subprocess.run")
    @patch("botpkg.handlers.commands.bot")
    @patch("botpkg.handlers.bot")
    def test_yaml_command_placeholder_escaping(self, mock_bot, mock_cmd_bot, mock_subproc_run, mock_usability_bot):
        from botpkg.handlers import handle_all_messages
        mock_subproc_run.return_value = MagicMock(stdout="vol set", stderr="", returncode=0)
        fake_commands = {"setvolume": {"cmd": "osascript -e 'set volume output volume {}'", "desc": "Vol"}}
        with patch("botpkg.handlers.commands.load_commands", return_value=fake_commands):
            msg = self._make_message("/setvolume 80")
            handle_all_messages(msg)
            shell_cmd = mock_subproc_run.call_args[0][0]
            self.assertIn("80", shell_cmd)
            self.assertNotIn("{}", shell_cmd)


# ═══════════════════════════════════════════════════════════════════
# YAML command argument escaping tests
# ═══════════════════════════════════════════════════════════════════

class TestArgumentEscaping(unittest.TestCase):
    """Test that {} placeholder escaping handles edge cases safely."""

    def _apply_escaping(self, template, args):
        """Reproduce the escaping logic from handlers.py."""
        import shlex
        shell_command = template
        if "{}" in shell_command:
            safe_args = args.replace('\\', '\\\\').replace('"', '\\"').replace("'", "'\\''")
            return shell_command.replace("{}", safe_args)
        else:
            return f"{shell_command} {shlex.quote(args)}"

    def test_simple_number(self):
        result = self._apply_escaping("osascript -e 'set volume output volume {}'", "80")
        self.assertEqual(result, "osascript -e 'set volume output volume 80'")

    def test_text_with_spaces(self):
        result = self._apply_escaping("notify '{}'", "hello world")
        self.assertEqual(result, "notify 'hello world'")

    def test_single_quote_escaped(self):
        result = self._apply_escaping("notify '{}'", "it's here")
        self.assertIn("'\\''", result)

    def test_double_quote_escaped(self):
        result = self._apply_escaping('osascript -e \'display notification "{}"\'', 'say "hi"')
        self.assertIn('\\"hi\\"', result)

    def test_backslash_escaped(self):
        result = self._apply_escaping("cmd '{}'", "path\\to\\file")
        self.assertIn("\\\\", result)

    def test_no_placeholder_uses_shlex_quote(self):
        result = self._apply_escaping("echo", "hello world")
        self.assertEqual(result, "echo 'hello world'")

    def test_no_placeholder_with_special_chars(self):
        result = self._apply_escaping("echo", "it's a \"test\"")
        # shlex.quote should handle this safely
        self.assertIn("it", result)


# ═══════════════════════════════════════════════════════════════════
# Shortcut handler tests
# ═══════════════════════════════════════════════════════════════════

class TestShortcutHandler(unittest.TestCase):
    """Test /shortcut command handler."""

    def _make_message(self, text, user_id=12345, chat_id=99):
        msg = MagicMock()
        msg.text = text
        msg.from_user.id = user_id
        msg.chat.id = chat_id
        return msg

    @patch("botpkg.handlers.productivity.subprocess.run")
    @patch("botpkg.handlers.productivity.bot")
    def test_shortcut_no_args_lists(self, mock_bot, mock_run):
        from botpkg.handlers.productivity import handle_shortcut
        mock_run.return_value = MagicMock(stdout="My Shortcut\nAnother One\n", returncode=0)
        msg = self._make_message("/shortcut")
        handle_shortcut(msg, 99, "/shortcut")
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0], ["shortcuts", "list"])
        sent = mock_bot.send_message.call_args[0][1]
        self.assertIn("My Shortcut", sent)
        self.assertIn("Another One", sent)

    @patch("botpkg.handlers.productivity.subprocess.run")
    @patch("botpkg.handlers.productivity.bot")
    def test_shortcut_no_shortcuts_found(self, mock_bot, mock_run):
        from botpkg.handlers.productivity import handle_shortcut
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        msg = self._make_message("/shortcut")
        handle_shortcut(msg, 99, "/shortcut")
        sent = mock_bot.send_message.call_args[0][1]
        self.assertIn("No shortcuts found", sent)

    @patch("botpkg.handlers.productivity.threading.Thread")
    @patch("botpkg.handlers.productivity.bot")
    def test_shortcut_runs_named(self, mock_bot, mock_thread):
        from botpkg.handlers.productivity import handle_shortcut
        msg = self._make_message("/shortcut My Shortcut")
        handle_shortcut(msg, 99, "/shortcut My Shortcut")
        mock_bot.reply_to.assert_called_once()
        self.assertIn("My Shortcut", mock_bot.reply_to.call_args[0][1])
        mock_thread.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Schedule handler tests
# ═══════════════════════════════════════════════════════════════════

class TestScheduleHandler(unittest.TestCase):
    """Test /schedule command handler."""

    def _make_message(self, text, user_id=12345, chat_id=99):
        msg = MagicMock()
        msg.text = text
        msg.from_user.id = user_id
        msg.chat.id = chat_id
        return msg

    @patch("botpkg.handlers.productivity.os.path.exists", return_value=False)
    @patch("botpkg.handlers.productivity.bot")
    def test_schedule_list_empty(self, mock_bot, mock_exists):
        from botpkg.handlers.productivity import handle_schedule
        msg = self._make_message("/schedule")
        handle_schedule(msg, 99, "/schedule")
        sent = mock_bot.send_message.call_args[0][1]
        self.assertIn("No schedules", sent)

    @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data="battery:\n  cmd: pmset -g batt\n  interval: '2h'\n  desc: Battery\n")
    @patch("botpkg.handlers.productivity.os.path.exists", return_value=True)
    @patch("botpkg.handlers.productivity.bot")
    def test_schedule_list_shows_entries(self, mock_bot, mock_exists, mock_file):
        from botpkg.handlers.productivity import handle_schedule
        msg = self._make_message("/schedule list")
        handle_schedule(msg, 99, "/schedule list")
        sent = mock_bot.send_message.call_args[0][1]
        self.assertIn("battery", sent)
        self.assertIn("2h", sent)

    @patch("botpkg.handlers.productivity.bot")
    def test_schedule_add_missing_args(self, mock_bot):
        from botpkg.handlers.productivity import handle_schedule
        msg = self._make_message("/schedule add")
        handle_schedule(msg, 99, "/schedule add")
        reply = mock_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply)

    @patch("botpkg.handlers.productivity.bot")
    def test_schedule_add_bad_interval(self, mock_bot):
        from botpkg.handlers.productivity import handle_schedule
        msg = self._make_message("/schedule add test banana echo hi")
        handle_schedule(msg, 99, "/schedule add test banana echo hi")
        reply = mock_bot.reply_to.call_args[0][1]
        self.assertIn("Invalid interval", reply)

    @patch("botpkg.handlers.productivity.bot")
    def test_schedule_remove_missing_name(self, mock_bot):
        from botpkg.handlers.productivity import handle_schedule
        msg = self._make_message("/schedule remove")
        handle_schedule(msg, 99, "/schedule remove")
        reply = mock_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply)

    @patch("botpkg.handlers.productivity.bot")
    def test_schedule_unknown_subcommand(self, mock_bot):
        from botpkg.handlers.productivity import handle_schedule
        msg = self._make_message("/schedule banana")
        handle_schedule(msg, 99, "/schedule banana")
        reply = mock_bot.reply_to.call_args[0][1]
        self.assertIn("Schedule Commands", reply)


if __name__ == "__main__":
    unittest.main()
