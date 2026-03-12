import unittest
from unittest.mock import patch, MagicMock
import time
import threading
import botpkg.heartbeat
import botpkg


class TestHeartbeat(unittest.TestCase):
    def setUp(self):
        """Reset heartbeat state before each test."""
        botpkg.heartbeat._last_hb_msg_id = None
        botpkg.heartbeat._hb_count = 0
        botpkg.heartbeat._stop_event.clear()

    def tearDown(self):
        """Ensure stop event is set after each test."""
        botpkg.heartbeat._stop_event.set()

    @patch("botpkg.heartbeat.bot")
    @patch("botpkg.heartbeat.logger")
    @patch("botpkg.heartbeat.HEARTBEAT_INTERVAL", 1)
    def test_heartbeat_loop_sends_emoji(self, mock_logger, mock_bot):
        """Test that heartbeat sends BOT_EMOJI + 💓 format."""
        botpkg.heartbeat._last_hb_msg_id = None
        botpkg.heartbeat._last_hb_text = ""

        mock_msg = MagicMock()
        mock_msg.message_id = 123
        mock_bot.send_message.return_value = mock_msg

        # Mock _stop_event.wait to return False once (run one iteration) then True (stop)
        call_count = [0]
        def fast_wait(timeout=None):
            call_count[0] += 1
            if call_count[0] >= 2:
                return True  # Stop loop
            return False  # Continue (one iteration)

        with patch.object(botpkg.heartbeat._stop_event, 'wait', side_effect=fast_wait):
            botpkg.heartbeat._heartbeat_loop()

        mock_bot.send_message.assert_called_once()
        from settings import BOT_EMOJI
        sent_text = mock_bot.send_message.call_args[0][1]
        self.assertIn(BOT_EMOJI, sent_text)
        self.assertIn("💓", sent_text)

    @patch("botpkg.heartbeat.bot")
    @patch("botpkg.heartbeat.logger")
    @patch("botpkg.heartbeat.HEARTBEAT_INTERVAL", 1)
    def test_heartbeat_edits_consecutive(self, mock_logger, mock_bot):
        """Test that consecutive heartbeats edit the message instead of sending new one."""
        mock_msg = MagicMock()
        mock_msg.message_id = 42
        mock_bot.send_message.return_value = mock_msg

        botpkg.heartbeat._last_hb_msg_id = None
        botpkg.heartbeat._last_hb_text = ""

        # Set HEARTBEAT_INTERVAL to very small so Event.wait returns quickly
        original_interval = botpkg.heartbeat.HEARTBEAT_INTERVAL
        # We need to patch the wait to run fast — use a side effect that counts calls
        call_count = [0]
        original_wait = botpkg.heartbeat._stop_event.wait

        def fast_wait(timeout=None):
            call_count[0] += 1
            if call_count[0] >= 4:
                botpkg.heartbeat._stop_event.set()
                return True  # Simulate stop
            return False  # Simulate not stopped (loop continues)

        with patch.object(botpkg.heartbeat._stop_event, 'wait', side_effect=fast_wait):
            botpkg.heartbeat._heartbeat_loop()

        # First call sends, subsequent should edit
        self.assertEqual(mock_bot.send_message.call_count, 1)
        self.assertTrue(mock_bot.edit_message_text.called)

    def test_reset_heartbeat_tracking(self):
        """Test that reset_heartbeat_tracking clears the tracked message."""
        botpkg.heartbeat._last_hb_msg_id = 123
        botpkg.heartbeat._hb_count = 5
        botpkg.heartbeat.reset_heartbeat_tracking()
        self.assertIsNone(botpkg.heartbeat._last_hb_msg_id)
        self.assertEqual(botpkg.heartbeat._hb_count, 0)

    @patch("botpkg.heartbeat.bot")
    @patch("botpkg.heartbeat.logger")
    @patch("botpkg.heartbeat.HEARTBEAT_INTERVAL", 0)
    def test_heartbeat_disabled_when_zero(self, mock_logger, mock_bot):
        """Test that start_heartbeat does nothing when interval is 0."""
        botpkg.heartbeat.start_heartbeat()
        mock_bot.send_message.assert_not_called()
