"""System control handlers: screenshot, webcam, key, type, kill, open, quit, restartbot, logs."""
import os
import subprocess
import threading
import time

from botpkg import bot, logger
from settings import LAUNCHD_SERVICE, SCRIPTS_DIR, LOG_FILE
from botpkg.config import MODIFIERS, KEY_CODES, screenshot_sessions
from botpkg.utils import send_file_smart, take_and_send_screenshot


# ═══════════════════════════════════════════════════════════════════
# Shared multi-capture helper (used by screenshot & webcam)
# ═══════════════════════════════════════════════════════════════════

def _parse_count(message, text, usage_msg):
    """Parse an optional positive integer count from command args.

    Returns (count, None) on success or (None, error_sent) if invalid.
    """
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        return 1, args
    if args.isdigit() and int(args) > 0:
        return int(args), args
    bot.reply_to(message, usage_msg, parse_mode="Markdown")
    return None, args


def _multi_capture(chat_id, count, capture_fn, emoji, label, cancellable=False):
    """Run capture_fn(chat_id, index) up to `count` times, 1 min apart.

    If cancellable=True, registers a cancel event in screenshot_sessions.
    """
    cancel_event = threading.Event() if cancellable else None
    if cancellable:
        screenshot_sessions[chat_id] = cancel_event

    def loop():
        try:
            for i in range(count):
                if cancel_event and cancel_event.is_set():
                    bot.send_message(chat_id, f"🛑 {label} session stopped at {i}/{count}.")
                    return
                if i > 0:
                    for _ in range(60):
                        if cancel_event and cancel_event.is_set():
                            bot.send_message(chat_id, f"🛑 {label} session stopped at {i}/{count}.")
                            return
                        time.sleep(1)
                    bot.send_message(chat_id, f"{emoji} Capturing {label.lower()} {i + 1}/{count}...")
                capture_fn(chat_id, i, count)
            if count > 1:
                bot.send_message(chat_id, f"✅ All {count} {label.lower()}s done.")
        finally:
            if cancellable:
                screenshot_sessions.pop(chat_id, None)

    if count == 1:
        loop()
    else:
        threading.Thread(target=loop, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# Handler functions
# ═══════════════════════════════════════════════════════════════════

def handle_screenshot(message, chat_id, text):
    screenshot_args = text.split(" ", 1)[1].strip() if " " in text else ""

    if screenshot_args.lower() == "stop":
        if chat_id in screenshot_sessions:
            screenshot_sessions[chat_id].set()
            bot.reply_to(message, "🛑 Screenshot session stopped.")
        else:
            bot.reply_to(message, "No active screenshot session.")
        return

    count, _ = _parse_count(message, text, "Usage: `/screenshot [count]` or `/screenshot stop`\nCount must be a positive integer.")
    if count is None:
        return

    if count == 1:
        bot.reply_to(message, "📸 Capturing screenshot...")
    else:
        bot.reply_to(message, f"📸 Capturing {count} screenshots (1 min apart)...")

    def capture_one(cid, i, total):
        take_and_send_screenshot(cid)
        logger.info(f"Screenshot {i + 1}/{total} sent successfully.")

    _multi_capture(chat_id, count, capture_one, "📸", "Screenshot", cancellable=True)


def handle_webcam(message, chat_id, text):
    count, _ = _parse_count(message, text, "Usage: `/webcam [count]`\nCount must be a positive integer.")
    if count is None:
        return

    if count == 1:
        bot.reply_to(message, "📷 Capturing webcam photo...")
    else:
        bot.reply_to(message, f"📷 Capturing {count} webcam photos (1 min apart)...")

    def capture_one(cid, i, total):
        webcam_path = f"/tmp/harahara_bot_webcam_{i}.jpg"
        try:
            subprocess.run(
                ["imagesnap", "-w", "1.5", webcam_path],
                check=True, capture_output=True, text=True,
            )
            if os.path.exists(webcam_path):
                send_file_smart(cid, webcam_path, caption=f"{i + 1}/{total}" if total > 1 else None)
                os.remove(webcam_path)
                logger.info(f"Webcam {i + 1}/{total} sent successfully.")
            else:
                bot.send_message(cid, f"❌ Webcam photo {i + 1}/{total} was not created.")
        except Exception as e:
            bot.send_message(cid, f"❌ Webcam {i + 1}/{total} error: {e}")
            logger.error(f"Webcam {i + 1}/{total} error: {e}")

    _multi_capture(chat_id, count, capture_one, "📷", "Webcam photo")


def handle_type(message, chat_id, text):
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/type <text>`", parse_mode="Markdown")
        return
    escaped = args.replace('\\', '\\\\').replace('"', '\\"')
    script = f'tell application "System Events" to keystroke "{escaped}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        bot.reply_to(message, f"⌨️ Typed: `{args[:50]}{'...' if len(args) > 50 else ''}`", parse_mode="Markdown")
        logger.info(f"Type command sent: {args[:50]}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Type error: {e}")
        logger.error(f"Type error: {e}")


def handle_url(message, chat_id, text):
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/url <url>`", parse_mode="Markdown")
        return
    try:
        subprocess.run(["open", args], check=True, capture_output=True, text=True)
        bot.reply_to(message, f"🌐 Opened: {args}")
        logger.info(f"Opened URL: {args}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ URL error: {e}")
        logger.error(f"URL error: {e}")


def handle_logs(message, chat_id, text, page=0, message_id=None):
    import telebot
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    n = 20
    if args and args.isdigit():
        n = int(args)
    try:
        result = subprocess.run(["tail", f"-{n}", LOG_FILE], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n') if result.stdout.strip() else ["(No logs)"]
        
        PAGE_SIZE = 15
        total_pages = max(1, (len(lines) + PAGE_SIZE - 1) // PAGE_SIZE)
        
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1
            
        start_idx = page * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        
        page_lines = lines[start_idx:end_idx]
        output = "\n".join(page_lines)
        if len(output) > 3500:
            output = output[-3500:]
            
        markup = None
        if total_pages > 1:
            markup = telebot.types.InlineKeyboardMarkup(row_width=3)
            row = []
            if page > 0:
                row.append(telebot.types.InlineKeyboardButton("⬅️ Prev", callback_data=f"logspage:{n}:{page-1}"))
            else:
                row.append(telebot.types.InlineKeyboardButton(" ", callback_data="ignore"))
                
            row.append(telebot.types.InlineKeyboardButton(f"Page {page+1}/{total_pages}", callback_data="ignore"))
            
            if page < total_pages - 1:
                row.append(telebot.types.InlineKeyboardButton("Next ➡️", callback_data=f"logspage:{n}:{page+1}"))
            else:
                row.append(telebot.types.InlineKeyboardButton(" ", callback_data="ignore"))
            
            markup.row(*row)
            markup.row(telebot.types.InlineKeyboardButton("📜 Show All", callback_data=f"logsall:{n}:0"))
            
        msg_text = f"📋 Last {n} log lines:\n```\n{output}\n```"
        if message_id:
            bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Logs error: {e}")

def handle_logs_all(chat_id, n):
    try:
        result = subprocess.run(["tail", f"-{n}", LOG_FILE], capture_output=True, text=True)
        output = result.stdout.strip() or "(No logs)"
        
        if len(output) > 4000:
            tmp_path = "/tmp/harahara_bot_logs_all.txt"
            with open(tmp_path, "w") as f:
                f.write(output)
            send_file_smart(chat_id, tmp_path, caption=f"📋 Full {n} log lines")
            os.remove(tmp_path)
        else:
            bot.send_message(chat_id, f"📋 Full {n} log lines:\n```\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Logs error: {e}")


def handle_kill(message, chat_id, text):
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/kill <process_name>`", parse_mode="Markdown")
        return
    try:
        result = subprocess.run(["killall", args], capture_output=True, text=True)
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            import telebot
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(f"↩️ Relaunch {args[:15]}", callback_data=f"undo_kill:{args}"))
            bot.reply_to(message, f"💀 Killed: {args}", reply_markup=markup)
        else:
            bot.reply_to(message, f"❌ {output or f'No process named {args} found.'}")
        logger.info(f"Kill command: {args} (exit {result.returncode})")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Kill error: {e}")
        logger.error(f"Kill error: {e}")



def handle_key(message, chat_id, text):
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/key <keys>`\nExamples: `/key enter`, `/key cmd l`, `/key alt shift 3`, `/key hello`", parse_mode="Markdown")
        return

    tokens = args.split()
    modifiers = []
    key_tokens = []

    for token in tokens:
        if token.lower() in MODIFIERS and not key_tokens:
            modifiers.append(MODIFIERS[token.lower()])
        else:
            key_tokens.append(token)

    modifier_clause = f" using {{{', '.join(modifiers)}}}" if modifiers else ""
    remaining = " ".join(key_tokens) if key_tokens else ""

    if not remaining and modifiers:
        bot.reply_to(message, "❌ Modifiers specified but no key given.")
        return

    if remaining.lower() in KEY_CODES:
        script = f'tell application "System Events" to key code {KEY_CODES[remaining.lower()]}{modifier_clause}'
    else:
        escaped = remaining.replace('\\', '\\\\').replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"{modifier_clause}'

    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        bot.reply_to(message, f"⌨️ Sent: `{args}`", parse_mode="Markdown")
        logger.info(f"Key command sent: {args} → {script}")
        take_and_send_screenshot(chat_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Key error: {e}")
        logger.error(f"Key command error: {e}")


def handle_open(message, chat_id, text):
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/open <app_name>`", parse_mode="Markdown")
        return
    bot.reply_to(message, f"📂 Opening {args}...")
    try:
        subprocess.run(["open", "-a", args], check=True, capture_output=True, text=True)
        time.sleep(2)
        take_and_send_screenshot(chat_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Open error: {e}")
        logger.error(f"Open error: {e}")


def handle_quit(message, chat_id, text):
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/quit <app_name>`", parse_mode="Markdown")
        return
    bot.reply_to(message, f"❌ Quitting {args}...")
    try:
        escaped_args = args.replace('"', '\\"')
        script = f'tell application "{escaped_args}" to quit'
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        time.sleep(2)
        take_and_send_screenshot(chat_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Quit error: {e}")
        logger.error(f"Quit error: {e}")


def handle_restartbot(message, chat_id, text):
    bot.reply_to(message, "🔄 Restarting bot...")
    logger.info("Bot restart requested via /restartbot.")
    subprocess.Popen(
        ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCHD_SERVICE}"],
        start_new_session=True,
    )


# ═══════════════════════════════════════════════════════════════════
# Screenshot Diff — visual change detection
# ═══════════════════════════════════════════════════════════════════

_DIFF_PREV_PATH = "/tmp/harahara_bot_diff_prev.png"
_DIFF_CURR_PATH = "/tmp/harahara_bot_diff_curr.png"
_DIFF_OUT_PATH = "/tmp/harahara_bot_diff_out.png"


def handle_diff(message, chat_id, text):
    """Take a screenshot and compare with the previous one, highlighting changes."""
    bot.reply_to(message, "📸 Capturing screenshot for comparison...")

    # Take current screenshot
    try:
        subprocess.run(
            ["screencapture", "-x", _DIFF_CURR_PATH],
            check=True, capture_output=True, timeout=10,
        )
    except Exception as e:
        bot.send_message(chat_id, f"❌ Screenshot failed: {e}")
        return

    if not os.path.exists(_DIFF_PREV_PATH):
        # First run — save as baseline
        import shutil
        shutil.copy2(_DIFF_CURR_PATH, _DIFF_PREV_PATH)
        send_file_smart(chat_id, _DIFF_CURR_PATH, caption="📸 First snapshot saved as baseline. Run /diff again to compare.")
        return

    try:
        from PIL import Image, ImageChops, ImageDraw

        prev = Image.open(_DIFF_PREV_PATH)
        curr = Image.open(_DIFF_CURR_PATH)

        # Resize if dimensions don't match
        if prev.size != curr.size:
            curr = curr.resize(prev.size)

        # Compute difference
        diff = ImageChops.difference(prev, curr)
        # Get bounding box of changed area
        bbox = diff.getbbox()

        if bbox is None:
            bot.send_message(chat_id, "✅ No visual changes detected.")
        else:
            # Draw red rectangle around changed area on the current image
            annotated = curr.copy()
            draw = ImageDraw.Draw(annotated)
            # Expand bbox slightly for visibility
            x1, y1, x2, y2 = bbox
            pad = 5
            x1 = max(0, x1 - pad)
            y1 = max(0, y1 - pad)
            x2 = min(curr.width, x2 + pad)
            y2 = min(curr.height, y2 + pad)
            for i in range(3):  # Draw thick border
                draw.rectangle([x1 + i, y1 + i, x2 - i, y2 - i], outline="red")

            annotated.save(_DIFF_OUT_PATH)

            # Calculate change percentage
            diff_gray = diff.convert("L")
            pixels = list(diff_gray.getdata())
            changed = sum(1 for p in pixels if p > 10)
            pct = (changed / len(pixels)) * 100

            send_file_smart(
                chat_id, _DIFF_OUT_PATH,
                caption=f"🔍 Changes detected! ({pct:.1f}% of pixels changed)\nRed box shows changed region.",
            )

        # Save current as next baseline
        import shutil
        shutil.copy2(_DIFF_CURR_PATH, _DIFF_PREV_PATH)

    except ImportError:
        bot.send_message(chat_id, "❌ PIL/Pillow not installed. Run: `pip install Pillow`")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Diff error: {e}")
        logger.error(f"Diff error: {e}")


# ═══════════════════════════════════════════════════════════════════
# Where — network context and geolocation
# ═══════════════════════════════════════════════════════════════════

def handle_where(message, chat_id, text):
    """Show network context: public IP, WiFi, geo, local IP."""
    bot.reply_to(message, "🗺 Gathering network info...")

    info_lines = ["🗺 *Network Context*\n"]

    # Public IP + geolocation
    try:
        import json
        result = subprocess.run(
            ["curl", "-s", "ipinfo.io/json"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result.stdout)
        ip = data.get("ip", "?")
        city = data.get("city", "?")
        region = data.get("region", "")
        country = data.get("country", "")
        org = data.get("org", "")
        loc = data.get("loc", "")
        info_lines.append(f"🌐 *Public IP:* `{ip}`")
        info_lines.append(f"📍 *Location:* {city}, {region}, {country}")
        if org:
            info_lines.append(f"🏢 *ISP:* {org}")
        if loc:
            info_lines.append(f"🗺 [Map](https://maps.google.com/?q={loc})")
    except Exception:
        info_lines.append("🌐 *Public IP:* (failed to fetch)")

    info_lines.append("")

    # WiFi SSID
    try:
        result = subprocess.run(
            ["networksetup", "-getairportnetwork", "en0"],
            capture_output=True, text=True, timeout=5,
        )
        ssid = result.stdout.strip().replace("Current Wi-Fi Network: ", "")
        info_lines.append(f"📡 *WiFi SSID:* `{ssid}`")
    except Exception:
        info_lines.append("📡 *WiFi:* (not available)")

    # WiFi signal strength
    try:
        airport_bin = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        if os.path.exists(airport_bin):
            result = subprocess.run(
                [airport_bin, "-I"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "agrCtlRSSI" in line:
                    rssi = line.split(":")[1].strip()
                    # Convert RSSI to signal quality
                    try:
                        rssi_val = int(rssi)
                        if rssi_val >= -50:
                            quality = "Excellent"
                        elif rssi_val >= -60:
                            quality = "Good"
                        elif rssi_val >= -70:
                            quality = "Fair"
                        else:
                            quality = "Weak"
                        info_lines.append(f"📶 *Signal:* {rssi} dBm ({quality})")
                    except ValueError:
                        info_lines.append(f"📶 *Signal:* {rssi} dBm")
                    break
    except Exception:
        pass

    # Local IP
    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            capture_output=True, text=True, timeout=5,
        )
        local_ip = result.stdout.strip()
        if local_ip:
            info_lines.append(f"🖥 *Local IP:* `{local_ip}`")
    except Exception:
        pass

    bot.send_message(chat_id, "\n".join(info_lines), parse_mode="Markdown", disable_web_page_preview=True)

