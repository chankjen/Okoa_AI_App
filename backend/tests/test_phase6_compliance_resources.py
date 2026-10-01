"""Phase 6 test suite — Resource Matching & Compliance Hardening (Roadmap 6.1 - 6.3)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import (
    AuditAction,
    AuditLogEntry,
    ChatSession,
    IdentityVaultRow,
    Message,
    MicroSurveyResponse,
    MoodEntry,
    Partner,
    PartnerCategory,
    RecoveryTracker,
    ReferralEvent,
    SubsidyStatus,
    User,
)
from app.db.seeds.seed_data import seed_partners_force, seed_partners_if_empty
from app.services.compliance_service import ComplianceService
from app.services.pipeline import InboundEvent
from app.services.resource_service import ResourceService, normalize_county
from tests.conftest import sign_body, wa_message_payload

TEST_PHONE = "254712345678"


async def _login(client) -> str:
    """Helper to authenticate a counselor and get token."""
    from app.auth.counselor_auth import hash_password
    from app.db.models import Counselor

    async with client.pipeline.session_factory() as db:
        c = Counselor(
            id="counselor-phase6-test",
            username="counselor_p6",
            password_hash=hash_password("Pass123!"),
            display_name="Dr. Ochieng P6",
            is_active=True,
        )
        db.add(c)
        await db.commit()

    resp = await client.post(
        "/counselor/login",
        json={"username": "counselor_p6", "password": "Pass123!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def _post_webhook(
    client,
    text: str,
    msg_id: str | None = None,
    interactive_id: str | None = None,
    interactive_type: str | None = None,
    phone: str = TEST_PHONE,
):
    """Post webhook payload and wait for pipeline worker to drain."""
    import asyncio

    body = wa_message_payload(phone, text, msg_id)
    headers = {"X-Hub-Signature-256": sign_body(body), "Content-Type": "application/json"}

    # If interactive, construct InboundEvent directly and process
    if interactive_id:
        evt = InboundEvent(
            wa_user_id=phone,
            text=text,
            wa_message_id=msg_id or "wamid.interactive.test",
            interactive_id=interactive_id,
            interactive_type=interactive_type or "list_reply",
        )
        await client.pipeline.handle(evt)
        return

    resp = await client.post("/webhooks/whatsapp", content=body, headers=headers)
    await client.pipeline.queue.join() if hasattr(client.pipeline.queue, "join") else None
    for _ in range(50):
        if client.pipeline.queue.empty():
            await asyncio.sleep(0.02)
            break
        await asyncio.sleep(0.02)
    return resp


# ---------------------------------------------------------------------------
# 6.1 Verified Partner Directory Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_seed_partners_directory(client):
    """Verify seed_partners_force loads vetted Kenyan partners."""
    async with client.pipeline.session_factory() as db:
        count = await seed_partners_force(db)
        assert count >= 10

        # Mathari Hospital (Nairobi)
        mathari = await db.get(Partner, "partner-nbi-mathari-001")
        assert mathari is not None
        assert mathari.county == "Nairobi"
        assert mathari.subsidy_status == SubsidyStatus.free

        # Reachout Centre Trust (Mombasa)
        reachout = await db.get(Partner, "partner-msa-reachout-005")
        assert reachout is not None
        assert reachout.county == "Mombasa"
        assert reachout.category == PartnerCategory.rehab

        # NACADA Helpline (Nationwide)
        nacada = await db.get(Partner, "partner-nat-nacada-013")
        assert nacada is not None
        assert nacada.county == "Nationwide"


@pytest.mark.asyncio
async def test_counselor_partner_crud_api(client):
    """Verify counselor endpoints for listing, adding, and updating partners."""
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create a new partner (backfill workflow)
    new_partner_payload = {
        "name": "Eldoret Hope Centre",
        "category": "rehab",
        "county": "Uasin Gishu",
        "sub_county": "Kapseret",
        "address": "Airport Road, Eldoret",
        "phone": "+254711998877",
        "helpline": "+254722998877",
        "services_description": "Holistic recovery, CBT, and youth relapse prevention.",
        "subsidy_status": "subsidized",
        "verified_by": "NACADA",
    }
    create_resp = await client.post("/counselor/partners", json=new_partner_payload, headers=headers)
    assert create_resp.status_code == 201
    created_id = create_resp.json()["id"]

    # 2. Get the partner
    get_resp = await client.get(f"/counselor/partners/{created_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Eldoret Hope Centre"
    assert get_resp.json()["county"] == "Uasin Gishu"

    # 3. List partners with filtering
    list_resp = await client.get("/counselor/partners?county=Uasin+Gishu", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(p["id"] == created_id for p in items)

    # 4. Update the partner
    update_resp = await client.put(
        f"/counselor/partners/{created_id}",
        json={"services_description": "Updated outpatient and inpatient recovery."},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "updated"


# ---------------------------------------------------------------------------
# 6.2 Geo-Matching & Referral Flow Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resource_service_search_and_fallback(client):
    """Verify search_partners returns county matches and appends nationwide resources."""
    async with client.pipeline.session_factory() as db:
        await seed_partners_force(db)
        svc = ResourceService()

        # Search Nairobi
        nbi_results = await svc.search_partners(db, county="Nairobi", limit=3)
        assert len(nbi_results) == 3
        assert any(p.county == "Nairobi" for p in nbi_results)

        # Search a county with few/no specific entries -> should fallback to Nationwide
        fallback_results = await svc.search_partners(db, county="Turkana", limit=3)
        assert len(fallback_results) > 0
        assert any(p.county == "Nationwide" for p in fallback_results)


@pytest.mark.asyncio
async def test_whatsapp_interactive_county_selection(client):
    """User selects county via WhatsApp interactive list -> top partners & referral recorded."""
    async with client.pipeline.session_factory() as db:
        await seed_partners_force(db)

    # Complete consent first
    await _post_webhook(client, "AGREE")

    # Send interactive selection: Mombasa
    await _post_webhook(client, "Mombasa County", interactive_id="res_county_mombasa")

    # Verify WhatsApp sent directory response
    sent_msgs = [body for _, body in client.pipeline.wa.sent]
    assert any("Mombasa" in m and "Reachout" in m for m in sent_msgs)
    assert any("Faragha Yako" in m or "Privacy" in m for m in sent_msgs)

    # Verify ReferralEvent recorded in DB
    async with client.pipeline.session_factory() as db:
        referrals = (await db.scalars(select(ReferralEvent))).all()
        assert len(referrals) > 0
        assert any(r.county == "Mombasa" and r.action == "partner_viewed" for r in referrals)


@pytest.mark.asyncio
async def test_rehab_keyword_triggers_county_list(client):
    """User sends 'rehab' -> system presents county selection interactive list."""
    await _post_webhook(client, "AGREE")
    await _post_webhook(client, "Nahitaji kituo cha rehab")

    # Verify interactive list was queued/sent
    assert len(client.pipeline.wa.interactive_sent) > 0
    last_interactive = client.pipeline.wa.interactive_sent[-1]
    assert last_interactive["type"] == "list"
    assert "Tafuta Kituo" in last_interactive["body"] or "Nearby" in last_interactive["body"]

    # Verify referral directory_search recorded
    async with client.pipeline.session_factory() as db:
        ref = await db.scalar(
            select(ReferralEvent).where(ReferralEvent.action == "directory_search").limit(1)
        )
        assert ref is not None


@pytest.mark.asyncio
async def test_partner_detail_selection(client):
    """User selects specific partner -> sends contact details and logs contact_requested."""
    async with client.pipeline.session_factory() as db:
        await seed_partners_force(db)

    await _post_webhook(client, "AGREE")
    await _post_webhook(
        client, "Details please", interactive_id="res_partner_partner-nbi-mathari-001"
    )

    sent_msgs = [body for _, body in client.pipeline.wa.sent]
    assert any("Mathari" in m and "+254202337694" in m for m in sent_msgs)

    async with client.pipeline.session_factory() as db:
        ref = await db.scalar(
            select(ReferralEvent).where(ReferralEvent.action == "contact_requested").limit(1)
        )
        assert ref is not None
        assert ref.partner_id == "partner-nbi-mathari-001"


@pytest.mark.asyncio
async def test_referral_analytics_kpi_progress(client):
    """Verify referral metrics API tracks progress towards 500+ referrals KPI."""
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    async with client.pipeline.session_factory() as db:
        svc = ResourceService()
        await svc.record_referral(
            db, user_uuid="test-uuid-1", partner_id="p-1", county="Nairobi", action="partner_viewed"
        )
        await svc.record_referral(
            db, user_uuid="test-uuid-2", partner_id="p-2", county="Mombasa", action="contact_requested"
        )
        await db.commit()

    resp = await client.get("/counselor/analytics/referrals", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_referrals"] >= 2
    assert data["annual_kpi_target"] == 500
    assert "county_breakdown" in data
    assert "action_breakdown" in data


# ---------------------------------------------------------------------------
# 6.3 Self-Service Data Controls (Kenya DPA 2019)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_data_summary_command(client):
    """User types 'maelezo' -> receives Kenya DPA 2019 Section 26 data summary."""
    await _post_webhook(client, "AGREE")
    await _post_webhook(client, "Niko poa leo")
    await _post_webhook(client, "maelezo")

    sent_msgs = [body for _, body in client.pipeline.wa.sent]
    summary_msg = sent_msgs[-1]
    assert "Maelezo ya Data Yako" in summary_msg or "Ripoti ya Data Yako" in summary_msg or "Data Summary" in summary_msg
    assert "Zero PII" in summary_msg or "Faragha" in summary_msg
    assert "FUTA DATA YANGU" in summary_msg


@pytest.mark.asyncio
async def test_futa_data_yangu_full_wipe(client):
    """User types 'futa data yangu' -> complete hard delete across all DB tables and tombstone vault."""
    # 1. Enrol user, accept consent, generate messages, mood entries, recovery tracker
    await _post_webhook(client, "AGREE")
    await _post_webhook(client, "mood_great", interactive_id="mood_great")
    await _post_webhook(client, "clean today")

    async with client.pipeline.session_factory() as db:
        user_row = await db.scalar(select(User).limit(1))
        assert user_row is not None
        user_uuid = user_row.user_uuid

        # Verify records exist before wipe
        sessions = (await db.scalars(select(ChatSession).where(ChatSession.user_uuid == user_uuid))).all()
        assert len(sessions) > 0
        moods = (await db.scalars(select(MoodEntry).where(MoodEntry.user_uuid == user_uuid))).all()
        assert len(moods) > 0
        tracker = await db.get(RecoveryTracker, user_uuid)
        assert tracker is not None

        vault_row = await db.scalar(
            select(IdentityVaultRow).where(IdentityVaultRow.user_uuid == user_uuid)
        )
        assert vault_row is not None
        assert vault_row.status == "active"
        assert len(vault_row.ciphertext) > 0

    # 2. Trigger the DPA Section 40 hard wipe command
    await _post_webhook(client, "Futa data yangu")

    # 3. Verify confirmation message was sent
    sent_msgs = [body for _, body in client.pipeline.wa.sent]
    last_msg = sent_msgs[-1]
    assert "Data Yako Yote Imefutwa Kabisa" in last_msg or "Erased" in last_msg

    # 4. Verify hard delete in database
    async with client.pipeline.session_factory() as db:
        # All messages deleted
        msgs = (await db.scalars(select(Message))).all()
        assert len(msgs) == 0

        # All sessions deleted
        sessions_after = (await db.scalars(select(ChatSession))).all()
        assert len(sessions_after) == 0

        # All mood entries deleted
        moods_after = (await db.scalars(select(MoodEntry))).all()
        assert len(moods_after) == 0

        # Recovery tracker deleted
        tracker_after = await db.get(RecoveryTracker, user_uuid)
        assert tracker_after is None

        # User marked purged
        user_after = await db.get(User, user_uuid)
        assert user_after.data_purged is True
        assert user_after.opt_out is True

        # Vault row tombstoned & ciphertext wiped
        vault_after = await db.scalar(
            select(IdentityVaultRow).where(IdentityVaultRow.user_uuid == user_uuid)
        )
        assert vault_after.status == "tombstoned"
        assert vault_after.ciphertext == b""
        assert vault_after.purged_at is not None

        # Chained audit log entry recorded
        audit_entry = await db.scalar(
            select(AuditLogEntry).where(AuditLogEntry.action == AuditAction.user_data_wiped).limit(1)
        )
        assert audit_entry is not None
        assert audit_entry.subject_uuid == user_uuid


@pytest.mark.asyncio
async def test_counselor_dpa_administrative_purge(client):
    """Counselor invokes /counselor/users/{uuid}/purge -> executes DPA Section 40 wipe."""
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    await _post_webhook(client, "AGREE")
    async with client.pipeline.session_factory() as db:
        user_row = await db.scalar(select(User).limit(1))
        user_uuid = user_row.user_uuid

    # Purge via counselor API
    resp = await client.post(f"/counselor/users/{user_uuid}/purge", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "purged"

    # Verify vault tombstone
    async with client.pipeline.session_factory() as db:
        v = await db.scalar(select(IdentityVaultRow).where(IdentityVaultRow.user_uuid == user_uuid))
        assert v.status == "tombstoned"
        assert v.ciphertext == b""
