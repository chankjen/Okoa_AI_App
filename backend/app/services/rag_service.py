"""RAG context layer for vetted CBT coping strategies (roadmap 4.5).

Provides clinical grounding for Llama 3 prompt generation:
- Retrieves vetted evidence-based CBT exercises (box breathing, grounding, thought reframing)
- Matches strategies based on detected distress categories and language (sw, sheng, en)
- Zero PII: only static clinical techniques are stored and injected
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CbtStrategy

logger = logging.getLogger("okoa.rag")

# Seed library of vetted clinical CBT techniques tailored for Kenya
BUILTIN_CBT_STRATEGIES: list[dict] = [
    {
        "category": "anxiety",
        "language": "sw",
        "title": "Mbinu ya Pumzi ya Sanduku (Box Breathing)",
        "summary": "Zoezi la kupunguza mapigo ya moyo na msongo wa mawazo wa haraka.",
        "instructions": (
            "1. Vuta pumzi polepole kupitia pua ukihesabu hadi 4.\n"
            "2. Shika pumzi hiyo kwa sekunde 4.\n"
            "3. Toa pumzi taratibu kupitia mdomo kwa sekunde 4.\n"
            "4. Tulia bila kuvuta pumzi kwa sekunde 4. Rudia mara 3 au 4."
        ),
        "keywords": "anxiety,wasiwasi,msongo,hofu,mapigo,pumzi,kutetemeka",
    },
    {
        "category": "anxiety",
        "language": "sheng",
        "title": "Kutuliza Mwili na Pumzi (Sheng Box Breathing)",
        "summary": "Mbinu poa ya kurelax mwili ikianza kusikia pressure na panic.",
        "instructions": (
            "1. Vuta hewa ndaani polepole kupitia pua ukicount 1 hadi 4.\n"
            "2. Hold hiyo pumzi kwa sekunde 4 bila haraka.\n"
            "3. Toa hewa yote nje polepole kupitia mdomo kwa sekunde 4.\n"
            "4. Relax sekunde 4 kabla ya kuvuta tena. Fanya mara 3 utaskia mwili inatulia."
        ),
        "keywords": "anxiety,panic,pressure,stress,noma,buda,manze,mwili",
    },
    {
        "category": "anxiety",
        "language": "en",
        "title": "Box Breathing Technique",
        "summary": "4-4-4-4 regulated breathing cycle to reset the nervous system.",
        "instructions": (
            "1. Inhale slowly through your nose for 4 counts.\n"
            "2. Hold your breath gently for 4 counts.\n"
            "3. Exhale completely through your mouth for 4 counts.\n"
            "4. Pause calmly for 4 counts before your next inhale. Repeat 3-4 times."
        ),
        "keywords": "anxiety,stress,panic,racing thoughts,breathe,heart rate",
    },
    {
        "category": "panic",
        "language": "sw",
        "title": "Mbinu ya Kutuliza Hisia 5-4-3-2-1 (Grounding)",
        "summary": "Kutumia milango ya fahamu kuleta akili katika wakati uliopo.",
        "instructions": (
            "Angalia mazingira yako na utambue:\n"
            "• Vitu 5 unavyoweza kuona,\n"
            "• Vitu 4 unavyoweza kugusa,\n"
            "• Vitu 3 unavyoweza kusikia,\n"
            "• Vitu 2 unavyoweza kunusa,\n"
            "• Kitu 1 chanya unachojua kuhusu wewe mwenyewe leo."
        ),
        "keywords": "panic,kushikwa na hofu,hofu kali,kutetemeka,grounding,fahamu",
    },
    {
        "category": "panic",
        "language": "sheng",
        "title": "Grounding ya Milango ya Fahamu 5-4-3-2-1",
        "summary": "Kutoa akili kwa mawazo mazito na kuirudisha kwa hali ya sasa.",
        "instructions": (
            "Cheki mtaa ama keja mahali uko sasa hivi utambue:\n"
            "• Vitu 5 unaona kwa macho,\n"
            "• Vitu 4 unaeza gusa na vidole,\n"
            "• Sauti 3 unaskia kwa maskio,\n"
            "• Vitu 2 unaeza nusa,\n"
            "• Kitu 1 kizuri unajivunia leo. Inasaidia akili kusimama."
        ),
        "keywords": "panic,grounding,msongo,akilini,kushikwa,fahamu,keja",
    },
    {
        "category": "panic",
        "language": "en",
        "title": "5-4-3-2-1 Sensory Grounding",
        "summary": "Sensory reconnect technique to interrupt panic and disassociation.",
        "instructions": (
            "Notice and name around you:\n"
            "• 5 things you can see,\n"
            "• 4 things you can physically touch,\n"
            "• 3 distinct sounds you hear,\n"
            "• 2 things you can smell,\n"
            "• 1 encouraging truth about yourself right now."
        ),
        "keywords": "panic,grounding,panic attack,dizzy,breathless,sensory",
    },
    {
        "category": "depression",
        "language": "sw",
        "title": "Kupunguza Mawazo Hasi (Cognitive Reframing)",
        "summary": "Kutambua kwamba hisia si ukweli na kupima fikira zako kwa uthibitisho.",
        "instructions": (
            "1. Tambua wazo linalokuletea huzuni (k.m., 'Siwezi chochote').\n"
            "2. Jiulize: Je, kuna ushahidi kamili kwamba hili ni kweli kwa asilimia mia moja?\n"
            "3. Badilisha wazo hilo kwa mtazamo wenye huruma (k.m., 'Ninapitia wakati mgumu sasa, lakini nimepitia mengine na ninaendelea kujaribu')."
        ),
        "keywords": "depression,huzuni,kutojali,kuchoka,sifai,upweke,kulia",
    },
    {
        "category": "depression",
        "language": "sheng",
        "title": "Kuvunja Mawazo ya Kujidharau (Reframing)",
        "summary": "Kuepuka kujipiga msasa na kuongea na nafsi yako kama mshkaji.",
        "instructions": (
            "1. Notisi lile wazo mbaya linalokushusha chini (k.m., 'Mimi ni fala siwezi make it').\n"
            "2. Jiulize: Kama beshte yako angekua anapitia hii kitu, je ungemwambia hivyo?\n"
            "3. Punguza makali na ujiongelee kwa heshima: 'Hii season ni ngumu lakini si mwisho wa safari yangu'."
        ),
        "keywords": "depression,kujidharau,huzuni,upweke,sifai,stress,manze",
    },
    {
        "category": "depression",
        "language": "en",
        "title": "Thought Reframing (CBT Cognitive Restructuring)",
        "summary": "Challenging negative automatic thoughts with realistic compassionate evidence.",
        "instructions": (
            "1. Identify the harsh internal statement (e.g., 'I ruin everything').\n"
            "2. Ask: What would I say to a friend who felt this way?\n"
            "3. Reframe into a compassionate, balanced thought: 'I am struggling right now, but a difficult moment does not define my worth.'"
        ),
        "keywords": "depression,hopeless,sadness,worthless,crying,alone,empty",
    },
    {
        "category": "insomnia",
        "language": "sw",
        "title": "Utulivu wa Akili Kabla ya Usingizi (Mental De-escalation)",
        "summary": "Mbinu ya kutoa mawazo kichwani kabla ya kulala.",
        "instructions": (
            "1. Andika kwenye karatasi au simu mawazo yote yanayokusumbua ili akili ijue hayajasahaulika.\n"
            "2. Weka kifaa mbali na kitanda.\n"
            "3. Funga macho na uzingatie pumzi polepole huku ukilegeza misuli ya mabega na taya."
        ),
        "keywords": "insomnia,usingizi,kukosa usingizi,usiku,mawazo mengi",
    },
    {
        "category": "insomnia",
        "language": "en",
        "title": "Sleep Wind-down & Thought Parking",
        "summary": "Technique to release racing thoughts and prepare the body for rest.",
        "instructions": (
            "1. Do a 'worry dump' on paper: write down racing concerns so your mind knows they are preserved for tomorrow.\n"
            "2. Keep screens away from your immediate bed area.\n"
            "3. Progressively release muscle tension in your shoulders, jaw, and brow as you take long, slow exhalations."
        ),
        "keywords": "insomnia,sleep,cannot sleep,awake,night,bedtime,rest",
    },
]


class RagService:
    """Service to retrieve clinically vetted CBT strategies for Llama 3 context injection."""

    def __init__(self):
        pass

    async def retrieve(
        self,
        db: AsyncSession | None,
        query_text: str,
        language: str = "sw",
        limit: int = 1,
    ) -> list[dict]:
        """Find the most clinically relevant coping strategies.

        Queries the database if available; falls back seamlessly to the builtin
        clinical library if the database table is empty or unseeded.
        """
        norm_query = query_text.lower()
        norm_lang = language.lower()
        if norm_lang not in ("sw", "sheng", "en"):
            norm_lang = "sw"

        # 1. Try DB query if db session provided
        if db is not None:
            try:
                stmt = select(CbtStrategy).where(
                    CbtStrategy.is_active.is_(True),
                    CbtStrategy.language == norm_lang,
                )
                db_rows = (await db.scalars(stmt)).all()
                if db_rows:
                    scored = []
                    for row in db_rows:
                        score = self._score_relevance(row.keywords, row.category, norm_query)
                        scored.append((score, {
                            "title": row.title,
                            "category": row.category,
                            "summary": row.summary,
                            "instructions": row.instructions,
                            "language": row.language,
                        }))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    return [item[1] for item in scored[:limit]]
            except Exception:
                logger.debug("DB CBT retrieval skipped/failed, using builtin library")

        # 2. Match from builtin library
        matches = [s for s in BUILTIN_CBT_STRATEGIES if s["language"] == norm_lang]
        if not matches:
            matches = [s for s in BUILTIN_CBT_STRATEGIES if s["language"] == "sw"]

        scored = []
        for item in matches:
            score = self._score_relevance(item.get("keywords", ""), item.get("category", ""), norm_query)
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def _score_relevance(self, keywords: str, category: str, query: str) -> int:
        score = 0
        words = query.split()
        kw_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        for kw in kw_list:
            if kw in query:
                score += 3
        if category.lower() in query:
            score += 5
        for w in words:
            if len(w) > 3 and w in kw_list:
                score += 2
        return score

    def format_context_block(self, strategies: Sequence[dict]) -> str:
        """Format retrieved strategies into an injection block for Llama 3 context."""
        if not strategies:
            return ""

        blocks = []
        for s in strategies:
            blocks.append(
                f"[VETTED CBT COPING TECHNIQUE: {s['title']}]\n"
                f"Summary: {s['summary']}\n"
                f"Instructions:\n{s['instructions']}"
            )
        return "\n\n" + "\n\n".join(blocks) + "\n\n(Guide the user gently using this technique if appropriate. Do NOT diagnose or prescribe.)"
