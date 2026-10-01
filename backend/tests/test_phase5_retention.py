"""Phase 5 tests — Daily Check-ins, Mood Tracking & Retention Loops (roadmap 5.1–5.5).

Covers:
- Scheduler quiet hours enforcement and eligible user selection.
- Interactive payload parsing (mood, survey, recovery).
- MoodService trend detection & downward spiral detection.
- SurveyService score recording and cohort delta calculations.
- RecoveryService streak management, milestone celebration, and relapse reset.
- Pipeline routing for all Phase 5 interactive events.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
import pytest_asyncio

# -- conftest helpers (populated by the session fixture in conftest.py) ------
from tests.conftest import sign_body, wa_interactive_payload, wa_message_payload


# ====================================================================== 5.3
# MoodService — trend analytics & mood parsing
# ======================================================================

class TestMoodService:
    @pytest.mark.anyio
    async def test_parse_mood_selection_from_interactive_id(self):
        from app.services.mood_service import MoodService
        svc = MoodService()
        score, label, trigger = svc.parse_mood_selection("", "mood_great")
        assert score == 5
        assert label == "great"
        assert trigger is None

    @pytest.mark.anyio
    async def test_parse_mood_selection_trigger_id(self):
        from app.services.mood_service import MoodService
        svc = MoodService()
        score, label, trigger = svc.parse_mood_selection("", "trigger_cravings")
        assert trigger == "cravings"
        assert score == 2

    @pytest.mark.anyio
    async def test_parse_mood_free_text_sw(self):
        from app.services.mood_service import MoodService
        svc = MoodService()
        score, label, _ = svc.parse_mood_selection("Nimelemewa kabisa leo")
        assert score == 1
        assert label == "overwhelmed"

    @pytest.mark.anyio
    async def test_parse_mood_free_text_en(self):
        from app.services.mood_service import MoodService
        svc = MoodService()
        score, label, _ = svc.parse_mood_selection("I'm feeling great today!")
        assert score == 5
        assert label == "great"

    @pytest.mark.anyio
    async def test_log_mood_and_get_history(self, db_session_factory):
        from app.services.mood_service import MoodService
        from app.db.models import User, ConsentStatus

        svc = MoodService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            await db.flush()
            entry = await svc.log_mood(db, user_uuid, "I'm okay today", "mood_okay")
            await db.commit()

        async with db_session_factory() as db:
            history = await svc.get_history(db, user_uuid, limit=5)
            assert len(history) == 1
            assert history[0].score == 3
            assert history[0].label == "okay"

    @pytest.mark.anyio
    async def test_analyze_trend_detects_downward_spiral(self, db_session_factory):
        from app.services.mood_service import MoodService
        from app.db.models import User, ConsentStatus, MoodEntry

        svc = MoodService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            # 3 consecutive low scores
            for i in range(3):
                db.add(MoodEntry(
                    user_uuid=user_uuid,
                    score=1,
                    label="overwhelmed",
                    raw_selection="nimelemewa",
                ))
            await db.commit()

        async with db_session_factory() as db:
            trend = await svc.analyze_trend(db, user_uuid)
            assert trend.is_downward_trend is True
            assert trend.suggested_action == "escalate_counselor"

    @pytest.mark.anyio
    async def test_analyze_trend_celebrate_high_mood(self, db_session_factory):
        from app.services.mood_service import MoodService
        from app.db.models import User, ConsentStatus, MoodEntry

        svc = MoodService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            for _ in range(4):
                db.add(MoodEntry(user_uuid=user_uuid, score=5, label="great", raw_selection="fiti"))
            await db.commit()

        async with db_session_factory() as db:
            trend = await svc.analyze_trend(db, user_uuid)
            assert trend.suggested_action == "celebrate"

    @pytest.mark.anyio
    async def test_analyze_trend_no_data_returns_none_action(self, db_session_factory):
        from app.services.mood_service import MoodService
        from app.db.models import User, ConsentStatus

        svc = MoodService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            await db.commit()

        async with db_session_factory() as db:
            trend = await svc.analyze_trend(db, user_uuid)
            assert trend.total_entries == 0
            assert trend.suggested_action == "none"
            assert trend.is_downward_trend is False


# ====================================================================== 5.4
# SurveyService — micro-surveys & cohort delta calculations
# ======================================================================

class TestSurveyService:
    @pytest.mark.anyio
    async def test_parse_survey_selection_interactive_id(self):
        from app.services.survey_service import SurveyService
        svc = SurveyService()
        result = svc.parse_survey_selection("", "survey_craving_3")
        assert result is not None
        stype, score = result
        assert stype == "craving"
        assert score == 3.0

    @pytest.mark.anyio
    async def test_parse_survey_selection_text_fallback(self):
        from app.services.survey_service import SurveyService
        svc = SurveyService()
        result = svc.parse_survey_selection("stress 4")
        assert result is not None
        stype, score = result
        assert stype == "stress"
        assert score == 4.0

    @pytest.mark.anyio
    async def test_record_survey_response_and_retrieve(self, db_session_factory):
        from app.services.survey_service import SurveyService
        from app.db.models import User, ConsentStatus

        svc = SurveyService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            await db.flush()
            await svc.record_survey_response(db, user_uuid, "craving", 4.0)
            await db.commit()

        async with db_session_factory() as db:
            history = await svc.get_user_survey_history(db, user_uuid, survey_type="craving")
            assert len(history) == 1
            assert history[0].score == 4.0
            assert history[0].survey_type == "craving"

    @pytest.mark.anyio
    async def test_pilot_cohort_deltas_improvement(self, db_session_factory):
        from app.services.survey_service import SurveyService
        from app.db.models import User, ConsentStatus

        svc = SurveyService()
        # Create 2 users each with baseline and improved scores
        user_uuids = [str(uuid.uuid4()) for _ in range(2)]

        async with db_session_factory() as db:
            for uid in user_uuids:
                db.add(User(user_uuid=uid, consent_status=ConsentStatus.granted))
            await db.flush()
            # Both users start high (4) and improve to low (2)
            for uid in user_uuids:
                await svc.record_survey_response(db, uid, "craving", 4.0)  # baseline
                await svc.record_survey_response(db, uid, "craving", 2.0)  # latest
            await db.commit()

        async with db_session_factory() as db:
            summary = await svc.get_pilot_cohort_deltas(db, survey_type="craving")
            assert summary.total_users_evaluated == 2
            assert summary.baseline_avg_score == 4.0
            assert summary.latest_avg_score == 2.0
            assert summary.net_score_delta == -2.0
            assert summary.pct_users_improved == 100.0

    @pytest.mark.anyio
    async def test_pilot_cohort_deltas_empty_cohort(self, db_session_factory):
        from app.services.survey_service import SurveyService

        svc = SurveyService()
        async with db_session_factory() as db:
            summary = await svc.get_pilot_cohort_deltas(db, survey_type="stress")
            assert summary.total_users_evaluated == 0
            assert summary.net_score_delta == 0.0

    @pytest.mark.anyio
    async def test_get_survey_prompt_returns_buttons(self):
        from app.services.survey_service import SurveyService
        svc = SurveyService()
        prompt = svc.get_survey_prompt("craving", "sw")
        assert "buttons" in prompt
        assert len(prompt["buttons"]) == 3
        # All button titles within WhatsApp 20-char limit
        for btn in prompt["buttons"]:
            assert len(btn["title"]) <= 20


# ====================================================================== 5.5
# RecoveryService — streak tracking & milestone celebrations
# ======================================================================

class TestRecoveryService:
    @pytest.mark.anyio
    async def test_get_or_create_tracker_new_user(self, db_session_factory):
        from app.services.recovery_service import RecoveryService
        from app.db.models import User, ConsentStatus

        svc = RecoveryService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            await db.flush()
            tracker = await svc.get_or_create_tracker(db, user_uuid)
            await db.commit()

        assert tracker.user_uuid == user_uuid
        assert tracker.current_streak_days == 0

    @pytest.mark.anyio
    async def test_log_clean_day_increments_streak(self, db_session_factory):
        from app.services.recovery_service import RecoveryService
        from app.db.models import User, ConsentStatus

        svc = RecoveryService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            await db.flush()
            tracker, cel = await svc.log_clean_day(db, user_uuid)
            await db.commit()
            assert tracker.current_streak_days == 1
            assert cel is not None  # Day 1 milestone message

    @pytest.mark.anyio
    async def test_milestone_day_7_celebration_swahili(self, db_session_factory):
        from app.services.recovery_service import RecoveryService, CELEBRATIONS
        from app.db.models import User, ConsentStatus, RecoveryTracker

        svc = RecoveryService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            # Start at day 6
            db.add(RecoveryTracker(
                user_uuid=user_uuid,
                current_streak_days=6,
                longest_streak_days=6,
                milestones_reached_json=json.dumps([1, 3]),
            ))
            await db.flush()
            tracker, celebration = await svc.log_clean_day(db, user_uuid, language="sw")
            await db.commit()

        assert tracker.current_streak_days == 7
        assert celebration is not None
        assert "Wiki" in celebration or "7" in celebration or "WIKI" in celebration

    @pytest.mark.anyio
    async def test_reset_streak_is_non_shaming(self, db_session_factory):
        from app.services.recovery_service import RecoveryService
        from app.db.models import User, ConsentStatus, RecoveryTracker

        svc = RecoveryService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            db.add(RecoveryTracker(
                user_uuid=user_uuid,
                current_streak_days=14,
                longest_streak_days=14,
                milestones_reached_json="[1, 3, 7, 14]",
            ))
            await db.flush()
            tracker, msg = await svc.reset_streak(db, user_uuid, language="sw")
            await db.commit()

        assert tracker.current_streak_days == 0
        # Must be encouraging, not punitive
        assert "peke yako" in msg.lower() or "lawama" in msg.lower() or "pamoja" in msg.lower()

    @pytest.mark.anyio
    async def test_longest_streak_preserved_after_reset(self, db_session_factory):
        from app.services.recovery_service import RecoveryService
        from app.db.models import User, ConsentStatus, RecoveryTracker

        svc = RecoveryService()
        user_uuid = str(uuid.uuid4())

        async with db_session_factory() as db:
            db.add(User(user_uuid=user_uuid, consent_status=ConsentStatus.granted))
            db.add(RecoveryTracker(
                user_uuid=user_uuid,
                current_streak_days=30,
                longest_streak_days=30,
                milestones_reached_json="[]",
            ))
            await db.flush()
            tracker, _ = await svc.reset_streak(db, user_uuid)
            await db.commit()

        assert tracker.current_streak_days == 0
        assert tracker.longest_streak_days == 30  # preserved


# ====================================================================== 5.1
# CheckInScheduler — quiet hours, eligible user selection, delivery
# ======================================================================

class TestCheckInScheduler:
    def test_is_quiet_hours_during_night(self):
        from app.services.scheduler import is_quiet_hours
        # 23:00 EAT = 20:00 UTC
        night = dt.datetime(2025, 1, 1, 20, 0, tzinfo=dt.timezone.utc)
        assert is_quiet_hours(night) is True

    def test_is_quiet_hours_early_morning(self):
        from app.services.scheduler import is_quiet_hours
        # 04:00 EAT = 01:00 UTC
        early = dt.datetime(2025, 1, 1, 1, 0, tzinfo=dt.timezone.utc)
        assert is_quiet_hours(early) is True

    def test_is_not_quiet_hours_midday(self):
        from app.services.scheduler import is_quiet_hours
        # 10:00 EAT = 07:00 UTC
        midday = dt.datetime(2025, 1, 1, 7, 30, tzinfo=dt.timezone.utc)
        assert is_quiet_hours(midday) is False

    def test_is_not_quiet_hours_evening(self):
        from app.services.scheduler import is_quiet_hours
        # 20:30 EAT = 17:30 UTC
        eve = dt.datetime(2025, 1, 1, 17, 30, tzinfo=dt.timezone.utc)
        assert is_quiet_hours(eve) is False

    @pytest.mark.anyio
    async def test_scheduler_tick_skipped_during_quiet_hours(self, db_session_factory):
        from app.services.scheduler import CheckInScheduler
        from tests.conftest import FakeWhatsAppClient
        from app.services.identity_service import IdentityService
        from app.vault.crypto import IdentityVault
        import os, base64

        vault_key = base64.b64encode(os.urandom(32)).decode()
        vault = IdentityVault(vault_key)
        identity = IdentityService(vault)
        fake_wa = FakeWhatsAppClient()
        scheduler = CheckInScheduler(identity, fake_wa)

        # 23:00 EAT = 20:00 UTC — quiet hours
        quiet_time = dt.datetime(2025, 1, 1, 20, 0, tzinfo=dt.timezone.utc)

        async with db_session_factory() as db:
            dispatched = await scheduler.run_checkin_tick(db, now=quiet_time)

        assert dispatched == 0
        assert len(fake_wa.sent) == 0

    @pytest.mark.anyio
    async def test_scheduler_skip_opted_out_user(self, db_session_factory):
        from app.services.scheduler import CheckInScheduler
        from tests.conftest import FakeWhatsAppClient
        from app.services.identity_service import IdentityService
        from app.vault.crypto import IdentityVault
        from app.db.models import User, ConsentStatus
        import os, base64

        vault_key = base64.b64encode(os.urandom(32)).decode()
        vault = IdentityVault(vault_key)
        identity = IdentityService(vault)
        fake_wa = FakeWhatsAppClient()
        scheduler = CheckInScheduler(identity, fake_wa)

        # Create opted-out user
        user_uuid = str(uuid.uuid4())
        async with db_session_factory() as db:
            db.add(User(
                user_uuid=user_uuid,
                consent_status=ConsentStatus.granted,
                opt_out=True,
            ))
            await db.commit()

        # 10:00 EAT = 07:00 UTC — active hours
        active_time = dt.datetime(2025, 1, 1, 7, 0, tzinfo=dt.timezone.utc)
        async with db_session_factory() as db:
            eligible = await scheduler.get_eligible_users(db, now=active_time)

        # Opted-out user should not appear
        assert all(u.user_uuid != user_uuid for u, _ in eligible)


# ====================================================================== Pipeline integration
# Full webhook → pipeline Phase 5 routing tests
# ======================================================================

class TestPhase5PipelineRouting:
    @pytest.mark.anyio
    async def test_mood_interactive_routed_and_acknowledged(self, client):
        """Inbound mood_good button_reply receives empathetic acknowledgment."""
        from tests.conftest import sign_body
        import asyncio
        wa_id = f"2547{uuid.uuid4().hex[:8]}"
        # First, send AGREE to get consent
        body = wa_message_payload(wa_id, "AGREE")
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": sign_body(body), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)  # let worker commit

        # Now send mood_good interactive
        mood_body = wa_interactive_payload(wa_id, "list_reply", "mood_good", "Niko Salama 🙂")
        resp2 = await client.post(
            "/webhooks/whatsapp",
            content=mood_body,
            headers={"X-Hub-Signature-256": sign_body(mood_body), "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)

        # Should have sent at least a mood acknowledgment
        assert len(client.wa.sent) >= 2

    @pytest.mark.anyio
    async def test_recovery_clean_day_text_command(self, client):
        """'siku safi' text triggers clean day logging and streak acknowledgment."""
        import asyncio
        wa_id = f"2547{uuid.uuid4().hex[:8]}"
        body = wa_message_payload(wa_id, "AGREE")
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": sign_body(body), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)

        clean_body = wa_message_payload(wa_id, "siku safi")
        resp2 = await client.post(
            "/webhooks/whatsapp",
            content=clean_body,
            headers={"X-Hub-Signature-256": sign_body(clean_body), "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)
        # Should send a congratulatory message
        assert any(
            "safi" in t[1].lower() or "day" in t[1].lower() or "hongera" in t[1].lower()
            for t in client.wa.sent
        )

    @pytest.mark.anyio
    async def test_relapse_text_reset_streak_non_judgmental(self, client):
        """'relapse' text resets streak and sends non-shaming encouragement."""
        import asyncio
        wa_id = f"2547{uuid.uuid4().hex[:8]}"
        body = wa_message_payload(wa_id, "AGREE")
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": sign_body(body), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)

        relapse_body = wa_message_payload(wa_id, "relapse")
        resp2 = await client.post(
            "/webhooks/whatsapp",
            content=relapse_body,
            headers={"X-Hub-Signature-256": sign_body(relapse_body), "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)

        # Message must be present and not shaming
        messages_sent = [t[1] for t in client.wa.sent]
        assert any(
            "peke yako" in m.lower() or "lawama" in m.lower() or "pamoja" in m.lower()
            or "alone" in m.lower() or "judgment" in m.lower() or "slip" in m.lower()
            for m in messages_sent
        )

    @pytest.mark.anyio
    async def test_survey_interactive_routed(self, client):
        """survey_ interactive ID triggers survey recording and acknowledgment."""
        import asyncio
        wa_id = f"2547{uuid.uuid4().hex[:8]}"
        body = wa_message_payload(wa_id, "AGREE")
        resp = await client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": sign_body(body), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)

        survey_body = wa_interactive_payload(wa_id, "button_reply", "survey_craving_2", "2 - Kiasi")
        resp2 = await client.post(
            "/webhooks/whatsapp",
            content=survey_body,
            headers={"X-Hub-Signature-256": sign_body(survey_body), "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        await client.pipeline.queue.join()
        await asyncio.sleep(0.05)
        assert len(client.wa.sent) >= 2
