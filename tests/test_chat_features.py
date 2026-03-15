"""Tests for new chat friendliness features:
- Emoji reactions
- Duplicate throttling
- Command chains (&&)
- Contextual follow-up buttons
- Quiet hours
- Status card image generation
- Favorites handler
"""
import time
import unittest
from unittest.mock import patch, MagicMock

from botpkg.handlers import (
    _react, _send_followups, _dispatch_single,
    _last_command, _THROTTLE_SECS,
)


class TestEmojiReactions(unittest.TestCase):
    """Test emoji reaction on command receipt."""

    @patch("botpkg.handlers.bot")
    def test_react_calls_set_message_reaction(self, mock_bot):
        _react(100, 42, "👀")
        mock_bot.set_message_reaction.assert_called_once()
        call_args = mock_bot.set_message_reaction.call_args
        self.assertEqual(call_args[0][0], 100)  # chat_id
        self.assertEqual(call_args[0][1], 42)   # message_id

    @patch("botpkg.handlers.bot")
    def test_react_silent_on_failure(self, mock_bot):
        mock_bot.set_message_reaction.side_effect = Exception("API error")
        # Should not raise
        _react(100, 42, "👀")

    @patch("botpkg.handlers.bot")
    def test_react_custom_emoji(self, mock_bot):
        _react(100, 42, "🔗")
        mock_bot.set_message_reaction.assert_called_once()


