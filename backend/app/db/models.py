"""SQLAlchemy models — Phase 1 schema.

Privacy invariant (TRD §5): only ``identity_vault`` ever touches a phone number.
Every other table references users exclusively via ``user_uuid``.
"""
from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class ConsentStatus(str, enum.Enum):
    pending = "pending"      # first contact, consent screen not yet accepted
    granted = "granted"      # user replied AGREE / NDIPO
    withdrawn = "withdrawn"  # STOP / FUTA — bot silent, data purge scheduled


class OptOutStatus(str, enum.Enum):
    active = "active"
    opted_out = "opted_out"


class User(Base):
    """Anonymous user — UUID is the ONLY identifier."""

    __tablename__ = "users"

    user_uuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    language: Mapped[str | None] = mapped_column(String(10))  # sw | en | sheng (Phase 4.6 refines)
    consent_status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus, name="consent_status"), default=ConsentStatus.pending
    )
    opt_out: Mapped[bool] = mapped_column(Boolean, default=False)
    data_purged: Mapped[bool] = mapped_column(Boolean, default=False)

    sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")


class ChatSession(Base):
    """Conversation window; Redis holds hot state, this is durable record."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_uuid: Mapped[str] = mapped_column(ForeignKey("users.user_uuid"), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageKind(str, enum.Enum):
    user_text = "user_text"
    canned_reply = "canned_reply"
    crisis_response = "crisis_response"   # Phase 2 intercept (keyword fallback now)
    consent_prompt = "consent_prompt"
    system = "system"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection, name="msg_direction"))
    kind: Mapped[MessageKind] = mapped_column(Enum(MessageKind, name="msg_kind"), default=MessageKind.user_text)
    # WhatsApp provider message id — enables dedupe of webhook retries.
    wa_message_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Phase 2 placeholder: risk score written by the sentiment engine.
    risk_label: Mapped[str | None] = mapped_column(String(16), nullable=True)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class IdentityVaultRow(Base):
    """The ONLY place PII lives — encrypted at rest (AES-256-GCM)."""

    __tablename__ = "identity_vault"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    blind_index: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    cipher_nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purged_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_messages_session_created", Message.session_id, Message.created_at)


# ---------------------------------------------------------------------------
# Phase 2 — Risk & Sentiment Engine (roadmap 2.1-2.5)
# ---------------------------------------------------------------------------


class RiskLabel(str, enum.Enum):
    safe = "safe"
    distressed = "distressed"
    crisis = "crisis"


class RiskAssessment(Base):
    """Every inbound message scored BEFORE the LLM path (roadmap 2.3).

    Stores classifier outputs + feature breakdown for the evaluation
    harness (2.5) and counselor review. Contains no PII — keyed by UUID.
    """

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    user_uuid: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    label: Mapped[RiskLabel] = mapped_column(Enum(RiskLabel, name="risk_label"))
    score: Mapped[float] = mapped_column()  # composite risk score 0..100
    crisis_prob: Mapped[float] = mapped_column(default=0.0)
    distress_prob: Mapped[float] = mapped_column(default=0.0)
    model_version: Mapped[str] = mapped_column(String(32), default="rules-v1")
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # keyword hits, negation, etc.
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    intercepted: Mapped[bool] = mapped_column(Boolean, default=False)  # True ⇒ crisis route taken
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("ix_risk_assessments_user_created", RiskAssessment.user_uuid, RiskAssessment.created_at)


# ---------------------------------------------------------------------------
# Phase 3 — Counselor Dashboard & Human-in-the-Loop (roadmap 3.1-3.4)
# ---------------------------------------------------------------------------


class EscalationStatus(str, enum.Enum):
    open = "open"          # waiting in queue
    claimed = "claimed"    # a counselor took ownership
    handed_over = "handed_over"  # bot paused, counselor typing directly
    resolved = "resolved"  # outcome recorded
    muted = "muted"        # false positive / no action; suppresses duplicates


class EscalationOutcome(str, enum.Enum):
    helpline_confirmed = "helpline_confirmed"      # user agreed to call 1199
    counselor_contacted = "counselor_contacted"    # human follow-up happened
    false_positive = "false_positive"
    unreachable = "unreachable"
    other = "other"


class Escalation(Base):
    """Flagged session in the counselor queue (roadmap 3.1)."""

    __tablename__ = "escalations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_uuid: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    trigger_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    risk_score: Mapped[float] = mapped_column(default=0.0)  # priority ordering key
    risk_label: Mapped[RiskLabel] = mapped_column(Enum(RiskLabel, name="escalation_risk_label"))
    status: Mapped[EscalationStatus] = mapped_column(
        Enum(EscalationStatus, name="escalation_status"), default=EscalationStatus.open, index=True
    )
    claimed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)   # counselor id
    claimed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_response_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # SLA measurement vs escalation_created (PRD KPI < 2 min)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[EscalationOutcome | None] = mapped_column(
        Enum(EscalationOutcome, name="escalation_outcome"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("ix_escalations_open_priority", Escalation.status, Escalation.risk_score.desc())


class HandoverMode(str, enum.Enum):
    bot_active = "bot_active"        # normal: pipeline replies
    counselor_active = "counselor_active"  # bot PAUSED; counselor types directly


class SessionControl(Base):
    """Per-user bot pause / handover state (roadmap 3.2 one-click handover).

    One row per user_uuid; the pipeline consults this before replying.
    """

    __tablename__ = "session_controls"

    user_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[HandoverMode] = mapped_column(
        Enum(HandoverMode, name="handover_mode"), default=HandoverMode.bot_active
    )
    active_escalation_id: Mapped[str | None] = mapped_column(
        ForeignKey("escalations.id"), nullable=True
    )
    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Counselor(Base):
    """Dashboard operator account. Credentials are hashed; never plaintext."""

    __tablename__ = "counselors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128))
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)  # on-duty WhatsApp alert target (3.4)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)      # email alert target (3.4)
    is_on_duty: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditAction(str, enum.Enum):
    escalation_created = "escalation_created"
    escalation_claimed = "escalation_claimed"
    escalation_unclaimed = "escalation_unclaimed"
    handover_started = "handover_started"
    handover_ended = "handover_ended"
    counselor_replied = "counselor_replied"
    escalation_resolved = "escalation_resolved"
    escalation_muted = "escalation_muted"
    notification_sent = "notification_sent"
    notification_failed = "notification_failed"
    login_success = "login_success"
    login_failure = "login_failure"
    drill_recorded = "drill_recorded"
    user_data_wiped = "user_data_wiped"
    user_data_exported = "user_data_exported"


class AuditLogEntry(Base):
    """Tamper-evident append-only audit trail (roadmap 3.3, TRD §5).

    Each entry carries a SHA-256 hash chained to the previous entry's hash;
    any edit/deletion breaks the chain and is detectable via verify_chain().
    """

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_type: Mapped[str] = mapped_column(String(16))  # system | counselor
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="audit_action"))
    subject_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    entry_hash: Mapped[str] = mapped_column(String(64), default="")


class ResponseDrill(Base):
    """SOP dry-run timing records (roadmap 3.5) — evidence for the < 2 min KPI."""

    __tablename__ = "response_drills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    performed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    scenario: Mapped[str] = mapped_column(String(128))
    seconds_to_first_response: Mapped[float] = mapped_column()
    participants: Mapped[str | None] = mapped_column(String(256), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Phase 4 — Conversational AI & RAG Context Layer (roadmap 4.5)
# ---------------------------------------------------------------------------


class CbtStrategy(Base):
    """Vetted CBT coping strategies and psychological resources for RAG.

    Contains clinical techniques (thought reframing, box breathing, grounding)
    categorized by problem domain and language (sw, sheng, en).
    Zero PII is ever stored in this table.
    """

    __tablename__ = "cbt_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    category: Mapped[str] = mapped_column(String(64), index=True)  # anxiety | depression | panic | grief | insomnia | craving
    language: Mapped[str] = mapped_column(String(10), index=True, default="sw")  # sw | sheng | en
    title: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(String(256))
    instructions: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(String(512), default="")  # comma-separated lookup tags
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded float vector for similarity search
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Phase 5 — Daily Check-ins, Mood Tracking & Retention Loops (roadmap 5.1-5.5)
# ---------------------------------------------------------------------------


class MoodEntry(Base):
    """Structured mood logs and trigger records (roadmap 5.2 / 5.3)."""

    __tablename__ = "mood_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_uuid: Mapped[str] = mapped_column(ForeignKey("users.user_uuid"), index=True)
    score: Mapped[int] = mapped_column()  # 1 (overwhelmed/crisis) to 5 (great/fiti)
    label: Mapped[str] = mapped_column(String(32))  # great | good | okay | low | overwhelmed
    trigger_category: Mapped[str | None] = mapped_column(String(64), nullable=True)  # cravings | work | family | loneliness | sleep
    raw_selection: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


Index("ix_mood_entries_user_created", MoodEntry.user_uuid, MoodEntry.created_at.desc())


class CheckInSchedule(Base):
    """User check-in cadences, quiet hours, and frequency limits (roadmap 5.1)."""

    __tablename__ = "checkin_schedules"

    user_uuid: Mapped[str] = mapped_column(ForeignKey("users.user_uuid"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_hour_eat: Mapped[int] = mapped_column(default=9)  # 09:00 EAT (UTC+3)
    last_prompted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    streak_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MicroSurveyResponse(Base):
    """Weekly self-report outcomes for clinical pilot KPI tracking (roadmap 5.4)."""

    __tablename__ = "micro_survey_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_uuid: Mapped[str] = mapped_column(ForeignKey("users.user_uuid"), index=True)
    survey_type: Mapped[str] = mapped_column(String(32), index=True)  # craving | stress | phq2 | gad2
    score: Mapped[float] = mapped_column()  # 1.0 .. 5.0 normalized or clinical scale sum
    responses_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class RecoveryTracker(Base):
    """'Days clean' recovery milestones and motivational streaks (roadmap 5.5, Amina persona)."""

    __tablename__ = "recovery_trackers"

    user_uuid: Mapped[str] = mapped_column(ForeignKey("users.user_uuid"), primary_key=True)
    target_habit: Mapped[str] = mapped_column(String(64), default="substances")  # alcohol | substances | smoking | betting
    start_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    current_streak_days: Mapped[int] = mapped_column(default=0)
    longest_streak_days: Mapped[int] = mapped_column(default=0)
    last_checkin_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    milestones_reached_json: Mapped[str] = mapped_column(Text, default="[]")  # e.g. ["day_1", "day_3", "day_7"]
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Phase 6 — Resource Matching & Compliance Hardening (roadmap 6.1-6.5)
# ---------------------------------------------------------------------------


class PartnerCategory(str, enum.Enum):
    rehab = "rehab"                      # Inpatient residential rehabilitation
    outpatient = "outpatient"            # Outpatient addiction / medical counseling
    support_group = "support_group"      # AA / NA / 12-step peer support groups
    youth_empowerment = "youth_empowerment"  # Vocational training, mentorship, wellness
    mental_health = "mental_health"      # Psychiatric, psychotherapy, trauma counseling


class SubsidyStatus(str, enum.Enum):
    free = "free"                        # 100% free / government / donor funded
    subsidized = "subsidized"            # Sliding scale or subsidized fees
    nhif_covered = "nhif_covered"        # Covered by Social Health Authority (SHA) / NHIF
    private = "private"                  # Private fee-for-service


class Partner(Base):
    """Verified NGO, rehab, or empowerment partner directory entry (roadmap 6.1)."""

    __tablename__ = "partners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[PartnerCategory] = mapped_column(
        Enum(PartnerCategory, name="partner_category"), index=True
    )
    county: Mapped[str] = mapped_column(String(64), index=True)
    sub_county: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str] = mapped_column(String(64))
    helpline: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    website: Mapped[str | None] = mapped_column(String(256), nullable=True)
    services_description: Mapped[str] = mapped_column(Text)
    subsidy_status: Mapped[SubsidyStatus] = mapped_column(
        Enum(SubsidyStatus, name="subsidy_status"), default=SubsidyStatus.subsidized
    )
    verified_by: Mapped[str] = mapped_column(String(128), default="NACADA / OKOA Clinical Advisory")
    verified_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    operating_hours: Mapped[str] = mapped_column(String(128), default="Mon-Fri 08:00-17:00")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    referrals: Mapped[list["ReferralEvent"]] = relationship(back_populates="partner")


class ReferralEvent(Base):
    """Referral event log for KPI tracking (roadmap 6.2 - 500+ referrals Year 1)."""

    __tablename__ = "referral_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_uuid: Mapped[str] = mapped_column(String(36), index=True)
    partner_id: Mapped[str | None] = mapped_column(
        ForeignKey("partners.id"), nullable=True, index=True
    )
    county: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(
        String(32), default="partner_viewed"
    )  # directory_search | partner_viewed | contact_requested
    status: Mapped[str] = mapped_column(String(32), default="initiated")
    source: Mapped[str] = mapped_column(String(32), default="whatsapp_interactive")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    partner: Mapped[Partner | None] = relationship(back_populates="referrals")


Index("ix_referrals_county_created", ReferralEvent.county, ReferralEvent.created_at.desc())


