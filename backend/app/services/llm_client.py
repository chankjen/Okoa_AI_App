"""Llama 3 inference client (roadmap 4.2).

Interfaces with OpenAI-compatible vLLM / TGI inference server on AWS g5.xlarge.
Measures latency to enforce the NFR (< 5s total response budget).
Includes a local simulation/mock engine so tests and developer environments
function end-to-end without requiring an active GPU cluster.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger("okoa.llm")


@dataclass
class LLMResponse:
    content: str
    latency_ms: float
    model: str
    finish_reason: str = "stop"
    is_simulated: bool = False


class Llama3Client:
    def __init__(self, settings: Settings | None = None, http_client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = http_client

    async def _http(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=httpx.Timeout(self.settings.llm_timeout_seconds, connect=2.0))

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        *,
        language: str = "sw",
        risk_label: str = "safe",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Call the Llama 3 8B model or fall back to local simulated response."""
        t0 = time.monotonic()
        temp = temperature if temperature is not None else self.settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else self.settings.llm_max_tokens

        # Check if live LLM is enabled and configured
        if self.settings.enable_llm and self.settings.llm_api_base:
            url = f"{self.settings.llm_api_base.rstrip('/')}/chat/completions"
            headers = {"Content-Type": "application/json"}
            if self.settings.llm_api_key:
                headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

            payload = {
                "model": self.settings.llm_model_name,
                "messages": messages,
                "temperature": temp,
                "max_tokens": tokens,
            }

            owns_client = self._client is None
            client = await self._http()
            try:
                resp = await client.post(url, json=payload, headers=headers)
                latency_ms = round((time.monotonic() - t0) * 1000, 2)

                if resp.status_code == 200:
                    data = resp.json()
                    choice = data["choices"][0]
                    content = choice["message"]["content"].strip()
                    logger.info("llm response generated", extra={
                        "event": "llm_success",
                        "latency_ms": latency_ms,
                        "model": self.settings.llm_model_name,
                    })
                    return LLMResponse(
                        content=content,
                        latency_ms=latency_ms,
                        model=self.settings.llm_model_name,
                        finish_reason=choice.get("finish_reason", "stop"),
                        is_simulated=False,
                    )
                logger.warning(
                    "llm inference failed status=%d body=%s; falling back to simulation",
                    resp.status_code, resp.text[:200],
                )
            except Exception as exc:
                logger.warning("llm connection error (%s); falling back to simulation", type(exc).__name__)
            finally:
                if owns_client:
                    await client.aclose()

        # Simulated fallback for local dev / offline testing
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        simulated_text = self._simulate_reply(messages, language=language, risk_label=risk_label)
        return LLMResponse(
            content=simulated_text,
            latency_ms=latency_ms,
            model="simulated-llama3-8b",
            finish_reason="stop",
            is_simulated=True,
        )

    def _simulate_reply(self, messages: list[dict[str, str]], language: str, risk_label: str) -> str:
        """Generate high-quality conversational response adhering to CBT guardrails."""
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        lang = language.lower()
        if lang == "sheng":
            if risk_label == "distressed":
                return (
                    "Pole sana manze kwa unayopitia. 🤍 Hapo nimekupata vizuri kabisa — "
                    "ile feeling ya kuchoka na pressure inaweza lemea msee. Lakini hauko solo, "
                    "uko safe hapa. Hebu pumua ndaani polepole kwanza, kisha uniambie ni kitu gani "
                    "inakupa uzito zaidi saa hii?"
                )
            return (
                "Niko hapa na wewe. 🤍 Asante kwa kubonga nami leo. "
                "Niambie risto inaendaje, niko tayari kukuskiliza bila jaji yoyote."
            )

        if lang == "en":
            if risk_label == "distressed":
                return (
                    "I hear you, and thank you for sharing this with me. 🤍 What you are carrying right now "
                    "sounds truly exhausting, but you are not alone in it. Let's take a slow, gentle breath together. "
                    "What part of this is feeling the heaviest for you today?"
                )
            return (
                "Thank you for reaching out. 🤍 I am here to listen and support you without judgment. "
                "How are you feeling right now?"
            )

        # Default Swahili
        if risk_label == "distressed":
            return (
                "Pole sana kwa unayopitia ndugu yangu. 🤍 Nimesikia uzito uliopo moyoni mwako, "
                "na ni kawaida kuhisi hivi unapokabiliwa na mazingira magumu. Huko peke yako. "
                "Tafadhali chukua pumzi ya kina, kisha unieleze zaidi kuhusu kile kinachokusumbua zaidi leo."
            )
        return (
            "Habari, asante kwa kuwasiliana nami. 🤍 Niko hapa kusikiliza bila kuhukumu. "
            "Unaendeleaje leo na ungependa tuzungumze kuhusu nini?"
        )
