"""Handlers package — dispatch table and bot message routing.

Each handler group is in its own module:
  system.py        — screenshot, webcam, key, type, kill, open, quit, restartbot, logs
  files.py         — download, upload, file_receive
  productivity.py  — note, notifications, shortcut, schedule
  remind.py        — remind, say, voices
  media.py         — record, audio, webcamrecord
  integrations.py  — calendar, mail, googlesetup
  ai_cmds.py       — ai, ollamasetup
  meta.py          — help, status, brain, keyboard, last, snippet
  timer.py         — timer, pomodoro
  build.py         — interactive build wizard
  usability.py     — start, menu, focus, pin, streak, fav, settings
  commands.py      — YAML command handler, macros
"""
import time
import threading

import telebot

from botpkg import bot, logger, AUTHORIZED_USER_ID
from botpkg.config import (
    SPECIAL_COMMANDS, pending_confirmations, activity_stats,
)
from botpkg.utils import (
    load_commands, take_and_send_screenshot,
    get_cmd_name, resolve_alias, followups_map,
)

# ─── Duplicate throttling ───
_last_command = {}  # chat_id -> (cmd_name, timestamp)
_THROTTLE_SECS = 5

# ─── Import handler modules ───
from botpkg.handlers.system import (
    handle_screenshot, handle_webcam, handle_type, handle_url,
    handle_logs, handle_kill, handle_key,
    handle_open, handle_quit, handle_restartbot,
    handle_diff, handle_where,
)
from botpkg.handlers.files import (
    handle_download, handle_upload, handle_file_receive,
)
from botpkg.handlers.productivity import (
    handle_notifications, handle_note,
    handle_shortcut, handle_schedule,
)
from botpkg.handlers.remind import (
    handle_remind, handle_say, handle_voices,
)
from botpkg.handlers.media import (
    handle_record, handle_audio, handle_webcamrecord,
)
from botpkg.handlers.integrations import (
    handle_calendar, handle_mail, handle_googlesetup,
)
from botpkg.handlers.ai_cmds import (
    handle_ollamasetup, handle_ai,
)
from botpkg.handlers.meta import (
    handle_help, handle_help_callback, handle_status, handle_brain,
    handle_keyboard, handle_last, handle_snippet, record_command,
)
from botpkg.handlers.timer import (
    handle_timer, handle_pomodoro,
)
from botpkg.handlers.build import (
    handle_build, process_build_step, pending_build,
)
from botpkg.handlers.usability import (
    handle_start, handle_menu, handle_focus,
    handle_pin, handle_pins, handle_streak,
    handle_pretty_status, handle_tour_callback,
    handle_menu_callback, suggest_command,
    try_natural_shortcut, update_streak,
    handle_fav, handle_settings,
)
from botpkg.handlers.commands import (
    handle_yaml_command, handle_macro, handle_macros,
)


# ═══════════════════════════════════════════════════════════════════
# Dispatch table: command name (without /) → handler function
# ═══════════════════════════════════════════════════════════════════

# Dispatch table: built once at module level (not per-message).
DISPATCH_TABLE = {
    "help":         handle_help,
    "screenshot":   handle_screenshot,
    "webcam":       handle_webcam,
    "type":         handle_type,
    "url":          handle_url,
    "logs":         handle_logs,
    "kill":         handle_kill,

    "key":          handle_key,
    "open":         handle_open,
    "quit":         handle_quit,
    "restartbot":   handle_restartbot,
    "remind":       handle_remind,
    "status":       handle_status,
    "say":          handle_say,
    "voices":       handle_voices,
    "keyboard":     handle_keyboard,
    "download":     handle_download,
    "upload":       handle_upload,
    "notifications":handle_notifications,
    "note":         handle_note,
    "record":       handle_record,
    "audio":        handle_audio,
    "webcamrecord": handle_webcamrecord,
    "macro":        handle_macro,
    "macros":       handle_macros,
    "brain":        handle_brain,
    "calendar":     handle_calendar,
    "mail":         handle_mail,
    "googlesetup":  handle_googlesetup,
    "last":         handle_last,
    "diff":         handle_diff,
    "where":        handle_where,
    "timer":        handle_timer,
    "pomodoro":     handle_pomodoro,
    "snippet":      handle_snippet,
    "build":        handle_build,
    "start":        handle_start,
    "menu":         handle_menu,
    "focus":        handle_focus,
    "pin":          handle_pin,
    "pins":         handle_pins,
    "streak":       handle_streak,
    "status":       handle_pretty_status,
    "fav":          handle_fav,
    "settings":     handle_settings,
    "shortcut":     handle_shortcut,
    "schedule":     handle_schedule,
    "ollamasetup":  handle_ollamasetup,
    "ai":           handle_ai,
}


# ═══════════════════════════════════════════════════════════════════
# Dangerous command confirmation helper
# ═══════════════════════════════════════════════════════════════════

