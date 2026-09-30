"""Phase 3 test suite — Counselor dashboard, auth, queue, handover & audit integrity."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from app.auth.counselor_auth import hash_password
from app.db.models import Counselor, Escalation, EscalationStatus, RiskLabel, User
from app.main import app


@pytest.mark.asyncio
async def test_counselor_login_and_auth_guard(db_session_factory):
    async with db_session_factory() as db:
        c = Counselor(
            username="test_counselor",
            password_hash=hash_password("Pass123!"),
            display_name="Dr. Test",
            is_on_duty=True,
            is_active=True,
        )
        db.add(c)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid login
        bad_res = await client.post("/counselor/login", json={"username": "test_counselor", "password": "wrong"})
        assert bad_res.status_code == 401

        # 2. Valid login
        res = await client.post("/counselor/login", json={"username": "test_counselor", "password": "Pass123!"})
        assert res.status_code == 200
        token = res.json()["access_token"]
        assert token

        # 3. Access guarded route without token → 401
        unauth = await client.get("/counselor/escalations")
        assert unauth.status_code == 401

        # 4. Access guarded route with token → paginated queue envelope
        auth_res = await client.get(
            "/counselor/escalations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert auth_res.status_code == 200
        body = auth_res.json()
        # Endpoint returns {"queue": [...], "open_count": N}
        assert isinstance(body, dict)
        assert "queue" in body
        assert "open_count" in body
        assert isinstance(body["queue"], list)


@pytest.mark.asyncio
async def test_counselor_claim_and_handover(db_session_factory):
    user_uuid = "test-user-uuid-1234"
    esc_id = "test-esc-uuid-1234"
    async with db_session_factory() as db:
        c = Counselor(
            username="claim_counselor",
            password_hash=hash_password("Pass123!"),
            display_name="Dr. Claimer",
            is_on_duty=True,
            is_active=True,
        )
        u = User(user_uuid=user_uuid)
        e = Escalation(
            id=esc_id,
            user_uuid=user_uuid,
            session_id="test-session-123",
            risk_score=95.0,
            risk_label=RiskLabel.crisis,
            status=EscalationStatus.open,
        )
        db.add_all([c, u, e])
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login
        login_res = await client.post(
            "/counselor/login",
            json={"username": "claim_counselor", "password": "Pass123!"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Claim escalation
        claim_res = await client.post(
            f"/counselor/escalations/{esc_id}/claim",
            headers=headers,
        )
        assert claim_res.status_code == 200
        assert claim_res.json()["status"] == "claimed"

        # Toggle handover to counselor_active
        # Route: POST /counselor/escalations/{escalation_id}/handover
        handover_res = await client.post(
            f"/counselor/escalations/{esc_id}/handover",
            headers=headers,
            json={"mode": "counselor_active"},
        )
        assert handover_res.status_code == 200
        assert handover_res.json()["mode"] == "counselor_active"

        # Verify audit chain
        audit_res = await client.get("/counselor/audit/verify", headers=headers)
        assert audit_res.status_code == 200
        assert audit_res.json()["valid"] is True
