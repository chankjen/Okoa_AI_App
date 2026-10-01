"""Seed script for OKOA AI CBT coping strategies (roadmap 4.5).

Seeds the database with vetted evidence-based CBT exercises in Swahili, Sheng,
and English.

Usage:
    python -m scripts.seed_cbt
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.db.models import CbtStrategy
from app.db.session import dispose_engine, get_session_factory, init_models
from app.services.rag_service import BUILTIN_CBT_STRATEGIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("okoa.seed_cbt")


async def seed_cbt() -> None:
    logger.info("Initializing database models...")
    await init_models()

    factory = get_session_factory()
    async with factory() as db:
        inserted = 0
        for item in BUILTIN_CBT_STRATEGIES:
            existing = await db.scalar(
                select(CbtStrategy).where(
                    CbtStrategy.title == item["title"],
                    CbtStrategy.language == item["language"],
                )
            )
            if existing is None:
                strat = CbtStrategy(
                    id=str(uuid.uuid4()),
                    category=item["category"],
                    language=item["language"],
                    title=item["title"],
                    summary=item["summary"],
                    instructions=item["instructions"],
                    keywords=item.get("keywords", ""),
                    is_active=True,
                )
                db.add(strat)
                inserted += 1

        await db.commit()
        logger.info("Seeded %d new CBT coping strategies into database.", inserted)

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed_cbt())
