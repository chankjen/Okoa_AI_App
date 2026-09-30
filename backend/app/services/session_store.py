"""Redis-backed hot session state + webhook dedupe (roadmap 1.3).

Graceful degradation: if Redis is unavailable the service logs a warning and
falls back to DB-only operation — message flow must never break on cache miss.
Keys hold only UUIDs — no phone numbers ever enter Redis.
"""
from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis

from app.core.config import get_settings

import time

logger = logging.getLogger("okoa.session_store")

_client: aioredis.Redis | None = None
_last_failure_time: float = 0.0
_failure_cooldown_seconds: float = 15.0


async def get_redis() -> aioredis.Redis | None:
    global _client, _last_failure_time
    now = time.monotonic()
    if _last_failure_time > 0 and (now - _last_failure_time) < _failure_cooldown_seconds:
        return None

    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await _client.ping()
        if _last_failure_time > 0:
            logger.info("redis connection restored; exiting degraded mode")
            _last_failure_time = 0.0
        return _client
    except Exception as exc:  # pragma: no cover - infra-dependent
        if _last_failure_time == 0.0:
            logger.warning("redis unavailable, degrading to DB-only mode: %s", type(exc).__name__)
        _last_failure_time = now
        return None


def reset_for_tests(client: aioredis.Redis | None = None) -> None:
    global _client, _last_failure_time
    _client = client
    _last_failure_time = 0.0


class SessionStore:
    """Hot conversation-window state keyed by anonymous UUID."""

    PREFIX = "okoa:sess"
    DEDUPE_PREFIX = "okoa:dedupe"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _key(self, user_uuid: str) -> str:
        return f"{self.PREFIX}:{user_uuid}"

    async def touch(self, user_uuid: str, session_id: str) -> None:
        r = await get_redis()
        if r is None:
            return
        try:
            payload = json.dumps({"session_id": session_id})
            await r.setex(self._key(user_uuid), self.settings.session_ttl_seconds, payload)
        except Exception:  # pragma: no cover
            logger.warning("session touch failed (non-fatal)", exc_info=True)

    async def get_active_session_id(self, user_uuid: str) -> str | None:
        r = await get_redis()
        if r is None:
            return None
        try:
            raw = await r.get(self._key(user_uuid))
            return json.loads(raw)["session_id"] if raw else None
        except Exception:  # pragma: no cover
            return None

    async def clear(self, user_uuid: str) -> None:
        """Used by opt-out / data-wipe flows (Phase 6 completes the purge)."""
        r = await get_redis()
        if r is None:
            return
        await r.delete(self._key(user_uuid))

    async def seen_message(self, wa_message_id: str) -> bool:
        """True if this WhatsApp message id was already processed.

        Meta retries webhooks; we must answer exactly-once. SETNX with TTL.
        Returns False (process it) when Redis is down — DB unique constraint
        on wa_message_id is the second safety net.
        """
        r = await get_redis()
        if r is None:
            return False
        try:
            ok = await r.set(f"{self.DEDUPE_PREFIX}:{wa_message_id}", "1", nx=True, ex=86400)
            return not ok
        except Exception:  # pragma: no cover
            return False
