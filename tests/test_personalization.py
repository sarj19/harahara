"""Tests for new personalization features: aliases, scheduler, digest, keyboard, themes."""
import os
import time
import tempfile
import textwrap
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN-FOR-TESTING")
os.environ.setdefault("TELEGRAM_AUTHORIZED_USER_ID", "12345")

import botpkg.utils as _utils
from botpkg.utils import resolve_alias, get_aliases_for, get_cmd_section, load_commands
from botpkg.config import (
    SPECIAL_COMMAND_ALIASES, CATEGORY_EMOJIS, activity_stats,
)

_NONEXISTENT = "/nonexistent/personal.yaml"


# ═══════════════════════════════════════════════════════════════════
# Feature 4: Alias Resolution
# ═══════════════════════════════════════════════════════════════════

class TestAliasResolution(unittest.TestCase):
    """Test alias resolution for both special and YAML-defined aliases."""

    def test_special_alias_resolves(self):
        self.assertEqual(resolve_alias("ss"), "screenshot")
        self.assertEqual(resolve_alias("snap"), "screenshot")
        self.assertEqual(resolve_alias("kb"), "keyboard")

    def test_unknown_alias_returns_as_is(self):
        self.assertEqual(resolve_alias("nonexistent"), "nonexistent")
        self.assertEqual(resolve_alias("ping"), "ping")

    def test_alias_case_insensitive(self):
        self.assertEqual(resolve_alias("SS"), "screenshot")
        self.assertEqual(resolve_alias("Kb"), "keyboard")

    def test_yaml_alias_resolution(self):
        path = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        path.write(textwrap.dedent("""
            mycommand:
              cmd: "echo hi"
              desc: "Test"
              aliases: [mc, my]
        """))
        path.close()
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path.name
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}
            _utils._aliases_cache = {}

            load_commands()
            self.assertEqual(resolve_alias("mc"), "mycommand")
            self.assertEqual(resolve_alias("my"), "mycommand")
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path.name)

    def test_get_aliases_for_special_command(self):
        aliases = get_aliases_for("screenshot")
        self.assertIn("ss", aliases)
        self.assertIn("snap", aliases)
        self.assertIn("sc", aliases)

    def test_get_aliases_for_yaml_command(self):
        path = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        path.write(textwrap.dedent("""
            deploy:
              cmd: "echo deploy"
              desc: "Deploy"
              aliases: [d, dep]
        """))
        path.close()
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path.name
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}
            _utils._aliases_cache = {}

            load_commands()
            aliases = get_aliases_for("deploy")
            self.assertIn("d", aliases)
            self.assertIn("dep", aliases)
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path.name)

    def test_get_aliases_for_unknown_returns_empty(self):
        aliases = get_aliases_for("nonexistent_command_xyz")
        self.assertEqual(aliases, [])


# ═══════════════════════════════════════════════════════════════════
# Feature 5: Scheduler
# ═══════════════════════════════════════════════════════════════════

class TestScheduler(unittest.TestCase):
    """Test schedule YAML loading and safety guards."""

    def test_load_schedules_from_yaml(self):
        from botpkg.scheduler import _load_schedules, _schedules_mtime, _schedules_cache
        import botpkg.scheduler as _sched

        path = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        path.write(textwrap.dedent("""
            battery_check:
              cmd: "echo 85%"
              interval: "2h"
              desc: "Battery level"
        """))
        path.close()
        try:
            old_path = _sched.SCHEDULES_PATH
            _sched.SCHEDULES_PATH = path.name
            _sched._schedules_mtime = 0
            _sched._schedules_cache = {}

            schedules = _sched._load_schedules()
            self.assertIn("battery_check", schedules)
            self.assertEqual(schedules["battery_check"]["cmd"], "echo 85%")
            self.assertEqual(schedules["battery_check"]["interval"], "2h")
        finally:
            _sched.SCHEDULES_PATH = old_path
            os.unlink(path.name)

    def test_load_schedules_missing_file(self):
        import botpkg.scheduler as _sched
        old_path = _sched.SCHEDULES_PATH
        _sched.SCHEDULES_PATH = "/nonexistent/schedules.yaml"
        _sched._schedules_cache = {}
        try:
            result = _sched._load_schedules()
            self.assertEqual(result, {})
        finally:
            _sched.SCHEDULES_PATH = old_path

    def test_dangerous_commands_skipped(self):
        """Verify that the scheduler logic identifies dangerous commands."""
        from botpkg.config import DANGEROUS_COMMANDS
        cmd = "/restart"
        cmd_name = cmd.lstrip("/").split()[0].lower()
        self.assertIn(cmd_name, DANGEROUS_COMMANDS)


