"""Logging to a file in the data directory, without sensitive data (constitution 6).

Code must not log email content or credentials in the first place; the filter is a
safety net that redacts what slips through: email addresses, tokens and secrets, and
the values of subject/body fields. It runs on the handler, so it also covers records
propagated from child loggers (``exitmap.*``) and formatted tracebacks.
"""

import logging
import re
from pathlib import Path

from exitmap.config import ensure_data_dir

LOGGER_NAME = "exitmap"
LOG_FILE_NAME = "exitmap.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
REDACTED = "[redacted]"

_SECRET_KEYS = (
    r"access_token|refresh_token|id_token|token|client_secret|secret|password|"
    r"contraseña|code_verifier|authorization"
)
_CONTENT_KEYS = r"subject|asunto|body|cuerpo|snippet"

_PATTERNS = (
    # "Bearer <token>" (e.g. an Authorization header).
    (re.compile(r"(?i)\bbearer\s+\S+"), f"Bearer {REDACTED}"),
    # key=value / key: value / "key": "value" for credentials.
    (
        re.compile(rf"(?i)(\b(?:{_SECRET_KEYS})\b[\"']?\s*[:=]\s*)[\"']?[^\s,;&\"'}}]+[\"']?"),
        rf"\1{REDACTED}",
    ),
    # OAuth authorization code in a redirect URL.
    (re.compile(r"([?&]code=)[^&\s]+"), rf"\1{REDACTED}"),
    # Subject/body fields: the value runs to the end of the line.
    (re.compile(rf"(?im)(\b(?:{_CONTENT_KEYS})\b[\"']?\s*[:=]\s*).*$"), rf"\1{REDACTED}"),
    # Google access (ya29.) and refresh (1//) tokens.
    (re.compile(r"\bya29\.[\w.-]+|(?<![\w/])1//[\w.-]+"), REDACTED),
    # JWTs (e.g. Microsoft id_token).
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]*"), REDACTED),
    # Email addresses.
    (re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)+"), REDACTED),
)


def redact(text: str) -> str:
    """Return ``text`` with addresses, tokens and subject/body values replaced."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Redact the message, traceback and stack of every record; never drops records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def setup_logging(directory: Path | None = None, level: int = logging.INFO) -> Path:
    """Send ``exitmap`` logs to ``<data dir>/exitmap.log`` through the filter.

    Calling it again replaces the previous handler. Returns the log file path.
    """
    directory = ensure_data_dir(directory)
    log_path = directory / LOG_FILE_NAME

    logger = logging.getLogger(LOGGER_NAME)
    for old in [h for h in logger.handlers if getattr(h, "_exitmap", False)]:
        logger.removeHandler(old)
        old.close()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler._exitmap = True
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(SensitiveDataFilter())
    logger.addHandler(handler)
    logger.setLevel(level)
    return log_path
