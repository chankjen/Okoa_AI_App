"""Phase 4 test suite — Conversational AI, Llama 3 Companion, CBT RAG & Language Detection."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import CbtStrategy, ChatSession, Message, MessageDirection, MessageKind, User
from app.services.language_service import detect_language
from app.services.llm_client import Llama3Client
from app.services.pipeline import InboundEvent, MessagePipeline, get_session_history
from app.services.prompt_service import PromptService
from app.services.rag_service import RagService


# ---------------------------------------------------------------------------
# 1. Language Auto-Detection (Roadmap 4.6)
# ---------------------------------------------------------------------------
def test_language_detection_swahili():
    text = "Habari za asubuhi, nina huzuni na maumivu ya moyo leo."
    res = detect_language(text)
    assert res.language == "sw"
    assert res.confidence >= 0.5


def test_language_detection_sheng():
    text = "Buda manze niko na panic noma sana, vitu haziendi fiti naskia ka nimekwama."
    res = detect_language(text)
    assert res.language == "sheng"
    assert res.confidence >= 0.6


def test_language_detection_english():
    text = "I am feeling so overwhelmed, stressed, and anxious with work today."
    res = detect_language(text)
    assert res.language == "en"
    assert res.confidence >= 0.5


# ---------------------------------------------------------------------------
# 2. CBT RAG Retrieval & Prompt Context (Roadmap 4.5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cbt_rag_retrieval_and_formatting():
    rag = RagService()

    # Swahili anxiety retrieval
    strategies_sw = await rag.retrieve(None, "Nina wasiwasi mwingi na mapigo ya moyo", language="sw")
    assert len(strategies_sw) == 1
    assert "Pumzi ya Sanduku" in strategies_sw[0]["title"]

    # Sheng panic retrieval
    strategies_sheng = await rag.retrieve(None, "Niko na panic kali sana keja", language="sheng")
    assert len(strategies_sheng) == 1
    assert "Grounding" in strategies_sheng[0]["title"]

    # Prompt block formatting
    context_block = rag.format_context_block(strategies_sw)
    assert "[VETTED CBT COPING TECHNIQUE:" in context_block
    assert "Do NOT diagnose or prescribe" in context_block


# ---------------------------------------------------------------------------
# 3. Prompt & Guardrail Service (Roadmap 4.1)
# ---------------------------------------------------------------------------
def test_prompt_service_guardrails():
    prompts = PromptService()

    # Swahili prompt
    prompt_sw = prompts.build_system_prompt(language="sw", risk_label="distressed", rag_context="[CBT BLOCK]")
    assert "HAUWEZI" in prompt_sw
    assert "1199" in prompt_sw
    assert "[CBT BLOCK]" in prompt_sw
    assert "dhiki na huzuni" in prompt_sw

    # Sheng prompt
    prompt_sheng = prompts.build_system_prompt(language="sheng", risk_label="safe")
    assert "ushauri wa dawa" in prompt_sheng
    assert "1199" in prompt_sheng
    assert "COUNSELOR" in prompt_sheng

    # English prompt
    prompt_en = prompts.build_system_prompt(language="en", risk_label="safe")
    assert "NEVER provide medication advice" in prompt_en
    assert "NEVER provide clinical or medical diagnoses" in prompt_en


# ---------------------------------------------------------------------------
# 4. Llama 3 Inference Serving & Simulation (Roadmap 4.2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_llama3_client_generation():
    client = Llama3Client()
    messages = [
        {"role": "system", "content": "You are OKOA."},
        {"role": "user", "content": "Buda niko na msongo wa mawazo."},
    ]

    resp = await client.generate_response(messages, language="sheng", risk_label="distressed")
    assert resp.content
    assert resp.latency_ms >= 0.0
    assert resp.latency_ms < 5000.0  # NFR < 5s
    assert "Pole sana manze" in resp.content or "🤍" in resp.content


# ---------------------------------------------------------------------------
# 5. Full Pipeline End-to-End Flow (Roadmap 4.2 / TRD §3)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_pipeline_phase4_conversation_flow(db_session_factory):
    from app.services.identity_service import IdentityService
    from app.services.session_store import SessionStore
    from app.services.whatsapp_client import WhatsAppClient
    from app.vault.crypto import IdentityVault, generate_key_material

    vault = IdentityVault(generate_key_material())
    identity = IdentityService(vault)
    sessions = SessionStore()

    class FakeWhatsApp:
        def __init__(self):
            self.sent = []

        async def send_text(self, to_wa_id, text, **kw):
            self.sent.append((to_wa_id, text))
            return "fake-msg-id"

    wa = FakeWhatsApp()
    pipeline = MessagePipeline(
        session_factory=db_session_factory,
        identity=identity,
        sessions=sessions,
        wa=wa,
    )

    phone = "+254711999888"

    # Step A: Enrol user and grant consent
    event_start = InboundEvent(wa_user_id=phone, text="AGREE", wa_message_id="msg-agree-001")
    await pipeline.handle(event_start)

    # Step B: User sends distressed message in Sheng
    event_sheng = InboundEvent(
        wa_user_id=phone,
        text="Manze buda niko na panic noma sana leo vitu haziendi fiti.",
        wa_message_id="msg-sheng-002",
    )
    await pipeline.handle(event_sheng)

    # Verify WhatsApp received an empathetic companion reply
    assert len(wa.sent) >= 2
    last_reply = wa.sent[-1][1]
    assert "🤍" in last_reply

    # Verify user language was auto-detected as Sheng and persisted
    async with db_session_factory() as db:
        user_uuid, _ = await identity.resolve_or_enrol(db, phone)
        user = await db.get(User, user_uuid)
        assert user is not None
        assert user.language == "sheng"

        # Verify multi-turn history extraction includes the user's message
        history = await get_session_history(db, user_uuid)
        assert len(history) >= 2
        assert any("panic noma" in h["content"] for h in history)