# ═══════════════════════════════════════════════════════════════════
# Feature 7: Activity Stats / Daily Digest
# ═══════════════════════════════════════════════════════════════════

class TestActivityStats(unittest.TestCase):
    """Test activity tracking counters."""

    def setUp(self):
        activity_stats["commands_run"] = 0
        activity_stats["screenshots_taken"] = 0
        activity_stats["commands_by_name"] = {}

    def test_counter_increments(self):
        activity_stats["commands_run"] += 1
        activity_stats["commands_run"] += 1
        self.assertEqual(activity_stats["commands_run"], 2)

    def test_commands_by_name_tracking(self):
        name = "ping"
        activity_stats["commands_by_name"][name] = activity_stats["commands_by_name"].get(name, 0) + 1
        activity_stats["commands_by_name"][name] = activity_stats["commands_by_name"].get(name, 0) + 1
        self.assertEqual(activity_stats["commands_by_name"]["ping"], 2)

    def test_digest_message_formatting(self):
        from botpkg.digest import _send_digest
        activity_stats["commands_run"] = 5
        activity_stats["screenshots_taken"] = 2
        activity_stats["commands_by_name"] = {"ping": 3, "screenshot": 2}

        with patch("botpkg.digest.bot") as mock_bot:
            _send_digest()
            mock_bot.send_message.assert_called_once()
            digest_text = mock_bot.send_message.call_args[0][1]
            self.assertIn("Daily Digest", digest_text)
            self.assertIn("5", digest_text)  # commands_run
            self.assertIn("2", digest_text)  # screenshots_taken
            self.assertIn("ping", digest_text)  # top command

        # Verify counters were reset
        self.assertEqual(activity_stats["commands_run"], 0)
        self.assertEqual(activity_stats["screenshots_taken"], 0)


# ═══════════════════════════════════════════════════════════════════
# Feature 8: Themed Responses / Category Emojis
# ═══════════════════════════════════════════════════════════════════

class TestThemedResponses(unittest.TestCase):
    """Test category emoji mapping and section lookup."""

    def test_known_categories_have_emojis(self):
        for cat in ("System Control", "Volume & Audio", "Network", "Dev & Automation"):
            self.assertIn(cat, CATEGORY_EMOJIS)
            self.assertTrue(len(CATEGORY_EMOJIS[cat]) > 0)

    def test_cmd_to_section_mapping(self):
        path = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        path.write(textwrap.dedent("""
            # ─── System Control ───
            ping:
              cmd: "echo pong"
              desc: "Ping"
            # ─── Audio ───
            volume:
              cmd: "echo 50"
              desc: "Volume"
        """))
        path.close()
        try:
            old_path, old_personal = _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH
            _utils.YAML_PATH = path.name
            _utils.PERSONAL_YAML_PATH = _NONEXISTENT
            _utils._commands_mtime = (0, 0)
            _utils._commands_cache = {}

            load_commands()
            self.assertEqual(get_cmd_section("ping"), "System Control")
            self.assertEqual(get_cmd_section("volume"), "Audio")
            self.assertEqual(get_cmd_section("nonexistent"), "")
        finally:
            _utils.YAML_PATH, _utils.PERSONAL_YAML_PATH = old_path, old_personal
            os.unlink(path.name)


# ═══════════════════════════════════════════════════════════════════
# Feature 10: Quick Reply Keyboard
# ═══════════════════════════════════════════════════════════════════

