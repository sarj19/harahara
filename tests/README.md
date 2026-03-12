# Tests

## Quick Run

```bash
python3 -m unittest discover -s tests -v
```

Or run a specific test file:

```bash
python3 -m unittest tests.test_bot -v
python3 -m unittest tests.test_ollama -v
python3 -m unittest tests.test_brain -v
```

## Local CLI (no Telegram needed)

Test commands interactively without connecting to Telegram:

```bash
python3 local_bot.py              # Interactive REPL
python3 local_bot.py /help        # Single command
python3 local_bot.py /build       # Test build wizard flow
```

## Test Files

| File | Coverage |
|---|---|
| `test_bot.py` | Core handlers, dispatch, auth, YAML commands, runner, parsing, notes, macros, recording, shortcuts, schedules |
| `test_brain.py` | NLP pipeline: fuzzy matching, conversation memory, command parsing, system prompts, plan handling |
| `test_build.py` | Build wizard: command/schedule/macro creation, mode picker, save, quick build |
| `test_ollama.py` | Ollama module, AI provider dispatch (auto-detect, fallback), setup handler, /ai command |
| `test_chat_features.py` | Conversational parameter filling, paginated output, progressive tips |
| `test_personalization.py` | Aliases, themed responses, voice, keyboard, digest, config sanity |
| `test_heartbeat.py` | Heartbeat: emoji format, edit-on-consecutive, reset, disabled state |
| `test_usability.py` | Onboarding, menu, pins, streak, focus, command suggestions, natural shortcuts |
| `test_calendar_mail.py` | Calendar & email handler tests |

## Writing Tests

All tests mock external dependencies (Telegram bot, subprocess, filesystem). Pattern:

```python
@patch("botpkg.handlers.productivity.bot")
def test_my_handler(self, mock_bot):
    from botpkg.handlers.productivity import handle_my_command
    msg = MagicMock()
    msg.chat.id = 99
    handle_my_command(msg, 99, "/mycommand args")
    reply = mock_bot.reply_to.call_args[0][1]
    self.assertIn("expected text", reply)
```

Set fake env vars at the top of test files:

```python
import os
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:FAKE-TOKEN-FOR-TESTING"
os.environ["TELEGRAM_AUTHORIZED_USER_ID"] = "12345"
```
