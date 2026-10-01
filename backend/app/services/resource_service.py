"""Resource matching service — Epic 5 & Roadmap 6.1, 6.2.

Provides coarse location-based lookup of vetted Kenyan NGOs, rehabs,
youth empowerment centres, and crisis resources. Enforces strict privacy:
NEVER collects or requires GPS-level PII — operates exclusively at
county/sub-county granularity.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Partner,
    PartnerCategory,
    ReferralEvent,
    SubsidyStatus,
)

logger = logging.getLogger("okoa.resource_service")

# Map of common Kenyan county names / slugs
COUNTY_MAP = {
    "nairobi": "Nairobi",
    "nbi": "Nairobi",
    "mombasa": "Mombasa",
    "msa": "Mombasa",
    "kisumu": "Kisumu",
    "ksm": "Kisumu",
    "nakuru": "Nakuru",
    "nku": "Nakuru",
    "kiambu": "Kiambu",
    "kbu": "Kiambu",
    "uasin gishu": "Uasin Gishu",
    "uasingishu": "Uasin Gishu",
    "eldoret": "Uasin Gishu",
    "eld": "Uasin Gishu",
    "nationwide": "Nationwide",
    "all": "Nationwide",
    "kenya": "Nationwide",
}


def normalize_county(raw: str | None) -> str:
    """Normalize input or interactive ID to a recognized Kenyan county."""
    if not raw:
        return "Nationwide"
    clean = raw.strip().lower()
    if clean.startswith("res_county_"):
        clean = clean.replace("res_county_", "")
    elif clean.startswith("county_"):
        clean = clean.replace("county_", "")
    return COUNTY_MAP.get(clean, clean.capitalize())


class ResourceService:
    """Coordinates partner directory discovery and anonymous referral logging."""

    async def search_partners(
        self,
        db: AsyncSession,
        *,
        county: str | None = None,
        category: str | None = None,
        subsidy_status: str | None = None,
        limit: int = 3,
    ) -> list[Partner]:
        """Retrieve top verified partners matching coarse location and criteria.

        If a county has fewer matches than ``limit``, appends nationwide
        services so that youth are never left without actionable support.
        """
        normalized = normalize_county(county) if county else None

        stmt = select(Partner).where(Partner.is_active == True)  # noqa: E712

        if normalized and normalized != "Nationwide":
            stmt = stmt.where(
                or_(
                    Partner.county.ilike(f"%{normalized}%"),
                    Partner.county == "Nationwide",
                )
            )

        if category:
            stmt = stmt.where(Partner.category == PartnerCategory(category))

        if subsidy_status:
            stmt = stmt.where(Partner.subsidy_status == SubsidyStatus(subsidy_status))

        # Prioritize matching county first, then free/subsidized facilities
        rows = (await db.scalars(stmt)).all()

        def _sort_key(p: Partner) -> tuple[int, int]:
            # 0 if exact county match, 1 if nationwide
            county_priority = 0 if (normalized and normalized.lower() in p.county.lower()) else 1
            # 0 if free, 1 if subsidized/nhif, 2 if private
            sub_priority = 0 if p.subsidy_status == SubsidyStatus.free else 1
            return (county_priority, sub_priority)

        sorted_partners = sorted(rows, key=_sort_key)
        return sorted_partners[:limit]

    async def get_partner(self, db: AsyncSession, partner_id: str) -> Partner | None:
        return await db.get(Partner, partner_id)

    async def list_partners(
        self,
        db: AsyncSession,
        *,
        county: str | None = None,
        category: str | None = None,
        subsidy_status: str | None = None,
        is_active: bool | None = True,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Partner]:
        """Administrative list endpoint for counselors and partner management."""
        stmt = select(Partner)
        if county:
            stmt = stmt.where(Partner.county.ilike(f"%{county}%"))
        if category:
            stmt = stmt.where(Partner.category == PartnerCategory(category))
        if subsidy_status:
            stmt = stmt.where(Partner.subsidy_status == SubsidyStatus(subsidy_status))
        if is_active is not None:
            stmt = stmt.where(Partner.is_active == is_active)

        stmt = stmt.order_by(Partner.county, Partner.name).offset(skip).limit(limit)
        return list((await db.scalars(stmt)).all())

    async def create_partner(self, db: AsyncSession, data: dict[str, Any]) -> Partner:
        cat = PartnerCategory(data["category"])
        sub = SubsidyStatus(data.get("subsidy_status", "subsidized"))
        partner = Partner(
            name=data["name"],
            category=cat,
            county=data["county"],
            sub_county=data.get("sub_county"),
            address=data.get("address"),
            phone=data["phone"],
            helpline=data.get("helpline"),
            email=data.get("email"),
            website=data.get("website"),
            services_description=data["services_description"],
            subsidy_status=sub,
            verified_by=data.get("verified_by", "OKOA Clinical Advisory"),
            operating_hours=data.get("operating_hours", "Mon-Fri 08:00-17:00"),
            is_active=data.get("is_active", True),
        )
        db.add(partner)
        await db.commit()
        await db.refresh(partner)
        return partner

    async def update_partner(self, db: AsyncSession, partner_id: str, data: dict[str, Any]) -> Partner | None:
        partner = await db.get(Partner, partner_id)
        if partner is None:
            return None

        for field in [
            "name", "county", "sub_county", "address", "phone",
            "helpline", "email", "website", "services_description",
            "verified_by", "operating_hours", "is_active"
        ]:
            if field in data and data[field] is not None:
                setattr(partner, field, data[field])

        if "category" in data and data["category"]:
            partner.category = PartnerCategory(data["category"])
        if "subsidy_status" in data and data["subsidy_status"]:
            partner.subsidy_status = SubsidyStatus(data["subsidy_status"])

        partner.updated_at = dt.datetime.now(dt.timezone.utc)
        await db.commit()
        await db.refresh(partner)
        return partner

    async def record_referral(
        self,
        db: AsyncSession,
        *,
        user_uuid: str,
        partner_id: str | None,
        county: str,
        category: str | None = None,
        action: str = "partner_viewed",
        source: str = "whatsapp_interactive",
    ) -> ReferralEvent:
        """Record referral event towards Year 1 KPI (target: 500+ referrals)."""
        event = ReferralEvent(
            user_uuid=user_uuid,
            partner_id=partner_id,
            county=county,
            category=category,
            action=action,
            source=source,
        )
        db.add(event)
        await db.flush()
        logger.info(
            "recorded referral event user=%s partner=%s county=%s action=%s",
            user_uuid, partner_id, county, action
        )
        return event

    async def get_referral_metrics(self, db: AsyncSession) -> dict[str, Any]:
        """Aggregate referral KPIs for counselor dashboard and reporting."""
        total_referrals = await db.scalar(select(func.count(ReferralEvent.id))) or 0

        # Breakdown by county
        county_stmt = (
            select(ReferralEvent.county, func.count(ReferralEvent.id))
            .group_by(ReferralEvent.county)
            .order_by(desc(func.count(ReferralEvent.id)))
        )
        county_counts = {row[0]: row[1] for row in (await db.execute(county_stmt)).all()}

        # Breakdown by action
        action_stmt = (
            select(ReferralEvent.action, func.count(ReferralEvent.id))
            .group_by(ReferralEvent.action)
        )
        action_counts = {row[0]: row[1] for row in (await db.execute(action_stmt)).all()}

        # Target progress: 500+ referrals Year 1 (Concept Note KPI)
        progress_pct = round(min(100.0, (total_referrals / 500.0) * 100.0), 1)

        return {
            "total_referrals": total_referrals,
            "annual_kpi_target": 500,
            "kpi_progress_pct": progress_pct,
            "county_breakdown": county_counts,
            "action_breakdown": action_counts,
        }

    # ------------------------------------------------ WhatsApp formatters
    def build_county_selection_interactive(self, language: str = "sw") -> tuple[str, str, list[dict]]:
        """Construct interactive WhatsApp list for coarse location capture."""
        title_text = {
            "sw": (
                "📍 *Tafuta Kituo / Msaada wa Karibu*\n\n"
                "Chagua kaunti yako hapa chini ili kupata vituo vilivyohakikiwa "
                "(vituo vya kurekebisha tabia, ushauri, au programu za vijana).\n\n"
                "🔒 *Faragha:* Hatuchukui GPS yako kamwe. Mahali unayochagua ni kwa ajili ya orodha pekee."
            ),
            "sheng": (
                "📍 *Cheki Kituo / Msaada Karibu Nawe*\n\n"
                "Chagua county yako hapa chini tuweze kukusort na vituo verified "
                "(rehabs, ushauri nasaha, au youth empowerment hubs).\n\n"
                "🔒 *Privacy:* Hatuchukui GPS yako hata kidogo. Chagua tu eneo lako."
            ),
            "en": (
                "📍 *Find Nearby Centers & Resources*\n\n"
                "Please select your county below to find verified rehabilitation centers, "
                "mental health clinics, and youth empowerment hubs.\n\n"
                "🔒 *Privacy Notice:* We never capture GPS coordinates. Location is used solely to display nearby resources."
            ),
        }.get(language, "📍 *Tafuta Kituo cha Karibu*")

        button_label = {
            "sw": "Chagua Kaunti",
            "sheng": "Select Eneo",
            "en": "Select County",
        }.get(language, "Chagua Kaunti")

        sections = [
            {
                "title": "Major Regions",
                "rows": [
                    {"id": "res_county_nairobi", "title": "Nairobi", "description": "Mathari, Chiromo, Asumbi, Youth Hubs"},
                    {"id": "res_county_mombasa", "title": "Mombasa", "description": "Reachout Old Town, MEWA Kisauni"},
                    {"id": "res_county_kisumu", "title": "Kisumu", "description": "Kisumu Youth Hub, St. Joseph's"},
                    {"id": "res_county_nakuru", "title": "Nakuru", "description": "Olive Tree Rehab, Youth Desk"},
                    {"id": "res_county_kiambu", "title": "Kiambu", "description": "The Retreat Clinic Limuru"},
                    {"id": "res_county_uasingishu", "title": "Uasin Gishu / Eldoret", "description": "MTRH Youth Clinic, Red Cross"},
                    {"id": "res_county_nationwide", "title": "Kitaifa (Nationwide)", "description": "NACADA 1192, Befrienders 1199"},
                ],
            }
        ]
        return title_text, button_label, sections

    def format_whatsapp_directory_response(
        self,
        partners: list[Partner],
        county: str,
        language: str = "sw",
    ) -> str:
        """Format matching partner list into culturally warm, low-data WhatsApp text."""
        if not partners:
            if language == "sheng":
                return (
                    f"Samahani, hatujapata kituo verified moja kwa moja ndani ya {county} kwa sasa. "
                    "Lakini unaweza kupiga simu bure kwa **NACADA Helpline: 1192** au **1199** kupata usaidizi wa haraka."
                )
            elif language == "en":
                return (
                    f"We could not find a verified partner directly in {county} at the moment. "
                    "However, you can reach out toll-free to **NACADA Helpline: 1192** or **1199** for immediate nationwide guidance."
                )
            else:
                return (
                    f"Samahani, hatujapata kituo kilichohakikiwa moja kwa moja ndani ya {county} kwa sasa. "
                    "Lakini unaweza kupiga simu bila malipo kwa **NACADA Helpline: 1192** au **1199** kwa mwongozo wa kitaifa."
                )

        norm_county = normalize_county(county)
        badge_map = {
            SubsidyStatus.free: "BURE / FREE",
            SubsidyStatus.subsidized: "RUZUKU / SUBSIDIZED",
            SubsidyStatus.nhif_covered: "SHA/NHIF INAKUBALIWA",
            SubsidyStatus.private: "KIBINAFSI",
        }

        header = {
            "sw": f"🌿 *Vituo Vilivyohakikiwa Karibu Nawe — {norm_county}*\n",
            "sheng": f"🌿 *Vituo Vimeiva Karibu Nawe — {norm_county}*\n",
            "en": f"🌿 *Verified Support Centers — {norm_county}*\n",
        }.get(language, f"🌿 *Vituo Karibu Nawe — {norm_county}*\n")

        lines = [header]
        for idx, p in enumerate(partners, 1):
            badge = badge_map.get(p.subsidy_status, "SUBSIDIZED")
            sub_c = f" ({p.sub_county})" if p.sub_county else ""
            lines.append(f"*{idx}. {p.name}* [{badge}]")
            lines.append(f"📍 Eneo: {p.county}{sub_c}")
            if p.phone:
                lines.append(f"📞 Simu: {p.phone}")
            if p.helpline and p.helpline != p.phone:
                lines.append(f"☎️ Hotline: {p.helpline}")
            lines.append(f"ℹ️ {p.services_description}")
            if p.operating_hours:
                lines.append(f"🕒 Saa za kazi: {p.operating_hours}")
            lines.append("")

        privacy_notice = {
            "sw": (
                "🔒 *Faragha Yako:* Hakuna jina wala nambari yako iliyoshirikiwa "
                "na kituo hiki. Unaweza kupiga au kutembelea moja kwa moja bila "
                "hofu ya unyanyapaa.\n\n"
                "Dharura ya saa 24: Piga **1199** au **1192** (bure)."
            ),
            "sheng": (
                "🔒 *Privacy Yako:* Hakuna mtu atajua identity yako. Hatushare namba "
                "yako na hawa mapartner. Piga simu ama tembelea centre directly bila stima.\n\n"
                "Emergency ya 24/7: Piga **1199** ama **1192** (free of charge)."
            ),
            "en": (
                "🔒 *Your Privacy:* No personal details or phone numbers have been shared "
                "with these facilities. You may call or visit directly and completely anonymously.\n\n"
                "24/7 Emergency Lines: Call **1199** or **1192** (toll-free)."
            ),
        }.get(language, "🔒 Faragha yako inalindwa 100%. Piga 1199 kwa dharura.")

        lines.append(privacy_notice)
        return "\n".join(lines)
