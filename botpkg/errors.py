"""Bot exception hierarchy for clearer error handling."""


class BotError(Exception):
    """Base exception for all bot errors."""
    pass


class BotConfigError(BotError):
    """Configuration error — missing env vars, invalid settings."""
    pass


class BotTimeoutError(BotError):
    """Command or operation timed out."""
    pass


class BotUserError(BotError):
    """User input error — bad syntax, missing arguments."""
    pass


class BotSystemError(BotError):
    """System error — disk full, permission denied, subprocess failure."""
    pass


class BotAPIError(BotError):
    """External API error — Telegram rate limit, Google API failure."""
    pass
