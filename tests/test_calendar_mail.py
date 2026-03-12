"""Tests for Calendar & Email integration: Google auth, services, handlers, and fallback."""
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:FAKE-TOKEN-FOR-TESTING")
os.environ.setdefault("TELEGRAM_AUTHORIZED_USER_ID", "12345")


# ═══════════════════════════════════════════════════════════════════
# Google Auth
# ═══════════════════════════════════════════════════════════════════

class TestGoogleAuth(unittest.TestCase):
    """Test Google OAuth2 helper functions."""

    def test_is_google_configured_no_token(self):
        from botpkg.google_auth import is_google_configured
        with patch("botpkg.google_auth.GOOGLE_TOKEN_PATH", "/nonexistent/path"):
            with patch("botpkg.google_auth.GOOGLE_CREDENTIALS_PATH", "/nonexistent/path2"):
                self.assertFalse(is_google_configured())

    def test_setup_instructions_returned(self):
        from botpkg.google_auth import get_setup_instructions
        instructions = get_setup_instructions()
        self.assertIn("Google Cloud Console", instructions)
        self.assertIn("OAuth", instructions)
        self.assertIn("google_credentials.json", instructions)

    def test_has_valid_token_no_file(self):
        from botpkg.google_auth import has_valid_token
        with patch("botpkg.google_auth.GOOGLE_TOKEN_PATH", "/nonexistent"):
            self.assertFalse(has_valid_token())


# ═══════════════════════════════════════════════════════════════════
# Google Services — Formatting
# ═══════════════════════════════════════════════════════════════════

class TestServiceFormatting(unittest.TestCase):
    """Test Calendar and Gmail formatting functions."""

    def test_format_events_empty(self):
        from botpkg.google_services import format_events_text
        result = format_events_text([], "Today")
        self.assertIn("no today", result.lower())

    def test_format_events_with_data(self):
        from botpkg.google_services import format_events_text
        events = [
            {"summary": "Team Standup", "start": "2026-03-13T09:00:00", "end": "2026-03-13T09:30:00", "location": ""},
            {"summary": "Lunch", "start": "2026-03-13T12:00:00", "end": "2026-03-13T13:00:00", "location": "Cafe"},
        ]
        result = format_events_text(events, "Today")
        self.assertIn("Team Standup", result)
        self.assertIn("Lunch", result)
        self.assertIn("Cafe", result)
        self.assertIn("09:00", result)

    def test_format_events_all_day(self):
        from botpkg.google_services import format_events_text
        events = [{"summary": "Holiday", "start": "2026-03-13", "end": "2026-03-14", "location": ""}]
        result = format_events_text(events, "Today")
        self.assertIn("All day", result)

    def test_format_inbox_empty(self):
        from botpkg.google_services import format_inbox_text
        result = format_inbox_text([])
        self.assertIn("No messages", result)

    def test_format_inbox_with_data(self):
        from botpkg.google_services import format_inbox_text
        messages = [
            {"id": "abc12345", "from": "John Doe <john@test.com>", "subject": "Hello", "snippet": "Hi there", "date": "Mon, 13 Mar 2026", "unread": True},
            {"id": "def67890", "from": "Jane <jane@test.com>", "subject": "Re: Project", "snippet": "Thanks", "date": "Mon, 13 Mar 2026", "unread": False},
        ]
        result = format_inbox_text(messages)
        self.assertIn("Hello", result)
        self.assertIn("John Doe", result)
        self.assertIn("🔵", result)  # Unread indicator
        self.assertIn("abc1234", result)  # Short message ID

    def test_format_inbox_truncates_long_sender(self):
        from botpkg.google_services import format_inbox_text
        messages = [{"id": "x", "from": "A Very Long Sender Name That Should Be Truncated", "subject": "Test", "snippet": "", "date": "", "unread": False}]
        result = format_inbox_text(messages)
        self.assertIn("...", result)


