"""OKOA AI backend application factory (Phase 1).

Lifespan wires: logging, DB schema (dev), Redis, vault, identity service,
WhatsApp client, async message pipeline worker.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import counselor, ops, webhooks, ws
from app.core.config import get_settings
from app.core.logging import configure_logging, new_request_id, request_id_var
from app.db.session import dispose_engine, get_session_factory, init_models
from app.safety.escalation import EscalationService
from app.services.identity_service import IdentityService
from app.services.llm_client import Llama3Client
from app.services.notifications import Notifier
from app.services.pipeline import MessagePipeline
from app.services.prompt_service import PromptService
from app.services.rag_service import RagService
from app.services.session_store import SessionStore
from app.services.whatsapp_client import WhatsAppClient
from app.vault.crypto import IdentityVault

logger = logging.getLogger("okoa.app")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        request_id_var["rid"] = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(logging.DEBUG if settings.debug else logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Dev convenience; Alembic owns the schema in staging/production.
        if not settings.is_production:
            try:
                await init_models()
            except Exception as exc:
                logger.warning("init_models skipped (%s) — will retry on first request", type(exc).__name__)

        if not settings.vault_master_key:
            raise RuntimeError(
                "VAULT_MASTER_KEY is required. Generate: "
                "python -c \"import os,base64;print(base64.b64encode(os.urandom(32)).decode())\""
            )

        vault = IdentityVault(settings.vault_master_key)
        app.state.identity = IdentityService(vault)
        app.state.sessions = SessionStore()
        app.state.wa = WhatsAppClient()
        app.state.notifier = Notifier(wa_client=app.state.wa)
        app.state.hub = ws.hub
        app.state.escalation = EscalationService(notifier=app.state.notifier, hub=app.state.hub)
        # Phase 4 components
        app.state.llm = Llama3Client(settings=settings)
        app.state.prompts = PromptService()
        app.state.rag = RagService()
        # Phase 5 components
        from app.services.mood_service import MoodService
        from app.services.survey_service import SurveyService
        from app.services.recovery_service import RecoveryService
        from app.services.scheduler import CheckInScheduler

        app.state.mood_service = MoodService()
        app.state.survey_service = SurveyService()
        app.state.recovery_service = RecoveryService()
        app.state.scheduler = CheckInScheduler(
            identity_service=app.state.identity,
            wa_client=app.state.wa,
        )
        app.state.pipeline = MessagePipeline(
            session_factory=get_session_factory(),
            identity=app.state.identity,
            sessions=app.state.sessions,
            wa=app.state.wa,
            escalation=app.state.escalation,
            llm=app.state.llm,
            prompts=app.state.prompts,
            rag=app.state.rag,
            mood_service=app.state.mood_service,
            survey_service=app.state.survey_service,
            recovery_service=app.state.recovery_service,
        )
        app.state.pipeline.start()
        logger.info("okoa backend ready env=%s", settings.environment)
        yield
        await app.state.pipeline.stop()
        await dispose_engine()

    app = FastAPI(title="OKOA AI Backend", version="0.5.0", lifespan=lifespan)
    app.add_middleware(RequestIDMiddleware)

    cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    if not cors_origins:
        cors_origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ops.router)
    app.include_router(webhooks.router)
    app.include_router(counselor.router)
    app.include_router(ws.router)

    @app.get("/")
    async def root():
        return {"service": settings.app_name, "phase": "5-mood-tracking-retention"}

    return app



app = create_app()
