"""Mood & Trigger Analytics Service (roadmap 5.2 / 5.3).

Handles:
- Parsing quick-reply button/list responses and free-text mood logs.
- Persisting structured MoodEntry records.
- Time-series trend analytics (detecting repeated downward spirals).
- Feeding downward trend signals to the risk engine & counselor queue.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CheckInSchedule, MoodEntry

logger = logging.getLogger("okoa.mood")

MOOD_MAP = {
    # ID -> (score, label, display_sw, display_sheng, display_en)
    "mood_great": (5, "great", "Niko Vizuri Sana 😊", "Niko Fiti Sana 😊", "Feeling Great 😊"),
    "mood_good": (4, "good", "Niko Salama 🙂", "Niko Poa 🙂", "Feeling Good 🙂"),
    "mood_okay": (3, "okay", "Niko Sawa Tu 😐", "Niko Kawaida 😐", "Feeling Okay 😐"),
    "mood_low": (2, "low", "Niko Chini / Huzuni 😔", "Niko Chini 😔", "Feeling Low 😔"),
    "mood_overwhelmed": (1, "overwhelmed", "Nimelemewa Kabisa 😫", "Nimelemewa Noma 😫", "Overwhelmed 😫"),
}

TRIGGER_MAP = {
    "trigger_cravings": "cravings",
    "trigger_work": "work",
    "trigger_family": "family",
    "trigger_loneliness": "loneliness",
    "trigger_sleep": "sleep",
    "trigger_financial": "financial",
}


@dataclass
class MoodTrendResult:
    user_uuid: str
    total_entries: int
    recent_scores: list[int]
    average_recent_score: float
    is_downward_trend: bool
    dominant_triggers: list[str]
    suggested_action: str  # 'supportive_nudge' | 'escalate_counselor' | 'celebrate' | 'none'


class MoodService:
    def parse_mood_selection(self, text: str, interactive_id: str | None = None) -> tuple[int, str, str | None]:
        """Convert an inbound message into (score, label, trigger_category)."""
        iid = (interactive_id or "").lower()
        if iid in MOOD_MAP:
            score, label, _, _, _ = MOOD_MAP[iid]
            return score, label, None
        if iid in TRIGGER_MAP:
            return 2, "low", TRIGGER_MAP[iid]

        # Free-text & emoji fallbacks
        low_text = text.lower()
        if any(e in low_text for e in ["😫", "nimelemewa", "overwhelmed", "siwezi"]):
            return 1, "overwhelmed", None
        if any(e in low_text for e in ["😔", "chini", "huzuni", "low", "sad", "down"]):
            return 2, "low", None
        if any(e in low_text for e in ["😐", "sawa", "okay", "kawaida"]):
            return 3, "okay", None
        if any(e in low_text for e in ["🙂", "poa", "salama", "good"]):
            return 4, "good", None
        if any(e in low_text for e in ["😊", "fiti", "great", "fresh", "vizuri sana"]):
            return 5, "great", None

        return 3, "okay", None

    async def log_mood(
        self,
        db: AsyncSession,
        user_uuid: str,
        text: str,
        interactive_id: str | None = None,
        notes: str | None = None,
    ) -> MoodEntry:
        """Record structured mood log and update checkin cadence."""
        score, label, trigger = self.parse_mood_selection(text, interactive_id)

        entry = MoodEntry(
            user_uuid=user_uuid,
            score=score,
            label=label,
            trigger_category=trigger,
            raw_selection=text[:128],
            notes=notes,
        )
        db.add(entry)

        # Update checkin schedule streak
        schedule = await db.get(CheckInSchedule, user_uuid)
        now = dt.datetime.now(dt.timezone.utc)
        if schedule is not None:
            schedule.last_completed_at = now
            schedule.streak_count += 1
        else:
            schedule = CheckInSchedule(
                user_uuid=user_uuid,
                last_completed_at=now,
                streak_count=1,
            )
            db.add(schedule)

        await db.flush()
        logger.info("logged mood entry", extra={
            "event": "mood_logged",
            "user_uuid": user_uuid,
            "score": score,
            "label": label,
        })
        return entry

    async def get_history(
        self,
        db: AsyncSession,
        user_uuid: str,
        limit: int = 14,
    ) -> Sequence[MoodEntry]:
        """Fetch mood time-series in chronological order."""
        stmt = (
            select(MoodEntry)
            .where(MoodEntry.user_uuid == user_uuid)
            .order_by(MoodEntry.created_at.desc())
            .limit(limit)
        )
        rows = (await db.scalars(stmt)).all()
        return list(reversed(rows))

    async def analyze_trend(
        self,
        db: AsyncSession,
        user_uuid: str,
    ) -> MoodTrendResult:
        """Detect downward trend patterns feeding the risk & escalation engine."""
        history = await self.get_history(db, user_uuid, limit=7)
        if not history:
            return MoodTrendResult(
                user_uuid=user_uuid,
                total_entries=0,
                recent_scores=[],
                average_recent_score=3.0,
                is_downward_trend=False,
                dominant_triggers=[],
                suggested_action="none",
            )

        scores = [e.score for e in history]
        triggers = [e.trigger_category for e in history if e.trigger_category]

        recent_window = scores[-3:] if len(scores) >= 3 else scores
        avg_recent = round(sum(recent_window) / len(recent_window), 2)

        # Downward spiral criteria:
        # 1. Last 3 consecutive check-ins <= 2 (low/overwhelmed)
        # 2. Or average over last 3 days < 2.3
        consecutive_low = len(recent_window) >= 3 and all(s <= 2 for s in recent_window)
        avg_depressed = avg_recent <= 2.2 and len(scores) >= 2
        is_downward = consecutive_low or avg_depressed

        suggested_action = "none"
        if consecutive_low:
            suggested_action = "escalate_counselor"
        elif is_downward:
            suggested_action = "supportive_nudge"
        elif avg_recent >= 4.5 and len(scores) >= 3:
            suggested_action = "celebrate"

        return MoodTrendResult(
            user_uuid=user_uuid,
            total_entries=len(scores),
            recent_scores=scores,
            average_recent_score=avg_recent,
            is_downward_trend=is_downward,
            dominant_triggers=sorted(set(triggers)),
            suggested_action=suggested_action,
        )
