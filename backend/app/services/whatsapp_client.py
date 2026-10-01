"""WhatsApp Business Cloud API client (roadmap 1.4).

Outbound text only, with:
  * timeout + bounded retries with exponential backoff on 5xx / 429,
  * rate-limit awareness (honours Retry-After),
  * structured logging that never includes message bodies or phone numbers.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("okoa.whatsapp")


class WhatsAppSendError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class WhatsAppClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        s = get_settings()
        self.base = s.whatsapp_api_base.rstrip("/")
        self.phone_number_id = s.whatsapp_phone_number_id
        self.token = s.whatsapp_access_token
        self._client = client

    async def _http(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))

    async def _post_message(self, payload: dict) -> str | None:
        url = f"{self.base}/{self.phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        owns_client = self._client is None
        client = await self._http()
        try:
            delay = 0.5
            for attempt in range(3):
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "whatsapp send network error attempt=%d err=%s", attempt + 1, type(exc).__name__
                    )
                    if attempt == 2:
                        raise WhatsAppSendError(0, "network error") from exc
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    msg_id = (data.get("messages") or [{}])[0].get("id")
                    logger.info("whatsapp sent", extra={"event": "wa_sent", "wa_message_id": msg_id})
                    return msg_id
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", delay))
                    logger.warning("whatsapp rate limited, sleeping %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                    delay = retry_after
                    continue
                if 500 <= resp.status_code < 600 and attempt < 2:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                # 4xx (non-429): don't retry — bad token/id, recipient blocked us etc.
                logger.error(
                    "whatsapp send failed status=%d body_keys=%s",
                    resp.status_code,
                    sorted(resp.json().get("error", {}).keys()) if resp.content else [],
                )
                raise WhatsAppSendError(resp.status_code, "send failed")
            raise WhatsAppSendError(429, "rate limit exhausted")
        finally:
            if owns_client:
                await client.aclose()

    async def send_text(self, to_wa_id: str, body: str, *, preview_url: bool = False) -> str | None:
        """Send a plain-text message. Returns provider message id or None."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_wa_id.lstrip("+"),
            "type": "text",
            "text": {"body": body[:4096], "preview_url": preview_url},
        }
        return await self._post_message(payload)

    async def send_interactive_buttons(
        self,
        to_wa_id: str,
        body_text: str,
        buttons: list[tuple[str, str]],  # [(button_id, button_title), ...] max 3
    ) -> str | None:
        """Send interactive reply buttons (roadmap 5.2). Max 3 buttons."""
        button_elements = [
            {
                "type": "reply",
                "reply": {
                    "id": b_id[:256],
                    "title": b_title[:20],  # WhatsApp 20 char max title limit
                },
            }
            for b_id, b_title in buttons[:3]
        ]
        payload = {
            "messaging_product": "whatsapp",
            "to": to_wa_id.lstrip("+"),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text[:1024]},
                "action": {"buttons": button_elements},
            },
        }
        return await self._post_message(payload)

    async def send_interactive_list(
        self,
        to_wa_id: str,
        body_text: str,
        button_label: str,
        sections: list[dict],
    ) -> str | None:
        """Send interactive list message (roadmap 5.2). Supports up to 10 rows."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_wa_id.lstrip("+"),
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text[:1024]},
                "action": {
                    "button": button_label[:20],
                    "sections": sections,
                },
            },
        }
        return await self._post_message(payload)