def _execute_confirmed_command(chat_id, pending):
    """Execute a previously confirmed dangerous command."""
    if time.time() - pending["time"] > 60:
        bot.send_message(chat_id, "⏰ Confirmation expired. Run the command again.")
        return
    commands = load_commands()
    cmd_name = pending["command"]
    entry = commands.get(cmd_name, {})
    shell_cmd = entry.get("cmd", "") if isinstance(entry, dict) else str(entry)
    from botpkg.runner import run_command_streaming
    try:
        run_command_streaming(chat_id, shell_cmd, 300, cmd_name)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")


# ═══════════════════════════════════════════════════════════════════
# Main message handler
# ═══════════════════════════════════════════════════════════════════

def _react(chat_id, message_id, emoji="👀"):
    """React to a message with an emoji (silent fail)."""
    try:
        bot.set_message_reaction(
            chat_id, message_id,
            [telebot.types.ReactionTypeEmoji(emoji)],
        )
    except Exception:
        pass  # Older API or reaction not supported


def _send_followups(chat_id, cmd_name, used_alias=False):
    """Send contextual follow-up buttons after a command.
    Checks YAML followups first, falls back to built-in defaults.
    """
    buttons = followups_map.get(cmd_name)
    
    # Progressive disclosure tip
    tip_text = ""
    if not used_alias:
        import random
        from botpkg.utils import get_aliases_for
        aliases = get_aliases_for(cmd_name)
        if aliases and random.random() < 0.2:  # 20% chance
            tip_text = f"💡 *Tip:* Next time, you can just type `/{aliases[0]}`"

    if not buttons and not tip_text:
        return

    markup = None
    if buttons:
        markup = telebot.types.InlineKeyboardMarkup(row_width=3)
        row = []
        for label, cmd in buttons:
            row.append(telebot.types.InlineKeyboardButton(label, callback_data=f"runcmd:{cmd.strip()}"))
        markup.row(*row)

    if buttons and tip_text:
        msg = f"{tip_text}\n\n⚡️ *Quick actions:*"
    elif tip_text:
        msg = tip_text
    else:
        msg = "💡 *Quick actions:*"
        
    bot.send_message(chat_id, msg, reply_markup=markup, parse_mode="Markdown")


def _dispatch_single(message, chat_id, text):
    """Dispatch a single command. Returns (cmd_name, used_alias) or (None, False)."""
    cmd = get_cmd_name(text)
    cmd_name = cmd.lstrip("/")

    # Resolve aliases
    resolved = resolve_alias(cmd_name)
    used_alias = False
    if resolved != cmd_name:
        text = "/" + resolved + text[len(cmd):]
        cmd_name = resolved
        used_alias = True

    # Track activity
    activity_stats["commands_run"] += 1
    activity_stats["commands_by_name"][cmd_name] = activity_stats["commands_by_name"].get(cmd_name, 0) + 1
    update_streak()
    from botpkg.persistence import save_stats
    save_stats(activity_stats)

    # Record in command history
    record_command(cmd_name, chat_id)

    # Dispatch to special command handlers
    if cmd_name in DISPATCH_TABLE:
        DISPATCH_TABLE[cmd_name](message, chat_id, text)
        return cmd_name, used_alias

    # Generic YAML command handler
    if not handle_yaml_command(message, chat_id, text):
        suggest_command(chat_id, cmd_name)

    return cmd_name, used_alias


@bot.message_handler(func=lambda msg: True, content_types=['text'])
def handle_all_messages(message):
    """Central router — auth check, NLP brain, alias resolution, dispatch."""
    if message.from_user.id != AUTHORIZED_USER_ID:
        from settings import UNAUTHORIZED_ID_FILE
        logger.warning(f"SECURITY ALERT: Unauthorized access attempt by user {message.from_user.id}")
        try:
            with open(UNAUTHORIZED_ID_FILE, "a") as f:
                f.write(f"{message.from_user.id}\n")
        except Exception:
            pass
        return

    import botpkg
    botpkg.last_interaction_time = time.time()
    # Reset heartbeat so next heartbeat is a new message (not an edit)
    from botpkg.heartbeat import reset_heartbeat_tracking
    reset_heartbeat_tracking()
    chat_id = message.chat.id

    # ─── Pending confirmation flow (legacy text fallback) ───
    if chat_id in pending_confirmations:
        pending = pending_confirmations.pop(chat_id)
        if message.text and message.text.strip().lower() == "yes":
            _execute_confirmed_command(chat_id, pending)
        else:
            bot.reply_to(message, "❌ Cancelled.")
        return

    # ─── Build wizard intercept (before NLP) ───
    if chat_id in pending_build:
        from botpkg.handlers.build import process_build_step
        if process_build_step(message, chat_id, message.text.strip()):
            return

    if not (message.text and message.text.strip().startswith("/")):
        # Natural language shortcuts (before NLP)
        if message.text and message.text.strip():
            if try_natural_shortcut(chat_id, message.text.strip()):
                return
        # NLP Brain: route plain text through the intelligent pipeline
        from settings import NLP_ENABLED
        if NLP_ENABLED and message.text and message.text.strip():
            from botpkg.brain import process_message
            process_message(message, chat_id, message.text.strip())
        return

    full_text = message.text.strip()

    # ─── Command chains: split on && ───
    if "&&" in full_text:
        parts = [p.strip() for p in full_text.split("&&") if p.strip()]
        if len(parts) > 1:
            _react(chat_id, message.message_id, "🔗")
            for part in parts:
                if not part.startswith("/"):
                    part = "/" + part
                _dispatch_single(message, chat_id, part)
            return

    text = full_text
    cmd = get_cmd_name(text)
    cmd_name = cmd.lstrip("/")
    resolved = resolve_alias(cmd_name)

    # ─── Duplicate throttling ───
    now = time.time()
    last = _last_command.get(chat_id)
    if last and last[0] == resolved and (now - last[1]) < _THROTTLE_SECS:
        bot.reply_to(message, f"⏱ `/{resolved}` is already running.", parse_mode="Markdown")
        return
    _last_command[chat_id] = (resolved, now)

    # ─── Emoji reaction ───
    _react(chat_id, message.message_id)

    # ─── Dispatch ───
    res = _dispatch_single(message, chat_id, text)

    # ─── Contextual follow-up buttons ───
    if res and res[0]:
        _send_followups(chat_id, res[0], res[1])


