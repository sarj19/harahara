"""Interactive /build wizard — create commands, schedules, and macros via Telegram.

Three modes:
  /build               → choose what to build (command, schedule, or macro)
  /build <name> <cmd>  → quick one-liner command creation

Command wizard:  name → shell cmd → description → aliases → timeout → confirm
Schedule wizard: name → command → interval → description → timeout → confirm
Macro wizard:    name → description → steps (loop) → continue_on_error → confirm
"""
import os

import yaml

from botpkg import bot, logger
from settings import PERSONAL_YAML_PATH
from botpkg.utils import load_commands


def _esc(text):
    """Escape Markdown special characters in user-provided text."""
    for ch in ('_', '*', '`', '['):
        text = text.replace(ch, f'\\{ch}')
    return text


def _send(chat_id, text, **kwargs):
    """Send message with Markdown, falling back to plain text on parse error."""
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", **kwargs)
    except Exception:
        # Strip markdown and retry without parse_mode
        bot.send_message(chat_id, text, **kwargs)

try:
    from settings import SCHEDULES_PATH
except ImportError:
    SCHEDULES_PATH = os.path.join(os.path.dirname(PERSONAL_YAML_PATH), "schedules.yaml")

try:
    from settings import MACROS_PATH
except ImportError:
    MACROS_PATH = os.path.join(os.path.dirname(PERSONAL_YAML_PATH), "macros.yaml")

# Active build sessions: chat_id → {mode, step, ...data}
pending_build = {}


