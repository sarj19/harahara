"""Meta handlers: help, status, brain, keyboard, last."""
import time
from datetime import datetime
from collections import deque

import telebot

from botpkg import bot, logger
from settings import BOT_STATUS_TAGLINE, BOT_KEYBOARD_COMMANDS
from botpkg.config import SPECIAL_COMMANDS, CATEGORY_EMOJIS, activity_stats
from botpkg.utils import load_commands, get_aliases_for

# ─── Command history (persistent) ───
from botpkg.persistence import load_history, save_history

_saved = load_history()
_command_history = deque(_saved[-100:], maxlen=100)


def record_command(cmd_name, chat_id, exit_code=None):
    """Record a command execution in history and persist."""
    _command_history.append({
        "cmd": cmd_name,
        "time": time.time(),
        "exit_code": exit_code,
    })
    save_history(_command_history)


def handle_help(message, chat_id, text):
    from settings import BOT_EMOJI
    # Show category picker with inline keyboard
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    categories = [
        ("🐟 Special", "help_special"),
    ]
    # Add YAML sections
    from botpkg.utils import commands_sections as sections
    if sections:
        for section_name, _ in sections:
            emoji = CATEGORY_EMOJIS.get(section_name, "📦")
            categories.append((f"{emoji} {section_name}", f"help_yaml_{section_name}"))

    # Build button rows
    for i in range(0, len(categories), 2):
        row = [telebot.types.InlineKeyboardButton(categories[i][0], callback_data=categories[i][1])]
        if i + 1 < len(categories):
            row.append(telebot.types.InlineKeyboardButton(categories[i+1][0], callback_data=categories[i+1][1]))
        markup.row(*row)
    markup.row(telebot.types.InlineKeyboardButton("📋 All Commands", callback_data="help_all"))

    bot.send_message(
        chat_id,
        f"{BOT_EMOJI} *Help* — pick a category:",
        parse_mode="Markdown",
        reply_markup=markup,
    )
    logger.info("Sent help categories.")


def handle_help_callback(call):
    """Handle help category selection."""
    chat_id = call.message.chat.id
    data = call.data
    bot.answer_callback_query(call.id)

    if data == "help_all":
        _send_full_help(chat_id)
        return

    if data == "help_special":
        from settings import BOT_EMOJI
        text = f"*{BOT_EMOJI} Special Commands*\n"
        for c, desc in SPECIAL_COMMANDS.items():
            aliases = get_aliases_for(c)
            alias_str = f" ({', '.join(aliases)})" if aliases else ""
            text += f"  `/{c}`{alias_str} — {desc}\n"
        text += "\n💡 _Any command supports_ `-t <duration>` _to override timeout_"
        bot.send_message(chat_id, text, parse_mode="Markdown")
        return

    if data.startswith("help_yaml_"):
        section_name = data[len("help_yaml_"):]
        from botpkg.utils import commands_sections as sections
        commands = load_commands()
        emoji = CATEGORY_EMOJIS.get(section_name, "📦")
        text = f"*{emoji} {section_name}*\n"
        if sections:
            for sname, cmd_names in sections:
                if sname == section_name:
                    for c in cmd_names:
                        entry = commands.get(c, {})
                        desc = entry.get("desc", "") if isinstance(entry, dict) else ""
                        aliases = get_aliases_for(c)
                        alias_str = f" ({', '.join(aliases)})" if aliases else ""
                        text += f"  `/{c}`{alias_str} — {desc}\n" if desc else f"  `/{c}`{alias_str}\n"
                    break
        bot.send_message(chat_id, text, parse_mode="Markdown")


