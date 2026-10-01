"""Compliance & self-service data controls — Kenya DPA (2019) compliance.

Implements statutory obligations under the Kenya Data Protection Act (2019):
- Section 40: Right to Erasure ("Futa data yangu" full data wipe)
- Section 26: Right of Access ("Maelezo" data subject access summary)
- Section 30: Lawful processing & consent withdrawal
- Section 31: Data Protection Impact Assessment safeguards & audit trails
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditAction,
    AuditLogEntry,
    ChatSession,
    CheckInSchedule,
    ConsentStatus,
    IdentityVaultRow,
    Message,
    MicroSurveyResponse,
    MoodEntry,
    RecoveryTracker,
    ReferralEvent,
    RiskAssessment,
    SessionControl,
    User,
)
from app.services.session_store import SessionStore

logger = logging.getLogger("okoa.compliance")


class ComplianceService:
    """Manages Kenya DPA 2019 data subject requests (erasure, access, portability)."""

    async def wipe_user_data(
        self,
        db: AsyncSession,
        user_uuid: str,
        session_store: SessionStore | None = None,
        actor: str = "user",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Perform a complete hard delete of all user records (DPA 2019 § 40).

        Deletes:
        - Messages (all sessions)
        - Chat sessions
        - Risk assessments
        - Mood entries
        - Micro surveys
        - Recovery tracking & streaks
        - Check-in schedules
        - Referral event links
        - Session control states

        Tombstones identity vault:
        - Sets status to 'tombstoned', purged_at to now, overwrites ciphertext/nonce to empty bytes.
        - Sets user.data_purged = True, user.opt_out = True, user.consent_status = withdrawn.
        - Clears Redis/session cache.
        - Appends an audit log entry documenting compliance.
        """
        # 1. Find user's sessions to delete messages
        session_ids = (
            await db.scalars(select(ChatSession.id).where(ChatSession.user_uuid == user_uuid))
        ).all()

        deleted_counts = {}

        if session_ids:
            msg_del = await db.execute(
                delete(Message).where(Message.session_id.in_(session_ids))
            )
            deleted_counts["messages"] = msg_del.rowcount or 0

        # 2. Hard delete sessions
        sess_del = await db.execute(
            delete(ChatSession).where(ChatSession.user_uuid == user_uuid)
        )
        deleted_counts["chat_sessions"] = sess_del.rowcount or 0

        # 3. Hard delete risk assessments
        risk_del = await db.execute(
            delete(RiskAssessment).where(RiskAssessment.user_uuid == user_uuid)
        )
        deleted_counts["risk_assessments"] = risk_del.rowcount or 0

        # 4. Hard delete mood entries
        mood_del = await db.execute(
            delete(MoodEntry).where(MoodEntry.user_uuid == user_uuid)
        )
        deleted_counts["mood_entries"] = mood_del.rowcount or 0

        # 5. Hard delete micro surveys
        survey_del = await db.execute(
            delete(MicroSurveyResponse).where(MicroSurveyResponse.user_uuid == user_uuid)
        )
        deleted_counts["micro_surveys"] = survey_del.rowcount or 0

        # 6. Hard delete recovery streaks
        rec_del = await db.execute(
            delete(RecoveryTracker).where(RecoveryTracker.user_uuid == user_uuid)
        )
        deleted_counts["recovery_trackers"] = rec_del.rowcount or 0

        # 7. Hard delete checkin schedule
        sched_del = await db.execute(
            delete(CheckInSchedule).where(CheckInSchedule.user_uuid == user_uuid)
        )
        deleted_counts["checkin_schedules"] = sched_del.rowcount or 0

        # 8. Anonymize or delete referral events
        ref_del = await db.execute(
            delete(ReferralEvent).where(ReferralEvent.user_uuid == user_uuid)
        )
        deleted_counts["referral_events"] = ref_del.rowcount or 0

        # 9. Delete session controls
        await db.execute(
            delete(SessionControl).where(SessionControl.user_uuid == user_uuid)
        )

        # 10. Tombstone vault entry — cryptographic erasure
        vault_row = await db.scalar(
            select(IdentityVaultRow).where(IdentityVaultRow.user_uuid == user_uuid)
        )
        if vault_row is not None:
            vault_row.status = "tombstoned"
            vault_row.purged_at = dt.datetime.now(dt.timezone.utc)
            vault_row.ciphertext = b""
            vault_row.cipher_nonce = b""

        # 11. Update user record to purged state
        user = await db.get(User, user_uuid)
        if user is not None:
            user.data_purged = True
            user.opt_out = True
            user.consent_status = ConsentStatus.withdrawn

        # 12. Clear Redis hot state
        if session_store is not None:
            await session_store.clear(user_uuid)

        # 13. Append tamper-evident audit record (TRD §5)
        # Import audit service helper if available, or write record directly
        last_entry = await db.scalar(
            select(AuditLogEntry).order_by(AuditLogEntry.seq.desc()).limit(1)
        )
        prev_hash = last_entry.entry_hash if last_entry else "0" * 64
        import hashlib
        entry_payload = json.dumps({"deleted_counts": deleted_counts, "dpa_section": "40"})
        ts_now = dt.datetime.now(dt.timezone.utc)
        h = hashlib.sha256()
        h.update(f"{prev_hash}|{ts_now.isoformat()}|user_data_wiped|{user_uuid}|{entry_payload}".encode())
        entry_hash = h.hexdigest()

        audit = AuditLogEntry(
            actor_type=actor,
            actor_id=actor_id,
            action=AuditAction.user_data_wiped,
            subject_uuid=user_uuid,
            details_json=entry_payload,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        db.add(audit)
        await db.commit()

        logger.info(
            "completed DPA section 40 data wipe for user=%s items_deleted=%s",
            user_uuid, deleted_counts
        )
        return {
            "status": "purged",
            "user_uuid": user_uuid,
            "deleted_records": deleted_counts,
            "purged_at": ts_now.isoformat(),
        }

    async def generate_data_summary(
        self,
        db: AsyncSession,
        user_uuid: str,
        language: str = "sw",
    ) -> str:
        """Data subject access request summary (Kenya DPA 2019 § 26)."""
        user = await db.get(User, user_uuid)
        if user is None:
            return "Hatujaweza kupata kumbukumbu zako katika mfumo wetu."

        # Count messages across user sessions
        session_ids = (
            await db.scalars(select(ChatSession.id).where(ChatSession.user_uuid == user_uuid))
        ).all()
        msg_count = 0
        if session_ids:
            msg_count = (
                await db.scalar(
                    select(func.count(Message.id)).where(Message.session_id.in_(session_ids))
                )
            ) or 0

        mood_count = (
            await db.scalar(
                select(func.count(MoodEntry.id)).where(MoodEntry.user_uuid == user_uuid)
            )
        ) or 0

        survey_count = (
            await db.scalar(
                select(func.count(MicroSurveyResponse.id)).where(MicroSurveyResponse.user_uuid == user_uuid)
            )
        ) or 0

        recovery = await db.get(RecoveryTracker, user_uuid)
        streak_days = recovery.current_streak_days if recovery else 0

        created_str = (
            user.created_at.strftime("%d-%m-%Y") if user.created_at else "Leo"
        )

        if language == "sheng":
            return (
                "📋 *Ripoti ya Data Yako (Kenya DPA 2019 § 26)*\n\n"
                f"• *Anonymous ID:* `{user_uuid[:8]}...`\n"
                f"• *Mwanzo wa safari:* {created_str}\n"
                f"• *Lugha unayopenda:* {user.language or 'sheng'}\n"
                f"• *Jumla ya messages:* {msg_count}\n"
                f"• *Mood check-ins zilizorekodiwa:* {mood_count}\n"
                f"• *Recovery streak:* Day {streak_days} safi\n"
                f"• *Surveys zilizojazwa:* {survey_count}\n\n"
                "🔒 *Zero PII Guarantee:*\n"
                "Hatuna jina lako, nambari yako ya simu haionekani (iko encrypted kwa vault), "
                "wala hatujawahi chukua GPS coordinates zako.\n\n"
                "⚖️ *Haki Zako:*\n"
                "Ukitaka kufuta kila kitu kabisa kutoka system zetu bila trace yoyote, "
                "andika: *FUTA DATA YANGU*."
            )
        elif language == "en":
            return (
                "📋 *Your Personal Data Summary (Kenya DPA 2019 § 26)*\n\n"
                f"• *Anonymous ID:* `{user_uuid[:8]}...`\n"
                f"• *Enrolled on:* {created_str}\n"
                f"• *Preferred Language:* {user.language or 'en'}\n"
                f"• *Messages Exchanged:* {msg_count}\n"
                f"• *Mood Check-ins Logged:* {mood_count}\n"
                f"• *Recovery Streak:* Day {streak_days} clean\n"
                f"• *Surveys Completed:* {survey_count}\n\n"
                "🔒 *Zero PII Guarantee:*\n"
                "OKOA AI does not store your real name, your phone number is isolated in an "
                "encrypted vault, and we never collect GPS location.\n\n"
                "⚖️ *Your Statutory Rights:*\n"
                "Under the Kenya Data Protection Act (2019), you have the right to erase all your "
                "records at any time. Simply reply: *FUTA DATA YANGU* or *DELETE MY DATA*."
            )
        else:
            return (
                "📋 *Maelezo ya Data Yako (Sheria ya Kenya DPA 2019 § 26)*\n\n"
                f"• *Kitambulisho Kisichojulikana:* `{user_uuid[:8]}...`\n"
                f"• *Tarehe uliyoanza:* {created_str}\n"
                f"• *Lugha teule:* {user.language or 'sw'}\n"
                f"• *Ujumbe uliotumiwa:* {msg_count}\n"
                f"• *Tathmini za hisia (Mood):* {mood_count}\n"
                f"• *Siku safi (Streak):* Siku {streak_days}\n"
                f"• *Utafiti mdogo uliokamilika:* {survey_count}\n\n"
                "🔒 *Uhakika wa Faragha (Zero PII):*\n"
                "Mfumo wetu hauna jina lako, nambari yako ya simu imefungwa kwenye chumba salama "
                "(encrypted vault), na hatuhifadhi eneo lako la GPS.\n\n"
                "⚖️ *Haki Zako Kisheria:*\n"
                "Kulingana na Sheria ya Kulinda Data ya Kenya (2019), una haki ya kufuta data "
                "yako yote kabisa wakati wowote. Andika tu: *FUTA DATA YANGU*."
            )

    def get_wipe_confirmation_message(self, language: str = "sw") -> str:
        """Localized acknowledgment following complete data erasure."""
        if language == "sheng":
            return (
                "✅ *Data Yako Yote Imefutwa Kabisa! (DPA 2019)*\n\n"
                "Tumefuta conversation zote, mood logs, streaks, na detail yoyote kutoka "
                "database zetu na server cache. Nambari yako kwenye vault imefungwa (tombstoned).\n\n"
                "Hakuna mtu anaweza ku-trace chochote. Asante kwa uaminifu wako. "
                "Ukihitaji usaidizi tena siku zijazo, tuandikie tu *Karibu*. Uko salama daima. 🤍"
            )
        elif language == "en":
            return (
                "✅ *All Your Data Has Been Permanently Erased (DPA 2019)*\n\n"
                "In full compliance with Section 40 of the Kenya Data Protection Act (2019), "
                "all your messages, mood logs, recovery trackers, and session states have been "
                "permanently purged. Your vault identity has been tombstoned.\n\n"
                "No recoverable record of your identity remains. If you ever need support in the future, "
                "simply message us 'Karibu'. Wishing you well on your journey. 🤍"
            )
        else:
            return (
                "✅ *Data Yako Yote Imefutwa Kabisa (Sheria ya DPA 2019)*\n\n"
                "Kulingana na Kifungu cha 40 cha Sheria ya Kulinda Data ya Kenya (2019), "
                "ujumbe wako wote, kumbukumbu za hisia, safari ya siku safi, na data yote "
                "imefutwa kabisa kutoka kwa hifadhidata zetu. Kitambulisho chako kimefungwa (tombstoned).\n\n"
                "Hakuna rekodi inayoweza kufuatiliwa iliyobaki. Ukitaka kurudi baadaye, "
                "tuandikie tu 'Karibu'. Tunakutakia amani na afya njema. 🤍"
            )
