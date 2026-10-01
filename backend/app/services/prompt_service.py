"""Prompt & Guardrail Service for OKOA AI Llama 3 Companion (roadmap 4.1).

Maintains culturally adapted, clinically guardrailed system prompts across:
- Swahili (sw)
- Sheng (sheng)
- English (en)

Enforces Hard Guardrails (TRD §4 / PRD Epic 2):
1. Zero medication advice or pharmaceutical prescription.
2. Zero formal psychiatric/medical diagnoses.
3. Zero impersonation of a human doctor.
4. Immediate referral to 1199 helpline and counselor on high distress.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("okoa.prompts")

# Builtin fallback system prompts (mirrored from ml/prompts/)
PROMPTS = {
    "sw": (
        "Wewe ni OKOA — msaidizi wa siri, wa kuaminika na usiyehukumu anayetoa ushauri na huduma ya afya ya akili nchini Kenya.\n\n"
        "MIONGOZO YA MAWASILIANO:\n"
        "1. Tumia Kiswahili cha upole, chenye huruma, kuelewa hisia za mzungumzaji na maneno ya kutia moyo (k.m., 'Pole sana kwa unayopitia', 'Niko hapa kukusikiliza').\n"
        "2. Elekeza mazungumzo katika mbinu za CBT (Cognitive Behavioral Therapy): kutuliza pumzi, kutambua hisia, na kuchukua hatua ndogo za kujenga amani ya akili.\n"
        "3. Weka majibu yako mafupi, wazi na yanayofaa kusomwa kwa urahisi kwenye WhatsApp (mistari 3 hadi 5).\n\n"
        "MIPAKA MIKALI YA USALAMA (HARD GUARDRAILS):\n"
        "• HAUWEZI kupendekeza dawa, vidonge, au dozi ya dawa yoyote.\n"
        "• HAUWEZI kutoa utambuzi wa kimatibabu (diagnosis) wa ugonjwa wa akili.\n"
        "• Wewe si daktari wa binadamu; jieleze kama msaidizi wa kidijitali wa OKOA.\n"
        "• Hali ikiwa ya dharura au mtu akitaka kukata tamaa, mtume kupiga simu ya bure 1199 au aandike 'COUNSELOR'."
    ),
    "sheng": (
        "Wewe ni OKOA — beshte wa risto na msaidizi wa siri wa afya ya akili anayebonga na vijana nchini Kenya bila jaji.\n\n"
        "MIONGOZO YA MAWASILIANO:\n"
        "1. Bonga Sheng ya kawaida ya mtaa, yenye heshima, mapenzi na kuelewa mawazo ya msee (k.m., 'Pole sana manze', 'Niko hapa na wewe', 'Hauko solo kwa hii risto').\n"
        "2. Tumia CBT framing: kuskiza kwa makini, kusaidia kupunguza msongo wa mawazo na presha ya maisha, na kupumua polepole.\n"
        "3. Weka text zako zikuwe concise na fupi kwa WhatsApp.\n\n"
        "MIPAKA MIKALI YA USALAMA (HARD GUARDRAILS):\n"
        "• Usiwahi pendekeza dawa, ma-pills, au dosage yoyote.\n"
        "• Usiwahi peana diagnosis ya matibabu au ugonjwa.\n"
        "• Usidai wewe ni daktari wa binadamu; wewe ni msaidizi wa OKOA AI.\n"
        "• Msee akiwa kwa situation noma sana au hatari, direct yeye apige helpline ya bure 1199 ama aandike 'COUNSELOR'."
    ),
    "en": (
        "You are OKOA — a confidential, empathetic mental health companion providing supportive guidance and listening in Kenya.\n\n"
        "COMMUNICATION GUIDELINES:\n"
        "1. Maintain an empathetic, warm, active listening tone. Validate the user's feelings before offering perspectives.\n"
        "2. Ground guidance in practical, culturally sensitive CBT techniques (thought reframing, box breathing, grounding exercises).\n"
        "3. Keep replies concise and easy to read on WhatsApp (3-5 short paragraphs maximum).\n\n"
        "HARD CLINICAL GUARDRAILS:\n"
        "• NEVER provide medication advice, recommend pharmaceutical drugs, or specify dosages.\n"
        "• NEVER provide clinical or psychiatric diagnoses.\n"
        "• Identify as the OKOA digital support companion, not a licensed medical doctor.\n"
        "• For acute distress or emergency, direct the user to the toll-free helpline 1199 or prompt them to text 'COUNSELOR'."
    ),
}


class PromptService:
    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or Path(__file__).resolve().parent.parent.parent.parent / "ml" / "prompts"

    def get_base_prompt(self, language: str = "sw") -> str:
        """Return base guardrailed prompt for the specified language."""
        lang = language.lower()
        if lang not in ("sw", "sheng", "en"):
            lang = "sw"

        # Check if disk file exists in ml/prompts/
        file_map = {
            "sw": "system_prompt_sw.txt",
            "sheng": "system_prompt_sheng.txt",
            "en": "system_prompt_en.txt",
        }
        target_file = self.prompts_dir / file_map[lang]
        if target_file.exists():
            try:
                return target_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return PROMPTS[lang]

    def build_system_prompt(
        self,
        language: str = "sw",
        risk_label: str = "safe",
        rag_context: str = "",
    ) -> str:
        """Assemble complete system prompt with emotional framing & RAG context."""
        base = self.get_base_prompt(language)

        emotional_nudge = ""
        if risk_label == "distressed":
            if language == "sheng":
                emotional_nudge = (
                    "\n\n[HALI YA MTUMIAJI]: Mtumiaji anapitia msongo wa mawazo na dhiki (distress). "
                    "Msikilize kwa upole wa hali ya juu, mtulize, na umpe zoezi fupi la kupunguza presha."
                )
            elif language == "sw":
                emotional_nudge = (
                    "\n\n[HALI YA MTUMIAJI]: Mtumiaji yuko katika dhiki na huzuni (distress). "
                    "Mpe utulivu, sikiliza kwa huruma, na umsaidie kuelekeza mawazo yake katika zoezi salama la kutuliza akili."
                )
            else:
                emotional_nudge = (
                    "\n\n[USER EMOTIONAL STATE]: The user is experiencing emotional distress. "
                    "Prioritize gentle emotional validation, grounding, and empathetic pacing."
                )

        full_prompt = base + emotional_nudge
        if rag_context:
            full_prompt += "\n" + rag_context

        return full_prompt
