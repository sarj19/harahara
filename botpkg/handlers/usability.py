"""Usability handlers — onboarding, category keyboards, pins, streak, focus, briefing.

Features for non-power users who want a personal assistant experience.
"""
import os
import json
import time
import subprocess
import threading
from datetime import datetime, timedelta

import telebot

from botpkg import bot, logger, AUTHORIZED_USER_ID
from botpkg.config import SPECIAL_COMMANDS, CATEGORY_EMOJIS, activity_stats
from settings import BOT_NAME, BOT_EMOJI, PROJECT_DIR

# ─── Persistent data paths ───
_PINS_FILE = os.path.join(PROJECT_DIR, "personal", "pins.json")
_STREAK_FILE = os.path.join(PROJECT_DIR, "personal", "streak.json")
_FAVS_FILE = os.path.join(PROJECT_DIR, "personal", "favorites.json")

_DEFAULT_FAVS = ["screenshot", "status", "help"]


def _load_favs():
    try:
        if os.path.exists(_FAVS_FILE):
            with open(_FAVS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return list(_DEFAULT_FAVS)


def _save_favs(favs):
    os.makedirs(os.path.dirname(_FAVS_FILE), exist_ok=True)
    with open(_FAVS_FILE, "w") as f:
        json.dump(favs, f, indent=2)


def handle_fav(message, chat_id, text):
    """Favorites bar: /fav add|remove|list|show."""
    args = text.split(" ", 2)
    subcmd = args[1].strip().lower() if len(args) > 1 else "show"
    param = args[2].strip().lstrip("/") if len(args) > 2 else ""

    favs = _load_favs()

    if subcmd == "add":
        if not param:
            bot.reply_to(message, "Usage: `/fav add <command>`\nExample: `/fav add screenshot`", parse_mode="Markdown")
            return
        if param not in favs:
            favs.append(param)
            _save_favs(favs)
        bot.reply_to(message, f"⭐ `/{param}` added to favorites.")
        _send_fav_keyboard(chat_id, favs)

    elif subcmd in ("remove", "rm"):
        if not param:
            bot.reply_to(message, "Usage: `/fav remove <command>`", parse_mode="Markdown")
            return
        if param in favs:
            favs.remove(param)
            _save_favs(favs)
            bot.reply_to(message, f"⭐ `/{param}` removed from favorites.")
        else:
            bot.reply_to(message, f"⭐ `/{param}` is not in favorites.")
        _send_fav_keyboard(chat_id, favs)

    elif subcmd == "list":
        if not favs:
            bot.reply_to(message, "⭐ No favorites. Add with `/fav add <command>`", parse_mode="Markdown")
            return
        lines = ", ".join(f"`/{f}`" for f in favs)
        bot.send_message(chat_id, f"⭐ *Favorites:* {lines}\n\n`/fav add <cmd>` · `/fav remove <cmd>`", parse_mode="Markdown")

    else:  # "show" or default — send keyboard
        _send_fav_keyboard(chat_id, favs)


def _send_fav_keyboard(chat_id, favs):
    """Send a persistent reply keyboard with favorite commands."""
    if not favs:
        return
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=False
    )
    row = []
    for cmd in favs:
        row.append(f"/{cmd}")
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)
    bot.send_message(chat_id, "⭐ Favorites:", reply_markup=markup)

# ═══════════════════════════════════════════════════════════════════
# 1. /start — Onboarding tour
# ═══════════════════════════════════════════════════════════════════