# ═══════════════════════════════════════════════════════════════════
# Inline button callback handler
# ═══════════════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handle inline keyboard button presses."""
    if call.from_user.id != AUTHORIZED_USER_ID:
        bot.answer_callback_query(call.id, "Unauthorized.")
        return

    chat_id = call.message.chat.id
    data = call.data or ""
    action, _, param = data.partition(":")

    bot.answer_callback_query(call.id)  # Dismiss the loading spinner

    if action == "repeat" and param:
        fake_msg = call.message
        fake_msg.from_user = call.from_user
        fake_msg.text = f"/{param}"
        handle_all_messages(fake_msg)
    elif action == "screenshot":
        take_and_send_screenshot(chat_id)
    elif action == "help":
        handle_help(None, chat_id, "/help")
    elif data.startswith("help_"):
        handle_help_callback(call)
    elif action == "confirm_cmd" and param:
        # Inline confirmation button pressed
        if chat_id in pending_confirmations:
            pending = pending_confirmations.pop(chat_id)
            _execute_confirmed_command(chat_id, pending)
        else:
            bot.send_message(chat_id, "⏰ Confirmation expired. Run the command again.")
    elif action == "cancel_cmd":
        pending_confirmations.pop(chat_id, None)
        bot.send_message(chat_id, "❌ Cancelled.")
    elif action == "logspage" and param:
        parts = param.split(":")
        if len(parts) == 2:
            n = parts[0]
            page = int(parts[1])
            from botpkg.handlers.system import handle_logs
            handle_logs(None, chat_id, f"/logs {n}", page, call.message.message_id)
    elif action == "logsall" and param:
        parts = param.split(":")
        if len(parts) >= 1:
            n = parts[0]
            from botpkg.handlers.system import handle_logs_all
            handle_logs_all(chat_id, n)
    elif action == "undo_kill" and param:
        bot.send_message(chat_id, f"📂 Relaunching {param}...")
        from botpkg.handlers.system import handle_open
        fake_msg = call.message
        fake_msg.from_user = call.from_user
        fake_msg.text = f"/open {param}"
        handle_open(fake_msg, chat_id, fake_msg.text)
    elif action == "undo_note" and param:
        if param.isdigit():
            note_id = int(param)
            from botpkg.notes import _deleted_notes, save_note
            if note_id in _deleted_notes:
                restored_text = _deleted_notes.pop(note_id)
                if restored_text:
                    restored_id = save_note(restored_text)
                    bot.send_message(chat_id, f"✅ Note restored as #{restored_id}.")
                else:
                    bot.send_message(chat_id, "❌ Note text was empty.")
            else:
                bot.send_message(chat_id, "❌ Note could not be restored (expired).")
    elif action == "brain_run" and param:
        from botpkg.brain import _execute_single_command
        from botpkg.memory import add_to_history
        add_to_history(chat_id, "assistant", f"[executing: {param}]")
        threading.Thread(
            target=_execute_single_command, args=(chat_id, param), daemon=True
        ).start()
    elif action == "brain_cancel":
        bot.send_message(chat_id, "❌ Cancelled.")
    elif action == "brain_plan" and param:
        from botpkg.brain import execute_plan
        execute_plan(chat_id, param)
    elif action == "tour" and param:
        handle_tour_callback(chat_id, param)
    elif action == "menu" and param:
        handle_menu_callback(chat_id, param)
    elif action == "runcmd" and param:
        # Execute a command by simulating a message
        fake_msg = call.message
        fake_msg.from_user = call.from_user
        fake_msg.text = param
        handle_all_messages(fake_msg)
    else:
        logger.warning(f"Unknown callback data: {data}")


# ═══════════════════════════════════════════════════════════════════
# File receiving handler (incoming documents, photos, audio, video)
# ═══════════════════════════════════════════════════════════════════

@bot.message_handler(content_types=['document', 'photo', 'audio', 'video'])
def _handle_file_receive(message):
    """Route file receives to the files handler."""
    handle_file_receive(message)
