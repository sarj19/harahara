"""Tests for Ollama integration — module, brain provider, and handler commands.

All tests mock subprocess — no actual Ollama needed.
"""
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ["TELEGRAM_BOT_TOKEN"] = "123456:FAKE-TOKEN-FOR-TESTING"
os.environ["TELEGRAM_AUTHORIZED_USER_ID"] = "12345"


# ═══════════════════════════════════════════════════════════════════
# ollama.py module tests
# ═══════════════════════════════════════════════════════════════════

class TestOllamaModule(unittest.TestCase):
    """Test the botpkg.ollama module functions."""

    @patch("botpkg.ollama.subprocess.run")
    @patch("botpkg.ollama.os.path.exists", return_value=False)
    def test_is_available_found_in_path(self, mock_exists, mock_run):
        from botpkg.ollama import is_available
        mock_run.return_value = MagicMock(stdout="/usr/local/bin/ollama")
        self.assertTrue(is_available())

    @patch("botpkg.ollama.subprocess.run")
    @patch("botpkg.ollama.os.path.exists", return_value=False)
    def test_is_available_not_found(self, mock_exists, mock_run):
        from botpkg.ollama import is_available
        mock_run.return_value = MagicMock(stdout="")
        self.assertFalse(is_available())

    @patch("botpkg.ollama.os.path.exists", return_value=True)
    def test_is_available_homebrew_path(self, mock_exists):
        from botpkg.ollama import is_available
        self.assertTrue(is_available())

    @patch("botpkg.ollama._find_ollama", return_value="/opt/homebrew/bin/ollama")
    @patch("botpkg.ollama.subprocess.run")
    def test_is_running_true(self, mock_run, mock_find):
        from botpkg.ollama import is_running
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(is_running())

    @patch("botpkg.ollama._find_ollama", return_value=None)
    def test_is_running_no_binary(self, mock_find):
        from botpkg.ollama import is_running
        self.assertFalse(is_running())

    @patch("botpkg.ollama._find_ollama", return_value="/opt/homebrew/bin/ollama")
    @patch("botpkg.ollama.subprocess.run")
    def test_list_models(self, mock_run, mock_find):
        from botpkg.ollama import list_models
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NAME                    ID              SIZE      MODIFIED\nllama3.2:1b             abc123          1.3 GB    2 hours ago\nqwen2.5:0.5b            def456          394 MB    1 day ago\n"
        )
        models = list_models()
        self.assertEqual(len(models), 2)
        self.assertIn("llama3.2:1b", models)
        self.assertIn("qwen2.5:0.5b", models)

    @patch("botpkg.ollama._find_ollama", return_value=None)
    def test_list_models_no_binary(self, mock_find):
        from botpkg.ollama import list_models
        self.assertEqual(list_models(), [])

    @patch("botpkg.ollama._find_ollama", return_value="/opt/homebrew/bin/ollama")
    @patch("botpkg.ollama.subprocess.run")
    def test_generate_success(self, mock_run, mock_find):
        from botpkg.ollama import generate
        mock_run.return_value = MagicMock(returncode=0, stdout="Hello! How can I help?", stderr="")
        result = generate("Say hello", model="llama3.2:1b")
        self.assertEqual(result, "Hello! How can I help?")
        # Verify the subprocess call
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "/opt/homebrew/bin/ollama")
        self.assertEqual(call_args[1], "run")
        self.assertEqual(call_args[2], "llama3.2:1b")

    @patch("botpkg.ollama._find_ollama", return_value=None)
    def test_generate_no_binary(self, mock_find):
        from botpkg.ollama import generate
        self.assertIsNone(generate("Say hello"))

    @patch("botpkg.ollama._find_ollama", return_value="/opt/homebrew/bin/ollama")
    @patch("botpkg.ollama.subprocess.run")
    def test_generate_timeout(self, mock_run, mock_find):
        import subprocess
        from botpkg.ollama import generate
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ollama", timeout=120)
        self.assertIsNone(generate("Say hello"))

    @patch("botpkg.ollama._find_ollama", return_value="/opt/homebrew/bin/ollama")
    @patch("botpkg.ollama.subprocess.run")
    def test_pull_model_success(self, mock_run, mock_find):
        from botpkg.ollama import pull_model
        mock_run.return_value = MagicMock(returncode=0, stdout="pulling...\nsuccess", stderr="")
        success, output = pull_model("llama3.2:1b")
        self.assertTrue(success)
        self.assertIn("success", output)

    @patch("botpkg.ollama._find_ollama", return_value="/opt/homebrew/bin/ollama")
    @patch("botpkg.ollama.subprocess.run")
    def test_pull_model_failure(self, mock_run, mock_find):
        from botpkg.ollama import pull_model
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error: model not found")
        success, output = pull_model("nonexistent:1b")
        self.assertFalse(success)

    def test_recommended_models_list(self):
        from botpkg.ollama import RECOMMENDED_MODELS
        self.assertGreaterEqual(len(RECOMMENDED_MODELS), 3)
        for model in RECOMMENDED_MODELS:
            self.assertIn("name", model)
            self.assertIn("size", model)
            self.assertIn("desc", model)


# ═══════════════════════════════════════════════════════════════════
# brain.py provider pattern tests
# ═══════════════════════════════════════════════════════════════════