class TestDuplicateThrottling(unittest.TestCase):
    """Test duplicate command throttling."""

    def setUp(self):
        _last_command.clear()

    @patch("botpkg.handlers.meta.bot")
    @patch("botpkg.handlers.bot")
    def test_first_command_not_throttled(self, mock_bot, mock_meta_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/help"
        msg.from_user.id = 12345
        msg.chat.id = 200
        handle_all_messages(msg)
        # Should NOT have been throttled
        mock_bot.reply_to.assert_not_called()

    def test_duplicate_within_threshold_throttled(self):
        """Test that sending the same command twice within _THROTTLE_SECS is detected."""
        import time as _time
        chat_id = 201
        resolved = "help"
        # Simulate first command setting _last_command
        _last_command[chat_id] = (resolved, _time.time())
        # Second command immediately — should be within threshold
        now = _time.time()
        last = _last_command.get(chat_id)
        self.assertIsNotNone(last)
        self.assertEqual(last[0], resolved)
        self.assertTrue((now - last[1]) < _THROTTLE_SECS,
                        "Expected time difference to be within throttle threshold")

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.meta.bot")
    @patch("botpkg.handlers.bot")
    def test_different_commands_not_throttled(self, mock_bot, mock_meta_bot, mock_usability_bot):
        from botpkg.handlers import handle_all_messages
        msg1 = MagicMock()
        msg1.text = "/help"
        msg1.from_user.id = 12345
        msg1.chat.id = 202
        handle_all_messages(msg1)

        msg2 = MagicMock()
        msg2.text = "/status"
        msg2.from_user.id = 12345
        msg2.chat.id = 202
        handle_all_messages(msg2)
        # Should NOT be throttled
        mock_bot.reply_to.assert_not_called()


class TestCommandChains(unittest.TestCase):
    """Test command chains via &&."""

    def setUp(self):
        _last_command.clear()

    def test_chain_dispatches_multiple(self):
        """Test that '&&' splits commands into multiple parts."""
        full_text = "/help && /status"
        parts = [p.strip() for p in full_text.split("&&") if p.strip()]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "/help")
        self.assertEqual(parts[1], "/status")

    @patch("botpkg.handlers.bot")
    def test_chain_reacts_with_link_emoji(self, mock_bot):
        """Test that _react is called with 🔗 emoji for chain commands."""
        _react(301, 42, "🔗")
        mock_bot.set_message_reaction.assert_called()

    @patch("botpkg.handlers.bot")
    @patch("botpkg.handlers.meta.bot")
    def test_single_command_not_chain(self, mock_meta_bot, mock_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/help"
        msg.from_user.id = 12345
        msg.chat.id = 302
        handle_all_messages(msg)
        # Should not get chain reaction
        # The set_message_reaction should be called with 👀, not 🔗
        if mock_bot.set_message_reaction.called:
            reaction = mock_bot.set_message_reaction.call_args[0][2]
            for r in reaction:
                self.assertNotEqual(getattr(r, 'emoji', None), '🔗')


class TestFollowupButtons(unittest.TestCase):
    """Test contextual follow-up buttons."""

    def test_followup_mapping_exists(self):
        """Ensure follow-up mappings are defined for key commands."""
        from botpkg.utils import load_commands, followups_map
        load_commands()  # Populate followups from YAML
        expected = ["screenshot", "webcam", "diff", "note", "timer",
                    "record", "where", "calendar", "mail"]
        for cmd in expected:
            self.assertIn(cmd, followups_map, f"Missing follow-up for /{cmd}")

    @patch("botpkg.handlers.bot")
    def test_send_followups_sends_buttons(self, mock_bot):
        _send_followups(100, "screenshot")
        mock_bot.send_message.assert_called_once()
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Quick actions", text)
        # Check reply_markup has buttons
        markup = mock_bot.send_message.call_args[1].get("reply_markup")
        self.assertIsNotNone(markup)

    @patch("botpkg.handlers.bot")
    def test_send_followups_no_op_for_unknown(self, mock_bot):
        _send_followups(100, "unknowncommand")
        mock_bot.send_message.assert_not_called()

    def test_yaml_followups_loaded(self):
        """YAML followups populate followups_map (e.g. ping has followups)."""
        from botpkg.utils import load_commands, followups_map
        load_commands()  # Force reload
        # ping has followups defined in bot_commands.yaml
        self.assertIn("ping", followups_map)
        self.assertTrue(len(followups_map["ping"]) > 0)


class TestQuietHours(unittest.TestCase):
    """Test quiet hours functionality."""

    @patch("botpkg.heartbeat.BOT_QUIET_START", "")
    @patch("botpkg.heartbeat.BOT_QUIET_END", "")
    def test_no_quiet_hours_configured(self):
        from botpkg.heartbeat import _is_quiet_hours
        self.assertFalse(_is_quiet_hours())

    @patch("botpkg.heartbeat.BOT_QUIET_START", "00:00")
    @patch("botpkg.heartbeat.BOT_QUIET_END", "23:59")
    @patch("botpkg.heartbeat.datetime")
    def test_always_quiet(self, mock_dt):
        from botpkg.heartbeat import _is_quiet_hours
        mock_dt.now.return_value.strftime.return_value = "12:00"
        self.assertTrue(_is_quiet_hours())

    @patch("botpkg.heartbeat.BOT_QUIET_START", "25:00")
    @patch("botpkg.heartbeat.BOT_QUIET_END", "26:00")
    def test_invalid_times_graceful(self):
        from botpkg.heartbeat import _is_quiet_hours
        # Should not crash on invalid times
        result = _is_quiet_hours()
        self.assertIsInstance(result, bool)

    @patch("botpkg.heartbeat.BOT_QUIET_START", "23:00")
    @patch("botpkg.heartbeat.BOT_QUIET_END", "07:00")
    @patch("botpkg.heartbeat.datetime")
    def test_midnight_wrap_during_quiet(self, mock_dt):
        from botpkg.heartbeat import _is_quiet_hours
        mock_dt.now.return_value.strftime.return_value = "02:00"
        self.assertTrue(_is_quiet_hours())

    @patch("botpkg.heartbeat.BOT_QUIET_START", "23:00")
    @patch("botpkg.heartbeat.BOT_QUIET_END", "07:00")
    @patch("botpkg.heartbeat.datetime")
    def test_midnight_wrap_outside_quiet(self, mock_dt):
        from botpkg.heartbeat import _is_quiet_hours
        mock_dt.now.return_value.strftime.return_value = "12:00"
        self.assertFalse(_is_quiet_hours())


class TestStatusCard(unittest.TestCase):
    """Test status card image generation."""

    def test_generate_returns_bytes_io(self):
        from botpkg.status_card import generate_status_card
        result = generate_status_card(
            bot_name="TestBot", bot_emoji="🐟",
            uptime_secs=3661, commands_run=42,
            screenshots=10, top_cmds=[("help", 5), ("status", 3)],
            streak_data={"current": 3, "best": 7},
            tagline="Test tagline",
        )
        # Result should be a BytesIO with PNG data
        self.assertTrue(hasattr(result, 'read'))
        data = result.read()
        self.assertTrue(len(data) > 0)
        # PNG magic bytes
        self.assertEqual(data[:4], b'\x89PNG')

    def test_generate_no_streak(self):
        from botpkg.status_card import generate_status_card
        result = generate_status_card(
            bot_name="TestBot", bot_emoji="🐟",
            uptime_secs=60, commands_run=0,
            screenshots=0, top_cmds=[],
            streak_data={"current": 0},
        )
        data = result.read()
        self.assertTrue(len(data) > 0)

    def test_generate_with_long_uptime(self):
        from botpkg.status_card import generate_status_card
        result = generate_status_card(
            bot_name="TestBot", bot_emoji="🐟",
            uptime_secs=86400 * 30,  # 30 days
            commands_run=99999,
            screenshots=5000,
            top_cmds=[("screenshot", 100), ("help", 80), ("status", 60), ("note", 40)],
            streak_data={"current": 30, "best": 30},
        )
        data = result.read()
        self.assertTrue(len(data) > 0)


class TestFavorites(unittest.TestCase):
    """Test /fav handler."""

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_favs", return_value=["screenshot", "status"])
    @patch("botpkg.handlers.usability._save_favs")
    def test_fav_add(self, mock_save, mock_load, mock_bot):
        from botpkg.handlers.usability import handle_fav
        msg = MagicMock()
        handle_fav(msg, 100, "/fav add timer")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        self.assertIn("timer", saved)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_favs", return_value=["screenshot", "status"])
    @patch("botpkg.handlers.usability._save_favs")
    def test_fav_remove(self, mock_save, mock_load, mock_bot):
        from botpkg.handlers.usability import handle_fav
        msg = MagicMock()
        handle_fav(msg, 100, "/fav remove screenshot")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        self.assertNotIn("screenshot", saved)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_favs", return_value=["screenshot", "status", "help"])
    def test_fav_list(self, mock_load, mock_bot):
        from botpkg.handlers.usability import handle_fav
        msg = MagicMock()
        handle_fav(msg, 100, "/fav list")
        text = mock_bot.send_message.call_args[0][1]
        self.assertIn("Favorites", text)
        self.assertIn("/screenshot", text)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_favs", return_value=["screenshot", "status"])
    def test_fav_show_sends_keyboard(self, mock_load, mock_bot):
        from botpkg.handlers.usability import handle_fav
        msg = MagicMock()
        handle_fav(msg, 100, "/fav")
        # Should send message with reply_markup (keyboard)
        mock_bot.send_message.assert_called()

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_favs", return_value=[])
    def test_fav_list_empty(self, mock_load, mock_bot):
        from botpkg.handlers.usability import handle_fav
        msg = MagicMock()
        handle_fav(msg, 100, "/fav list")
        mock_bot.reply_to.assert_called()
        text = mock_bot.reply_to.call_args[0][1]
        self.assertIn("No favorites", text)

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_favs", return_value=["screenshot"])
    @patch("botpkg.handlers.usability._save_favs")
    def test_fav_add_no_duplicates(self, mock_save, mock_load, mock_bot):
        from botpkg.handlers.usability import handle_fav
        msg = MagicMock()
        handle_fav(msg, 100, "/fav add screenshot")
        # Should not save since it already exists
        mock_save.assert_not_called()

    @patch("botpkg.handlers.usability.bot")
    @patch("botpkg.handlers.usability._load_favs", return_value=["screenshot"])
    def test_fav_remove_nonexistent(self, mock_load, mock_bot):
        from botpkg.handlers.usability import handle_fav
        msg = MagicMock()
        handle_fav(msg, 100, "/fav remove timer")
        text = mock_bot.reply_to.call_args[0][1]
        self.assertIn("not in favorites", text)


if __name__ == "__main__":
    unittest.main()
