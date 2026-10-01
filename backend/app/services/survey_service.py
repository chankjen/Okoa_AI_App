"""Weekly Micro-Survey Service (roadmap 5.4).

Provides clinical KPI measurement for pilot cohorts (PRD §5):
- Self-reported craving intensity (1–5 scale).
- Self-reported stress intensity (1–5 scale).
- PHQ-2 / GAD-2 screening prompts.
- Baseline vs. Latest outcome delta calculations across cohorts.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MicroSurveyResponse

logger = logging.getLogger("okoa.surveys")

SURVEY_SCALES = {
    "craving": {
        "sw": {
            "title": "Tathmini ya Hamu (Craving)",
            "body": "Habari! Ni wakati wa tathmini yetu ya kila wiki. Katika siku 7 zilizopita, umepata hamu au msukumo wa kutumia kwa kiwango gani?",
            "options": [
                ("survey_craving_1", "1 - Hakuna Kabisa 🟢"),
                ("survey_craving_3", "3 - Kiwango cha Wastani 🟡"),
                ("survey_craving_5", "5 - Hamu Kali Sana 🔴"),
            ],
        },
        "sheng": {
            "title": "Tathmini ya Cravings",
            "body": "Niaje! Time ya weekly check-in ya cravings. In the last 7 days, msukumo wa kutumia ulikuwa vipi?",
            "options": [
                ("survey_craving_1", "1 - Zero kabisa 🟢"),
                ("survey_craving_3", "3 - Kiasi tu 🟡"),
                ("survey_craving_5", "5 - Noma sana 🔴"),
            ],
        },
        "en": {
            "title": "Weekly Craving Assessment",
            "body": "Hello! It's time for our weekly check-in. In the past 7 days, how strong were your cravings or urge to use?",
            "options": [
                ("survey_craving_1", "1 - None at all 🟢"),
                ("survey_craving_3", "3 - Moderate 🟡"),
                ("survey_craving_5", "5 - Very Intense 🔴"),
            ],
        },
    },
    "stress": {
        "sw": {
            "title": "Tathmini ya Msongo wa Mawazo (Stress)",
            "body": "Katika wiki iliyopita, umekuwa ukipata msongo wa mawazo au wasiwasi kwa kiwango gani?",
            "options": [
                ("survey_stress_1", "1 - Kidogo / Hakuna 🟢"),
                ("survey_stress_3", "3 - Wastani 🟡"),
                ("survey_stress_5", "5 - Mkubwa Sana 🔴"),
            ],
        },
        "sheng": {
            "title": "Tathmini ya Stress",
            "body": "Katika wiki iliyopita, stress au presha ilikua kiwango gani kwako?",
            "options": [
                ("survey_stress_1", "1 - Sina stress 🟢"),
                ("survey_stress_3", "3 - Kiasi tu 🟡"),
                ("survey_stress_5", "5 - Stress kibao 🔴"),
            ],
        },
        "en": {
            "title": "Weekly Stress Assessment",
            "body": "In the past week, how would you rate your overall stress level?",
            "options": [
                ("survey_stress_1", "1 - Low / None 🟢"),
                ("survey_stress_3", "3 - Moderate 🟡"),
                ("survey_stress_5", "5 - Very High 🔴"),
            ],
        },
    },
}


@dataclass
class CohortDeltaSummary:
    survey_type: str
    total_users_evaluated: int
    baseline_avg_score: float
    latest_avg_score: float
    net_score_delta: float
    pct_users_improved: float  # Percentage of users whose score decreased (less craving/stress)


class SurveyService:
    def get_survey_prompt(
        self,
        survey_type: str = "craving",
        language: str = "sw",
    ) -> dict[str, Any]:
        """Generate interactive WhatsApp button options for survey."""
        lang_key = language if language in ("sw", "sheng", "en") else "sw"
        config = SURVEY_SCALES.get(survey_type, SURVEY_SCALES["craving"])[lang_key]

        buttons = [
            {"id": opt_id, "title": label[:20]}
            for opt_id, label in config["options"]
        ]

        return {
            "survey_type": survey_type,
            "body_text": config["body"],
            "buttons": buttons,
        }

    def parse_survey_selection(self, text: str, interactive_id: str | None = None) -> tuple[str, float] | None:
        """Parse inbound response into (survey_type, score)."""
        iid = (interactive_id or "").lower()
        if iid.startswith("survey_"):
            parts = iid.split("_")
            if len(parts) >= 3:
                stype = parts[1]
                try:
                    score = float(parts[2])
                    return stype, score
                except ValueError:
                    pass

        # Text matching fallbacks
        low = text.lower().strip()
        if "craving" in low or "hamu" in low:
            stype = "craving"
        elif "stress" in low or "msongo" in low:
            stype = "stress"
        else:
            return None

        for digit in ["5", "4", "3", "2", "1"]:
            if digit in low:
                return stype, float(digit)

        return None

    async def record_survey_response(
        self,
        db: AsyncSession,
        user_uuid: str,
        survey_type: str,
        score: float,
        details: dict[str, Any] | None = None,
    ) -> MicroSurveyResponse:
        """Persist a weekly micro-survey response."""
        record = MicroSurveyResponse(
            user_uuid=user_uuid,
            survey_type=survey_type,
            score=round(score, 1),
            responses_json=json.dumps(details or {}),
        )
        db.add(record)
        await db.flush()
        logger.info("recorded survey response", extra={
            "event": "survey_recorded",
            "user_uuid": user_uuid,
            "survey_type": survey_type,
            "score": score,
        })
        return record

    async def get_user_survey_history(
        self,
        db: AsyncSession,
        user_uuid: str,
        survey_type: str | None = None,
        limit: int = 12,
    ) -> Sequence[MicroSurveyResponse]:
        """Fetch chronological survey responses for a user."""
        stmt = (
            select(MicroSurveyResponse)
            .where(MicroSurveyResponse.user_uuid == user_uuid)
        )
        if survey_type:
            stmt = stmt.where(MicroSurveyResponse.survey_type == survey_type)
        stmt = stmt.order_by(MicroSurveyResponse.created_at.asc()).limit(limit)
        return (await db.scalars(stmt)).all()

    async def get_pilot_cohort_deltas(
        self,
        db: AsyncSession,
        survey_type: str = "craving",
    ) -> CohortDeltaSummary:
        """Calculate baseline vs. latest delta across the pilot user cohort.

        Measures PRD §5 clinical KPI (e.g. reduction in craving/stress over time).
        """
        # Get all responses ordered by user and time
        stmt = (
            select(MicroSurveyResponse)
            .where(MicroSurveyResponse.survey_type == survey_type)
            .order_by(MicroSurveyResponse.user_uuid, MicroSurveyResponse.created_at.asc())
        )
        rows = (await db.scalars(stmt)).all()

        user_records: dict[str, list[MicroSurveyResponse]] = {}
        for r in rows:
            user_records.setdefault(r.user_uuid, []).append(r)

        # Filter users with at least 2 responses (baseline and follow-up)
        multi_response_users = {
            uid: recs for uid, recs in user_records.items() if len(recs) >= 2
        }

        if not multi_response_users:
            return CohortDeltaSummary(
                survey_type=survey_type,
                total_users_evaluated=0,
                baseline_avg_score=0.0,
                latest_avg_score=0.0,
                net_score_delta=0.0,
                pct_users_improved=0.0,
            )

        baseline_scores: list[float] = []
        latest_scores: list[float] = []
        improved_count = 0

        for recs in multi_response_users.values():
            base = recs[0].score
            latest = recs[-1].score
            baseline_scores.append(base)
            latest_scores.append(latest)
            if latest < base:  # Score reduction indicates clinical improvement
                improved_count += 1

        b_avg = round(sum(baseline_scores) / len(baseline_scores), 2)
        l_avg = round(sum(latest_scores) / len(latest_scores), 2)
        delta = round(l_avg - b_avg, 2)
        pct_improved = round((improved_count / len(multi_response_users)) * 100, 1)

        return CohortDeltaSummary(
            survey_type=survey_type,
            total_users_evaluated=len(multi_response_users),
            baseline_avg_score=b_avg,
            latest_avg_score=l_avg,
            net_score_delta=delta,
            pct_users_improved=pct_improved,
        )