class TestAIProviderDispatch(unittest.TestCase):
    """Test the _call_ai dispatcher in brain.py."""

    def setUp(self):
        import botpkg.brain
        botpkg.brain._detected_backend = None  # Reset cache between tests

    @patch("settings.BOT_AI_BACKEND", "gemini")
    @patch("botpkg.brain._call_gemini", return_value="Hello from Gemini")
    def test_gemini_backend(self, mock_gemini):
        from botpkg.brain import _call_ai
        result = _call_ai("test", 99)
        self.assertIsNotNone(result)
        response, backend = result
        self.assertEqual(response, "Hello from Gemini")
        self.assertEqual(backend, "gemini")
        mock_gemini.assert_called_once()

    @patch("settings.BOT_AI_BACKEND", "ollama")
    @patch("botpkg.brain._call_ollama", return_value="Hello from Ollama")
    def test_ollama_backend(self, mock_ollama):
        from botpkg.brain import _call_ai
        result = _call_ai("test", 99)
        self.assertIsNotNone(result)
        response, backend = result
        self.assertEqual(response, "Hello from Ollama")
        self.assertEqual(backend, "ollama")

    @patch("settings.BOT_AI_BACKEND", "ollama")
    @patch("botpkg.brain._call_gemini", return_value="Gemini fallback")
    @patch("botpkg.brain._call_ollama", return_value=None)
    def test_ollama_fallback_to_gemini(self, mock_ollama, mock_gemini):
        from botpkg.brain import _call_ai
        result = _call_ai("test", 99)
        self.assertIsNotNone(result)
        response, backend = result
        self.assertEqual(response, "Gemini fallback")
        self.assertEqual(backend, "gemini")

    @patch("settings.BOT_AI_BACKEND", "auto")
    @patch("botpkg.brain._find_gemini", return_value=None)
    @patch("botpkg.ollama.is_running", return_value=True)
    @patch("botpkg.ollama.is_available", return_value=True)
    @patch("botpkg.brain._call_ollama", return_value="Auto-detected Ollama")
    def test_auto_detect_ollama(self, mock_call, mock_avail, mock_run, mock_gemini):
        from botpkg.brain import _call_ai
        result = _call_ai("test", 99)
        self.assertIsNotNone(result)
        response, backend = result
        self.assertEqual(backend, "ollama")

    @patch("settings.BOT_AI_BACKEND", "auto")
    @patch("botpkg.brain._find_gemini", return_value="/usr/local/bin/gemini")
    @patch("botpkg.ollama.is_available", return_value=False)
    @patch("botpkg.brain._call_gemini", return_value="Auto-detected Gemini")
    def test_auto_detect_gemini(self, mock_call, mock_avail, mock_gemini):
        from botpkg.brain import _call_ai
        result = _call_ai("test", 99)
        self.assertIsNotNone(result)
        response, backend = result
        self.assertEqual(backend, "gemini")


# ═══════════════════════════════════════════════════════════════════
# Handler tests
# ═══════════════════════════════════════════════════════════════════

class TestOllamaSetupHandler(unittest.TestCase):
    """Test /ollamasetup handler."""

    def _make_message(self, text, user_id=12345, chat_id=99):
        msg = MagicMock()
        msg.text = text
        msg.from_user.id = user_id
        msg.chat.id = chat_id
        return msg

    @patch("botpkg.ollama.os.path.exists", return_value=False)
    @patch("botpkg.ollama.subprocess.run")
    @patch("botpkg.handlers.ai_cmds.bot")
    def test_not_installed(self, mock_bot, mock_run, mock_exists):
        mock_run.return_value = MagicMock(stdout="")
        from botpkg.handlers.ai_cmds import handle_ollamasetup
        msg = self._make_message("/ollamasetup")
        handle_ollamasetup(msg, 99, "/ollamasetup")
        sent = mock_bot.send_message.call_args[0][1]
        self.assertIn("not installed", sent)
        self.assertIn("brew install ollama", sent)


class TestAIHandler(unittest.TestCase):
    """Test /ai handler."""

    def _make_message(self, text, user_id=12345, chat_id=99):
        msg = MagicMock()
        msg.text = text
        msg.from_user.id = user_id
        msg.chat.id = chat_id
        return msg

    @patch("botpkg.handlers.ai_cmds.bot")
    def test_ai_no_args_shows_usage(self, mock_bot):
        from botpkg.handlers.ai_cmds import handle_ai
        msg = self._make_message("/ai")
        handle_ai(msg, 99, "/ai")
        reply = mock_bot.reply_to.call_args[0][1]
        self.assertIn("AI Query", reply)
        self.assertIn("Usage", reply)

    @patch("botpkg.handlers.ai_cmds.threading.Thread")
    @patch("botpkg.handlers.ai_cmds.bot")
    def test_ai_with_query_starts_thread(self, mock_bot, mock_thread):
        from botpkg.handlers.ai_cmds import handle_ai
        msg = self._make_message("/ai what time is it")
        handle_ai(msg, 99, "/ai what time is it")
        mock_bot.reply_to.assert_called_once()
        self.assertIn("Thinking", mock_bot.reply_to.call_args[0][1])
        mock_thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
