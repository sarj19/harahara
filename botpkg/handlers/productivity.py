"""Productivity handlers: note, notifications, shortcut, schedule."""
import os
import subprocess
import threading

from botpkg import bot, logger
from botpkg.utils import parse_duration


# ═══════════════════════════════════════════════════════════════════
# Notifications
# ═══════════════════════════════════════════════════════════════════

def handle_notifications(message, chat_id, text):
    """Show recent macOS notifications."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    count = 10
    if args and args.isdigit():
        count = int(args)

    db_path = os.path.expanduser(
        "~/Library/Group Containers/group.com.apple.usernoted/db2/db"
    )
    if os.path.exists(db_path):
        query = (
            f'sqlite3 "{db_path}" '
            '"SELECT '
            "json_extract(data, '$.req.titl') AS title, "
            "json_extract(data, '$.req.body') AS body, "
            "datetime(rec_ts + 978307200, 'unixepoch', 'localtime') AS time "
            f'FROM record ORDER BY rec_ts DESC LIMIT {count};"'
        )
        try:
            result = subprocess.run(
                query, shell=True, capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if output:
                lines = output.split("\n")
                formatted = []
                for line in lines:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        title = parts[0].strip() or "(no title)"
                        body = parts[1].strip() or ""
                        ts = parts[2].strip()
                        entry = f"  *{title}*"
                        if body:
                            entry += f"\n    {body}"
                        entry += f"\n    _{ts}_"
                        formatted.append(entry)
                    else:
                        formatted.append(f"  {line}")
                bot.send_message(
                    chat_id,
                    f"🔔 *Recent Notifications ({len(formatted)}):*\n\n" + "\n\n".join(formatted),
                    parse_mode="Markdown",
                )
                return
        except Exception as e:
            logger.error(f"Notification DB query failed: {e}")

    # Fallback
    try:
        script = (
            'tell application "System Events" to get the name of every process '
            'whose background only is false'
        )
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=10
        )
        bot.send_message(
            chat_id,
            "⚠️ Could not read notification database.\n"
            "This may require Full Disk Access for your terminal.\n\n"
            f"Running apps: `{result.stdout.strip()}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.send_message(chat_id, f"❌ Notifications error: {e}")


# ═══════════════════════════════════════════════════════════════════
# Notes
# ═══════════════════════════════════════════════════════════════════

def handle_note(message, chat_id, text):
    """Handle /note save|list|search|delete subcommands."""
    from botpkg.notes import save_note, list_notes, search_notes, delete_note, get_backend, get_backend_label

    args = text.split(" ", 2)
    if len(args) < 2:
        backend = get_backend_label()
        bot.reply_to(
            message,
            f"📝 Notes ({backend})\n\n"
            "Usage:\n"
            "  `/note save <text>` — save a note\n"
            "  `/note list` — list all notes\n"
            "  `/note search <query>` — search notes\n"
            "  `/note delete <id>` — delete a note\n"
            "  `/note backend` — show current storage backend\n\n"
            "_Set_ `BOT_NOTES_BACKEND` _to_ `local`, `apple`, _or_ `google`",
            parse_mode="Markdown",
        )
        return

    subcmd = args[1].strip().lower()
    rest = args[2].strip() if len(args) > 2 else ""

    if subcmd == "backend":
        backend = get_backend_label()
        bot.reply_to(message, f"📝 Current backend: {backend}\n\nSet `BOT_NOTES_BACKEND` in .env to `local`, `apple`, or `google`.", parse_mode="Markdown")

    elif subcmd == "save":
        if not rest:
            bot.reply_to(message, "Usage: `/note save <text>`", parse_mode="Markdown")
            return
        note_id = save_note(rest)
        bot.reply_to(message, f"📝 Note #{note_id} saved.")

    elif subcmd == "list":
        notes = list_notes()
        if not notes:
            bot.reply_to(message, "📝 No notes yet. Use `/note save <text>` to add one.", parse_mode="Markdown")
            return
        lines = []
        for n in notes[-20:]:
            lines.append(f"  `#{n['id']}` {n['text'][:60]}{'...' if len(n['text']) > 60 else ''}")
        count_note = f" (showing last 20 of {len(notes)})" if len(notes) > 20 else ""
        bot.send_message(
            chat_id,
            f"📝 *Notes{count_note}:*\n\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    elif subcmd == "search":
        if not rest:
            bot.reply_to(message, "Usage: `/note search <query>`", parse_mode="Markdown")
            return
        results = search_notes(rest)
        if not results:
            bot.reply_to(message, f"📝 No notes matching: `{rest}`", parse_mode="Markdown")
            return
        lines = [f"  `#{n['id']}` {n['text'][:60]}" for n in results[:20]]
        bot.send_message(
            chat_id,
            f"📝 *Search results for '{rest}' ({len(results)}):*\n\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    elif subcmd in ("delete", "del", "rm"):
        if not rest or not rest.lstrip("#").isdigit():
            bot.reply_to(message, "Usage: `/note delete <id>`", parse_mode="Markdown")
            return
        note_id = int(rest.lstrip("#"))
        deleted = delete_note(note_id)
        if deleted:
            from botpkg.notes import _deleted_notes
            _deleted_notes[note_id] = deleted["text"] if isinstance(deleted, dict) else ""
            import telebot
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("↩️ Undo", callback_data=f"undo_note:{note_id}"))
            bot.reply_to(message, f"🗑 Note #{note_id} deleted.", reply_markup=markup)
        else:
            bot.reply_to(message, f"❌ Note #{note_id} not found.")
    else:
        bot.reply_to(message, f"Unknown subcommand: `{subcmd}`. Use save, list, search, or delete.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# Shortcut — run macOS Shortcuts.app shortcuts
# ═══════════════════════════════════════════════════════════════════

def handle_shortcut(message, chat_id, text):
    """Handle /shortcut [name] — list or run macOS Shortcuts."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""

    if not args or args.lower() == "list":
        # List available shortcuts
        try:
            result = subprocess.run(
                ["shortcuts", "list"],
                capture_output=True, text=True, timeout=10,
            )
            output = result.stdout.strip()
            if not output:
                bot.send_message(chat_id, "📎 No shortcuts found.\n\nCreate shortcuts in the Shortcuts app first.")
                return
            shortcuts = output.split("\n")
            lines = [f"  `{s.strip()}`" for s in shortcuts[:30]]
            count_note = f" (showing 30 of {len(shortcuts)})" if len(shortcuts) > 30 else ""
            bot.send_message(
                chat_id,
                f"📎 *Available Shortcuts{count_note}:*\n\n" + "\n".join(lines)
                + "\n\n💡 Run one with: `/shortcut <name>`",
                parse_mode="Markdown",
            )
        except FileNotFoundError:
            bot.send_message(chat_id, "❌ `shortcuts` CLI not found. Requires macOS 12+.", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Shortcuts error: {e}")
            logger.error(f"Shortcuts list error: {e}")
        return

    # Run a named shortcut
    shortcut_name = args
    bot.reply_to(message, f"📎 Running shortcut: `{shortcut_name}`...", parse_mode="Markdown")

    def run_shortcut():
        try:
            result = subprocess.run(
                ["shortcuts", "run", shortcut_name],
                capture_output=True, text=True, timeout=120,
            )
            output = (result.stdout + result.stderr).strip()
            if result.returncode == 0:
                if output:
                    if len(output) > 4000:
                        output = output[:4000] + "\n...[truncated]"
                    bot.send_message(chat_id, f"✅ *Shortcut complete:* `{shortcut_name}`\n```\n{output}\n```", parse_mode="Markdown")
                else:
                    bot.send_message(chat_id, f"✅ Shortcut `{shortcut_name}` completed.", parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"❌ Shortcut `{shortcut_name}` failed (exit {result.returncode}):\n`{output[:500]}`", parse_mode="Markdown")
        except subprocess.TimeoutExpired:
            bot.send_message(chat_id, f"❌ Shortcut `{shortcut_name}` timed out (120s limit).", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Shortcut error: {e}")
            logger.error(f"Shortcut run error: {e}")

    threading.Thread(target=run_shortcut, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# Schedule — manage scheduled tasks (schedules.yaml)
# ═══════════════════════════════════════════════════════════════════

def handle_schedule(message, chat_id, text):
    """Handle /schedule [list|add|remove] — manage scheduled tasks."""
    import yaml
    from settings import SCHEDULES_PATH

    args = text.split(" ", 1)[1].strip() if " " in text else ""
    parts = args.split(" ", 1) if args else [""]
    subcmd = parts[0].lower()

    # Default or explicit list
    if not subcmd or subcmd == "list":
        _schedule_list(chat_id, SCHEDULES_PATH)
        return

    if subcmd == "add":
        rest = parts[1].strip() if len(parts) > 1 else ""
        _schedule_add(message, chat_id, rest, SCHEDULES_PATH)
        return

    if subcmd in ("remove", "rm", "delete", "del"):
        rest = parts[1].strip() if len(parts) > 1 else ""
        _schedule_remove(message, chat_id, rest, SCHEDULES_PATH)
        return

    bot.reply_to(
        message,
        "⏰ *Schedule Commands:*\n\n"
        "  `/schedule` — list all schedules\n"
        "  `/schedule add <name> <interval> <cmd>` — add a schedule\n"
        "  `/schedule remove <name>` — remove a schedule\n\n"
        "💡 Or use `/build` → option 2 for the interactive wizard.",
        parse_mode="Markdown",
    )


def _schedule_list(chat_id, schedules_path):
    """List all scheduled tasks."""
    import yaml

    if not os.path.exists(schedules_path):
        bot.send_message(
            chat_id,
            "⏰ No schedules configured yet.\n\n"
            "Add one with: `/schedule add <name> <interval> <cmd>`\n"
            "Example: `/schedule add battery 2h pmset -g batt`",
            parse_mode="Markdown",
        )
        return

    try:
        with open(schedules_path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error reading schedules: {e}")
        return

    if not data:
        bot.send_message(
            chat_id,
            "⏰ No schedules configured yet.\n\n"
            "Add one with: `/schedule add <name> <interval> <cmd>`",
            parse_mode="Markdown",
        )
        return

    lines = []
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        interval = entry.get("interval", "?")
        desc = entry.get("desc", "")
        cmd = entry.get("cmd", "")
        label = desc or cmd[:40]
        lines.append(f"  `{name}` — every `{interval}` — {label}")

    bot.send_message(
        chat_id,
        f"⏰ *Scheduled Tasks ({len(lines)}):*\n\n" + "\n".join(lines)
        + "\n\n💡 `/schedule remove <name>` to delete one.",
        parse_mode="Markdown",
    )


def _schedule_add(message, chat_id, rest, schedules_path):
    """Add a new scheduled task: /schedule add <name> <interval> <cmd>."""
    import yaml

    parts = rest.split(" ", 2) if rest else []
    if len(parts) < 3:
        bot.reply_to(
            message,
            "Usage: `/schedule add <name> <interval> <cmd>`\n"
            "Example: `/schedule add battery 2h pmset -g batt`",
            parse_mode="Markdown",
        )
        return

    name = parts[0].lower().strip()
    interval_str = parts[1].strip()
    cmd = parts[2].strip()

    # Validate interval
    delay, label = parse_duration(interval_str)
    if delay is None or delay <= 0:
        bot.reply_to(message, f"❌ Invalid interval: `{interval_str}`. Use e.g. `30m`, `2h`, `6h`.", parse_mode="Markdown")
        return

    # Load existing
    data = {}
    if os.path.exists(schedules_path):
        try:
            with open(schedules_path, "r") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            data = {}

    if name in data:
        bot.reply_to(message, f"⚠️ Schedule `{name}` already exists. Remove it first with `/schedule remove {name}`.", parse_mode="Markdown")
        return

    data[name] = {
        "cmd": cmd,
        "interval": interval_str,
        "desc": f"{name} (every {label})",
    }

    try:
        os.makedirs(os.path.dirname(schedules_path), exist_ok=True)
        with open(schedules_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
        bot.reply_to(
            message,
            f"✅ Schedule `{name}` added — runs every `{interval_str}`.\n"
            f"_Active on next scheduler cycle (60s)._",
            parse_mode="Markdown",
        )
        logger.info(f"Schedule added: {name} (every {interval_str})")
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to save schedule: {e}")
        logger.error(f"Schedule save error: {e}")


def _schedule_remove(message, chat_id, name, schedules_path):
    """Remove a scheduled task by name."""
    import yaml

    if not name:
        bot.reply_to(message, "Usage: `/schedule remove <name>`", parse_mode="Markdown")
        return

    name = name.lower().strip()

    if not os.path.exists(schedules_path):
        bot.reply_to(message, f"❌ No schedules file found.")
        return

    try:
        with open(schedules_path, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        bot.reply_to(message, f"❌ Error reading schedules: {e}")
        return

    if name not in data:
        available = ", ".join(f"`{k}`" for k in data.keys()) if data else "none"
        bot.reply_to(message, f"❌ Schedule `{name}` not found.\nAvailable: {available}", parse_mode="Markdown")
        return

    del data[name]
    try:
        with open(schedules_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False) if data else f.write("")
        bot.reply_to(message, f"🗑 Schedule `{name}` removed.", parse_mode="Markdown")
        logger.info(f"Schedule removed: {name}")
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to save: {e}")
        logger.error(f"Schedule remove error: {e}")
