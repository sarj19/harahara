"""Remind, say, and voices handlers."""
import subprocess
import threading
import time

from botpkg import bot, logger
from settings import BOT_VOICE
from botpkg.utils import parse_duration


# ═══════════════════════════════════════════════════════════════════
# Remind
# ═══════════════════════════════════════════════════════════════════

def handle_remind(message, chat_id, text):
    parts_r = text.split(" ", 2)
    
    if len(parts_r) < 2:
        msg = bot.reply_to(message, "⏰ When should I remind you? (e.g. `5m`, `2h`, `30s`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, _remind_step_duration, chat_id=chat_id)
        return
        
    if len(parts_r) < 3:
        delay, label = parse_duration(parts_r[1])
        if delay is None:
            bot.reply_to(message, "❌ Invalid duration. Use a number with optional suffix: `30`, `5m`, `2h`", parse_mode="Markdown")
            return
        msg = bot.reply_to(message, f"⏰ What's the reminder for {label}?", parse_mode="Markdown")
        bot.register_next_step_handler(msg, _remind_step_message, delay=delay, label=label, chat_id=chat_id)
        return

    delay, label = parse_duration(parts_r[1])
    if delay is None:
        bot.reply_to(message, "❌ Invalid duration. Use a number with optional suffix: `30`, `5m`, `2h`", parse_mode="Markdown")
        return
    _set_reminder(message, chat_id, delay, label, parts_r[2])

def _remind_step_duration(message, chat_id):
    if not message.text:
        return
    dur_text = message.text.strip()
    if dur_text.startswith("/"): return  # Cancel if they send another command
    
    delay, label = parse_duration(dur_text)
    if delay is None:
        bot.reply_to(message, "❌ Invalid duration. Cancelled reminder.", parse_mode="Markdown")
        return
        
    msg = bot.reply_to(message, f"⏰ Got it. What's the reminder for {label}?", parse_mode="Markdown")
    bot.register_next_step_handler(msg, _remind_step_message, delay=delay, label=label, chat_id=chat_id)

def _remind_step_message(message, delay, label, chat_id):
    if not message.text:
        return
    reminder_msg = message.text.strip()
    if reminder_msg.startswith("/"): return
    _set_reminder(message, chat_id, delay, label, reminder_msg)

def _set_reminder(message, chat_id, delay, label, reminder_msg):
    bot.reply_to(message, f"⏰ Reminder set for {label}.")
    def send_reminder():
        time.sleep(delay)
        bot.send_message(chat_id, f"🔔 Reminder: {reminder_msg}")
    threading.Thread(target=send_reminder, daemon=True).start()
    logger.info(f"Reminder set: {label} ({delay}s) - {reminder_msg}")


# ═══════════════════════════════════════════════════════════════════
# Say & Voices
# ═══════════════════════════════════════════════════════════════════

def handle_say(message, chat_id, text):
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/say <text>`", parse_mode="Markdown")
        return
    cmd = ["say"]
    if BOT_VOICE:
        cmd.extend(["-v", BOT_VOICE])
    cmd.append(args)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
        voice_label = f" (voice: {BOT_VOICE})" if BOT_VOICE else ""
        bot.reply_to(message, f"🔊 Spoke: `{args[:50]}{'...' if len(args) > 50 else ''}`{voice_label}", parse_mode="Markdown")
        logger.info(f"Say command: {args[:50]}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Say error: {e}")
        logger.error(f"Say error: {e}")


def handle_voices(message, chat_id, text):
    try:
        result = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=10
        )
        output = result.stdout.strip()
        if not output:
            bot.send_message(chat_id, "❌ No voices found.")
            return
        voices = []
        for line in output.split("\n"):
            parts = line.split()
            if parts:
                voices.append(parts[0])
        voice_list = ", ".join(voices[:50])
        current = f"\n\n🎙 Current voice: *{BOT_VOICE}*" if BOT_VOICE else "\n\n🎙 Using default voice"
        bot.send_message(
            chat_id,
            f"🗣 *Available Voices ({len(voices)}):*\n`{voice_list}`{current}\n\n💡 Set via `BOT_VOICE` in `.env`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.send_message(chat_id, f"❌ Voices error: {e}")
        logger.error(f"Voices error: {e}")