def _send_full_help(chat_id):
    """Send the full command list (all categories)."""
    from botpkg.utils import commands_sections as sections
    from settings import BOT_EMOJI
    commands = load_commands()
    help_text = f"*📋 All Commands*\n\n*{BOT_EMOJI} Special Commands*\n"
    for c, desc in SPECIAL_COMMANDS.items():
        aliases = get_aliases_for(c)
        alias_str = f" ({', '.join(aliases)})" if aliases else ""
        help_text += f"  `/{c}`{alias_str} — {desc}\n"
    if sections:
        for section_name, cmd_names in sections:
            emoji = CATEGORY_EMOJIS.get(section_name, "📦")
            section_cmds = []
            for c in cmd_names:
                entry = commands.get(c, {})
                desc = entry.get("desc", "") if isinstance(entry, dict) else ""
                aliases = get_aliases_for(c)
                alias_str = f" ({', '.join(aliases)})" if aliases else ""
                section_cmds.append(f"  `/{c}`{alias_str} — {desc}" if desc else f"  `/{c}`{alias_str}")
            if section_cmds:
                help_text += f"\n*{emoji} {section_name}*\n" + "\n".join(section_cmds) + "\n"
    else:
        for c in sorted(commands.keys()):
            desc = commands[c].get("desc", "") if isinstance(commands[c], dict) else ""
            help_text += f"  `/{c}` — {desc}\n" if desc else f"  `/{c}`\n"
    help_text += "\n💡 _Any command supports_ `-t <duration>` _to override timeout_"
    bot.send_message(chat_id, help_text, parse_mode="Markdown")
    logger.info("Sent full help message.")


def handle_status(message, chat_id, text):
    """Report bot uptime, stats, and config."""
    import botpkg
    from settings import HEARTBEAT_INTERVAL, BOT_NAME, BOT_EMOJI

    uptime_secs = int(time.time() - activity_stats["start_time"])
    hours = uptime_secs // 3600
    mins = (uptime_secs % 3600) // 60

    idle_secs = int(time.time() - botpkg.last_interaction_time)
    idle_mins = idle_secs // 60
    idle_label = f"{idle_mins} min{'s' if idle_mins != 1 else ''}" if idle_mins > 0 else "just now"
    hb_label = f"every {HEARTBEAT_INTERVAL}m" if HEARTBEAT_INTERVAL > 0 else "disabled"

    cmds_run = activity_stats["commands_run"]
    screenshots = activity_stats["screenshots_taken"]

    # Top 3 commands
    top_cmds = sorted(
        activity_stats["commands_by_name"].items(),
        key=lambda x: x[1], reverse=True
    )[:3]

    status_text = (
        f"{BOT_EMOJI} *{BOT_NAME} Status*\n\n"
        f"  ⏱ Uptime: *{hours}h {mins}m*\n"
        f"  💬 Last interaction: {idle_label} ago\n"
        f"  💓 Heartbeat: {hb_label}\n"
        f"  📊 Commands: *{cmds_run}*  |  📸 Screenshots: *{screenshots}*\n"
    )

    if top_cmds:
        top_str = ", ".join(f"`/{c}` ({n}×)" for c, n in top_cmds)
        status_text += f"  🏆 Top: {top_str}\n"

    if BOT_STATUS_TAGLINE:
        status_text += f"\n  🏷 _{BOT_STATUS_TAGLINE}_"

    bot.send_message(chat_id, status_text, parse_mode="Markdown")


def handle_brain(message, chat_id, text):
    """Handle /brain status|clear commands."""
    from botpkg.brain import get_memory_stats, clear_history, get_history
    from settings import NLP_ENABLED

    args = text.split(" ", 1)[1].strip().lower() if " " in text else "status"

    if args == "clear":
        clear_history(chat_id)
        bot.reply_to(message, "🧠 Conversation memory cleared.")
        return

    stats = get_memory_stats(chat_id)
    status = "✅ Enabled" if NLP_ENABLED else "❌ Disabled"
    history = get_history(chat_id)

    status_text = (
        f"🧠 *NLP Brain Status*\n\n"
        f"  Mode: {status}\n"
        f"  Memory: {stats['messages']}/{stats['max_size']} messages\n"
    )
    if history:
        last = history[-1]
        role = "You" if last["role"] == "user" else "Bot"
        status_text += f"  Last: {role}: {last['text'][:80]}...\n"

    status_text += (
        f"\n_Usage:_\n"
        f"  `/brain` — show status\n"
        f"  `/brain clear` — clear memory\n"
        f"  Send any plain text with NLP enabled to use the brain."
    )
    bot.send_message(chat_id, status_text, parse_mode="Markdown")


