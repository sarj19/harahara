#!/usr/bin/env python3
"""Local CLI to test bot commands without Telegram.

Usage:
  python3 local_bot.py                    # Interactive REPL
  python3 local_bot.py /screenshot        # Run single command
  python3 local_bot.py /build             # Test build wizard flow

Output is printed to stdout instead of sent via Telegram.
"""
import sys
import os
import types
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class LocalBot:
    """Mock bot that prints to stdout instead of sending via Telegram."""

    def __init__(self, chat_id):
        self.chat_id = chat_id
        self._last_msg_id = 0

    def _make_result(self):
        self._last_msg_id += 1
        msg = types.SimpleNamespace()
        msg.message_id = self._last_msg_id
        msg.chat = types.SimpleNamespace(id=self.chat_id)
        return msg

    # ─── Decorator stubs (called at import time) ───
    def message_handler(self, **kwargs):
        def decorator(func):
            return func
        return decorator

    def callback_query_handler(self, **kwargs):
        def decorator(func):
            return func
        return decorator

    def send_message(self, chat_id, text, **kwargs):
        pm = kwargs.get("parse_mode", "")
        tag = f" [{pm}]" if pm else ""
        print(f"\n\033[36m{'─' * 50}\033[0m")
        print(f"\033[36m📨 BOT{tag}:\033[0m {text}")
        # Show keyboard buttons if present
        markup = kwargs.get("reply_markup")
        if markup and hasattr(markup, "keyboard"):
            for row in markup.keyboard:
                btns = "  ".join(
                    f"[{b.get('text', b) if isinstance(b, dict) else b.text}]"
                    for b in row
                )
                print(f"  \033[33m{btns}\033[0m")
        return self._make_result()

    def reply_to(self, message, text, **kwargs):
        return self.send_message(self.chat_id, text, **kwargs)

    def edit_message_text(self, text, **kwargs):
        print(f"\033[35m✏️  EDIT:\033[0m {text}")
        return self._make_result()

    def answer_callback_query(self, *args, **kwargs):
        pass


def make_fake_message(text, chat_id, user_id):
    """Create a mock Telegram message object."""
    msg = types.SimpleNamespace()
    msg.text = text
    msg.chat = types.SimpleNamespace(id=chat_id)
    msg.from_user = types.SimpleNamespace(id=user_id)
    msg.message_id = int(time.time())
    msg.reply_to_message = None
    msg.content_type = "text"
    return msg


def main():
    # Load settings first
    import settings
    chat_id = int(settings.TELEGRAM_AUTHORIZED_USER_ID)
    user_id = chat_id

    # Monkey-patch the bot BEFORE importing handlers (decorators run at import)
    local_bot = LocalBot(chat_id)
    import botpkg
    botpkg.bot = local_bot
    botpkg.AUTHORIZED_USER_ID = user_id

    # Now import handlers — decorators will use our LocalBot stubs
    import botpkg.handlers
    import botpkg.handlers.system
    import botpkg.handlers.files
    import botpkg.handlers.productivity
    import botpkg.handlers.meta
    import botpkg.handlers.timer
    import botpkg.handlers.build
    import botpkg.handlers.commands
    import botpkg.handlers.usability
    for mod in [botpkg.handlers, botpkg.handlers.system, botpkg.handlers.files,
                botpkg.handlers.productivity, botpkg.handlers.meta,
                botpkg.handlers.timer, botpkg.handlers.build,
                botpkg.handlers.commands, botpkg.handlers.usability]:
        if hasattr(mod, "bot"):
            mod.bot = local_bot

    from botpkg.handlers import handle_all_messages

    print("\033[1m🐟 harahara local CLI\033[0m")
    print("Type commands as you would in Telegram (e.g. /help, /build)")
    print("Type 'quit' or Ctrl+C to exit.\n")

    # Single command mode
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        msg = make_fake_message(text, chat_id, user_id)
        handle_all_messages(msg)
        return

    # Interactive REPL
    while True:
        try:
            text = input("\033[32m❯ \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\033[90mBye!\033[0m")
            break

        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            print("\033[90mBye!\033[0m")
            break

        msg = make_fake_message(text, chat_id, user_id)
        try:
            handle_all_messages(msg)
        except Exception as e:
            print(f"\033[31m❌ Error: {e}\033[0m")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
