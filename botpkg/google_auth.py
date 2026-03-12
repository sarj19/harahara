"""Google OAuth2 authentication for Calendar and Gmail APIs.

Handles credential storage, token refresh, and the initial auth flow.
Token stored in personal/google_token.json (gitignored).
"""
import os

from botpkg import logger

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False

try:
    from settings import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH
except ImportError:
    GOOGLE_CREDENTIALS_PATH = "./personal/google_credentials.json"
    GOOGLE_TOKEN_PATH = "./personal/google_token.json"

# Scopes required for Calendar + Gmail
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/tasks",
]


def is_google_available():
    """Check if Google API libraries are installed."""
    return GOOGLE_LIBS_AVAILABLE


def is_google_configured():
    """Check if Google credentials are set up and usable."""
    if not GOOGLE_LIBS_AVAILABLE:
        return False
    return os.path.exists(GOOGLE_TOKEN_PATH) or os.path.exists(GOOGLE_CREDENTIALS_PATH)


def has_valid_token():
    """Check if a valid (or refreshable) token exists."""
    if not GOOGLE_LIBS_AVAILABLE or not os.path.exists(GOOGLE_TOKEN_PATH):
        return False
    try:
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, SCOPES)
        return creds and (creds.valid or creds.refresh_token)
    except Exception:
        return False


def get_credentials():
    """Get valid Google API credentials.

    Returns Credentials object or None if not configured.
    Automatically refreshes expired tokens.
    """
    if not GOOGLE_LIBS_AVAILABLE:
        return None

    creds = None

    # Load existing token
    if os.path.exists(GOOGLE_TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.error(f"Error loading Google token: {e}")

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
        except Exception as e:
            logger.error(f"Error refreshing Google token: {e}")
            creds = None

    return creds if (creds and creds.valid) else None


def run_auth_flow():
    """Run the one-time OAuth2 consent flow.

    Opens a browser for the user to authorize.
    Saves the resulting token to GOOGLE_TOKEN_PATH.
    """
    if not GOOGLE_LIBS_AVAILABLE:
        raise RuntimeError(
            "Google API libraries not installed.\n"
            "Run: pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )

    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Credentials file not found: {GOOGLE_CREDENTIALS_PATH}\n"
            "Download from Google Cloud Console → APIs & Services → Credentials → OAuth2 Desktop App"
        )

    flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    print("✅ Google authentication successful! Token saved.")
    return creds


def _save_token(creds):
    """Save credentials to token file."""
    os.makedirs(os.path.dirname(GOOGLE_TOKEN_PATH) or ".", exist_ok=True)
    with open(GOOGLE_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())


def get_setup_instructions():
    """Return user-friendly setup instructions."""
    return (
        "📅 *Google Calendar & Gmail Setup*\n\n"
        "*Step 1:* Go to [Google Cloud Console](https://console.cloud.google.com)\n"
        "*Step 2:* Create a project (or select one)\n"
        "*Step 3:* Enable _Google Calendar API_ and _Gmail API_\n"
        "  → APIs & Services → Library → search and enable both\n"
        "*Step 4:* Create OAuth credentials\n"
        "  → APIs & Services → Credentials → Create → OAuth Client ID → Desktop App\n"
        "*Step 5:* Download the JSON and save it as:\n"
        "  `personal/google_credentials.json`\n"
        "*Step 6:* Run `/googlesetup` to complete authentication\n\n"
        "_Or run `setup.sh` again — it includes a Google setup step._"
    )