class TestKeyboard(unittest.TestCase):
    """Test keyboard command parsing."""

    def test_parse_keyboard_commands(self):
        cmd_str = "ping,screenshot,volume,status,help"
        cmd_list = [c.strip() for c in cmd_str.split(",") if c.strip()]
        self.assertEqual(len(cmd_list), 5)
        self.assertEqual(cmd_list[0], "ping")
        self.assertEqual(cmd_list[-1], "help")

    def test_empty_keyboard_commands(self):
        cmd_str = ""
        cmd_list = [c.strip() for c in cmd_str.split(",") if c.strip()]
        self.assertEqual(cmd_list, [])

    @patch("botpkg.handlers.meta.bot")
    @patch("botpkg.handlers.bot")
    def test_keyboard_handler_sends_markup(self, mock_bot, mock_meta_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/keyboard"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        mock_meta_bot.send_message.assert_called()
        call_kwargs = mock_meta_bot.send_message.call_args
        self.assertIn("Quick commands", call_kwargs[0][1])


# ═══════════════════════════════════════════════════════════════════
# Feature 1: Time-based Greetings
# ═══════════════════════════════════════════════════════════════════

class TestTimeGreeting(unittest.TestCase):
    """Test time-of-day greeting logic."""

    def test_morning_greeting(self):
        from telegram_listener import _time_greeting
        with patch("telegram_listener.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 12, 8, 0)
            self.assertIn("morning", _time_greeting().lower())

    def test_afternoon_greeting(self):
        from telegram_listener import _time_greeting
        with patch("telegram_listener.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 12, 14, 0)
            self.assertIn("afternoon", _time_greeting().lower())

    def test_evening_greeting(self):
        from telegram_listener import _time_greeting
        with patch("telegram_listener.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 12, 19, 0)
            self.assertIn("evening", _time_greeting().lower())

    def test_night_greeting(self):
        from telegram_listener import _time_greeting
        with patch("telegram_listener.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 12, 22, 0)
            self.assertIn("night", _time_greeting().lower())


# ═══════════════════════════════════════════════════════════════════
# Feature 6: Custom Voice — /say handler
# ═══════════════════════════════════════════════════════════════════

class TestSayCommand(unittest.TestCase):
    """Test /say handler with custom voice."""

    def setUp(self):
        from botpkg.handlers import _last_command
        _last_command.clear()

    @patch("botpkg.handlers.remind.subprocess")
    @patch("botpkg.handlers.remind.bot")
    @patch("botpkg.handlers.bot")
    def test_say_no_args(self, mock_bot, mock_prod_bot, mock_subproc):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/say"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        reply_text = mock_prod_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply_text)

    @patch("botpkg.handlers.remind.BOT_VOICE", "Samantha")
    @patch("botpkg.handlers.remind.subprocess")
    @patch("botpkg.handlers.remind.bot")
    @patch("botpkg.handlers.bot")
    def test_say_with_voice(self, mock_bot, mock_prod_bot, mock_subproc):
        from botpkg.handlers import handle_all_messages
        mock_subproc.run.return_value = MagicMock(returncode=0)
        msg = MagicMock()
        msg.text = "/say hello world"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        # Check that say was called with -v Samantha
        say_call = mock_subproc.run.call_args
        self.assertIn("-v", say_call[0][0])
        self.assertIn("Samantha", say_call[0][0])


# ═══════════════════════════════════════════════════════════════════
# Handler integration: alias dispatch
# ═══════════════════════════════════════════════════════════════════

class TestAliasDispatch(unittest.TestCase):
    """Test that alias commands resolve to the correct handler."""

    @classmethod
    def setUpClass(cls):
        from botpkg.utils import load_commands
        load_commands()  # Populate aliases

    def test_ss_resolves_to_screenshot(self):
        from botpkg.utils import resolve_alias
        self.assertEqual(resolve_alias("ss"), "screenshot")

    def test_snap_resolves_to_screenshot(self):
        from botpkg.utils import resolve_alias
        self.assertEqual(resolve_alias("snap"), "screenshot")

    def test_screenshot_in_dispatch_table(self):
        from botpkg.handlers import DISPATCH_TABLE
        self.assertIn("screenshot", DISPATCH_TABLE)


# ═══════════════════════════════════════════════════════════════════
# Wave 2: Notes CRUD
# ═══════════════════════════════════════════════════════════════════

class TestNotes(unittest.TestCase):
    """Test persistent notes module."""

    def setUp(self):
        import botpkg.notes as _notes
        self._notes = _notes
        self._tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self._tmp.write("[]")
        self._tmp.close()
        self._old = _notes.NOTES_FILE
        _notes.NOTES_FILE = self._tmp.name

    def tearDown(self):
        self._notes.NOTES_FILE = self._old
        try:
            os.unlink(self._tmp.name)
        except Exception:
            pass

    def test_save_and_list(self):
        nid = self._notes.save_note("Buy milk")
        self.assertEqual(nid, 1)
        notes = self._notes.list_notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "Buy milk")

    def test_multiple_notes_incrementing_ids(self):
        self._notes.save_note("Note 1")
        nid2 = self._notes.save_note("Note 2")
        self.assertEqual(nid2, 2)
        self.assertEqual(len(self._notes.list_notes()), 2)

    def test_search(self):
        self._notes.save_note("Buy groceries")
        self._notes.save_note("Call dentist")
        self._notes.save_note("Buy birthday gift")
        results = self._notes.search_notes("buy")
        self.assertEqual(len(results), 2)

    def test_search_case_insensitive(self):
        self._notes.save_note("IMPORTANT meeting")
        results = self._notes.search_notes("important")
        self.assertEqual(len(results), 1)

    def test_delete(self):
        self._notes.save_note("Temp note")
        self.assertTrue(self._notes.delete_note(1))
        self.assertEqual(len(self._notes.list_notes()), 0)

    def test_delete_nonexistent(self):
        self.assertFalse(self._notes.delete_note(999))

    def test_empty_file_ok(self):
        notes = self._notes.list_notes()
        self.assertEqual(notes, [])


# ═══════════════════════════════════════════════════════════════════
# Wave 2: Macros
# ═══════════════════════════════════════════════════════════════════

class TestMacros(unittest.TestCase):
    """Test macro loading and listing."""

    def test_load_macros_from_yaml(self):
        from botpkg.handlers.commands import _load_macros
        import botpkg.handlers.commands as _h
        path = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        path.write(textwrap.dedent("""
            morning:
              desc: "Morning check"
              steps:
                - cmd: "echo hello"
                  desc: "Say hello"
                - cmd: "uptime"
                  desc: "Uptime"
        """))
        path.close()
        try:
            old_path = _h.MACROS_PATH
            _h.MACROS_PATH = path.name
            macros = _load_macros()
            self.assertIn("morning", macros)
            self.assertEqual(len(macros["morning"]["steps"]), 2)
        finally:
            _h.MACROS_PATH = old_path
            os.unlink(path.name)

    def test_load_macros_missing_file(self):
        from botpkg.handlers.commands import _load_macros
        import botpkg.handlers.commands as _h
        old_path = _h.MACROS_PATH
        _h.MACROS_PATH = "/nonexistent/macros.yaml"
        try:
            result = _load_macros()
            self.assertEqual(result, {})
        finally:
            _h.MACROS_PATH = old_path

    @patch("botpkg.handlers.commands.bot")
    @patch("botpkg.handlers.bot")
    def test_macros_handler_no_macros(self, mock_bot, mock_cmd_bot):
        from botpkg.handlers import handle_all_messages
        import botpkg.handlers.commands as _h
        old_path = _h.MACROS_PATH
        _h.MACROS_PATH = "/nonexistent/macros.yaml"
        try:
            msg = MagicMock()
            msg.text = "/macros"
            msg.from_user.id = 12345
            msg.chat.id = 99
            handle_all_messages(msg)
            reply_text = mock_cmd_bot.reply_to.call_args[0][1]
            self.assertIn("No macros", reply_text)
        finally:
            _h.MACROS_PATH = old_path


# ═══════════════════════════════════════════════════════════════════
# Wave 2: File Download
# ═══════════════════════════════════════════════════════════════════

class TestFileDownload(unittest.TestCase):
    """Test /download handler."""

    def setUp(self):
        from botpkg.handlers import _last_command
        _last_command.clear()

    @patch("botpkg.handlers.files.bot")
    @patch("botpkg.handlers.bot")
    def test_download_no_args(self, mock_bot, mock_file_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/download"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        reply_text = mock_file_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply_text)

    @patch("botpkg.handlers.files.bot")
    @patch("botpkg.handlers.bot")
    def test_download_file_not_found(self, mock_bot, mock_file_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/download /nonexistent/file.txt"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        reply_text = mock_file_bot.reply_to.call_args[0][1]
        self.assertIn("not found", reply_text)


# ═══════════════════════════════════════════════════════════════════
# Wave 2: Record & Audio duration validation
# ═══════════════════════════════════════════════════════════════════

class TestRecordAndAudio(unittest.TestCase):
    """Test /record and /audio handlers."""

    def setUp(self):
        from botpkg.handlers import _last_command
        _last_command.clear()

    @patch("botpkg.handlers.media.bot")
    @patch("botpkg.handlers.bot")
    def test_record_no_args(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/record"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        reply_text = mock_prod_bot.reply_to.call_args[0][1]
        self.assertIn("Recording", reply_text)  # Smart default: records 15s

    @patch("botpkg.handlers.media.bot")
    @patch("botpkg.handlers.bot")
    def test_record_max_duration(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/record 10m"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        reply_text = mock_prod_bot.reply_to.call_args[0][1]
        self.assertIn("5 minutes", reply_text)

    @patch("botpkg.handlers.media.bot")
    @patch("botpkg.handlers.bot")
    def test_audio_no_args(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/audio"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        reply_text = mock_prod_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply_text)


# ═══════════════════════════════════════════════════════════════════
# Wave 2: Notifications
# ═══════════════════════════════════════════════════════════════════

class TestNotifications(unittest.TestCase):
    """Test /notifications handler."""

    @patch("botpkg.handlers.productivity.subprocess")
    @patch("botpkg.handlers.productivity.bot")
    @patch("botpkg.handlers.productivity.os.path.exists", return_value=False)
    @patch("botpkg.handlers.bot")
    def test_notifications_no_db(self, mock_bot, mock_exists, mock_prod_bot, mock_subproc):
        from botpkg.handlers import handle_all_messages
        mock_subproc.run.return_value = MagicMock(stdout="Finder, Safari", returncode=0)
        msg = MagicMock()
        msg.text = "/notifications"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        mock_prod_bot.send_message.assert_called()


# ═══════════════════════════════════════════════════════════════════
# Wave 2: Inline Buttons / Callback Handler
# ═══════════════════════════════════════════════════════════════════

class TestInlineButtons(unittest.TestCase):
    """Test callback query handler."""

    @patch("botpkg.handlers.handle_help")
    @patch("botpkg.handlers.bot")
    def test_help_callback(self, mock_bot, mock_help):
        from botpkg.handlers import handle_callback_query
        call = MagicMock()
        call.from_user.id = 12345
        call.message.chat.id = 99
        call.data = "help:"
        handle_callback_query(call)
        mock_help.assert_called_once_with(None, 99, "/help")

    @patch("botpkg.handlers.take_and_send_screenshot")
    @patch("botpkg.handlers.bot")
    def test_screenshot_callback(self, mock_bot, mock_screenshot):
        from botpkg.handlers import handle_callback_query
        call = MagicMock()
        call.from_user.id = 12345
        call.message.chat.id = 99
        call.data = "screenshot:"
        handle_callback_query(call)
        mock_screenshot.assert_called_once_with(99)

    @patch("botpkg.handlers.bot")
    def test_unauthorized_callback_rejected(self, mock_bot):
        from botpkg.handlers import handle_callback_query
        call = MagicMock()
        call.from_user.id = 99999  # Unauthorized
        call.data = "help:"
        handle_callback_query(call)
        mock_bot.answer_callback_query.assert_called_with(call.id, "Unauthorized.")


# ═══════════════════════════════════════════════════════════════════
# Wave 2: New aliases in config
# ═══════════════════════════════════════════════════════════════════

class TestWave2Aliases(unittest.TestCase):
    """Test new aliases added for wave 2 commands."""

    def test_download_alias(self):
        self.assertEqual(resolve_alias("dl"), "download")

    def test_upload_alias(self):
        self.assertEqual(resolve_alias("ul"), "upload")

    def test_notifications_alias(self):
        self.assertEqual(resolve_alias("notifs"), "notifications")

    def test_note_alias(self):
        self.assertEqual(resolve_alias("n"), "note")

    def test_record_alias(self):
        self.assertEqual(resolve_alias("rec"), "record")

    def test_audio_alias(self):
        self.assertEqual(resolve_alias("mic"), "audio")


# ═══════════════════════════════════════════════════════════════════
# Wave 2: Config has all new special commands
# ═══════════════════════════════════════════════════════════════════

class TestWave2Config(unittest.TestCase):
    """Verify all wave 2 commands are registered in SPECIAL_COMMANDS."""

    def test_all_wave2_commands_in_special(self):
        from botpkg.config import SPECIAL_COMMANDS
        wave2 = ["download", "upload", "notifications", "note", "record", "audio", "macro", "macros"]
        for cmd in wave2:
            self.assertIn(cmd, SPECIAL_COMMANDS, f"Missing: {cmd}")


# ═══════════════════════════════════════════════════════════════════
# Wave 2: Note handler dispatch
# ═══════════════════════════════════════════════════════════════════

class TestNoteHandler(unittest.TestCase):
    """Test /note handler subcommand dispatch."""

    def setUp(self):
        from botpkg.handlers import _last_command
        _last_command.clear()

    @patch("botpkg.handlers.productivity.bot")
    @patch("botpkg.handlers.bot")
    def test_note_no_args_shows_usage(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/note"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        reply_text = mock_prod_bot.reply_to.call_args[0][1]
        self.assertIn("Usage", reply_text)

    @patch("botpkg.handlers.productivity.bot")
    @patch("botpkg.handlers.bot")
    def test_note_save(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        import botpkg.notes as _notes
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        tmp.write("[]")
        tmp.close()
        old = _notes.NOTES_FILE
        _notes.NOTES_FILE = tmp.name
        try:
            msg = MagicMock()
            msg.text = "/note save Remember to test"
            msg.from_user.id = 12345
            msg.chat.id = 99
            handle_all_messages(msg)
            reply_text = mock_prod_bot.reply_to.call_args[0][1]
            self.assertIn("#1", reply_text)
        finally:
            _notes.NOTES_FILE = old
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()

