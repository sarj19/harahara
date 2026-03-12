"""YAML command handler and macro system."""
import os
import shlex
import subprocess
import threading
import time

import telebot

from botpkg import bot, logger
from settings import MACROS_PATH
from botpkg.config import (
    DANGEROUS_COMMANDS, CATEGORY_EMOJIS,
    pending_confirmations, activity_stats,
)
from botpkg.utils import (
    load_commands, take_and_send_screenshot,
    parse_duration, get_cmd_name, resolve_alias, get_cmd_section,
)
from botpkg.runner import run_command_with_screenshots, run_command_streaming


def handle_yaml_command(message, chat_id, text):
    """Generic handler for commands defined in bot_commands.yaml.

    Returns True if the command was found and handled, False otherwise.
    """
    parts = text[1:].split(" ", 1)
    command_name = parts[0].split("@")[0].strip().lower()
    command_args = parts[1].strip() if len(parts) > 1 else ""
    commands = load_commands()

    # Resolve alias for YAML commands too
    command_name = resolve_alias(command_name)

    if command_name not in commands:
        return False

    # Dangerous command confirmation (with inline buttons)
    if command_name in DANGEROUS_COMMANDS:
        if chat_id in pending_confirmations:
            bot.reply_to(message, "⚠️ Another command is awaiting confirmation.")
            return True
        pending_confirmations[chat_id] = {"command": command_name, "time": time.time()}
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_cmd:{command_name}"),
            telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_cmd:"),
        )
        bot.reply_to(
            message,
            f"⚠️ *Run /{command_name}?*",
            parse_mode="Markdown",
            reply_markup=markup,
        )
        return True

    entry = commands[command_name]
    shell_command = entry["cmd"] if isinstance(entry, dict) else entry

    # Parse optional inline timeout: /cmd -t 30m <args>
    inline_timeout = None
    if command_args and command_args.startswith("-t "):
        t_parts = command_args.split(" ", 2)
        if len(t_parts) >= 2:
            parsed_t, t_label = parse_duration(t_parts[1])
            if parsed_t:
                inline_timeout = parsed_t
                command_args = t_parts[2].strip() if len(t_parts) > 2 else ""

    if command_args:
        if "{}" in shell_command:
            safe_args = command_args.replace('\\', '\\\\').replace('"', '\\"').replace("'", "'\\''")
            shell_command = shell_command.replace("{}", safe_args)
        else:
            shell_command = f"{shell_command} {shlex.quote(command_args)}"

    # Themed response emoji
    section = get_cmd_section(command_name)
    section_emoji = CATEGORY_EMOJIS.get(section, "") if section else ""
    prefix = f"{section_emoji} " if section_emoji else ""

    bot.reply_to(message, f"{prefix}Executing: {shell_command}")
    logger.info(f"Executing command: {shell_command}")

    cmd_timeout = inline_timeout or (entry.get("timeout", 300) if isinstance(entry, dict) else 300)

    def execute():
        try:
            output, returncode = run_command_streaming(chat_id, shell_command, cmd_timeout, command_name)

            # Record in command history
            from botpkg.handlers.meta import record_command
            record_command(command_name, chat_id, returncode)
        except subprocess.TimeoutExpired:
            bot.send_message(chat_id, f"⏰ Command timed out after {cmd_timeout}s.")
            logger.error(f"Command timed out: {shell_command}")
        except Exception as e:
            bot.send_message(chat_id, f"Error executing command: {e}")
            logger.error(f"Error executing command {shell_command}: {e}")

    threading.Thread(target=execute, daemon=True).start()
    return True


# ═══════════════════════════════════════════════════════════════════
# Macros
# ═══════════════════════════════════════════════════════════════════

