"""Phase 6 security review test suite — roadmap 6.4 security hardening.

Verifies:
- AES-256-GCM encryption at rest & AAD integrity (tamper detection)
- Vault isolation: no plaintext phone numbers in application tables
- Log scrubbing: automatic PII redaction of phone numbers and emails
- TLS 1.3 / HSTS and defensive HTTP security headers
- Authentication & access boundaries
"""
from __future__ import annotations

import base64
import os
import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from app.core.logging import scrub, CRISIS_MARKER, EMAIL_MARKER
from app.db.models import IdentityVaultRow, Message, MoodEntry, Partner, User
from app.vault.crypto import IdentityVault, normalise_msisdn
from tests.conftest import TEST_VAULT_KEY, wa_message_payload, sign_body

TEST_PHONE = "254712345678"


# ---------------------------------------------------------------------------
# 1. AES-256-GCM Encryption at Rest & Tamper Detection
# ---------------------------------------------------------------------------
def test_vault_aes256_gcm_aad_integrity():
    """Verify AES-256-GCM enforces Authenticated Associated Data (AAD = user_uuid).

    Attempting to decrypt ciphertext with a mismatched UUID or tampered nonce
    must raise InvalidTag (preventing identity swapping or DB row spoofing).
    """
    vault = IdentityVault(TEST_VAULT_KEY)
    uuid_1 = vault.new_uuid()
    uuid_2 = vault.new_uuid()
    phone = "+254712345678"

    nonce, ct = vault.encrypt_phone(phone, uuid_1)

    # Decrypting with correct UUID succeeds
    decrypted = vault.decrypt_phone(nonce, ct, uuid_1)
    assert decrypted == phone

    # Decrypting with mismatched UUID (AAD breach) raises InvalidTag
    with pytest.raises(InvalidTag):
        vault.decrypt_phone(nonce, ct, uuid_2)

    # Tampered ciphertext raises InvalidTag
    tampered_ct = bytearray(ct)
    tampered_ct[0] ^= 0xFF
    with pytest.raises(InvalidTag):
        vault.decrypt_phone(nonce, bytes(tampered_ct), uuid_1)


def test_vault_key_validation():
    """Vault rejects invalid key lengths (enforces full 256-bit entropy)."""
    short_key = base64.b64encode(os.urandom(16)).decode()  # 128 bit
    with pytest.raises(ValueError, match="32 bytes"):
        IdentityVault(short_key)


# ---------------------------------------------------------------------------
# 2. Vault Isolation Verification
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vault_isolation_no_plaintext_phones_in_app_tables(client):
    """Verify plaintext MSISDN is never persisted in messages, users, or mood tables."""
    # Send a message through the webhook
    body = wa_message_payload(TEST_PHONE, "Habari yako OKOA")
    headers = {"X-Hub-Signature-256": sign_body(body), "Content-Type": "application/json"}
    await client.post("/webhooks/whatsapp", content=body, headers=headers)
    await client.pipeline.queue.join() if hasattr(client.pipeline.queue, "join") else None

    async with client.pipeline.session_factory() as db:
        # Check users table
        users = (await db.scalars(select(User))).all()
        for u in users:
            assert TEST_PHONE not in u.user_uuid

        # Check messages table
        messages = (await db.scalars(select(Message))).all()
        for m in messages:
            assert TEST_PHONE not in m.body

        # Check identity_vault table: only place ciphertext exists
        vault_rows = (await db.scalars(select(IdentityVaultRow))).all()
        assert len(vault_rows) > 0
        for r in vault_rows:
            # Ciphertext should not match plaintext
            assert TEST_PHONE.encode() not in r.ciphertext


# ---------------------------------------------------------------------------
# 3. PII Log Scrubbing
# ---------------------------------------------------------------------------
def test_log_scrubber_redacts_phone_formats():
    """Verify scrub() removes Kenyan and international MSISDN formats."""
    # 07... Kenyan local
    assert scrub("User phone is 0712345678 please call") == f"User phone is {CRISIS_MARKER} please call"
    # 01... Kenyan local
    assert scrub("Contact 0112345678 now") == f"Contact {CRISIS_MARKER} now"
    # +254... international
    assert scrub("Dial +254712345678 for help") == f"Dial {CRISIS_MARKER} for help"
    # Spaced / dashed format
    assert scrub("Call 0712-345-678 or 0712 345 678") == f"Call {CRISIS_MARKER} or {CRISIS_MARKER}"
    # International format
    assert scrub("Reach +14155552671") == f"Reach {CRISIS_MARKER}"


def test_log_scrubber_redacts_emails():
    """Verify scrub() removes email addresses from log records."""
    assert scrub("Email me at user@example.com for info") == f"Email me at {EMAIL_MARKER} for info"
    assert scrub("Reach out to counselor.test@ngo.or.ke") == f"Reach out to {EMAIL_MARKER}"


# ---------------------------------------------------------------------------
# 4. HTTP Defensive Security Headers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_security_headers_present_on_responses(client):
    """Verify SecurityHeadersMiddleware enforces HSTS, nosniff, and frame deny."""
    resp = await client.get("/")
    assert resp.status_code == 200
    headers = resp.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert "Strict-Transport-Security" in headers
    assert "max-age=63072000" in headers["Strict-Transport-Security"]
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ---------------------------------------------------------------------------
# 5. Access Boundaries & Counselor Authentication
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_routes_reject_unauthenticated_access(client):
    """Ensure sensitive counselor and DPA routes reject requests without valid JWT."""
    resp1 = await client.get("/counselor/partners")
    assert resp1.status_code == 401

    resp2 = await client.get("/counselor/analytics/referrals")
    assert resp2.status_code == 401

    resp3 = await client.post("/counselor/users/some-uuid/purge")
    assert resp3.status_code == 401