def handle_keyboard(message, chat_id, text):
    cmd_list = [c.strip() for c in BOT_KEYBOARD_COMMANDS.split(",") if c.strip()]
    if not cmd_list:
        bot.reply_to(message, "No keyboard commands configured. Set `BOT_KEYBOARD_COMMANDS` in `.env`.")
        return

    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    row = []
    for cmd in cmd_list:
        row.append(f"/{cmd}")
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)

    bot.send_message(chat_id, "⌨️ Quick commands:", reply_markup=markup)
    logger.info("Sent quick reply keyboard.")


def handle_last(message, chat_id, text):
    """Show last N commands executed."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    n = 10
    if args and args.isdigit():
        n = min(int(args), 50)

    if not _command_history:
        bot.reply_to(message, "📜 No command history yet.")
        return

    entries = list(_command_history)[-n:]
    entries.reverse()  # Most recent first

    lines = []
    for entry in entries:
        ts = datetime.fromtimestamp(entry["time"]).strftime("%H:%M:%S")
        exit_str = ""
        if entry.get("exit_code") is not None:
            exit_str = f" → {'✅' if entry['exit_code'] == 0 else '❌'}{entry['exit_code']}"
        lines.append(f"  `{ts}` /{entry['cmd']}{exit_str}")

    bot.send_message(
        chat_id,
        f"📜 *Last {len(entries)} Commands:*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


def handle_snippet(message, chat_id, text):
    """Handle /snippet — clipboard history viewer."""
    from botpkg.clipboard import get_history, search_history, clear_history, get_entry

    args = text.split(" ", 1)[1].strip() if " " in text else ""

    if not args:
        # Show last 10 entries
        entries = get_history(10)
        if not entries:
            bot.reply_to(message, "📋 Clipboard history is empty.")
            return

        lines = ["📋 *Clipboard History* (latest first)\n"]
        for i, entry in enumerate(entries, 1):
            ts = datetime.fromtimestamp(entry["time"]).strftime("%H:%M:%S")
            text_preview = entry["text"][:60].replace("\n", "↵")
            truncated = "..." if entry["full_length"] > 60 else ""
            lines.append(f"  `{i}.` `{ts}` {text_preview}{truncated}")
        lines.append("\n_Use_ `/snippet N` _to retrieve full entry_")
        try:
            bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, "\n".join(lines))
        return

    if args.lower() == "clear":
        clear_history()
        bot.reply_to(message, "📋 Clipboard history cleared.")
        return

    if args.isdigit():
        index = int(args)
        entry = get_entry(index)
        if entry:
            ts = datetime.fromtimestamp(entry["time"]).strftime("%H:%M:%S")
            try:
                bot.send_message(
                    chat_id,
                    f"📋 *Clip #{index}* (`{ts}`):\n```\n{entry['text']}\n```",
                    parse_mode="Markdown",
                )
            except Exception:
                bot.send_message(chat_id, f"📋 Clip #{index} ({ts}):\n\n{entry['text']}")
        else:
            bot.reply_to(message, f"❌ No entry #{index}.")
        return

    if args.startswith("search "):
        query = args[7:].strip()
        if not query:
            bot.reply_to(message, "Usage: `/snippet search <query>`", parse_mode="Markdown")
            return
        results = search_history(query)
        if not results:
            bot.reply_to(message, f"📋 No clips matching '{query}'.")
            return
        lines = [f"📋 *Search results for '{query}':*\n"]
        for entry in results:
            ts = datetime.fromtimestamp(entry["time"]).strftime("%H:%M:%S")
            preview = entry["text"][:60].replace("\n", "↵")
            lines.append(f"  `{ts}` {preview}")
        try:
            bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, "\n".join(lines))
        return

    bot.reply_to(
        message,
        "📋 *Snippet Usage:*\n"
        "  `/snippet` — last 10 clips\n"
        "  `/snippet N` — retrieve clip #N\n"
        "  `/snippet search <q>` — search clips\n"
        "  `/snippet clear` — clear history",
        parse_mode="Markdown",
    )
