"""Daily Check-in Scheduler Service (roadmap 5.1 / 5.2).

Automates daily mental-health check-ins ("Vipi leo?") with:
- Strict quiet-hours enforcement (21:00–07:00 EAT / UTC+3).
- Opt-out & consent status checks (TRD §5 / DPA 2019).
- 24-hour rate limit cap (never more than 1 proactive check-in per day).
- WhatsApp native interactive list / button delivery.
- Background execution runner for asyncio / Celery / APScheduler.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CheckInSchedule, ConsentStatus, User
from app.services.identity_service import IdentityService
from app.services.whatsapp_client import WhatsAppClient

logger = logging.getLogger("okoa.scheduler")

EAT_TIMEZONE = dt.timezone(dt.timedelta(hours=3))

CHECKIN_PROMPTS = {
    "sw": {
        "greeting": "Habari! Hapa ni Amina kutoka OKOA. Ni wakati wa mapumziko kidogo — unajihisi vipi leo?",
        "button_label": "Chagua Hali Yako",
        "section_title": "Hali ya Leo",
        "rows": [
            ("mood_great", "Niko Vizuri Sana 😊", "Ninayo furaha na amani"),
            ("mood_good", "Niko Salama 🙂", "Mambo yanaenda vizuri"),
            ("mood_okay", "Niko Sawa Tu 😐", "Kawaida, napambana"),
            ("mood_low", "Niko Chini 😔", "Ninayo huzuni au uchovu"),
            ("mood_overwhelmed", "Nimelemewa Kabisa 😫", "Nahitaji usaidizi wa haraka"),
        ],
    },
    "sheng": {
        "greeting": "Niaje! Amina hapa wa OKOA. Quick check-in — rada yako ikoje leo?",
        "button_label": "Chagua Mood",
        "section_title": "Mood ya Leo",
        "rows": [
            ("mood_great", "Niko Fiti Sana 😊", "Everything iko shwari"),
            ("mood_good", "Niko Poa 🙂", "Mambo iko sawa"),
            ("mood_okay", "Niko Kawaida 😐", "Hustle inaendelea"),
            ("mood_low", "Niko Chini 😔", "Siko sawa sana leo"),
            ("mood_overwhelmed", "Nimelemewa Noma 😫", "Nahitaji usaidizi chap"),
        ],
    },
    "en": {
        "greeting": "Hello! This is Amina from OKOA. Just checking in — how are you feeling today?",
        "button_label": "Select Mood",
        "section_title": "Today's Feeling",
        "rows": [
            ("mood_great", "Feeling Great 😊", "Full of energy & peace"),
            ("mood_good", "Feeling Good 🙂", "Doing well today"),
            ("mood_okay", "Feeling Okay 😐", "Getting through the day"),
            ("mood_low", "Feeling Low 😔", "Tired or feeling down"),
            ("mood_overwhelmed", "Overwhelmed 😫", "Need immediate support"),
        ],
    },
}


def is_quiet_hours(now: dt.datetime | None = None) -> bool:
    """Check if current time is within Kenyan quiet hours (21:00 - 07:00 EAT)."""
    current_utc = now or dt.datetime.now(dt.timezone.utc)
    eat_time = current_utc.astimezone(EAT_TIMEZONE)
    hour = eat_time.hour
    return hour >= 21 or hour < 7


class CheckInScheduler:
    def __init__(self, identity_service: IdentityService, wa_client: WhatsAppClient):
        self.identity_service = identity_service
        self.wa_client = wa_client

    async def get_eligible_users(
        self,
        db: AsyncSession,
        limit: int = 100,
        now: dt.datetime | None = None,
    ) -> Sequence[tuple[User, CheckInSchedule | None]]:
        """Find users eligible for daily check-in.

        Eligibility rules:
        - Consent granted
        - Not opted out and not data-purged
        - CheckInSchedule enabled (or not yet created)
        - At least 24 hours since last_prompted_at
        """
        current = now or dt.datetime.now(dt.timezone.utc)
        cutoff_24h = current - dt.timedelta(hours=24)

        # Select users joined with checkin schedule
        stmt = (
            select(User, CheckInSchedule)
            .outerjoin(CheckInSchedule, User.user_uuid == CheckInSchedule.user_uuid)
            .where(
                User.consent_status == ConsentStatus.granted,
                User.opt_out.is_(False),
                User.data_purged.is_(False),
                or_(
                    CheckInSchedule.enabled.is_(None),
                    CheckInSchedule.enabled.is_(True),
                ),
                or_(
                    CheckInSchedule.last_prompted_at.is_(None),
                    CheckInSchedule.last_prompted_at <= cutoff_24h,
                ),
            )
            .limit(limit)
        )
        return (await db.execute(stmt)).all()

    async def send_checkin(
        self,
        db: AsyncSession,
        user: User,
        schedule: CheckInSchedule | None = None,
    ) -> bool:
        """Deliver daily check-in interactive message to a user."""
        phone = await self.identity_service.reveal_msisdn(db, user.user_uuid)
        if not phone:
            logger.warning("cannot deliver checkin: no active phone in vault", extra={
                "event": "checkin_skipped", "user_uuid": user.user_uuid,
            })
            return False

        lang = user.language if user.language in ("sw", "sheng", "en") else "sw"
        config = CHECKIN_PROMPTS[lang]

        sections = [
            {
                "title": config["section_title"],
                "rows": [
                    {"id": r_id, "title": r_title[:24], "description": r_desc[:72]}
                    for r_id, r_title, r_desc in config["rows"]
                ],
            }
        ]

        now = dt.datetime.now(dt.timezone.utc)
        try:
            # Deliver interactive WhatsApp list
            await self.wa_client.send_interactive_list(
                to_wa_id=phone,
                body_text=config["greeting"],
                button_label=config["button_label"],
                sections=sections,
            )

            # Record schedule prompt timestamp
            if schedule is not None:
                schedule.last_prompted_at = now
            else:
                schedule = CheckInSchedule(
                    user_uuid=user.user_uuid,
                    last_prompted_at=now,
                    enabled=True,
                )
                db.add(schedule)

            await db.flush()
            logger.info("daily check-in sent", extra={
                "event": "checkin_sent",
                "user_uuid": user.user_uuid,
            })
            return True
        except Exception as exc:
            logger.exception("failed to deliver checkin to user %s: %s", user.user_uuid, exc)
            return False

    async def run_checkin_tick(
        self,
        db: AsyncSession,
        limit: int = 100,
        now: dt.datetime | None = None,
    ) -> int:
        """Run single checkin scheduler cycle."""
        current = now or dt.datetime.now(dt.timezone.utc)
        if is_quiet_hours(current):
            logger.info("scheduler tick skipped: quiet hours active (21:00-07:00 EAT)")
            return 0

        eligible = await self.get_eligible_users(db, limit=limit, now=current)
        sent_count = 0
        for user, sched in eligible:
            success = await self.send_checkin(db, user, sched)
            if success:
                sent_count += 1

        logger.info("scheduler tick completed", extra={
            "event": "scheduler_tick",
            "eligible": len(eligible),
            "dispatched": sent_count,
        })
        return sent_count


async def run_scheduler_worker(
    session_factory,
    identity_service: IdentityService,
    wa_client: WhatsAppClient,
    interval_seconds: int = 3600,
    stop_event: asyncio.Event | None = None,
):
    """Background worker task executed during application lifecycle."""
    scheduler = CheckInScheduler(identity_service, wa_client)
    logger.info("check-in scheduler background worker started")

    while stop_event is None or not stop_event.is_set():
        try:
            async with session_factory() as db:
                await scheduler.run_checkin_tick(db)
                await db.commit()
        except Exception as err:
            logger.error("error during scheduler worker tick: %s", err)

        try:
            if stop_event:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            else:
                await asyncio.sleep(interval_seconds)
        except asyncio.TimeoutError:
            pass