def handle_build(message, chat_id, text):
    """Start the /build wizard or do a quick-add."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""

    # Quick one-liner: /build mycommand echo hello
    if args:
        _quick_build(message, chat_id, args)
        return

    # Show mode picker
    pending_build[chat_id] = {"mode": None, "step": -1}
    bot.send_message(
        chat_id,
        "🔨 *What would you like to build?*\n\n"
        "  `1` — 📦 New command\n"
        "  `2` — ⏰ Scheduled task\n"
        "  `3` — 🔗 Multi-step macro\n\n"
        "Reply with `1`, `2`, or `3`.\n"
        "Send `cancel` at any time to abort.",
        parse_mode="Markdown",
    )


def process_build_step(message, chat_id, text):
    """Process the next step in the build wizard.

    Called from the dispatch hub when a build session is active.
    Returns True if the message was consumed by the wizard.
    """
    if chat_id not in pending_build:
        return False

    text = text.strip()
    if text.lower() == "cancel":
        pending_build.pop(chat_id, None)
        bot.reply_to(message, "❌ Build cancelled.")
        return True

    session = pending_build[chat_id]

    # Mode selection
    if session.get("mode") is None:
        return _pick_mode(message, chat_id, text, session)

    mode = session["mode"]
    if mode == "command":
        return _command_wizard(message, chat_id, text, session)
    elif mode == "schedule":
        return _schedule_wizard(message, chat_id, text, session)
    elif mode == "macro":
        return _macro_wizard(message, chat_id, text, session)

    return False


# ═══════════════════════════════════════════════════════════════════
# Mode picker
# ═══════════════════════════════════════════════════════════════════

def _pick_mode(message, chat_id, text, session):
    if text in ("1", "command", "cmd"):
        session["mode"] = "command"
        session["step"] = 0
        _send(
            chat_id,
            "📦 *Build New Command*\n\n"
            "Step 1/5: What should the command be called?\n"
            "_(just the name, no `/` prefix)_",
        )
    elif text in ("2", "schedule", "sched", "cron"):
        session["mode"] = "schedule"
        session["step"] = 0
        _send(
            chat_id,
            "⏰ *Build Scheduled Task*\n\n"
            "Step 1/4: Name for this schedule?\n"
            "_(e.g. `battery_check`, `disk_report`)_",
        )
    elif text in ("3", "macro"):
        session["mode"] = "macro"
        session["step"] = 0
        session["steps"] = []
        _send(
            chat_id,
            "🔗 *Build Multi-step Macro*\n\n"
            "Step 1/3: Name for this macro?\n"
            "_(e.g. `morning`, `deploy`)_",
        )
    else:
        bot.reply_to(message, "Reply `1` (command), `2` (schedule), or `3` (macro):")
    return True


# ═══════════════════════════════════════════════════════════════════
# Command wizard (5 steps)
# ═══════════════════════════════════════════════════════════════════

def _command_wizard(message, chat_id, text, session):
    step = session["step"]

    if step == 0:  # Name
        name = text.lower().lstrip("/").replace(" ", "_")
        if not name:
            bot.reply_to(message, "❌ Name can't be empty. Try again:")
            return True
        from botpkg.config import SPECIAL_COMMANDS
        if name in SPECIAL_COMMANDS:
            bot.reply_to(message, f"❌ `/{name}` is a built-in command. Choose another:", parse_mode="Markdown")
            return True
        session["name"] = name
        session["step"] = 1
        _send(
            chat_id,
            f"✅ Name: `/{_esc(name)}`\n\n"
            "Step 2/5: Shell command to run?\n\n"
            "*Without arguments:*\n"
            "  `uptime`\n"
            "  → `/mycommand` runs `uptime`\n\n"
            "*With arguments:*\n"
            "  `~/scripts/deploy.sh {}`\n"
            "  → `/mycommand staging` runs `~/scripts/deploy.sh staging`\n\n"
            "💡 _Use `{}` where user arguments should go._",
        )

    elif step == 1:  # Command
        if not text:
            bot.reply_to(message, "❌ Command can't be empty. Try again:")
            return True
        session["cmd"] = text
        session["step"] = 2
        _send(chat_id, "Step 3/5: Description? _(or `skip`)_")

    elif step == 2:  # Description
        session["desc"] = "" if text.lower() == "skip" else text
        session["step"] = 3
        _send(chat_id, "Step 4/5: Aliases? _(comma-separated, or `skip`)_")

    elif step == 3:  # Aliases
        if text.lower() == "skip":
            session["aliases"] = []
        else:
            session["aliases"] = [a.strip().lower().lstrip("/") for a in text.split(",") if a.strip()]
        session["step"] = 4
        _send(chat_id, "Step 5/5: Timeout in seconds? _(or `skip` for 300s)_")

    elif step == 4:  # Timeout
        if text.lower() == "skip":
            session["timeout"] = 300
        else:
            try:
                session["timeout"] = int(text)
            except ValueError:
                bot.reply_to(message, "❌ Must be a number. Try again or `skip`:")
                return True
        session["step"] = 5
        _show_command_review(chat_id, session)

    elif step == 5:  # Confirm
        if text.lower() in ("yes", "y", "save"):
            _save_command(chat_id, session)
            pending_build.pop(chat_id, None)
        elif text.lower() in ("no", "n", "cancel"):
            pending_build.pop(chat_id, None)
            bot.send_message(chat_id, "❌ Build cancelled.")
        else:
            bot.reply_to(message, "Reply `yes` to save or `no` to cancel.")

    return True


def _show_command_review(chat_id, session):
    name = _esc(session['name'])
    cmd = _esc(session['cmd'][:80])
    review = f"🔨 *Review New Command*\n\n  📛 Name: `/{name}`\n  ⚙️ Command: `{cmd}`\n"
    if session.get("desc"):
        review += f"  📝 Description: {_esc(session['desc'])}\n"
    if session.get("aliases"):
        review += f"  🔗 Aliases: {', '.join(f'`/{_esc(a)}`' for a in session['aliases'])}\n"
    review += f"  ⏱ Timeout: {session.get('timeout', 300)}s\n\n*Save?* Reply `yes` or `no`."
    _send(chat_id, review)


def _save_command(chat_id, session):
    entry = {"cmd": session["cmd"]}
    if session.get("desc"):
        entry["desc"] = session["desc"]
    if session.get("timeout", 300) != 300:
        entry["timeout"] = session["timeout"]
    if session.get("aliases"):
        entry["aliases"] = session["aliases"]

    try:
        data = {}
        if os.path.exists(PERSONAL_YAML_PATH):
            with open(PERSONAL_YAML_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
        data[session["name"]] = entry
        with open(PERSONAL_YAML_PATH, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        alias_str = f"\nAliases: {', '.join(f'`/{_esc(a)}`' for a in session.get('aliases', []))}" if session.get("aliases") else ""
        _send(chat_id, f"✅ *Command saved!* `/{_esc(session['name'])}` is now available.{alias_str}\n_No restart needed._")
        logger.info(f"Build: saved command '{session['name']}'")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Save failed: {e}")
        logger.error(f"Build save error: {e}")


# ═══════════════════════════════════════════════════════════════════
# Schedule wizard (4 steps)
# ═══════════════════════════════════════════════════════════════════

def _schedule_wizard(message, chat_id, text, session):
    step = session["step"]

    if step == 0:  # Name
        name = text.lower().replace(" ", "_")
        if not name:
            bot.reply_to(message, "❌ Name can't be empty. Try again:")
            return True
        session["name"] = name
        session["step"] = 1
        _send(
            chat_id,
            f"✅ Schedule: `{_esc(name)}`\n\n"
            "Step 2/4: Command to run?\n"
            "_(shell command or `/bot\_command`)_",
        )

    elif step == 1:  # Command
        if not text:
            bot.reply_to(message, "❌ Command can't be empty. Try again:")
            return True
        session["cmd"] = text
        session["step"] = 2
        _send(
            chat_id,
            "Step 3/4: How often? _(e.g. `30m`, `2h`, `6h`, `1d`)_",
        )

    elif step == 2:  # Interval
        from botpkg.utils import parse_duration
        secs, label = parse_duration(text)
        if not secs:
            bot.reply_to(message, "❌ Invalid duration. Use e.g. `30m`, `2h`, `1d`. Try again:")
            return True
        session["interval"] = text.strip()
        session["step"] = 3
        _send(chat_id, "Step 4/4: Description? _(or `skip`)_")

    elif step == 3:  # Description
        session["desc"] = "" if text.lower() == "skip" else text
        session["step"] = 4
        _show_schedule_review(chat_id, session)

    elif step == 4:  # Confirm
        if text.lower() in ("yes", "y", "save"):
            _save_schedule(chat_id, session)
            pending_build.pop(chat_id, None)
        elif text.lower() in ("no", "n", "cancel"):
            pending_build.pop(chat_id, None)
            bot.send_message(chat_id, "❌ Build cancelled.")
        else:
            bot.reply_to(message, "Reply `yes` to save or `no` to cancel.")

    return True


def _show_schedule_review(chat_id, session):
    review = (
        f"⏰ *Review Scheduled Task*\n\n"
        f"  📛 Name: `{_esc(session['name'])}`\n"
        f"  ⚙️ Command: `{_esc(session['cmd'][:80])}`\n"
        f"  🔁 Interval: every `{_esc(session['interval'])}`\n"
    )
    if session.get("desc"):
        review += f"  📝 Description: {_esc(session['desc'])}\n"
    review += "\n*Save?* Reply `yes` or `no`."
    _send(chat_id, review)


def _save_schedule(chat_id, session):
    entry = {
        "cmd": session["cmd"],
        "interval": session["interval"],
    }
    if session.get("desc"):
        entry["desc"] = session["desc"]

    try:
        data = {}
        if os.path.exists(SCHEDULES_PATH):
            with open(SCHEDULES_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
        data[session["name"]] = entry
        with open(SCHEDULES_PATH, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        _send(
            chat_id,
            f"✅ *Schedule saved!* `{_esc(session['name'])}` will run every `{_esc(session['interval'])}`.\n_Active on next scheduler cycle._",
        )
        logger.info(f"Build: saved schedule '{session['name']}'")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Save failed: {e}")
        logger.error(f"Build schedule save error: {e}")


# ═══════════════════════════════════════════════════════════════════
# Macro wizard (3 steps + step loop)
# ═══════════════════════════════════════════════════════════════════

def _macro_wizard(message, chat_id, text, session):
    step = session["step"]

    if step == 0:  # Name
        name = text.lower().replace(" ", "_")
        if not name:
            bot.reply_to(message, "❌ Name can't be empty. Try again:")
            return True
        session["name"] = name
        session["step"] = 1
        _send(chat_id, f"✅ Macro: `{_esc(name)}`\n\nStep 2/3: Description? _(or `skip`)_")

    elif step == 1:  # Description
        session["desc"] = "" if text.lower() == "skip" else text
        session["step"] = 2
        _send(
            chat_id,
            "Step 3/3: Add steps one at a time.\n\n"
            "Format: `command | description`\n"
            "Examples:\n"
            "  `pmset -g batt | Battery check`\n"
            "  `/screenshot | Take screenshot`\n"
            "  `uptime`\n\n"
            "Send `done` when finished adding steps.",
        )

    elif step == 2:  # Adding steps
        if text.lower() == "done":
            if not session.get("steps"):
                bot.reply_to(message, "❌ Need at least one step. Add a step or `cancel`:")
                return True
            session["step"] = 3
            _send(chat_id, "Continue on error? _(yes/no, default: no)_")
            return True

        # Parse step: "command | description" or just "command"
        if "|" in text:
            parts = text.split("|", 1)
            step_cmd = parts[0].strip()
            step_desc = parts[1].strip()
        else:
            step_cmd = text.strip()
            step_desc = f"Step {len(session['steps']) + 1}"

        session["steps"].append({"cmd": step_cmd, "desc": step_desc})
        n = len(session["steps"])
        _send(
            chat_id,
            f"✅ Step {n} added: `{_esc(step_cmd[:50])}`\n\n"
            f"Add another step, or send `done` to finish.",
        )

    elif step == 3:  # Continue on error
        session["continue_on_error"] = text.lower() in ("yes", "y", "true")
        session["step"] = 4
        _show_macro_review(chat_id, session)

    elif step == 4:  # Confirm
        if text.lower() in ("yes", "y", "save"):
            _save_macro(chat_id, session)
            pending_build.pop(chat_id, None)
        elif text.lower() in ("no", "n", "cancel"):
            pending_build.pop(chat_id, None)
            bot.send_message(chat_id, "❌ Build cancelled.")
        else:
            bot.reply_to(message, "Reply `yes` to save or `no` to cancel.")

    return True


def _show_macro_review(chat_id, session):
    steps_text = ""
    for i, s in enumerate(session["steps"], 1):
        steps_text += f"    {i}. `{_esc(s['cmd'][:50])}` — {_esc(s['desc'])}\n"

    review = (
        f"🔗 *Review Macro*\n\n"
        f"  📛 Name: `{_esc(session['name'])}`\n"
    )
    if session.get("desc"):
        review += f"  📝 Description: {_esc(session['desc'])}\n"
    review += f"  📋 Steps ({len(session['steps'])}):\n{steps_text}"
    if session.get("continue_on_error"):
        review += "  ⚠️ Continue on error: yes\n"
    review += "\n*Save?* Reply `yes` or `no`."
    _send(chat_id, review)


def _save_macro(chat_id, session):
    entry = {"steps": session["steps"]}
    if session.get("desc"):
        entry["desc"] = session["desc"]
    if session.get("continue_on_error"):
        entry["continue_on_error"] = True

    try:
        data = {}
        if os.path.exists(MACROS_PATH):
            with open(MACROS_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
        data[session["name"]] = entry
        with open(MACROS_PATH, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        _send(
            chat_id,
            f"✅ *Macro saved!* Run with `/macro {_esc(session['name'])}` ({len(session['steps'])} steps).\n_No restart needed._",
        )
        logger.info(f"Build: saved macro '{session['name']}'")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Save failed: {e}")
        logger.error(f"Build macro save error: {e}")


# ═══════════════════════════════════════════════════════════════════
# Quick build (one-liner)
# ═══════════════════════════════════════════════════════════════════

def _quick_build(message, chat_id, args):
    """Quick one-liner: /build mycommand echo hello world."""
    parts = args.split(" ", 1)
    name = parts[0].lower().lstrip("/")
    cmd = parts[1].strip() if len(parts) > 1 else ""

    if not cmd:
        bot.reply_to(
            message,
            "🔨 *Quick Build:* `/build name command`\n"
            "Or just `/build` for the interactive wizard.",
            parse_mode="Markdown",
        )
        return

    session = {"name": name, "cmd": cmd, "desc": "", "aliases": [], "timeout": 300}
    _save_command(chat_id, session)
