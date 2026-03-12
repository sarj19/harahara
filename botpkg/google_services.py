"""Google Calendar and Gmail service wrappers.

Provides thin, bot-friendly functions over the Google APIs.
All functions gracefully return None/empty when Google isn't configured.
"""
import base64
import email.mime.text
from datetime import datetime, timedelta

from botpkg import logger

try:
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


def _get_calendar_service():
    """Build and return a Calendar API service, or None."""
    from botpkg.google_auth import get_credentials
    creds = get_credentials()
    if not creds:
        return None
    try:
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to build Calendar service: {e}")
        return None


def _get_gmail_service():
    """Build and return a Gmail API service, or None."""
    from botpkg.google_auth import get_credentials
    creds = get_credentials()
    if not creds:
        return None
    try:
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to build Gmail service: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# Calendar
# ═══════════════════════════════════════════════════════════════════

def get_events_today():
    """Get today's calendar events."""
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return get_events_range(start, end)


def get_events_tomorrow():
    """Get tomorrow's calendar events."""
    now = datetime.now()
    start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return get_events_range(start, end)


def get_events_week():
    """Get this week's calendar events."""
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return get_events_range(start, end)


def get_events_range(start, end):
    """Get calendar events in a date range.

    Returns list of dicts: [{"summary", "start", "end", "location"}]
    """
    service = _get_calendar_service()
    if not service:
        return None

    try:
        time_min = start.isoformat() + "Z" if start.tzinfo is None else start.isoformat()
        time_max = end.isoformat() + "Z" if end.tzinfo is None else end.isoformat()

        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute()

        events = []
        for item in result.get("items", []):
            start_dt = item.get("start", {})
            end_dt = item.get("end", {})
            events.append({
                "summary": item.get("summary", "(No title)"),
                "start": start_dt.get("dateTime", start_dt.get("date", "")),
                "end": end_dt.get("dateTime", end_dt.get("date", "")),
                "location": item.get("location", ""),
            })
        return events
    except Exception as e:
        logger.error(f"Calendar API error: {e}")
        return None


def quick_add_event(text):
    """Quick-add a calendar event using natural language.

    Example: "Meeting tomorrow at 3pm with John"
    Returns the created event dict or None.
    """
    service = _get_calendar_service()
    if not service:
        return None

    try:
        result = service.events().quickAdd(
            calendarId="primary",
            text=text,
        ).execute()
        return {
            "summary": result.get("summary", text),
            "start": result.get("start", {}).get("dateTime", ""),
            "link": result.get("htmlLink", ""),
        }
    except Exception as e:
        logger.error(f"Calendar quick-add error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# Gmail
# ═══════════════════════════════════════════════════════════════════

def get_inbox(count=5):
    """Get recent inbox messages.

    Returns list of dicts: [{"id", "from", "subject", "snippet", "date", "unread"}]
    """
    service = _get_gmail_service()
    if not service:
        return None

    try:
        result = service.users().messages().list(
            userId="me",
            labelIds=["INBOX"],
            maxResults=count,
        ).execute()

        messages = []
        for msg_info in result.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=msg_info["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            messages.append({
                "id": msg_info["id"],
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(No subject)"),
                "snippet": msg.get("snippet", ""),
                "date": headers.get("Date", ""),
                "unread": "UNREAD" in msg.get("labelIds", []),
            })
        return messages
    except Exception as e:
        logger.error(f"Gmail inbox error: {e}")
        return None


def search_mail(query, count=10):
    """Search Gmail using Gmail search syntax.

    Examples: "from:rabi", "is:unread", "subject:invoice"
    Returns list of message dicts (same format as get_inbox).
    """
    service = _get_gmail_service()
    if not service:
        return None

    try:
        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=count,
        ).execute()

        messages = []
        for msg_info in result.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=msg_info["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            messages.append({
                "id": msg_info["id"],
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(No subject)"),
                "snippet": msg.get("snippet", ""),
                "date": headers.get("Date", ""),
            })
        return messages
    except Exception as e:
        logger.error(f"Gmail search error: {e}")
        return None


def get_message(msg_id):
    """Get full message body by ID.

    Returns dict: {"from", "subject", "date", "body"}
    """
    service = _get_gmail_service()
    if not service:
        return None

    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full",
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        # Extract body text
        body = _extract_body(msg.get("payload", {}))

        return {
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "(No subject)"),
            "date": headers.get("Date", ""),
            "body": body[:3000],  # Truncate for Telegram
        }
    except Exception as e:
        logger.error(f"Gmail message error: {e}")
        return None


def send_mail(to, subject, body_text):
    """Send an email.

    Returns dict: {"id", "threadId"} or None.
    """
    service = _get_gmail_service()
    if not service:
        return None

    try:
        message = email.mime.text.MIMEText(body_text)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()

        return {"id": result.get("id"), "threadId": result.get("threadId")}
    except Exception as e:
        logger.error(f"Gmail send error: {e}")
        return None


def _extract_body(payload):
    """Extract plain text body from a Gmail message payload."""
    # Check for direct body
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    # Check parts (multipart messages)
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        # Recurse into nested parts
        if part.get("parts"):
            result = _extract_body(part)
            if result:
                return result

    return "(Could not extract message body)"


def format_events_text(events, label="Events"):
    """Format a list of calendar events into Telegram-friendly text."""
    if not events:
        return f"📅 No {label.lower()} found."

    lines = [f"📅 *{label}* ({len(events)})\n"]
    for ev in events:
        start = ev.get("start", "")
        # Parse time from ISO format
        time_str = ""
        if "T" in start:
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M")
            except Exception:
                time_str = start
        else:
            time_str = "All day"

        line = f"  `{time_str}` — {ev['summary']}"
        if ev.get("location"):
            line += f" 📍 _{ev['location']}_"
        lines.append(line)

    return "\n".join(lines)


def format_inbox_text(messages, label="Inbox"):
    """Format a list of email messages into Telegram-friendly text."""
    if not messages:
        return f"📧 No messages found."

    lines = [f"📧 *{label}* ({len(messages)})\n"]
    for i, msg in enumerate(messages, 1):
        sender = msg.get("from", "Unknown")
        # Shorten sender: "John Doe <john@example.com>" → "John Doe"
        if "<" in sender:
            sender = sender.split("<")[0].strip().strip('"')
        if len(sender) > 25:
            sender = sender[:22] + "..."

        unread = "🔵" if msg.get("unread") else "  "
        subject = msg.get("subject", "(No subject)")
        if len(subject) > 45:
            subject = subject[:42] + "..."

        lines.append(f"  {unread} *{i}.* {subject}")
        lines.append(f"       _{sender}_  `{msg.get('id', '')[:8]}`")

    lines.append(f"\n_Use_ `/mail read <id>` _to read a message._")
    return "\n".join(lines)
