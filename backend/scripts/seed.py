"""Seed script for OKOA AI database.

Seeds:
1. Default counselor account:
   - Username: dr_ochieng
   - Password: Password123!
2. Sample active escalations with realistic transcripts for testing the
   Counselor Dashboard UI immediately.

Usage:
    python -m scripts.seed
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid

from sqlalchemy import select

from app.auth.counselor_auth import hash_password
from app.core.config import get_settings
from app.db.models import (
    AuditAction,
    AuditLogEntry,
    ChatSession,
    Counselor,
    Escalation,
    EscalationStatus,
    HandoverMode,
    Message,
    MessageDirection,
    MessageKind,
    RiskAssessment,
    RiskLabel,
    SessionControl,
    User,
)
from app.db.session import dispose_engine, get_session_factory, init_models
from app.safety.audit import audit_append

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("okoa.seed")


async def seed() -> None:
    settings = get_settings()
    logger.info("Initializing database models on %s...", settings.database_url)
    await init_models()

    factory = get_session_factory()
    async with factory() as db:
        # 1. Counselors
        counselor = await db.scalar(
            select(Counselor).where(Counselor.username == "dr_ochieng")
        )
        if counselor is None:
            counselor = Counselor(
                id=str(uuid.uuid4()),
                username="dr_ochieng",
                password_hash=hash_password("Password123!"),
                display_name="Dr. Ochieng (Lead Clinical Officer)",
                phone_e164="+254700111222",
                email="dr.ochieng@okoa.ai",
                is_on_duty=True,
                is_active=True,
            )
            db.add(counselor)
            await db.flush()
            logger.info("Created default counselor: dr_ochieng (Password: Password123!)")
        else:
            logger.info("Counselor dr_ochieng already exists.")

        # 2. Sample Escalation 1: High Risk Suicidal Crisis (Open)
        user1_uuid = str(uuid.uuid4())
        user1 = await db.get(User, user1_uuid)
        if user1 is None:
            user1 = User(user_uuid=user1_uuid, language="sw")
            db.add(user1)

            session1 = ChatSession(id=str(uuid.uuid4()), user_uuid=user1_uuid)
            db.add(session1)
            await db.flush()

            # Conversation history
            m1 = Message(
                session_id=session1.id,
                direction=MessageDirection.inbound,
                kind=MessageKind.user_text,
                body="Habari, nimekuwa nikipitia magumu sana wiki hii.",
                created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5),
            )
            m2 = Message(
                session_id=session1.id,
                direction=MessageDirection.outbound,
                kind=MessageKind.canned_reply,
                body="Karibu OKOA. Niko hapa kukusikiliza bila hukumu. Ni nini kinachokusumbua zaidi?",
                created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=4),
            )
            m3 = Message(
                session_id=session1.id,
                direction=MessageDirection.inbound,
                kind=MessageKind.user_text,
                body="Siwezi kuendelea tena maishani. Nataka kuisha nina mpango wa kumeza dawa usiku huu.",
                created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=45),
            )
            m4 = Message(
                session_id=session1.id,
                direction=MessageDirection.outbound,
                kind=MessageKind.crisis_response,
                body="Nimesikia unachosema na nina wasiwasi kuhusu usalama wako. Tafadhali pigia 1199 (Red Cross, bure masaa 24). Mshauri wetu anaunganishwa sasa hivi.",
                created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=40),
            )
            db.add_all([m1, m2, m3, m4])
            await db.flush()

            esc1 = Escalation(
                id=str(uuid.uuid4()),
                user_uuid=user1_uuid,
                session_id=session1.id,
                trigger_message_id=m3.id,
                risk_score=96.0,
                risk_label=RiskLabel.crisis,
                status=EscalationStatus.open,
                created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=45),
            )
            db.add(esc1)

            control1 = SessionControl(
                user_uuid=user1_uuid,
                mode=HandoverMode.bot_active,
                active_escalation_id=esc1.id,
            )
            db.add(control1)

            await audit_append(
                db,
                action=AuditAction.escalation_created,
                actor_type="system",
                subject_uuid=user1_uuid,
                details={"risk_score": 96.0, "reason": "crisis_phrase_detected"},
            )
            logger.info("Created sample Crisis escalation (Risk: 96.0, Status: open)")

        # 3. Sample Escalation 2: Severe Substance Abuse & Distress (Claimed by Dr. Ochieng)
        user2_uuid = str(uuid.uuid4())
        user2 = User(user_uuid=user2_uuid, language="sheng")
        db.add(user2)
        session2 = ChatSession(id=str(uuid.uuid4()), user_uuid=user2_uuid)
        db.add(session2)
        await db.flush()

        m2_1 = Message(
            session_id=session2.id,
            direction=MessageDirection.inbound,
            kind=MessageKind.user_text,
            body="Buda niko na cravings mbaya sana za pombe, niko chini na naogopa relapse.",
            created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=15),
        )
        m2_2 = Message(
            session_id=session2.id,
            direction=MessageDirection.outbound,
            kind=MessageKind.canned_reply,
            body="Pole sana Amina. Kushiriki hili ni hatua kubwa ya ujasiri. Umekuwa safi kwa siku ngapi?",
            created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=14),
        )
        m2_3 = Message(
            session_id=session2.id,
            direction=MessageDirection.inbound,
            kind=MessageKind.user_text,
            body="Ni siku 14 lakini leo mawazo yamenilemea sana, niko peke yangu na nina huzuni.",
            created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=3),
        )
        db.add_all([m2_1, m2_2, m2_3])
        await db.flush()

        esc2 = Escalation(
            id=str(uuid.uuid4()),
            user_uuid=user2_uuid,
            session_id=session2.id,
            trigger_message_id=m2_3.id,
            risk_score=72.0,
            risk_label=RiskLabel.distressed,
            status=EscalationStatus.claimed,
            claimed_by=counselor.id,
            claimed_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2),
            first_response_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1),
            created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=3),
        )
        db.add(esc2)

        control2 = SessionControl(
            user_uuid=user2_uuid,
            mode=HandoverMode.counselor_active,
            active_escalation_id=esc2.id,
            changed_by=counselor.id,
        )
        db.add(control2)

        await audit_append(
            db,
            action=AuditAction.escalation_claimed,
            actor_type="counselor",
            actor_id=counselor.id,
            subject_uuid=user2_uuid,
            details={"escalation_id": esc2.id},
        )
        logger.info("Created sample Distressed escalation (Risk: 72.0, Status: claimed/handover)")

        await db.commit()

    await dispose_engine()
    logger.info("Database seeding completed successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
