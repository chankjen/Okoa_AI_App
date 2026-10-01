"""Language auto-detection service (roadmap 4.6).

Detects Sheng / Swahili / English per inbound message to allow matching reply
language while preserving casual register and cultural warmth.

Kenyan linguistic context:
- English (en): standard or Kenyan English phrasing.
- Swahili (sw): formal or standard East-African Swahili grammar and vocabulary.
- Sheng (sheng): Nairobi urban vernacular mixing Swahili structure, English
  loanwords, and rapidly evolving local youth slang/idioms.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Curated linguistic markers for Kenyan communication
SHENG_MARKERS = {
    "buda", "manze", "maze", "msee", "wasee", "mbogi", "risto", "fiti", "poa",
    "ngumu", "rada", "form", "chapaa", "doo", "janta", "ndo", "ka", "solo",
    "naskia", "inauma", "kuhepa", "bonga", "sherehe", "sherehez", "kulemba",
    "mresh", "beshte", "dwanzi", "kikao", "keja", "mtaa", "nduthi", "mat",
    "chali", "morio", "kuisha", "noma", "fala", "kuteseka", "kushow",
}

SWAHILI_MARKERS = {
    "habari", "jambo", "asante", "shukrani", "tafadhali", "huzuni", "maumivu",
    "msongo", "mawazo", "maisha", "upweke", "hofu", "moyo", "usingizi", "kwa",
    "nini", "kwanini", "nina", "nime", "nita", "sita", "siwezi", "naomba",
    "kusaidia", "msaada", "dharura", "hali", "akili", "familia", "ndugu",
    "dada", "kaka", "mama", "baba", "rafiki", "kesho", "jana", "leo",
    "ndiyo", "hapana", "salama", "shida", "tabu", "vizuri", "pole", "sana",
}

ENGLISH_MARKERS = {
    "hello", "hi", "hey", "help", "please", "thank", "thanks", "anxious",
    "anxiety", "depressed", "depression", "stress", "stressed", "overwhelmed",
    "feeling", "feel", "crying", "lonely", "hopeless", "worthless", "pain",
    "tired", "sleep", "cannot", "cant", "suicide", "counselor", "doctor",
    "family", "work", "money", "struggling", "struggle", "today", "tonight",
    "myself", "life", "good", "bad", "need", "someone", "talk", "listen",
}

_WORD_RE = re.compile(r"[a-zA-Z']+")


@dataclass
class LanguageDetectionResult:
    language: str              # 'sheng' | 'sw' | 'en'
    confidence: float          # 0.0 .. 1.0
    features: dict[str, int]   # hit counts per language category


def detect_language(text: str, default: str = "sw") -> LanguageDetectionResult:
    """Detect whether a message is in Sheng, Swahili, or English.

    Uses normalized token overlap with priority weighting:
    - Sheng markers carry highest distinctive weight because Sheng borrows
      from Swahili/English but contains distinct slang markers.
    - Pure Swahili takes precedence when standard Swahili morphological cues dominate.
    - English takes precedence when English vocabulary dominates.
    """
    if not text or not text.strip():
        return LanguageDetectionResult(language=default, confidence=1.0, features={})

    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return LanguageDetectionResult(language=default, confidence=1.0, features={})

    sheng_hits = sum(1 for w in words if w in SHENG_MARKERS)
    swahili_hits = sum(1 for w in words if w in SWAHILI_MARKERS)
    english_hits = sum(1 for w in words if w in ENGLISH_MARKERS)

    features = {
        "sheng_hits": sheng_hits,
        "swahili_hits": swahili_hits,
        "english_hits": english_hits,
        "total_words": len(words),
    }

    # Distinct Sheng markers immediately flag Sheng register
    if sheng_hits > 0 and sheng_hits >= swahili_hits * 0.4:
        total_scored = max(1, sheng_hits + swahili_hits + english_hits)
        confidence = round(min(1.0, 0.6 + 0.4 * (sheng_hits / total_scored)), 2)
        return LanguageDetectionResult("sheng", confidence, features)

    if swahili_hits > english_hits:
        total_scored = max(1, swahili_hits + english_hits)
        confidence = round(min(1.0, 0.5 + 0.5 * (swahili_hits / total_scored)), 2)
        return LanguageDetectionResult("sw", confidence, features)

    if english_hits > swahili_hits:
        total_scored = max(1, english_hits + swahili_hits)
        confidence = round(min(1.0, 0.5 + 0.5 * (english_hits / total_scored)), 2)
        return LanguageDetectionResult("en", confidence, features)

    # Tie-break or short greeting: default to Swahili (primary national language)
    return LanguageDetectionResult(default, 0.5, features)
