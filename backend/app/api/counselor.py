"""Counselor dashboard API — Phase 3 human-in-the-loop (roadmap 3.1–3.5).

All routes except /login require a Bearer JWT from /counselor/login.
Privacy: conversation views expose user_uuid only — never phones, names or
contact details (TRD §5). Every state transition lands in the chained audit
log via the services; SLA timers are computed server-side for drill reports.
"""
from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.counselor_auth import (
    authenticate,
    create_token,
    require_counselor,
)
from app.db.models import (
    AuditAction,
    Counselor,
    Escalation,
    EscalationOutcome,
    EscalationStatus,
    HandoverMode,
    Message,
    MessageDirection,
    MessageKind,
    ResponseDrill,
    RiskAssessment,
    SessionControl,
)
from app.db.session import get_db
from app.safety.audit import audit_append, export_audit_csv, verify_chain

logger = logging.getLogger("okoa.counselor_api")

router = APIRouter(prefix="/counselor", tags=["counselor"])


# ---------------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    counselor = await authenticate(db, body.username, body.password)
    if counselor is None:
        # Log failed attempts to the audit trail too (accountability).
        await audit_append(
            db, action=AuditAction.login_failure, actor_type="system",
            details={"username": body.username},
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token, ttl = create_token(counselor)
    await audit_append(
        db, action=AuditAction.login_success, actor_type="counselor",
        actor_id=counselor.id, details={"username": counselor.username},
    )
    await db.commit()
    return {"access_token": token, "expires_in": ttl,
            "display_name": counselor.display_name}


# ------------------------------------------------------------------ queue 3.1
def _esc_dict(e: Escalation) -> dict:
    return {
        "id": e.id,
        "user_uuid": e.user_uuid,
        "session_id": e.session_id,
        "risk_score": e.risk_score,
        "risk_label": e.risk_label.value,
        "status": e.status.value,
        "claimed_by": e.claimed_by,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "first_response_at": e.first_response_at.isoformat() if e.first_response_at else None,
        "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
        "outcome": e.outcome.value if e.outcome else None,
        "notes": e.notes,
    }


@router.get("/escalations")
async def list_escalations(
    request: Request,
    include_closed: bool = False,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """Priority-ordered queue (highest risk first) — roadmap 3.1."""
    q = select(Escalation)
    if not include_closed:
        q = q.where(Escalation.status.in_(
            [EscalationStatus.open, EscalationStatus.claimed, EscalationStatus.handed_over]))
    q = q.order_by(Escalation.risk_score.desc(), Escalation.created_at.asc())
    rows = (await db.scalars(q)).all()
    sla = request.app.state.settings.escalation_sla_seconds if hasattr(
        request.app.state, "settings") else 120
    out = []
    now = dt.datetime.now(dt.timezone.utc)
    for e in rows:
        d = _esc_dict(e)
        if e.created_at:
            created = e.created_at.replace(tzinfo=dt.timezone.utc) \
                if e.created_at.tzinfo is None else e.created_at
            d["age_seconds"] = round((now - created).total_seconds())
            d["sla_breached"] = (
                e.status is EscalationStatus.open and d["age_seconds"] > sla
            )
        out.append(d)
    return {"queue": out, "open_count": sum(
        1 for e in rows if e.status is EscalationStatus.open)}


@router.post("/escalations/{escalation_id}/claim")
async def claim(escalation_id: str, request: Request,
                counselor: Counselor = Depends(require_counselor),
                db: AsyncSession = Depends(get_db)):
    esc = await db.get(Escalation, escalation_id)
    if esc is None:
        raise HTTPException(404, "escalation not found")
    if esc.status not in (EscalationStatus.open, EscalationStatus.claimed):
        raise HTTPException(409, f"cannot claim from status {esc.status.value}")
    esc.status = EscalationStatus.claimed
    esc.claimed_by = counselor.id
    esc.claimed_at = dt.datetime.now(dt.timezone.utc)
    await audit_append(
        db, action=AuditAction.escalation_claimed, actor_type="counselor",
        actor_id=counselor.id, subject_uuid=esc.user_uuid,
        details={"escalation_id": esc.id},
    )
    await db.commit()
    await _broadcast(payload={"type": "escalation_update", **_esc_dict(esc)})
    return _esc_dict(esc)


@router.post("/escalations/{escalation_id}/unclaim")
async def unclaim(escalation_id: str,
                  counselor: Counselor = Depends(require_counselor),
                  db: AsyncSession = Depends(get_db)):
    esc = await db.get(Escalation, escalation_id)
    if esc is None:
        raise HTTPException(404, "escalation not found")
    if esc.claimed_by != counselor.id:
        raise HTTPException(403, "only the owner can unclaim")
    esc.status = EscalationStatus.open
    esc.claimed_by = None
    esc.claimed_at = None
    await audit_append(
        db, action=AuditAction.escalation_unclaimed, actor_type="counselor",
        actor_id=counselor.id, subject_uuid=esc.user_uuid,
        details={"escalation_id": esc.id},
    )
    await db.commit()
    await _broadcast(payload={"type": "escalation_update", **_esc_dict(esc)})
    return _esc_dict(esc)


class ResolveRequest(BaseModel):
    outcome: EscalationOutcome
    notes: str | None = Field(default=None, max_length=2000)


@router.post("/escalations/{escalation_id}/resolve")
async def resolve(escalation_id: str, body: ResolveRequest,
                  counselor: Counselor = Depends(require_counselor),
                  db: AsyncSession = Depends(get_db)):
    esc = await db.get(Escalation, escalation_id)
    if esc is None:
        raise HTTPException(404, "escalation not found")
    if esc.status in (EscalationStatus.resolved, EscalationStatus.muted):
        raise HTTPException(409, "already closed")
    was_open_like = esc.status in (
        EscalationStatus.open, EscalationStatus.claimed, EscalationStatus.handed_over)
    esc.status = EscalationStatus.resolved
    esc.outcome = body.outcome
    esc.notes = body.notes
    esc.resolved_at = dt.datetime.now(dt.timezone.utc)
    # Return bot control to automation.
    control = await db.get(SessionControl, esc.user_uuid)
    if control and control.active_escalation_id == esc.id:
        control.mode = HandoverMode.bot_active
        control.active_escalation_id = None
        control.changed_by = counselor.id
    await audit_append(
        db, action=AuditAction.escalation_resolved, actor_type="counselor",
        actor_id=counselor.id, subject_uuid=esc.user_uuid,
        details={"escalation_id": esc.id, "outcome": body.outcome.value},
    )
    await db.commit()
    await _broadcast(payload={"type": "escalation_update", **_esc_dict(esc)})
    logger.info("escalation resolved", extra={"event": "resolved",
                                              "was_open_like": was_open_like})
    return _esc_dict(esc)


@router.post("/escalations/{escalation_id}/mute")
async def mute(escalation_id: str, body: ResolveRequest,
               counselor: Counselor = Depends(require_counselor),
               db: AsyncSession = Depends(get_db)):
    """Mark false-positive / suppress duplicates (still audited)."""
    esc = await db.get(Escalation, escalation_id)
    if esc is None:
        raise HTTPException(404, "escalation not found")
    esc.status = EscalationStatus.muted
    esc.outcome = body.outcome
    esc.notes = body.notes
    esc.resolved_at = dt.datetime.now(dt.timezone.utc)
    control = await db.get(SessionControl, esc.user_uuid)
    if control and control.active_escalation_id == esc.id:
        control.mode = HandoverMode.bot_active
        control.active_escalation_id = None
    await audit_append(
        db, action=AuditAction.escalation_muted, actor_type="counselor",
        actor_id=counselor.id, subject_uuid=esc.user_uuid,
        details={"escalation_id": esc.id, "outcome": body.outcome.value},
    )
    await db.commit()
    await _broadcast(payload={"type": "escalation_update", **_esc_dict(esc)})
    return _esc_dict(esc)


# ------------------------------------------------------- conversation 3.2
@router.get("/sessions/{user_uuid}/messages")
async def session_messages(user_uuid: str, limit: int = 50,
                           _: Counselor = Depends(require_counselor),
                           db: AsyncSession = Depends(get_db)):
    """Anonymized conversation view — UUID only, no PII anywhere."""
    rows = (await db.scalars(
        select(Message)
        .where(Message.session_id.in_(
            select(Escalation.session_id).where(Escalation.user_uuid == user_uuid)))
        .order_by(Message.created_at.desc())
        .limit(min(limit, 200))
    )).all()
    return {
        "user_uuid": user_uuid,
        "messages": [
            {
                "id": m.id,
                "direction": m.direction.value,
                "kind": m.kind.value,
                "body": m.body,
                "risk_label": m.risk_label,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in reversed(rows)
        ],
    }


# ---------------------------------------------------------- handover 3.2
class HandoverRequest(BaseModel):
    mode: HandoverMode


@router.post("/escalations/{escalation_id}/handover")
async def handover(escalation_id: str, body: HandoverRequest, request: Request,
                   counselor: Counselor = Depends(require_counselor),
                   db: AsyncSession = Depends(get_db)):
    """One-click: bot pauses (counselor_active) or resumes (bot_active)."""
    esc = await db.get(Escalation, escalation_id)
    if esc is None:
        raise HTTPException(404, "escalation not found")
    service = _service_from_request(request)
    await service.set_handover(
        db, esc.user_uuid, body.mode,
        counselor_id=counselor.id,
        escalation_id=esc.id if body.mode is HandoverMode.counselor_active else None,
    )
    if body.mode is HandoverMode.counselor_active:
        esc.status = EscalationStatus.handed_over
        if esc.claimed_by is None:
            esc.claimed_by = counselor.id
            esc.claimed_at = dt.datetime.now(dt.timezone.utc)
    elif esc.status is EscalationStatus.handed_over:
        esc.status = EscalationStatus.claimed
    await db.commit()
    await _broadcast(payload={"type": "escalation_update", **_esc_dict(esc)})
    return {"escalation": _esc_dict(esc), "mode": body.mode.value}


class CounselorReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/sessions/{user_uuid}/reply")
async def counselor_reply(user_uuid: str, body: CounselorReplyRequest,
                          request: Request,
                          counselor: Counselor = Depends(require_counselor),
                          db: AsyncSession = Depends(get_db)):
    """Counselor types directly to the user (requires handover mode)."""
    control = await db.get(SessionControl, user_uuid)
    if control is None or control.mode is not HandoverMode.counselor_active:
        raise HTTPException(409, "handover mode not active for this user")
    wa = request.app.state.wa
    vault = request.app.state.identity
    msisdn = await vault.reveal_msisdn(db, user_uuid)
    if msisdn is None:
        raise HTTPException(410, "identity purged/opted-out; cannot deliver")
    await wa.send_text(msisdn, body.text)

    session_id = await db.scalar(
        select(Escalation.session_id).where(Escalation.user_uuid == user_uuid)
        .order_by(Escalation.created_at.desc()).limit(1))
    db.add(Message(session_id=session_id or "direct",
                   direction=MessageDirection.outbound,
                   kind=MessageKind.system, body=body.text[:4000]))
    # SLA clock: first counselor message marks first response.
    esc = await db.scalar(
        select(Escalation).where(
            Escalation.user_uuid == user_uuid,
            Escalation.status.in_([EscalationStatus.claimed, EscalationStatus.handed_over]),
        ).order_by(Escalation.created_at.desc()).limit(1))
    if esc is not None and esc.first_response_at is None:
        esc.first_response_at = dt.datetime.now(dt.timezone.utc)
    await audit_append(
        db, action=AuditAction.counselor_replied, actor_type="counselor",
        actor_id=counselor.id, subject_uuid=user_uuid,
        details={"escalation_id": esc.id if esc else None,
                 "length": len(body.text)},
    )
    await db.commit()
    return {"sent": True}


# ------------------------------------------------------------ audit 3.3
@router.get("/audit")
async def read_audit(limit: int = 200,
                     _: Counselor = Depends(require_counselor),
                     db: AsyncSession = Depends(get_db)):
    from app.db.models import AuditLogEntry

    rows = (await db.scalars(
        select(AuditLogEntry).order_by(AuditLogEntry.seq.desc()).limit(min(limit, 1000))
    )).all()
    return [{
        "seq": r.seq, "timestamp": r.timestamp.isoformat(),
        "actor_type": r.actor_type, "actor_id": r.actor_id,
        "action": r.action.value, "subject_uuid": r.subject_uuid,
        "details": r.details_json, "entry_hash": r.entry_hash,
    } for r in rows]


@router.get("/audit/verify")
async def audit_verify(_: Counselor = Depends(require_counselor),
                       db: AsyncSession = Depends(get_db)):
    return await verify_chain(db)


@router.get("/audit/export", response_class=PlainTextResponse)
async def audit_export(_: Counselor = Depends(require_counselor),
                       db: AsyncSession = Depends(get_db)):
    csv_text = await export_audit_csv(db)
    return PlainTextResponse(
        csv_text, media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="okoa_audit.csv"'},
    )


# ------------------------------------------------------- metrics & drills
@router.get("/metrics/sla")
async def sla_metrics(_: Counselor = Depends(require_counselor),
                      db: AsyncSession = Depends(get_db)):
    """Median/percentile time-to-first-response vs the < 2 min PRD KPI."""
    rows = (await db.scalars(
        select(Escalation).where(Escalation.first_response_at.is_not(None))
    )).all()
    deltas = sorted(
        (e.first_response_at - (e.created_at if e.created_at.tzinfo else
                                e.created_at.replace(tzinfo=dt.timezone.utc))).total_seconds()
        for e in rows if e.created_at and e.first_response_at
    )
    open_rows = (await db.scalars(
        select(func.count()).select_from(Escalation)
        .where(Escalation.status.in_([EscalationStatus.open, EscalationStatus.claimed,
                                      EscalationStatus.handed_over]))
    )).one()
    def pct(p: float) -> float | None:
        if not deltas:
            return None
        idx = min(len(deltas) - 1, int(p * (len(deltas) - 1)))
        return round(deltas[idx], 1)
    return {
        "count_with_response": len(deltas),
        "median_seconds": pct(0.5),
        "p90_seconds": pct(0.9),
        "max_seconds": round(max(deltas), 1) if deltas else None,
        "currently_open": int(open_rows or 0),
    }


class DrillRequest(BaseModel):
    scenario: str
    seconds_to_first_response: float
    participants: str | None = None
    notes: str | None = None


@router.post("/drills")
async def record_drill(body: DrillRequest, request: Request,
                       counselor: Counselor = Depends(require_counselor),
                       db: AsyncSession = Depends(get_db)):
    """SOP dry-run record (roadmap 3.5); pass/fail vs configured SLA."""
    sla = getattr(request.app.state, "settings", None)
    threshold = sla.escalation_sla_seconds if sla else 120
    drill = ResponseDrill(
        scenario=body.scenario,
        seconds_to_first_response=body.seconds_to_first_response,
        participants=body.participants,
        passed=body.seconds_to_first_response <= threshold,
        notes=body.notes,
    )
    db.add(drill)
    await audit_append(
        db, action=AuditAction.drill_recorded, actor_type="counselor",
        actor_id=counselor.id,
        details={"scenario": body.scenario,
                 "seconds": body.seconds_to_first_response,
                 "passed": drill.passed},
    )
    await db.commit()
    return {"id": drill.id, "passed": drill.passed}


@router.get("/drills/summary")
async def drill_summary(_: Counselor = Depends(require_counselor),
                        db: AsyncSession = Depends(get_db)):
    """Weekly rollup used for the exit criterion: two consecutive weeks < 2 min median."""
    rows = (await db.scalars(select(ResponseDrill).order_by(ResponseDrill.performed_at))).all()
    by_week: dict[str, list[float]] = {}
    for r in rows:
        wk = r.performed_at.strftime("%G-W%V") if r.performed_at else "?"
        by_week.setdefault(wk, []).append(r.seconds_to_first_response)
    weeks = [{"week": w, "n": len(v), "median_seconds": round(sorted(v)[len(v) // 2], 1)}
             for w, v in sorted(by_week.items())]
    ok = [w for w in weeks if w["median_seconds"] < 120]
    return {"weeks": weeks, "weeks_passing_120s": len(ok)}


# ------------------------------------------------------------- Phase 5 Retention & Mood
@router.get("/users/{user_uuid}/mood-history")
async def get_user_mood_history(
    user_uuid: str,
    limit: int = 14,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve mood history and downward spiral trend analytics for a user."""
    from app.services.mood_service import MoodService

    svc = MoodService()
    history = await svc.get_history(db, user_uuid, limit=limit)
    trend = await svc.analyze_trend(db, user_uuid)
    return {
        "user_uuid": user_uuid,
        "history": [
            {
                "id": m.id,
                "score": m.score,
                "label": m.label,
                "trigger_category": m.trigger_category,
                "raw_selection": m.raw_selection,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in history
        ],
        "trend": {
            "average_recent_score": trend.average_recent_score,
            "is_downward_trend": trend.is_downward_trend,
            "dominant_triggers": trend.dominant_triggers,
            "suggested_action": trend.suggested_action,
        },
    }


@router.get("/users/{user_uuid}/recovery")
async def get_user_recovery(
    user_uuid: str,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve recovery milestones and sobriety streaks for a user."""
    import json
    from app.services.recovery_service import RecoveryService

    svc = RecoveryService()
    tracker = await svc.get_or_create_tracker(db, user_uuid)
    try:
        milestones = json.loads(tracker.milestones_reached_json or "[]")
    except Exception:
        milestones = []
    return {
        "user_uuid": user_uuid,
        "target_habit": tracker.target_habit,
        "current_streak_days": tracker.current_streak_days,
        "longest_streak_days": tracker.longest_streak_days,
        "last_checkin_at": tracker.last_checkin_at.isoformat() if tracker.last_checkin_at else None,
        "milestones_reached": milestones,
    }


@router.get("/analytics/surveys")
async def get_survey_analytics(
    survey_type: str = "craving",
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """Calculate baseline vs latest clinical outcome score deltas across pilot cohort."""
    from app.services.survey_service import SurveyService

    svc = SurveyService()
    deltas = await svc.get_pilot_cohort_deltas(db, survey_type=survey_type)
    return {
        "survey_type": deltas.survey_type,
        "total_users_evaluated": deltas.total_users_evaluated,
        "baseline_avg_score": deltas.baseline_avg_score,
        "latest_avg_score": deltas.latest_avg_score,
        "net_score_delta": deltas.net_score_delta,
        "pct_users_improved": deltas.pct_users_improved,
    }


# ------------------------------------------------------------- on-duty 3.4
class DutyRequest(BaseModel):
    on_duty: bool


@router.post("/me/duty")
async def set_duty(body: DutyRequest,
                   counselor: Counselor = Depends(require_counselor),
                   db: AsyncSession = Depends(get_db)):
    counselor.is_on_duty = body.on_duty
    await db.commit()
    return {"is_on_duty": counselor.is_on_duty}


# ------------------------------------------------------------- Phase 6 Partners (6.1)
class PartnerCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    category: str = Field(..., description="rehab | outpatient | support_group | youth_empowerment | mental_health")
    county: str = Field(..., max_length=64)
    sub_county: str | None = None
    address: str | None = None
    phone: str = Field(..., max_length=64)
    helpline: str | None = None
    email: str | None = None
    website: str | None = None
    services_description: str
    subsidy_status: str = Field("subsidized", description="free | subsidized | nhif_covered | private")
    verified_by: str = "NACADA / OKOA Clinical Advisory"
    operating_hours: str = "Mon-Fri 08:00-17:00"
    is_active: bool = True


class PartnerUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    county: str | None = None
    sub_county: str | None = None
    address: str | None = None
    phone: str | None = None
    helpline: str | None = None
    email: str | None = None
    website: str | None = None
    services_description: str | None = None
    subsidy_status: str | None = None
    verified_by: str | None = None
    operating_hours: str | None = None
    is_active: bool | None = None


@router.get("/partners")
async def list_partners(
    county: str | None = None,
    category: str | None = None,
    subsidy_status: str | None = None,
    is_active: bool | None = True,
    skip: int = 0,
    limit: int = 50,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """List verified partner facilities for resource matching (roadmap 6.1)."""
    from app.services.resource_service import ResourceService

    svc = ResourceService()
    partners = await svc.list_partners(
        db,
        county=county,
        category=category,
        subsidy_status=subsidy_status,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category.value if hasattr(p.category, "value") else str(p.category),
            "county": p.county,
            "sub_county": p.sub_county,
            "address": p.address,
            "phone": p.phone,
            "helpline": p.helpline,
            "email": p.email,
            "website": p.website,
            "services_description": p.services_description,
            "subsidy_status": p.subsidy_status.value if hasattr(p.subsidy_status, "value") else str(p.subsidy_status),
            "verified_by": p.verified_by,
            "operating_hours": p.operating_hours,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in partners
    ]


@router.post("/partners", status_code=status.HTTP_201_CREATED)
async def create_partner(
    body: PartnerCreateRequest,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """Add a new vetted partner to the directory (roadmap 6.1 backfill workflow)."""
    from app.services.resource_service import ResourceService

    svc = ResourceService()
    try:
        partner = await svc.create_partner(db, body.model_dump())
        return {
            "id": partner.id,
            "name": partner.name,
            "category": partner.category.value if hasattr(partner.category, "value") else str(partner.category),
            "county": partner.county,
            "sub_county": partner.sub_county,
            "status": "created",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create partner: {exc}",
        )


@router.get("/partners/{partner_id}")
async def get_partner(
    partner_id: str,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    from app.services.resource_service import ResourceService

    svc = ResourceService()
    p = await svc.get_partner(db, partner_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    return {
        "id": p.id,
        "name": p.name,
        "category": p.category.value if hasattr(p.category, "value") else str(p.category),
        "county": p.county,
        "sub_county": p.sub_county,
        "address": p.address,
        "phone": p.phone,
        "helpline": p.helpline,
        "email": p.email,
        "website": p.website,
        "services_description": p.services_description,
        "subsidy_status": p.subsidy_status.value if hasattr(p.subsidy_status, "value") else str(p.subsidy_status),
        "verified_by": p.verified_by,
        "operating_hours": p.operating_hours,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.put("/partners/{partner_id}")
async def update_partner(
    partner_id: str,
    body: PartnerUpdateRequest,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    from app.services.resource_service import ResourceService

    svc = ResourceService()
    p = await svc.update_partner(db, partner_id, body.model_dump(exclude_unset=True))
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    return {
        "id": p.id,
        "name": p.name,
        "status": "updated",
    }


# ------------------------------------------------------------- Referral Analytics (6.2)
@router.get("/analytics/referrals")
async def get_referral_analytics(
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate referral events for Concept Note KPI tracking (500+ referrals Year 1)."""
    from app.services.resource_service import ResourceService

    svc = ResourceService()
    return await svc.get_referral_metrics(db)


# ------------------------------------------------------------- DPA Compliance Controls (6.3)
@router.get("/users/{user_uuid}/data-summary")
async def get_user_data_summary(
    user_uuid: str,
    language: str = "sw",
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """DPA 2019 Section 26 Subject Access summary view."""
    from app.services.compliance_service import ComplianceService

    svc = ComplianceService()
    summary = await svc.generate_data_summary(db, user_uuid, language=language)
    return {"user_uuid": user_uuid, "summary": summary}


@router.post("/users/{user_uuid}/purge")
async def purge_user_data(
    user_uuid: str,
    request: Request,
    counselor: Counselor = Depends(require_counselor),
    db: AsyncSession = Depends(get_db),
):
    """DPA 2019 Section 40 Data Erasure administrative purge."""
    from app.services.compliance_service import ComplianceService

    svc = ComplianceService()
    session_store = getattr(request.app.state, "sessions", None)
    result = await svc.wipe_user_data(
        db,
        user_uuid=user_uuid,
        session_store=session_store,
        actor="counselor",
        actor_id=counselor.id,
    )
    return result


# ----------------------------------------------------------------- helpers
async def _broadcast(payload: dict) -> None:
    from app.api.ws import hub

    try:
        await hub.broadcast(payload)
    except Exception:  # pragma: no cover
        logger.exception("ws broadcast failed")


def _service_from_request(request: Request):
    """Return the app-wide EscalationService, creating one lazily in test envs."""
    try:
        return request.app.state.escalation
    except AttributeError:
        from app.safety.escalation import EscalationService as _EscalationService
        from app.services.notifications import Notifier
        from app.services.whatsapp_client import WhatsAppClient
        from app.api.ws import hub as _hub

        _wa = WhatsAppClient()
        _notifier = Notifier(wa_client=_wa)
        svc = _EscalationService(notifier=_notifier, hub=_hub)
        request.app.state.escalation = svc
        return svc

