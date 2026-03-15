"""NLP Brain — intelligent command routing with system prompts, fuzzy matching,
conversation memory, and multi-step planning.

Replaces the dumb NLP pipe (text → gemini --yolo) with a 3-stage pipeline:
  Stage 1: Fuzzy match against command names + descriptions
  Stage 2: Gemini CLI with rich system prompt + conversation history
  Stage 3: Multi-step plan detection and execution
"""
import difflib
import json
import os
import re
import subprocess
import threading
import time
import uuid
from collections import deque

from botpkg import bot, logger
from botpkg.config import SPECIAL_COMMANDS, activity_stats
from botpkg.utils import load_commands, take_and_send_screenshot
from botpkg.memory import (
    add_to_history, get_history, clear_history, get_memory_stats,
    _chat_history, NLP_CONTEXT_SIZE,
)
from settings import BOT_NAME, BOT_EMOJI

import telebot

# ─── Pending multi-step plans ───
# Owner: this module. Stores plans awaiting user confirmation.
_pending_plans = {}  # plan_id → {"chat_id": int, "commands": [str], "time": float}


# ═══════════════════════════════════════════════════════════════════
# System Prompt Builder
# ═══════════════════════════════════════════════════════════════════

def _build_system_prompt(chat_id):
    """Build a dynamic system prompt with available commands and history."""
    commands = load_commands()

    # Gather all commands (special + YAML)
    cmd_lines = []
    for name, desc in sorted(SPECIAL_COMMANDS.items()):
        cmd_lines.append(f"  /{name} — {desc}")
    for name, entry in sorted(commands.items()):
        desc = entry.get("desc", "") if isinstance(entry, dict) else ""
        cmd_lines.append(f"  /{name} — {desc}")

    commands_block = "\n".join(cmd_lines)

    # Build conversation history block
    history = get_history(chat_id)
    history_block = ""
    if history:
        hist_lines = []
        for msg in history[-10:]:  # Last 10 for the prompt (keep token count reasonable)
            role_label = "User" if msg["role"] == "user" else BOT_NAME
            hist_lines.append(f"  {role_label}: {msg['text']}")
        history_block = "\n".join(hist_lines)

    prompt = f"""You are {BOT_NAME} {BOT_EMOJI}, a macOS remote-control assistant on Telegram.

AVAILABLE COMMANDS:
{commands_block}

{"RECENT CONVERSATION:" + chr(10) + history_block if history_block else ""}

INSTRUCTIONS:
- If the user's request can be fulfilled by one or more available commands, respond with ONLY the command(s), one per line, starting with /
- Include any arguments the command needs (e.g. /say Hello there)
- If multiple commands are needed, list them in execution order, one per line
- If no command matches the request, respond conversationally — be concise and helpful
- Never make up commands that aren't in the list above
- Be concise — this is a chat, not an essay"""

    return prompt


# ═══════════════════════════════════════════════════════════════════
# Stage 1: Fuzzy Command Matching
# ═══════════════════════════════════════════════════════════════════

def _get_all_command_info():
    """Get all command names with descriptions for fuzzy matching."""
    commands = load_commands()
    info = {}

    # Special commands
    for name, desc in SPECIAL_COMMANDS.items():
        info[name] = desc.lower()

    # YAML commands
    for name, entry in commands.items():
        desc = entry.get("desc", "") if isinstance(entry, dict) else ""
        info[name] = desc.lower()

    return info


def _fuzzy_match(text):
    """Fuzzy match user text against command names and descriptions.

    Returns list of (command_name, score, description) sorted by score desc.
    """
    text_lower = text.lower().strip()
    cmd_info = _get_all_command_info()
    matches = []

    # Direct name match (highest priority)
    for name, desc in cmd_info.items():
        if text_lower == name:
            matches.append((name, 1.0, desc))
            continue
        # Check if the text is a substring of the command name or vice versa
        if text_lower in name or name in text_lower:
            score = 0.85 if name in text_lower else 0.7
            matches.append((name, score, desc))
            continue

    # difflib fuzzy matching on command names
    close_names = difflib.get_close_matches(text_lower, list(cmd_info.keys()), n=3, cutoff=0.6)
    for name in close_names:
        if not any(m[0] == name for m in matches):
            ratio = difflib.SequenceMatcher(None, text_lower, name).ratio()
            matches.append((name, ratio, cmd_info[name]))

    # Keyword matching against descriptions
    words = text_lower.split()
    for name, desc in cmd_info.items():
        if not any(m[0] == name for m in matches):
            word_hits = sum(1 for w in words if w in desc or w in name)
            if word_hits > 0:
                score = min(0.65, 0.3 + 0.15 * word_hits)
                matches.append((name, score, desc))

    # Sort by score descending and return top 3
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:3]


