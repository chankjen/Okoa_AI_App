"""Seed database with vetted Kenyan partners (roadmap 6.1)."""
from __future__ import annotations

import json
from pathlib import Path
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Partner, PartnerCategory, SubsidyStatus

logger = logging.getLogger("okoa.seed")

SEEDS_DIR = Path(__file__).resolve().parent
PARTNERS_JSON = SEEDS_DIR / "partners.json"


async def seed_partners_if_empty(db: AsyncSession) -> int:
    """Insert vetted partners if the table has no active records.

    Returns the count of partners added.
    """
    existing_count = await db.scalar(select(Partner.id).limit(1))
    if existing_count is not None:
        return 0

    return await seed_partners_force(db)


async def seed_partners_force(db: AsyncSession) -> int:
    """Read partners.json and insert or update partner records."""
    if not PARTNERS_JSON.exists():
        logger.warning("partners.json not found at %s", PARTNERS_JSON)
        return 0

    with open(PARTNERS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    inserted = 0
    for item in data:
        partner_id = item["id"]
        existing = await db.get(Partner, partner_id)
        cat = PartnerCategory(item["category"])
        sub = SubsidyStatus(item.get("subsidy_status", "subsidized"))

        if existing is None:
            partner = Partner(
                id=partner_id,
                name=item["name"],
                category=cat,
                county=item["county"],
                sub_county=item.get("sub_county"),
                address=item.get("address"),
                phone=item["phone"],
                helpline=item.get("helpline"),
                email=item.get("email"),
                website=item.get("website"),
                services_description=item["services_description"],
                subsidy_status=sub,
                verified_by=item.get("verified_by", "NACADA / OKOA Clinical Advisory"),
                operating_hours=item.get("operating_hours", "Mon-Fri 08:00-17:00"),
                is_active=True,
            )
            db.add(partner)
            inserted += 1
        else:
            existing.name = item["name"]
            existing.category = cat
            existing.county = item["county"]
            existing.sub_county = item.get("sub_county")
            existing.address = item.get("address")
            existing.phone = item["phone"]
            existing.helpline = item.get("helpline")
            existing.email = item.get("email")
            existing.website = item.get("website")
            existing.services_description = item["services_description"]
            existing.subsidy_status = sub
            existing.verified_by = item.get("verified_by", existing.verified_by)
            existing.operating_hours = item.get("operating_hours", existing.operating_hours)

    await db.commit()
    logger.info("seeded %d partners into database", inserted)
    return inserted
