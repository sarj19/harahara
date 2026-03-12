"""Google integrations: calendar, mail, googlesetup."""
import os
import subprocess

from botpkg import bot, logger


# ═══════════════════════════════════════════════════════════════════
# Calendar
# ═══════════════════════════════════════════════════════════════════

def handle_calendar(message, chat_id, text):
    """Handle /calendar [today|tomorrow|week|add <text>]."""
    from botpkg.google_auth import is_google_configured, has_valid_token, get_setup_instructions
    from botpkg.google_services import (
        get_events_today, get_events_tomorrow, get_events_week,
        quick_add_event, format_events_text, GOOGLE_API_AVAILABLE,
    )

    args = text.split(" ", 1)[1].strip() if " " in text else "today"

    if is_google_configured() and has_valid_token() and GOOGLE_API_AVAILABLE:
        if args.startswith("add "):
            event_text = args[4:].strip()
            if not event_text:
                bot.reply_to(message, "📅 Usage: `/calendar add Meeting tomorrow at 3pm`", parse_mode="Markdown")
                return
            bot.reply_to(message, "📅 Adding event...")
            result = quick_add_event(event_text)
            if result:
                msg = f"✅ Event created: *{result['summary']}*"
                if result.get("start"):
                    msg += f"\n⏰ {result['start']}"
                if result.get("link"):
                    msg += f"\n🔗 [Open]({result['link']})"
                bot.send_message(chat_id, msg, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "❌ Failed to create event.")
            return

        if args in ("tomorrow", "tmrw"):
            events = get_events_tomorrow()
            label = "Tomorrow"
        elif args in ("week", "w"):
            events = get_events_week()
            label = "This Week"
        else:
            events = get_events_today()
            label = "Today"

        if events is not None:
            bot.send_message(chat_id, format_events_text(events, label), parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ Failed to fetch calendar events. Try `/googlesetup`.", parse_mode="Markdown")
        return

    # macOS native fallback
    try:
        script = '''
        set today to current date
        set todayStart to today - (time of today)
        set todayEnd to todayStart + (1 * days)
        set output to ""
        tell application "Calendar"
            repeat with c in calendars
                set evts to (every event of c whose start date ≥ todayStart and start date < todayEnd)
                repeat with e in evts
                    set output to output & (start date of e as string) & " | " & summary of e & linefeed
                end repeat
            end repeat
        end tell
        if output is "" then
            return "No events today."
        end if
        return output
        '''
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            bot.send_message(chat_id, f"📅 *Today's Events* (via Calendar.app)\n\n```\n{result.stdout.strip()}\n```", parse_mode="Markdown")
            return
    except Exception as e:
        logger.warning(f"Calendar AppleScript fallback failed: {e}")

    msg = (
        "📅 *Calendar not configured.*\n\n"
        "*Option 1 — macOS native:*\n"
        "  Add your Google account in System Settings → Internet Accounts.\n"
        "  Calendar.app will sync automatically.\n\n"
        "*Option 2 — Google API (recommended):*\n"
        "  Run `/googlesetup` for full calendar access.\n"
        "  Supports: today, tomorrow, week, add events."
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# Mail
# ═══════════════════════════════════════════════════════════════════

def handle_mail(message, chat_id, text):
    """Handle /mail [count|search <q>|read <id>|send <to> <subject> <body>]."""
    from botpkg.google_auth import is_google_configured, has_valid_token, get_setup_instructions
    from botpkg.google_services import (
        get_inbox, search_mail, get_message, send_mail,
        format_inbox_text, GOOGLE_API_AVAILABLE,
    )

    args = text.split(" ", 1)[1].strip() if " " in text else ""

    if is_google_configured() and has_valid_token() and GOOGLE_API_AVAILABLE:
        if args.startswith("search "):
            query = args[7:].strip()
            if not query:
                bot.reply_to(message, "📧 Usage: `/mail search from:john`", parse_mode="Markdown")
                return
            bot.reply_to(message, f"🔍 Searching: _{query}_...", parse_mode="Markdown")
            results = search_mail(query)
            if results is not None:
                bot.send_message(chat_id, format_inbox_text(results, f"Search: {query}"), parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "❌ Search failed.")
            return

        if args.startswith("read "):
            msg_id = args[5:].strip()
            if not msg_id:
                bot.reply_to(message, "📧 Usage: `/mail read <message_id>`", parse_mode="Markdown")
                return
            msg_data = get_message(msg_id)
            if msg_data:
                email_text = (
                    f"📧 *{msg_data['subject']}*\n"
                    f"From: _{msg_data['from']}_\n"
                    f"Date: {msg_data['date']}\n\n"
                    f"{msg_data['body']}"
                )
                if len(email_text) > 4000:
                    email_text = email_text[:4000] + "\n...[truncated]"
                bot.send_message(chat_id, email_text, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"❌ Could not find message `{msg_id}`.", parse_mode="Markdown")
            return

        if args.startswith("send "):
            parts = args[5:].strip().split(" ", 1)
            if len(parts) < 2:
                bot.reply_to(message, "📧 Usage: `/mail send user@email.com Subject | Body text`", parse_mode="Markdown")
                return
            to_addr = parts[0]
            rest = parts[1]
            if "|" in rest:
                subject, body = rest.split("|", 1)
            else:
                subject = rest
                body = rest
            result = send_mail(to_addr, subject.strip(), body.strip())
            if result:
                bot.send_message(chat_id, f"✅ Email sent to `{to_addr}`", parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "❌ Failed to send email.")
            return

        count = 5
        if args.isdigit():
            count = min(int(args), 20)

        bot.reply_to(message, "📧 Fetching inbox...")
        messages = get_inbox(count)
        if messages is not None:
            bot.send_message(chat_id, format_inbox_text(messages), parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ Failed to fetch inbox. Try `/googlesetup`.", parse_mode="Markdown")
        return

    # macOS native fallback
    try:
        script = '''
        tell application "Mail"
            set msgs to messages 1 thru 5 of inbox
            set output to ""
            repeat with m in msgs
                set output to output & "From: " & (sender of m) & linefeed
                set output to output & "Subject: " & (subject of m) & linefeed & "---" & linefeed
            end repeat
            return output
        end tell
        '''
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            bot.send_message(chat_id, f"📧 *Recent Email* (via Mail.app)\n\n```\n{result.stdout.strip()}\n```", parse_mode="Markdown")
            return
    except Exception as e:
        logger.warning(f"Mail AppleScript fallback failed: {e}")

    msg = (
        "📧 *Email not configured.*\n\n"
        "*Option 1 — macOS native:*\n"
        "  Add your Google account in System Settings → Internet Accounts.\n"
        "  Mail.app will sync automatically.\n\n"
        "*Option 2 — Google API (recommended):*\n"
        "  Run `/googlesetup` for full Gmail access.\n"
        "  Supports: inbox, search, read, send."
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
# Google Setup
# ═══════════════════════════════════════════════════════════════════

def handle_googlesetup(message, chat_id, text):
    """Handle /googlesetup — run Google OAuth2 auth flow."""
    from botpkg.google_auth import (
        is_google_available, is_google_configured, has_valid_token,
        run_auth_flow, get_setup_instructions, GOOGLE_CREDENTIALS_PATH,
    )

    if not is_google_available():
        bot.reply_to(
            message,
            "❌ Google API libraries not installed.\n\n"
            "Run:\n```\npip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib\n```\n"
            "Then try `/googlesetup` again.",
            parse_mode="Markdown",
        )
        return

    if has_valid_token():
        bot.reply_to(message, "✅ Google is already configured and authenticated!\n\nTry `/calendar` or `/mail`.")
        return

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        bot.send_message(chat_id, get_setup_instructions(), parse_mode="Markdown")
        return

    bot.reply_to(message, "🔐 Starting Google Auth...\nA browser will open on your Mac for consent.")
    try:
        run_auth_flow()
        bot.send_message(chat_id, "✅ Google authentication successful!\n\nTry `/calendar` or `/mail`.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Auth failed: {e}\n\nMake sure you're at the Mac and can access a browser.")