# ═══════════════════════════════════════════════════════════════════
# Stage 2: Gemini CLI Integration
# ═══════════════════════════════════════════════════════════════════

def _find_gemini():
    """Find the gemini CLI binary."""
    # Check common paths
    for path in ["/opt/homebrew/bin/gemini", "/usr/local/bin/gemini"]:
        if os.path.exists(path):
            return path
    # Fall back to PATH
    result = subprocess.run(["which", "gemini"], capture_output=True, text=True)
    return result.stdout.strip() or None


def _call_gemini(user_text, chat_id):
    """Call Gemini CLI with system prompt and conversation history."""
    gemini_path = _find_gemini()
    if not gemini_path:
        return None

    system_prompt = _build_system_prompt(chat_id)
    full_prompt = f"{system_prompt}\n\nUser: {user_text}"

    try:
        result = subprocess.run(
            [gemini_path, "-p", full_prompt, "--yolo", "--output-format", "text"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        response = result.stdout.strip()
        if result.returncode != 0 and not response:
            response = result.stderr.strip() or "(Gemini returned no output)"
        return response
    except subprocess.TimeoutExpired:
        logger.error("Gemini CLI timed out")
        return None
    except Exception as e:
        logger.error(f"Gemini CLI error: {e}")
        return None


def _call_ollama(user_text, chat_id):
    """Call local Ollama model with system prompt and conversation history."""
    try:
        from botpkg.ollama import generate
    except ImportError:
        return None

    system_prompt = _build_system_prompt(chat_id)
    full_prompt = f"{system_prompt}\n\nUser: {user_text}"

    return generate(full_prompt)


_detected_backend = None  # Cached after first probe


def _detect_backend():
    """Auto-detect the best available AI backend (cached)."""
    global _detected_backend
    if _detected_backend is not None:
        return _detected_backend

    # Check if Ollama is available and running
    try:
        from botpkg.ollama import is_available, is_running
        if is_available() and is_running():
            _detected_backend = "ollama"
            logger.info("AI backend auto-detected: ollama")
            return _detected_backend
    except ImportError:
        pass

    # Check if Gemini CLI exists
    if _find_gemini():
        _detected_backend = "gemini"
        logger.info("AI backend auto-detected: gemini")
        return _detected_backend

    _detected_backend = "none"
    logger.warning("No AI backend detected (neither Ollama nor Gemini)")
    return _detected_backend


def _call_ai(user_text, chat_id):
    """Dispatch to the configured AI backend with auto-detection and fallback."""
    try:
        from settings import BOT_AI_BACKEND
    except (ImportError, AttributeError):
        BOT_AI_BACKEND = "auto"

    # Resolve backend
    if BOT_AI_BACKEND in ("auto", ""):
        backend = _detect_backend()
    else:
        backend = BOT_AI_BACKEND

    if backend == "ollama":
        response = _call_ollama(user_text, chat_id)
        if response is not None:
            return response, "ollama"
        # Fallback to Gemini if Ollama fails
        logger.warning("Ollama failed, falling back to Gemini")
        response = _call_gemini(user_text, chat_id)
        return (response, "gemini") if response else None
    elif backend == "gemini":
        response = _call_gemini(user_text, chat_id)
        return (response, "gemini") if response else None
    else:
        return None



# ═══════════════════════════════════════════════════════════════════
# Response Parsing
# ═══════════════════════════════════════════════════════════════════

def _parse_commands(ai_response):
    """Extract /commands from an AI response.

    Returns (commands_list, remaining_text).
    commands_list: list of command strings like ["/battery", "/screenshot"]
    remaining_text: any non-command text in the response
    """
    if not ai_response:
        return [], ""

    lines = ai_response.strip().split("\n")
    commands = []
    text_lines = []

    for line in lines:
        stripped = line.strip()
        # Match lines that start with / and look like commands
        if re.match(r'^/[a-zA-Z]', stripped):
            # Could be "/battery" or "/say hello world"
            commands.append(stripped)
        else:
            if stripped:
                text_lines.append(stripped)

    return commands, "\n".join(text_lines)


# ═══════════════════════════════════════════════════════════════════
# Inline Button Helpers
# ═══════════════════════════════════════════════════════════════════

def _suggest_single_command(chat_id, command, context="", edit_message_id=None):
    """Suggest a single command with Run/Cancel buttons."""
    markup = telebot.types.InlineKeyboardMarkup()
    # Truncate callback_data to 64 bytes (Telegram limit)
    cmd_data = command[:50]
    markup.row(
        telebot.types.InlineKeyboardButton(f"▶ Run {command.split()[0]}", callback_data=f"brain_run:{cmd_data}"),
        telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="brain_cancel:"),
    )
    msg = f"🧠 I think you want:\n`{command}`"
    if context:
        msg += f"\n_{context}_"
    if edit_message_id:
        bot.edit_message_text(msg, chat_id=chat_id, message_id=edit_message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)


def _suggest_multiple_commands(chat_id, commands, context="", edit_message_id=None):
    """Suggest multiple commands as a clickable list."""
    markup = telebot.types.InlineKeyboardMarkup()
    for cmd in commands[:5]:  # Max 5 suggestions
        label = cmd.split()[0]  # Just the /command part
        cmd_data = cmd[:50]
        markup.add(telebot.types.InlineKeyboardButton(
            f"▶ {cmd}", callback_data=f"brain_run:{cmd_data}"
        ))
    markup.add(telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="brain_cancel:"))

    msg = "🧠 Did you mean one of these?"
    if context:
        msg += f"\n_{context}_"
    if edit_message_id:
        bot.edit_message_text(msg, chat_id=chat_id, message_id=edit_message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)


