"""Persistent notes — multi-backend storage for quick memos.

Backends:
  - local (default): JSON file at NOTES_FILE path
  - apple: Apple Notes via AppleScript (syncs to iCloud/all devices)
  - google: Google Tasks via Tasks API (requires Google OAuth2 setup)

Set via BOT_NOTES_BACKEND env var.
"""
import json
import os
import subprocess
from datetime import datetime

from botpkg import logger
from settings import NOTES_FILE

try:
    from settings import NOTES_BACKEND
except ImportError:
    NOTES_BACKEND = "local"

_deleted_notes = {}  # Volatile storage for undo



# ═══════════════════════════════════════════════════════════════════
# Backend Detection
# ═══════════════════════════════════════════════════════════════════

def get_backend():
    """Get the active notes backend name."""
    return NOTES_BACKEND


def get_backend_label():
    """Get a human-readable label for current backend."""
    return {"local": "📁 Local", "apple": "🍎 Apple Notes", "google": "☁️ Google Tasks"}.get(NOTES_BACKEND, "📁 Local")


# ═══════════════════════════════════════════════════════════════════
# Local Backend (JSON file)
# ═══════════════════════════════════════════════════════════════════

def _load_notes_local():
    if not os.path.exists(NOTES_FILE):
        return []
    try:
        with open(NOTES_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading notes: {e}")
        return []


def _save_notes_local(notes):
    try:
        os.makedirs(os.path.dirname(NOTES_FILE) or ".", exist_ok=True)
        with open(NOTES_FILE, "w") as f:
            json.dump(notes, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving notes: {e}")


def _next_id(notes):
    if not notes:
        return 1
    return max(n["id"] for n in notes) + 1


def _save_note_local(text):
    notes = _load_notes_local()
    note_id = _next_id(notes)
    notes.append({
        "id": note_id,
        "text": text,
        "created": datetime.now().isoformat(timespec="seconds"),
    })
    _save_notes_local(notes)
    return note_id


def _list_notes_local():
    return _load_notes_local()


def _search_notes_local(query):
    query_lower = query.lower()
    return [n for n in _load_notes_local() if query_lower in n["text"].lower()]


def _delete_note_local(note_id):
    notes = _load_notes_local()
    original_len = len(notes)
    deleted_note = next((n for n in notes if n["id"] == note_id), None)
    notes = [n for n in notes if n["id"] != note_id]
    if len(notes) < original_len:
        _save_notes_local(notes)
        return deleted_note
    return None


# ═══════════════════════════════════════════════════════════════════
# Apple Notes Backend (AppleScript)
# ═══════════════════════════════════════════════════════════════════

HARAHARA_FOLDER = "harahara"


def _ensure_apple_folder():
    """Ensure the harahara folder exists in Apple Notes."""
    script = f'''
    tell application "Notes"
        if not (exists folder "{HARAHARA_FOLDER}") then
            make new folder with properties {{name:"{HARAHARA_FOLDER}"}}
        end if
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    except Exception as e:
        logger.warning(f"Could not ensure Apple Notes folder: {e}")


def _save_note_apple(text):
    _ensure_apple_folder()
    # Use note title as first line, body as full text
    title = text[:50].replace('"', '\\"')
    body = text.replace('"', '\\"').replace('\n', '\\n')
    script = f'''
    tell application "Notes"
        tell folder "{HARAHARA_FOLDER}"
            make new note with properties {{name:"{title}", body:"{body}"}}
        end tell
    end tell
    return "ok"
    '''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            # Also save locally for ID tracking
            note_id = _save_note_local(text)
            logger.info(f"Note saved to Apple Notes + local (#{note_id})")
            return note_id
    except Exception as e:
        logger.error(f"Apple Notes save error: {e}")
    # Fallback to local
    return _save_note_local(text)


def _list_notes_apple():
    """List notes from Apple Notes harahara folder."""
    _ensure_apple_folder()
    script = f'''
    tell application "Notes"
        set noteList to ""
        tell folder "{HARAHARA_FOLDER}"
            repeat with n in notes
                set noteList to noteList & id of n & "|||" & name of n & "|||" & creation date of n & linefeed
            end repeat
        end tell
        return noteList
    end tell
    '''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            notes = []
            for i, line in enumerate(result.stdout.strip().split("\n"), 1):
                parts = line.split("|||")
                if len(parts) >= 2:
                    notes.append({
                        "id": i,
                        "text": parts[1].strip(),
                        "created": parts[2].strip() if len(parts) > 2 else "",
                    })
            return notes
    except Exception as e:
        logger.error(f"Apple Notes list error: {e}")
    return _list_notes_local()


def _search_notes_apple(query):
    """Search Apple Notes — fall back to searching local + Apple list."""
    all_notes = _list_notes_apple()
    q = query.lower()
    return [n for n in all_notes if q in n["text"].lower()]


def _delete_note_apple(note_id):
    """Delete from local. Apple Notes doesn't support easy deletion by ID via AppleScript."""
    logger.info(f"Note #{note_id} deleted from local (Apple Notes deletion not supported via bot)")
    return _delete_note_local(note_id)


# ═══════════════════════════════════════════════════════════════════
# Google Tasks Backend
# ═══════════════════════════════════════════════════════════════════

GOOGLE_TASKLIST_TITLE = "harahara notes"


def _get_tasks_service():
    """Build Google Tasks API service."""
    try:
        from botpkg.google_auth import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        if not creds:
            return None
        return build("tasks", "v1", credentials=creds)
    except Exception as e:
        logger.error(f"Google Tasks service error: {e}")
        return None


def _get_or_create_tasklist(service):
    """Get or create the harahara task list."""
    try:
        result = service.tasklists().list().execute()
        for tl in result.get("items", []):
            if tl["title"] == GOOGLE_TASKLIST_TITLE:
                return tl["id"]
        # Create it
        new_list = service.tasklists().insert(body={"title": GOOGLE_TASKLIST_TITLE}).execute()
        return new_list["id"]
    except Exception as e:
        logger.error(f"Google Tasks list error: {e}")
        return None


def _save_note_google(text):
    service = _get_tasks_service()
    if not service:
        logger.warning("Google Tasks not available, saving locally")
        return _save_note_local(text)

    tasklist_id = _get_or_create_tasklist(service)
    if not tasklist_id:
        return _save_note_local(text)

    try:
        task = service.tasks().insert(
            tasklist=tasklist_id,
            body={"title": text[:1024], "notes": text},
        ).execute()
        # Also save locally
        note_id = _save_note_local(text)
        logger.info(f"Note saved to Google Tasks + local (#{note_id})")
        return note_id
    except Exception as e:
        logger.error(f"Google Tasks save error: {e}")
        return _save_note_local(text)


def _list_notes_google():
    service = _get_tasks_service()
    if not service:
        return _list_notes_local()

    tasklist_id = _get_or_create_tasklist(service)
    if not tasklist_id:
        return _list_notes_local()

    try:
        result = service.tasks().list(tasklist=tasklist_id, maxResults=50).execute()
        notes = []
        for i, task in enumerate(result.get("items", []), 1):
            notes.append({
                "id": i,
                "text": task.get("title", ""),
                "created": task.get("updated", ""),
                "google_id": task.get("id", ""),
            })
        return notes
    except Exception as e:
        logger.error(f"Google Tasks list error: {e}")
        return _list_notes_local()


def _search_notes_google(query):
    all_notes = _list_notes_google()
    q = query.lower()
    return [n for n in all_notes if q in n["text"].lower()]


def _delete_note_google(note_id):
    """Delete from local only — Google Tasks would need the google_id."""
    return _delete_note_local(note_id)


# ═══════════════════════════════════════════════════════════════════
# Public API — dispatches to active backend
# ═══════════════════════════════════════════════════════════════════

def save_note(text):
    """Save a note using the active backend."""
    if NOTES_BACKEND == "apple":
        return _save_note_apple(text)
    elif NOTES_BACKEND == "google":
        return _save_note_google(text)
    return _save_note_local(text)


def list_notes():
    """List notes using the active backend."""
    if NOTES_BACKEND == "apple":
        return _list_notes_apple()
    elif NOTES_BACKEND == "google":
        return _list_notes_google()
    return _list_notes_local()


def search_notes(query):
    """Search notes using the active backend."""
    if NOTES_BACKEND == "apple":
        return _search_notes_apple(query)
    elif NOTES_BACKEND == "google":
        return _search_notes_google(query)
    return _search_notes_local(query)


def delete_note(note_id):
    """Delete a note using the active backend."""
    if NOTES_BACKEND == "apple":
        return _delete_note_apple(note_id)
    elif NOTES_BACKEND == "google":
        return _delete_note_google(note_id)
    return _delete_note_local(note_id)