def _load_macros():
    """Load macros from YAML with simple caching."""
    import yaml
    if not os.path.exists(MACROS_PATH):
        return {}
    try:
        with open(MACROS_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading macros: {e}")
        return {}


def handle_macros(message, chat_id, text):
    """List available macros."""
    macros = _load_macros()
    if not macros:
        bot.reply_to(message, "📋 No macros defined.\nCreate `personal/macros.yaml` — see `macros.yaml.example`.")
        return
    lines = []
    for name, entry in macros.items():
        desc = entry.get("desc", "") if isinstance(entry, dict) else ""
        steps = len(entry.get("steps", [])) if isinstance(entry, dict) else 0
        lines.append(f"  `/{name}` — {desc} ({steps} steps)" if desc else f"  `/{name}` ({steps} steps)")
    bot.send_message(chat_id, f"📋 *Available Macros:*\n\n" + "\n".join(lines), parse_mode="Markdown")


def handle_macro(message, chat_id, text):
    """Run a multi-step macro."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/macro <name>`\nRun `/macros` to see available macros.", parse_mode="Markdown")
        return

    macros = _load_macros()
    macro_name = args.lower()
    if macro_name not in macros:
        bot.reply_to(message, f"❌ Unknown macro: `{macro_name}`\nRun `/macros` to see available macros.", parse_mode="Markdown")
        return

    macro = macros[macro_name]
    if not isinstance(macro, dict) or "steps" not in macro:
        bot.reply_to(message, f"❌ Invalid macro format: `{macro_name}`", parse_mode="Markdown")
        return

    steps = macro["steps"]
    desc = macro.get("desc", macro_name)
    continue_on_error = macro.get("continue_on_error", False)

    bot.reply_to(message, f"🚀 Running macro: *{desc}* ({len(steps)} steps)...", parse_mode="Markdown")

    def run_macro():
        for i, step in enumerate(steps, 1):
            step_cmd = step.get("cmd", "") if isinstance(step, dict) else str(step)
            step_desc = step.get("desc", f"Step {i}") if isinstance(step, dict) else f"Step {i}"
            step_timeout = step.get("timeout", 300) if isinstance(step, dict) else 300

            bot.send_message(chat_id, f"⚙️ [{i}/{len(steps)}] {step_desc}...")

            try:
                if step_cmd.startswith("/"):
                    from botpkg.utils import load_commands as _load_cmds
                    bot_cmd = step_cmd.lstrip("/").split()[0].lower()
                    commands = _load_cmds()

                    if bot_cmd == "screenshot":
                        take_and_send_screenshot(chat_id)
                        continue

                    if bot_cmd in commands:
                        entry = commands[bot_cmd]
                        shell_cmd = entry["cmd"] if isinstance(entry, dict) else entry
                        cmd_args = step_cmd.split(" ", 1)[1].strip() if " " in step_cmd else ""
                        if cmd_args and "{}" in shell_cmd:
                            shell_cmd = shell_cmd.replace("{}", cmd_args)
                        elif cmd_args:
                            import shlex as _shlex
                            shell_cmd = f"{shell_cmd} {_shlex.quote(cmd_args)}"
                    else:
                        bot.send_message(chat_id, f"⚠️ [{i}] Unknown command: {bot_cmd}")
                        if not continue_on_error:
                            break
                        continue
                else:
                    shell_cmd = step_cmd

                result = subprocess.run(
                    shell_cmd, shell=True, capture_output=True, text=True, timeout=step_timeout
                )
                output = (result.stdout + result.stderr).strip() or "(No output)"
                if len(output) > 2000:
                    output = output[:2000] + "\n...[truncated]"

                status = "✅" if result.returncode == 0 else "⚠️"
                bot.send_message(
                    chat_id,
                    f"{status} [{i}/{len(steps)}] {step_desc}\n```\n{output}\n```",
                    parse_mode="Markdown",
                )

                if result.returncode != 0 and not continue_on_error:
                    bot.send_message(chat_id, f"🛑 Macro '{desc}' stopped at step {i} (non-zero exit).")
                    return
            except subprocess.TimeoutExpired:
                bot.send_message(chat_id, f"⏰ [{i}] Step timed out after {step_timeout}s.")
                if not continue_on_error:
                    bot.send_message(chat_id, f"🛑 Macro '{desc}' stopped at step {i}.")
                    return
            except Exception as e:
                bot.send_message(chat_id, f"❌ [{i}] Error: {e}")
                if not continue_on_error:
                    return

        bot.send_message(chat_id, f"✅ Macro '{desc}' completed ({len(steps)} steps).")

    threading.Thread(target=run_macro, daemon=True).start()