def handle_start(message, chat_id, text):
    """Interactive onboarding tour with tappable examples."""
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("📸 Screenshot", callback_data="tour:screenshot"),
        telebot.types.InlineKeyboardButton("⏰ Set Reminder", callback_data="tour:remind"),
        telebot.types.InlineKeyboardButton("📝 Save Note", callback_data="tour:note"),
        telebot.types.InlineKeyboardButton("⏱ Start Timer", callback_data="tour:timer"),
        telebot.types.InlineKeyboardButton("📋 Clipboard", callback_data="tour:snippet"),
        telebot.types.InlineKeyboardButton("🗺 Where Am I?", callback_data="tour:where"),
        telebot.types.InlineKeyboardButton("🔨 Build Command", callback_data="tour:build"),
        telebot.types.InlineKeyboardButton("📖 Full Help", callback_data="tour:help"),
    )

    bot.send_message(
        chat_id,
        f"{BOT_EMOJI} *Welcome to {BOT_NAME}!*\n\n"
        "I'm your personal Mac remote control. Here's what I can do:\n\n"
        "📸 Take screenshots & webcam photos\n"
        "⌨️ Type text & press keys remotely\n"
        "⏰ Set reminders & countdown timers\n"
        "📝 Save notes & clipboard history\n"
        "🗺 Check your network & location\n"
        "📁 Upload & download files\n"
        "🔨 Build custom commands on the fly\n"
        "🧠 Optional AI assistant (Gemini)\n\n"
        "*Tap a button below to try it out!*\n"
        "Or use `/menu` for quick-access category keyboards.",
        parse_mode="Markdown",
        reply_markup=markup,
    )


def handle_tour_callback(chat_id, action):
    """Handle tour button presses with helpful examples."""
    examples = {
        "screenshot": ("📸 *Screenshots*\n\n"
                       "`/screenshot` — take one now\n"
                       "`/screenshot 3` — take 3, one per minute\n"
                       "`/diff` — see what changed since last screenshot"),
        "remind": ("⏰ *Reminders*\n\n"
                   "`/remind 5m Call back` — 5 minutes\n"
                   "`/remind 2h Check oven` — 2 hours\n"
                   "`/timer 25m Deep work` — visual countdown"),
        "note": ("📝 *Notes*\n\n"
                 "`/note save Buy groceries`\n"
                 "`/note list` — see all notes\n"
                 "`/note search groceries`\n"
                 "`/pin` — reply to any message to bookmark it"),
        "timer": ("⏱ *Timers*\n\n"
                  "`/timer 25m Work sprint` — visual progress bar\n"
                  "`/pomodoro` — 25m work → 5m break\n"
                  "`/focus 45m Deep work` — timer + Do Not Disturb\n"
                  "`/timer stop` — cancel active timer"),
        "snippet": ("📋 *Clipboard*\n\n"
                    "I monitor your clipboard in the background.\n"
                    "`/snippet` — last 10 clips\n"
                    "`/snippet 3` — retrieve clip #3\n"
                    "`/snippet search tax` — search history"),
        "where": ("🗺 *Network Context*\n\n"
                  "`/where` — one command shows:\n"
                  "  • Public IP + geolocation\n"
                  "  • WiFi SSID + signal strength\n"
                  "  • Local IP + map link"),
        "build": ("🔨 *Build Custom Commands*\n\n"
                  "`/build` — interactive wizard\n"
                  "`/build weather curl wttr.in` — quick add\n\n"
                  "Build commands, schedules, or macros\n"
                  "without editing any files!"),
        "help": None,  # Will dispatch to handle_help
    }

    if action == "help":
        from botpkg.handlers.meta import handle_help
        handle_help(chat_id)
        return

    example = examples.get(action, "")
    if example:
        bot.send_message(chat_id, example, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# 2. /menu — Category keyboards
# ═══════════════════════════════════════════════════════════════════

def handle_menu(message, chat_id, text):
    """Show categorized command keyboards."""
    args = text.split(" ", 1)[1].strip().lower() if " " in text else ""

    categories = {
        "screen": ("📸 Screen & Visual", [
            ("/screenshot", "📸 Screenshot"),
            ("/webcam", "📷 Webcam"),
            ("/diff", "🔍 Diff"),
            ("/record 30s", "🎬 Record"),
        ]),
        "productivity": ("⏰ Productivity", [
            ("/remind 5m ", "⏰ Remind"),
            ("/timer 25m ", "⏱ Timer"),
            ("/pomodoro", "🍅 Pomodoro"),
            ("/focus 25m ", "🎯 Focus"),
            ("/note list", "📝 Notes"),
            ("/snippet", "📋 Clipboard"),
        ]),
        "system": ("🖥 System", [
            ("/status", "📊 Status"),
            ("/where", "🗺 Network"),
            ("/logs 20", "📄 Logs"),
            ("/streak", "🔥 Streak"),
        ]),
        "files": ("📁 Files & Media", [
            ("/download ", "📥 Download"),
            ("/upload", "📤 Upload"),
            ("/audio 10s", "🎙 Audio"),
        ]),
        "tools": ("🔧 Tools", [
            ("/build", "🔨 Build"),
            ("/macro ", "🔗 Macro"),
            ("/calendar", "📅 Calendar"),
            ("/mail", "✉️ Mail"),
        ]),
    }

    if args and args in categories:
        _send_category_keyboard(chat_id, args, categories[args])
        return

    # Show top-level category picker
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    for key, (label, _) in categories.items():
        markup.add(telebot.types.InlineKeyboardButton(label, callback_data=f"menu:{key}"))

    bot.send_message(
        chat_id,
        "📂 *Quick Menu* — tap a category:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


def _send_category_keyboard(chat_id, key, category_data):
    """Send a reply keyboard for a specific category."""
    label, commands = category_data
    markup = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True, one_time_keyboard=True
    )
    row = []
    for cmd, btn_label in commands:
        row.append(btn_label if cmd.endswith(" ") else cmd)
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)

    bot.send_message(chat_id, f"{label} — tap a command:", reply_markup=markup)