def _suggest_plan(chat_id, commands, edit_message_id=None):
    """Suggest a multi-step plan with Run All button."""
    plan_id = str(uuid.uuid4())[:8]
    _pending_plans[plan_id] = {
        "chat_id": chat_id,
        "commands": commands,
        "time": time.time(),
    }

    steps = "\n".join(f"  {i}. `{cmd}`" for i, cmd in enumerate(commands, 1))
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("▶ Run All", callback_data=f"brain_plan:{plan_id}"),
        telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="brain_cancel:"),
    )
    plan_msg = f"🧠 *Plan ({len(commands)} steps):*\n\n{steps}"
    if edit_message_id:
        bot.edit_message_text(plan_msg, chat_id=chat_id, message_id=edit_message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, plan_msg, parse_mode="Markdown", reply_markup=markup)


# ═══════════════════════════════════════════════════════════════════
# Plan Execution
# ═══════════════════════════════════════════════════════════════════

def execute_plan(chat_id, plan_id):
    """Execute a multi-step plan by plan_id."""
    plan = _pending_plans.pop(plan_id, None)
    if not plan:
        bot.send_message(chat_id, "❌ Plan expired or not found.")
        return
    if time.time() - plan["time"] > 300:
        bot.send_message(chat_id, "⏰ Plan expired (5 min timeout).")
        return

    commands = plan["commands"]
    status_msg = bot.send_message(chat_id, f"🚀 Executing plan ({len(commands)} steps)...")

    def _run():
        for i, cmd_text in enumerate(commands, 1):
            bot.send_message(chat_id, f"⚙️ [{i}/{len(commands)}] `{cmd_text}`...", parse_mode="Markdown")
            _execute_single_command(chat_id, cmd_text)
            time.sleep(0.5)  # Small delay between steps
        bot.edit_message_text(f"✅ Plan completed ({len(commands)} steps).", chat_id=chat_id, message_id=status_msg.message_id)

    threading.Thread(target=_run, daemon=True).start()