# ═══════════════════════════════════════════════════════════════════
# Body Extraction
# ═══════════════════════════════════════════════════════════════════

class TestBodyExtraction(unittest.TestCase):
    """Test Gmail message body extraction."""

    def test_extract_plain_text(self):
        import base64
        from botpkg.google_services import _extract_body
        encoded = base64.urlsafe_b64encode(b"Hello world").decode()
        payload = {"mimeType": "text/plain", "body": {"data": encoded}}
        self.assertEqual(_extract_body(payload), "Hello world")

    def test_extract_from_parts(self):
        import base64
        from botpkg.google_services import _extract_body
        encoded = base64.urlsafe_b64encode(b"Part body").decode()
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded}},
                {"mimeType": "text/html", "body": {"data": "irrelevant"}},
            ]
        }
        self.assertEqual(_extract_body(payload), "Part body")

    def test_extract_no_body(self):
        from botpkg.google_services import _extract_body
        payload = {"mimeType": "text/html", "body": {}}
        result = _extract_body(payload)
        self.assertIn("Could not extract", result)


# ═══════════════════════════════════════════════════════════════════
# Handlers — Fallback behavior
# ═══════════════════════════════════════════════════════════════════

class TestCalendarHandler(unittest.TestCase):
    """Test /calendar handler fallback."""

    @patch("botpkg.handlers.integrations.bot")
    @patch("botpkg.handlers.integrations.subprocess.run")
    @patch("botpkg.handlers.bot")
    def test_calendar_not_configured_shows_instructions(self, mock_bot, mock_run, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        # AppleScript fails
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        msg = MagicMock()
        msg.text = "/calendar"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        calls = mock_prod_bot.send_message.call_args_list
        text = calls[-1][0][1]
        self.assertIn("Calendar not configured", text)
        self.assertIn("googlesetup", text)


class TestMailHandler(unittest.TestCase):
    """Test /mail handler fallback."""

    @patch("botpkg.handlers.integrations.bot")
    @patch("botpkg.handlers.integrations.subprocess.run")
    @patch("botpkg.handlers.bot")
    def test_mail_not_configured_shows_instructions(self, mock_bot, mock_run, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        msg = MagicMock()
        msg.text = "/mail"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        calls = mock_prod_bot.send_message.call_args_list
        text = calls[-1][0][1]
        self.assertIn("Email not configured", text)
        self.assertIn("googlesetup", text)


class TestGoogleSetupHandler(unittest.TestCase):
    """Test /googlesetup handler."""

    @patch("botpkg.handlers.integrations.bot")
    @patch("botpkg.handlers.bot")
    def test_googlesetup_shows_instructions_when_no_creds(self, mock_bot, mock_prod_bot):
        from botpkg.handlers import handle_all_messages
        msg = MagicMock()
        msg.text = "/googlesetup"
        msg.from_user.id = 12345
        msg.chat.id = 99
        handle_all_messages(msg)
        # Should show instructions or "not installed" message
        self.assertTrue(mock_prod_bot.send_message.called or mock_prod_bot.reply_to.called)


# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

class TestCalendarMailConfig(unittest.TestCase):
    """Test calendar/mail in config."""

    @classmethod
    def setUpClass(cls):
        from botpkg.utils import load_commands
        load_commands()  # Populates SPECIAL_COMMANDS and aliases

    def test_commands_registered(self):
        from botpkg.config import SPECIAL_COMMANDS
        self.assertIn("calendar", SPECIAL_COMMANDS)
        self.assertIn("mail", SPECIAL_COMMANDS)
        self.assertIn("googlesetup", SPECIAL_COMMANDS)

    def test_aliases(self):
        from botpkg.utils import resolve_alias
        self.assertEqual(resolve_alias("cal"), "calendar")
        self.assertEqual(resolve_alias("email"), "mail")
        self.assertEqual(resolve_alias("gmail"), "mail")
        self.assertEqual(resolve_alias("today"), "calendar")


if __name__ == "__main__":
    unittest.main()