def handle_menu_callback(chat_id, category):
    """Handle menu category button press."""
    categories = {
        "screen": ("📸 Screen & Visual", [
            ("/screenshot", "📸"), ("/webcam", "📷"), ("/diff", "🔍 Diff"), ("/record 30s", "🎬"),
        ]),
        "productivity": ("⏰ Productivity", [
            ("/remind 5m ", "⏰ Remind"), ("/timer 25m ", "⏱ Timer"),
            ("/pomodoro", "🍅 Pomo"), ("/focus 25m ", "🎯 Focus"),
            ("/note list", "📝 Notes"), ("/snippet", "📋 Clips"),
        ]),
        "system": ("🖥 System", [
            ("/status", "📊"), ("/where", "🗺"), ("/logs 20", "📄"), ("/streak", "🔥"),
        ]),
        "files": ("📁 Files", [
            ("/download ", "📥 Download"), ("/upload", "📤 Upload"), ("/audio 10s", "🎙"),
        ]),
        "tools": ("🔧 Tools", [
            ("/build", "🔨 Build"), ("/macro ", "🔗 Macro"),
            ("/calendar", "📅 Cal"), ("/mail", "✉️ Mail"),
        ]),
    }

    if category in categories:
        label, cmds = categories[category]
        markup = telebot.types.InlineKeyboardMarkup(row_width=3)
        buttons = []
        for cmd, btn_label in cmds:
            buttons.append(telebot.types.InlineKeyboardButton(
                btn_label, callback_data=f"runcmd:{cmd.strip()}"
            ))
        # Add in rows of 3
        for i in range(0, len(buttons), 3):
            markup.row(*buttons[i:i+3])
        bot.send_message(chat_id, f"{label}:", reply_markup=markup, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# 4. Daily briefing
# ═══════════════════════════════════════════════════════════════════

def send_daily_briefing(chat_id=None):
    """Send a morning briefing: battery, reminders, calendar, weather summary."""
    if chat_id is None:
        chat_id = AUTHORIZED_USER_ID

    parts = [f"{BOT_EMOJI} *Good morning! Here's your briefing:*\n"]

    # Battery
    try:
        batt = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5
        )
        for line in batt.stdout.split("\n"):
            if "%" in line:
                parts.append(f"🔋 {line.strip()}")
                break
    except Exception:
        pass

    # Disk usage
    try:
        df = subprocess.run(
            ["df", "-h", "/"], capture_output=True, text=True, timeout=5
        )
        lines = df.stdout.strip().split("\n")
        if len(lines) > 1:
            fields = lines[1].split()
            if len(fields) >= 5:
                parts.append(f"💾 Disk: {fields[4]} used ({fields[2]} of {fields[1]})")
    except Exception:
        pass

    # Uptime
    uptime_secs = int(time.time() - activity_stats["start_time"])
    hours = uptime_secs // 3600
    parts.append(f"⏱ Bot uptime: {hours}h")

    # Commands yesterday
    cmds = activity_stats["commands_run"]
    if cmds > 0:
        parts.append(f"📊 Commands run: {cmds}")

    # Streak
    streak_data = _load_streak()
    if streak_data.get("current", 0) > 0:
        parts.append(f"🔥 Streak: {streak_data['current']} day{'s' if streak_data['current'] != 1 else ''}")

    parts.append("\n_Send /menu for quick commands._")

    bot.send_message(chat_id, "\n".join(parts), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# 5. /focus — Timer + DND + Summary
# ═══════════════════════════════════════════════════════════════════

def handle_focus(message, chat_id, text):
    """Start a focus session: timer + Do Not Disturb."""
    from botpkg.utils import parse_duration
    args = text.split(" ", 1)[1].strip() if " " in text else ""

    if args.lower() == "stop":
        # Turn off DND
        try:
            subprocess.run([
                "osascript", "-e",
                'do shell script "defaults write com.apple.controlcenter DoNotDisturb -bool false; killall ControlCenter"'
            ], capture_output=True, timeout=5)
        except Exception:
            pass
        bot.reply_to(message, "🎯 Focus session ended. Do Not Disturb off.")
        return

    # Parse duration
    parts = args.split(" ", 1)
    dur_str = parts[0] if parts else "25m"
    label = parts[1] if len(parts) > 1 else "Focus time"
    total_secs, dur_label = parse_duration(dur_str)
    if not total_secs:
        total_secs = 25 * 60
        dur_label = "25m"

    # Enable DND
    try:
        subprocess.run([
            "osascript", "-e",
            'do shell script "defaults write com.apple.controlcenter DoNotDisturb -bool true; killall ControlCenter"'
        ], capture_output=True, timeout=5)
    except Exception:
        pass

    bot.send_message(
        chat_id,
        f"🎯 *Focus Mode: ON*\n\n"
        f"  📝 {label}\n"
        f"  ⏱ {dur_label}\n"
        f"  🔕 Do Not Disturb: enabled\n\n"
        f"_Send /focus stop to end early._",
        parse_mode="Markdown",
    )

    # Start timer in background
    from botpkg.handlers.timer import handle_timer
    # Create a fake message to forward to timer
    handle_timer(message, chat_id, f"/timer {dur_str} 🎯 {label}")

    # Schedule DND off
    def _end_focus():
        time.sleep(total_secs)
        try:
            subprocess.run([
                "osascript", "-e",
                'do shell script "defaults write com.apple.controlcenter DoNotDisturb -bool false; killall ControlCenter"'
            ], capture_output=True, timeout=5)
        except Exception:
            pass
        bot.send_message(
            chat_id,
            f"🎯 *Focus complete!* {label}\n"
            f"🔔 Do Not Disturb: off\n"
            f"📊 You focused for {dur_label}.",
            parse_mode="Markdown",
        )
    threading.Thread(target=_end_focus, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# 7. /pin & /pins — Bookmark messages
# ═══════════════════════════════════════════════════════════════════

def _load_pins():
    try:
        if os.path.exists(_PINS_FILE):
            with open(_PINS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_pins(pins):
    os.makedirs(os.path.dirname(_PINS_FILE), exist_ok=True)
    with open(_PINS_FILE, "w") as f:
        json.dump(pins, f, indent=2)


def handle_pin(message, chat_id, text):
    """Pin a message by replying to it, or pin with text."""
    pins = _load_pins()

    # If replying to a message, pin that
    if message.reply_to_message:
        pinned_text = message.reply_to_message.text or "(media)"
        pin_entry = {
            "text": pinned_text[:500],
            "time": time.time(),
            "msg_id": message.reply_to_message.message_id,
        }
    else:
        # Pin inline text
        args = text.split(" ", 1)[1].strip() if " " in text else ""
        if not args:
            bot.reply_to(message, "📌 *Pin Usage:*\n  Reply to a message with `/pin`\n  Or: `/pin some text to save`", parse_mode="Markdown")
            return
        pin_entry = {
            "text": args[:500],
            "time": time.time(),
        }

    pins.append(pin_entry)
    _save_pins(pins)
    bot.reply_to(message, f"📌 Pinned! ({len(pins)} total)")


def handle_pins(message, chat_id, text):
    """List or clear pinned messages."""
    args = text.split(" ", 1)[1].strip().lower() if " " in text else ""

    if args == "clear":
        _save_pins([])
        bot.reply_to(message, "📌 All pins cleared.")
        return

    pins = _load_pins()
    if not pins:
        bot.reply_to(message, "📌 No pins yet. Reply to a message with `/pin` to save it.", parse_mode="Markdown")
        return

    lines = ["📌 *Pinned Items*\n"]
    for i, pin in enumerate(reversed(pins[-15:]), 1):
        ts = datetime.fromtimestamp(pin["time"]).strftime("%m/%d %H:%M")
        preview = pin["text"][:60].replace("\n", "↵")
        truncated = "..." if len(pin["text"]) > 60 else ""
        lines.append(f"  `{i}.` `{ts}` {preview}{truncated}")

    lines.append(f"\n_{len(pins)} pinned_ — `/pins clear` to reset")
    bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# 8. Pretty /status (enhanced version)
# ═══════════════════════════════════════════════════════════════════

def handle_pretty_status(message, chat_id, text):
    """Enhanced status — sends a visual dashboard image."""
    import botpkg

    uptime_secs = int(time.time() - activity_stats["start_time"])
    cmds_run = activity_stats["commands_run"]
    screenshots = activity_stats["screenshots_taken"]
    streak_data = _load_streak()

    top_cmds = sorted(
        activity_stats["commands_by_name"].items(),
        key=lambda x: x[1], reverse=True
    )[:4]

    from settings import BOT_STATUS_TAGLINE
    tagline = BOT_STATUS_TAGLINE or ""

    markup = telebot.types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        telebot.types.InlineKeyboardButton("📸 Screenshot", callback_data="runcmd:/screenshot"),
        telebot.types.InlineKeyboardButton("📂 Menu", callback_data="runcmd:/menu"),
        telebot.types.InlineKeyboardButton("📖 Help", callback_data="tour:help"),
    )

    try:
        from botpkg.status_card import generate_status_card
        card = generate_status_card(
            bot_name=BOT_NAME, bot_emoji=BOT_EMOJI,
            uptime_secs=uptime_secs, commands_run=cmds_run,
            screenshots=screenshots, top_cmds=top_cmds,
            streak_data=streak_data, tagline=tagline,
        )
        card.name = "status.png"
        bot.send_photo(chat_id, card, reply_markup=markup)
    except Exception as e:
        logger.error(f"Status card generation failed: {e}")
        # Fallback to text
        hours = uptime_secs // 3600
        mins = (uptime_secs % 3600) // 60
        bot.send_message(
            chat_id,
            f"{BOT_EMOJI} *{BOT_NAME}* — {hours}h {mins}m up\n"
            f"📊 {cmds_run} commands | 📸 {screenshots} screenshots",
            parse_mode="Markdown", reply_markup=markup,
        )


# ═══════════════════════════════════════════════════════════════════
# 9. /streak — Usage gamification
# ═══════════════════════════════════════════════════════════════════

def _load_streak():
    try:
        if os.path.exists(_STREAK_FILE):
            with open(_STREAK_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"current": 0, "best": 0, "last_date": "", "total_days": 0}


def _save_streak(data):
    os.makedirs(os.path.dirname(_STREAK_FILE), exist_ok=True)
    with open(_STREAK_FILE, "w") as f:
        json.dump(data, f, indent=2)


def update_streak():
    """Called on every command to update the streak counter."""
    data = _load_streak()
    today = datetime.now().strftime("%Y-%m-%d")

    if data.get("last_date") == today:
        return  # Already counted today

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if data.get("last_date") == yesterday:
        data["current"] = data.get("current", 0) + 1
    else:
        data["current"] = 1  # Reset streak

    data["last_date"] = today
    data["total_days"] = data.get("total_days", 0) + 1
    data["best"] = max(data.get("best", 0), data["current"])
    _save_streak(data)


def handle_streak(message, chat_id, text):
    """Show usage streak and stats."""
    data = _load_streak()
    current = data.get("current", 0)
    best = data.get("best", 0)
    total = data.get("total_days", 0)

    # Streak flame visualization
    if current >= 7:
        flame = "🔥" * min(current // 7, 5) + f" {current} days!"
    elif current > 0:
        flame = "🔥" * current
    else:
        flame = "No active streak"

    cmds = activity_stats["commands_run"]

    status = (
        f"🔥 *Your Streak*\n\n"
        f"  Current: {flame}\n"
        f"  Best: {best} day{'s' if best != 1 else ''}\n"
        f"  Total active days: {total}\n"
        f"  Commands this session: {cmds}\n"
    )

    # Milestones
    if current == 7:
        status += "\n🎉 *1 week streak! Keep it going!*"
    elif current == 30:
        status += "\n🏆 *30 day streak! You're a power user!*"
    elif current == 100:
        status += "\n👑 *100 days! Legendary!*"

    bot.send_message(chat_id, status, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# Settings Wizard
# ═══════════════════════════════════════════════════════════════════

def handle_settings(message, chat_id, text):
    """Interactive wizard to configure basic bot settings."""
    import telebot
    import settings
    import os
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    config_keys = [
        ("🗣 Voice", "BOT_VOICE"),
        ("🐟 Status Tagline", "BOT_STATUS_TAGLINE"),
        ("⏰ Digest Time", "BOT_DIGEST_TIME"),
        ("⌨️ Keyboard Items", "BOT_KEYBOARD_COMMANDS"),
    ]
    
    for label, key in config_keys:
        current_val = getattr(settings, key, os.environ.get(key, ""))
        display_val = (current_val[:20] + '..') if len(current_val) > 20 else current_val
        if not display_val: display_val = "(empty)"
        markup.add(telebot.types.InlineKeyboardButton(f"{label}: {display_val}", callback_data=f"setenv:{key}"))
        
    bot.send_message(chat_id, "⚙️ *Bot Settings*\nClick an item to change its value:", parse_mode="Markdown", reply_markup=markup)

def _settings_step_prompt(chat_id, key, message_id):
    import telebot
    import settings
    import os
    current_val = getattr(settings, key, os.environ.get(key, ""))
    
    msg = bot.send_message(chat_id, f"✏️ Enter new value for `{key}`:\n(Current: `{current_val}`)\n\n*Type /cancel to abort.*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, _settings_step_save, key=key, chat_id=chat_id)

def _settings_step_save(message, key, chat_id):
    if not message.text: return
    val = message.text.strip()
    if val.startswith("/cancel") or val.startswith("/start") or val == "❌ Cancel":
        bot.reply_to(message, "❌ Cancelled settings update.")
        return
        
    from botpkg.utils import update_env_var
    update_env_var(key, val)
    bot.reply_to(message, f"✅ Updated `{key}` to `{val}`.")
    
    # Rerender settings menu
    handle_settings(message, chat_id, "/settings")

# ═══════════════════════════════════════════════════════════════════
# 10. Conversational error handling — "Did you mean?"
# ═══════════════════════════════════════════════════════════════════

def suggest_command(chat_id, cmd_name):
    """Find the closest matching command and suggest it.

    Returns True if a suggestion was sent, False otherwise.
    """
    from botpkg.config import SPECIAL_COMMAND_ALIASES
    from botpkg.utils import load_commands

    all_commands = set(SPECIAL_COMMANDS.keys())
    yaml_cmds = load_commands()
    all_commands.update(yaml_cmds.keys())
    all_commands.update(SPECIAL_COMMAND_ALIASES.keys())

    # Simple fuzzy: find commands where name is a substring or has small edit distance
    scored = []
    for c in all_commands:
        score = _similarity(cmd_name.lower(), c.lower())
        if score > 0.4:
            scored.append((c, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:3]

    if not top:
        bot.send_message(
            chat_id,
            f"❓ Unknown command `/{cmd_name}`.\n"
            "Send `/help` for all commands or `/menu` for quick access.",
            parse_mode="Markdown",
        )
        return True

    # Resolve to canonical names
    from botpkg.config import SPECIAL_COMMAND_ALIASES
    suggestions = []
    for name, score in top:
        canonical = SPECIAL_COMMAND_ALIASES.get(name, name)
        if canonical not in [s[0] for s in suggestions]:
            suggestions.append((canonical, score))

    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    
    if len(suggestions) == 1:
        name = suggestions[0][0]
        markup.add(
            telebot.types.InlineKeyboardButton(f"▶ Run", callback_data=f"runcmd:/{name}"),
            telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="brain_cancel")
        )
        msg_text = f"❓ Command `/{cmd_name}` not found. Did you mean `/{name}`?"
    else:
        for name, _ in suggestions[:3]:
            markup.add(telebot.types.InlineKeyboardButton(
                f"▶ /{name}", callback_data=f"runcmd:/{name}"
            ))
        markup.add(telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="brain_cancel"))
        msg_text = f"❓ Command `/{cmd_name}` not found. Did you mean one of these?"

    bot.send_message(
        chat_id,
        msg_text,
        parse_mode="Markdown",
        reply_markup=markup,
    )
    return True


def _similarity(a, b):
    """Simple string similarity (Jaccard on character bigrams + prefix bonus)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    # Prefix bonus
    prefix_len = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            prefix_len += 1
        else:
            break
    prefix_score = prefix_len / max(len(a), len(b))

    # Substring check
    if a in b or b in a:
        return 0.8 + prefix_score * 0.2

    # Bigram Jaccard
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s)-1)) if len(s) > 1 else {s}
    ba, bb = bigrams(a), bigrams(b)
    if not ba or not bb:
        return prefix_score
    jaccard = len(ba & bb) / len(ba | bb)

    return jaccard * 0.6 + prefix_score * 0.4


# ═══════════════════════════════════════════════════════════════════
# 3. Natural language shortcuts (without NLP)
# ═══════════════════════════════════════════════════════════════════

# Common phrases mapped to commands
NATURAL_SHORTCUTS = {
    "take a screenshot":    "/screenshot",
    "screenshot":           "/screenshot",
    "take photo":           "/screenshot",
    "webcam":               "/webcam",
    "what time is it":      "/status",
    "battery":              "/status",
    "how's my mac":         "/status",
    "remind me":            "/remind",
    "set reminder":         "/remind",
    "set timer":            "/timer",
    "start timer":          "/timer",
    "clipboard":            "/snippet",
    "what did i copy":      "/snippet",
    "my notes":             "/note list",
    "show notes":           "/note list",
    "where am i":           "/where",
    "my ip":                "/where",
    "wifi":                 "/where",
    "help":                 "/help",
    "what can you do":      "/start",
    "menu":                 "/menu",
    "good morning":         "briefing",
}


def try_natural_shortcut(chat_id, text):
    """Try to match natural language to a command. Returns True if matched."""
    lower = text.lower().strip()

    for phrase, cmd in NATURAL_SHORTCUTS.items():
        if phrase in lower:
            if cmd == "briefing":
                send_daily_briefing(chat_id)
                return True

            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(
                telebot.types.InlineKeyboardButton(
                    f"▶ Run {cmd}", callback_data=f"runcmd:{cmd}"
                ),
                telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="brain_cancel"),
            )
            bot.send_message(
                chat_id,
                f"💡 I think you want: `{cmd}`",
                parse_mode="Markdown",
                reply_markup=markup,
            )
            return True

    return False


# ═══════════════════════════════════════════════════════════════════
# /setup — macOS permission walkthrough + tips
# ═══════════════════════════════════════════════════════════════════

_PERMISSIONS = [
    ("📸", "Screen Recording", "/screenshot, /record",
     "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"),
    ("⌨️", "Accessibility", "/key, /type",
     "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"),
    ("📷", "Camera", "/webcam",
     "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"),
    ("🎙", "Microphone", "/audio",
     "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"),
    ("💾", "Full Disk Access", "/notifications",
     "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"),
]


def handle_setup(message, chat_id, text):
    """Interactive macOS permission walkthrough, one at a time."""
    # Parse which step we're on (e.g. /setup or /setup 2)
    args = text.split()
    step = 0
    if len(args) > 1 and args[1].isdigit():
        step = int(args[1])

    if step < len(_PERMISSIONS):
        icon, name, cmds, url = _PERMISSIONS[step]
        total = len(_PERMISSIONS)

        # Open the exact settings pane on the Mac
        try:
            subprocess.run(["open", url], capture_output=True, timeout=5)
        except Exception:
            pass

        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.InlineKeyboardButton(
                "✅ Done" if step < total - 1 else "✅ Finish",
                callback_data=f"runcmd:/setup {step + 1}",
            ),
            telebot.types.InlineKeyboardButton(
                "⏭ Skip", callback_data=f"runcmd:/setup {step + 1}",
            ),
        )

        bot.send_message(
            chat_id,
            f"🔐 *Permission {step + 1}/{total}: {icon} {name}*\n\n"
            f"Enables: `{cmds}`\n"
            f"Grant to: *Terminal.app* (or your terminal emulator)\n\n"
            f"_Settings pane opened on your Mac._",
            parse_mode="Markdown",
            reply_markup=markup,
        )
    else:
        # All permissions done — show tips
        bot.send_message(
            chat_id,
            f"{BOT_EMOJI} *Setup complete!* All permissions configured.\n\n"
            "🔨 *Build custom commands, schedules & macros:*\n"
            "  `/build` → interactive wizard\n"
            "  `/build mycommand curl wttr.in` → quick one-liner\n\n"
            "  Or edit YAML files directly:\n"
            "  `personal/bot_commands.yaml` → commands (live-reloaded)\n"
            "  `personal/schedules.yaml` → scheduled tasks\n"
            "  `personal/macros.yaml` → multi-step sequences\n\n"
            "📝 *Quick notes:*\n"
            "  `/note save Remember to deploy`\n"
            "  `/note list` · `/note search deploy` · `/note delete 1`\n\n"
            "📅 *Google Calendar & Gmail:*\n"
            "  Send `/googlesetup` to connect your Google account.\n\n"
            "Send /help for the full command list.",
            parse_mode="Markdown",
        )