def _execute_single_command(chat_id, cmd_text):
    """Execute a single /command by routing it through the handler."""
    from botpkg.utils import load_commands as _load_cmds, resolve_alias
    from botpkg.runner import run_command_with_screenshots
    from botpkg.config import SPECIAL_COMMANDS

    cmd_parts = cmd_text.lstrip("/").split(" ", 1)
    cmd_name = cmd_parts[0].lower()
    cmd_args = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

    # Resolve aliases
    cmd_name = resolve_alias(cmd_name)

    # Handle screenshot specially (just take & send, no fake message needed)
    if cmd_name == "screenshot":
        take_and_send_screenshot(chat_id)
        return

    # Check if this is a special command — route through the handler dispatch table
    if cmd_name in SPECIAL_COMMANDS:
        try:
            # Import the dispatch table from handlers
            from botpkg.handlers import _build_dispatch_table
            dispatch = _build_dispatch_table()
            handler_fn = dispatch.get(cmd_name)
            if handler_fn:
                # Create a fake message object for the handler
                import telebot as _tb
                fake_msg = _tb.types.Message(
                    message_id=0,
                    from_user=_tb.types.User(id=0, is_bot=False, first_name="Brain"),
                    date=0,
                    chat=_tb.types.Chat(id=chat_id, type="private"),
                    content_type="text",
                    options={},
                    json_string="",
                )
                fake_msg.text = cmd_text if cmd_text.startswith("/") else f"/{cmd_text}"
                handler_fn(fake_msg, chat_id, fake_msg.text)
                add_to_history(chat_id, "assistant", f"[/{cmd_name} executed]")
                return
        except Exception as e:
            logger.error(f"Error dispatching special command /{cmd_name}: {e}")
            bot.send_message(chat_id, f"❌ Error running /{cmd_name}: {e}")
            return

    # Look up in YAML commands
    commands = _load_cmds()
    if cmd_name in commands:
        import shlex
        entry = commands[cmd_name]
        shell_cmd = entry["cmd"] if isinstance(entry, dict) else entry
        timeout = entry.get("timeout", 300) if isinstance(entry, dict) else 300

        if cmd_args:
            if "{}" in shell_cmd:
                safe_args = cmd_args.replace('\\', '\\\\').replace('"', '\\"').replace("'", "'\\''")
                shell_cmd = shell_cmd.replace("{}", safe_args)
            else:
                shell_cmd = f"{shell_cmd} {shlex.quote(cmd_args)}"

        try:
            output, returncode = run_command_with_screenshots(chat_id, shell_cmd, timeout, cmd_name)
            if not output.strip():
                output = "(No output)"
            if len(output) > 3000:
                output = output[:3000] + "\n...[truncated]"
            bot.send_message(
                chat_id,
                f"```\n{output}\n```\nExit: {returncode}",
                parse_mode="Markdown",
            )
            # Record the output in conversation memory
            add_to_history(chat_id, "assistant", f"[/{cmd_name} output] {output[:200]}")
        except subprocess.TimeoutExpired:
            bot.send_message(chat_id, f"⏰ `/{cmd_name}` timed out.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error running `/{cmd_name}`: {e}")
    else:
        bot.send_message(chat_id, f"❌ Unknown command: `/{cmd_name}`", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════

def process_message(message, chat_id, text):
    """Main NLP brain entry point — replaces the dumb pipe.

    3-stage pipeline:
      1. Fuzzy match → suggest with inline buttons
      2. Gemini CLI with system prompt → parse response for /commands
      3. Multi-step plan → show plan with Run All button
    """
    # Record user message in conversation memory
    add_to_history(chat_id, "user", text)

    # Track activity
    activity_stats["commands_run"] += 1
    activity_stats["commands_by_name"]["nlp"] = activity_stats["commands_by_name"].get("nlp", 0) + 1

    # ── Stage 1: Fuzzy match ──
    matches = _fuzzy_match(text)
    if matches:
        best_name, best_score, best_desc = matches[0]

        if best_score >= 0.8:
            # High confidence — suggest single command
            logger.info(f"NLP fuzzy match: '{text}' → /{best_name} (score={best_score:.2f})")
            _suggest_single_command(chat_id, f"/{best_name}", f"Matched: {best_desc}")
            return

        if best_score >= 0.5 and len(matches) > 1:
            # Moderate confidence — show top suggestions
            logger.info(f"NLP fuzzy suggestions for '{text}': {[m[0] for m in matches]}")
            cmds = [f"/{m[0]}" for m in matches if m[1] >= 0.4]
            if cmds:
                _suggest_multiple_commands(chat_id, cmds, "Based on your message")
                return

    # ── Stage 2: Gemini with system prompt ──
    status_msg = bot.send_message(chat_id, "🧠 Thinking...")
    logger.info(f"NLP → Gemini: '{text}'")

    def _process_with_ai():
        result = _call_ai(text, chat_id)
        if result is None:
            bot.edit_message_text("❌ No AI backend available.\n\n" "• Gemini: `npm install -g @google/generative-ai-cli`\n" "• Ollama: `/ollamasetup`", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
            return

        response, backend = result
        if response is None:
            bot.edit_message_text("❌ No AI backend available.\n\n" "• Gemini: `npm install -g @google/generative-ai-cli`\n" "• Ollama: `/ollamasetup`", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
            return

        # Parse for commands
        commands, remaining_text = _parse_commands(response)

        if commands:
            # Record AI response in memory
            add_to_history(chat_id, "assistant", f"[suggested: {', '.join(commands)}]")

            if len(commands) == 1:
                # ── Single command → suggest with button ──
                _suggest_single_command(chat_id, commands[0], edit_message_id=status_msg.message_id)
            else:
                # ── Stage 3: Multi-step plan ──
                _suggest_plan(chat_id, commands, edit_message_id=status_msg.message_id)
        else:
            # Pure conversational response
            add_to_history(chat_id, "assistant", response[:500])
            if len(response) > 4000:
                response = response[:4000] + "\n...[truncated]"
            bot.edit_message_text(response, chat_id=chat_id, message_id=status_msg.message_id)

    threading.Thread(target=_process_with_ai, daemon=True).start()
