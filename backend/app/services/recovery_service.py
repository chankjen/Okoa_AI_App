"""Recovery Milestone & Habit Tracking Service (roadmap 5.5).

Designed for youth and young adults in early recovery (Amina persona, PRD §2/§5):
- "Days clean" / sobriety streak tracking.
- Non-punitive, compassionate relapse reset framing.
- Culturally affirmative milestone celebrations (Days 1, 3, 7, 14, 30, 60, 90)
  in Swahili, Sheng, and English.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RecoveryTracker

logger = logging.getLogger("okoa.recovery")

# Milestone thresholds in days
MILESTONES = [1, 3, 7, 14, 30, 60, 90, 180, 365]

CELEBRATIONS: dict[int, dict[str, str]] = {
    1: {
        "sw": "🎉 Hongera sana kwa kufikisha Siku ya 1 bila kutumia! Hatua ya kwanza ndiyo muhimu zaidi. Tuko pamoja nawe kila hatua.",
        "sheng": "🎉 Big up sana kwa kuanza safari! Day 1 clean ni ushindi mkubwa sana. Keep going, tuko na wewe mwanzo mwisho!",
        "en": "🎉 Congratulations on Day 1! The first step takes the most courage. We are with you all the way.",
    },
    3: {
        "sw": "🌟 Siku ya 3! Mwili na akili yako vinaanza kujiponya. Endelea kusimama imara, una uwezo mkubwa.",
        "sheng": "🌟 Day 3 imetiki! Mwili inaanza kuclean up. Umesimama kidedea, usirudi nyuma bro/sis!",
        "en": "🌟 Day 3 reached! Your mind and body are adjusting and healing. You're stronger than you think.",
    },
    7: {
        "sw": "🏆 WIKI MOJA NZIMA (Siku 7)! Huu ni ushindi wa ajabu sana. Jiandae zawadi ndogo ya kujipongeza leo.",
        "sheng": "🏆 One full week! Siku saba fiti bila kurudi nyuma! Hii ni level ingine ya nguvu. Saluti kwako!",
        "en": "🏆 ONE FULL WEEK (Day 7)! This is a huge milestone. Be truly proud of your resilience today.",
    },
    14: {
        "sw": "🔥 Wiki Mbili (Siku 14)! Umejenga tabia mpya na unaonyesha ujasiri wa kweli. Kila siku inazidi kuwa nafuu.",
        "sheng": "🔥 2 weeks clean! Ndoto inaanza kuwa real. Ile discipline uko nayo ni hatari sana!",
        "en": "🔥 Two weeks clean! You are rewriting your story one day at a time.",
    },
    30: {
        "sw": "👑 MWEZI MMOJA KAMILI (Siku 30)! Umeonyesha uthabiti na uwezo wa kipekee. Tuko na furaha kubwa kwa ajili yako.",
        "sheng": "👑 1 MONTH CLEAN! Hii ni noma sana! Hakuna kitu kinaweza kukushinda sasa ukijiamini. Hongera champ!",
        "en": "👑 ONE FULL MONTH (Day 30)! You have proven that lasting change is possible. Massive respect!",
    },
    60: {
        "sw": "💎 Siku 60 za ushindi mfululizo! Wewe ni mfano bora wa matumaini na ujasiri.",
        "sheng": "💎 Siku 60 bila kugeuka nyuma! Safari yako ni inspiration kibao.",
        "en": "💎 60 days clean! You are inspiring and truly transforming your life.",
    },
    90: {
        "sw": "🌈 SIKU 90! Miezi mitatu ya ushindi. Nuru mpya inang'aa maishani mwako. Endelea kutembea kifua mbele!",
        "sheng": "🌈 90 DAYS! Miezi tatu ya kuwashwashi na kubaki fiti! You did it, and the future is yours!",
        "en": "🌈 90 DAYS! Three months of dedication and strength. You have built a solid foundation for the future.",
    },
}

RESET_MESSAGES = {
    "sw": "Tuko pamoja nawe. Kuteleza si kuanguka, na safari ya kupona ina milima na mabonde. Unapata nafasi ya kuanza tena sasa hivi bila lawama.",
    "sheng": "Usife heart hata kidogo. Relapse haimaanishi safari imeisha; ni darasa tu ya kujifunza. Tuanze upya leo pamoja, tuko nawe.",
    "en": "Please be gentle with yourself. A slip does not erase the progress you've made. Recovery is a journey, and you can restart today without judgment.",
}


class RecoveryService:
    async def get_or_create_tracker(
        self,
        db: AsyncSession,
        user_uuid: str,
        target_habit: str = "substances",
    ) -> RecoveryTracker:
        """Fetch or initialize recovery tracker for user."""
        tracker = await db.get(RecoveryTracker, user_uuid)
        if tracker is None:
            now = dt.datetime.now(dt.timezone.utc)
            tracker = RecoveryTracker(
                user_uuid=user_uuid,
                target_habit=target_habit,
                start_date=now,
                current_streak_days=0,
                longest_streak_days=0,
                last_checkin_at=None,
                milestones_reached_json="[]",
            )
            db.add(tracker)
            await db.flush()
        return tracker

    async def log_clean_day(
        self,
        db: AsyncSession,
        user_uuid: str,
        language: str = "sw",
    ) -> tuple[RecoveryTracker, str | None]:
        """Record another successful clean day, increment streak, and return celebratory note if milestone reached."""
        tracker = await self.get_or_create_tracker(db, user_uuid)
        now = dt.datetime.now(dt.timezone.utc)

        # Increment streak
        tracker.current_streak_days += 1
        if tracker.current_streak_days > tracker.longest_streak_days:
            tracker.longest_streak_days = tracker.current_streak_days
        tracker.last_checkin_at = now

        # Parse reached milestones
        try:
            reached: list[int] = json.loads(tracker.milestones_reached_json or "[]")
        except Exception:
            reached = []

        celebration_msg: str | None = None
        current = tracker.current_streak_days
        lang_key = language if language in ("sw", "sheng", "en") else "sw"

        # Check if current streak reaches a new milestone
        for m in MILESTONES:
            if current >= m and m not in reached:
                reached.append(m)
                tracker.milestones_reached_json = json.dumps(reached)
                celebration_msg = CELEBRATIONS.get(m, {}).get(lang_key)
                break

        await db.flush()
        logger.info("clean day logged", extra={
            "event": "clean_day_logged",
            "user_uuid": user_uuid,
            "streak": tracker.current_streak_days,
            "milestone_reached": bool(celebration_msg),
        })
        return tracker, celebration_msg

    async def reset_streak(
        self,
        db: AsyncSession,
        user_uuid: str,
        language: str = "sw",
    ) -> tuple[RecoveryTracker, str]:
        """Reset streak with non-shaming clinical framing and return comforting encouragement."""
        tracker = await self.get_or_create_tracker(db, user_uuid)
        tracker.current_streak_days = 0
        tracker.last_checkin_at = dt.datetime.now(dt.timezone.utc)
        await db.flush()

        lang_key = language if language in ("sw", "sheng", "en") else "sw"
        enc_msg = RESET_MESSAGES.get(lang_key, RESET_MESSAGES["sw"])

        logger.info("recovery streak reset", extra={
            "event": "recovery_reset",
            "user_uuid": user_uuid,
        })
        return tracker, enc_msg
