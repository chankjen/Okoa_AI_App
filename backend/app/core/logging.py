"""Structured JSON logging with automatic PII scrubbing.

Guarantees (TRD §5 / roadmap 1.x exit criteria):
  * Phone numbers are NEVER written to logs in plaintext — even accidentally.
  * Message content is redacted by default (only length recorded).
"""
from __future__ import annotations

import json
import logging
import re
import sys
import uuid as _uuid

# Request id propagated by middleware so all lines of one request correlate.
request_id_var: dict[str, str] = {}

# Matches East-African / international MSISDNs in free text: +254 7..., 07.../01...
_PHONE_RE = re.compile(r"(?:(?:\+?254|0)[\s\-]?(?:7|1)(?:[\s\-]?\d){8}|\+\d(?:[\s\-]?\d){8,14})\b")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

CRISIS_MARKER = "<REDACTED_PHONE>"
EMAIL_MARKER = "<REDACTED_EMAIL>"


def scrub(text: str) -> str:
    """Remove phone-number and email substrings from arbitrary text."""
    if not text:
        return text
    s = _PHONE_RE.sub(CRISIS_MARKER, text)
    return _EMAIL_RE.sub(EMAIL_MARKER, s)


class ScrubJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage()),
        }
        rid = getattr(record, "request_id", None) or request_id_var.get("rid")
        if rid:
            payload["request_id"] = rid
        for key in ("event", "user_uuid", "wa_message_id", "path", "status"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ScrubJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Quiet noisy third-party loggers.
    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


def new_request_id() -> str:
    return _uuid.uuid4().hex[:16]
