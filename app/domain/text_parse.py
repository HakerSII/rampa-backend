"""Free-text description → suggested observations (rules, PL + EN, offline). Pure.
A suggestion only: it pre-fills the report form, it never changes data."""
import re
from dataclasses import dataclass

from app.domain.enums import FeatureKey as F, ObservationValue

# inflected Polish stems (pętli, windy, psy …); explicit forms where a stem would over-match
ESCALATOR_WORDS = ("schody ruchome", "ruchome schody", "escalator")
TEXT_KEYWORDS: dict[F, tuple[str, ...]] = {
    F.ESCALATOR: ESCALATOR_WORDS,
    F.ELEVATOR: ("winda", "windy", "windzie", "windą", "windę", "elevator", "lift"),
    F.RAMP: ("podjazd", "ramp"),
    F.ACCESSIBLE_TOILET: ("toalet", "wc", "toilet"),
    F.INDUCTION_LOOP: ("pętl", "induction"),
    F.BRAILLE: ("braille", "brajl"),
    F.TACTILE_PATHS: ("ścieżk", "tactile"),
    F.LOWERED_CURB: ("krawęż", "curb", "kerb"),
    F.GOOD_LIGHTING: ("oświetl", "ciemn", "lighting", "dark"),
    F.PLATFORM_ELEVATOR: ("peron", "platform"),
    F.SIGN_LANGUAGE_INTERPRETER: ("pjm", "tłumacz", "sign language"),
    F.ASSISTANCE_DOG_ALLOWED: ("pies", "psa", "psy", "psem", "guide dog", "assistance dog"),
}
STAIRS = ("schod", "stopni", "stopień", "stairs", "steps")
STEP_FREE = ("bez schod", "step-free", "step free", "level entrance", "z poziomu")

NEGATIVE = ("nie działa", "nie dziala", "nieczynn", "zepsut", "brak", "zablokow", "zastawion", "awari", "remont",
            "niedostępn", "nie jest", "nie ma", "zakaz", "nie wolno", "nie można", "nie wpuszcz", "słab", "ciemn",
            "not working", "broken", "out of order", "blocked", "not allowed", "dark", "poorly")
POSITIVE = ("działa", "naprawion", "jest", "dostępn", "odśnieżon", "wpuszcza", "wolno", "można", "jasno",
            "works", "working", "repaired", "available", "allowed")
TEMPORARY = re.compile(r"\bod\b|tymczasow|chwilow|remont|dziś|dzisiaj|zastawion|temporar|\btoday\b")
CLAUSES = re.compile(r"[.,;!?]|\b(?:ale|lecz|but)\b")
EXPLICIT, IMPLIED = 0.8, 0.6


@dataclass(slots=True)
class TextSuggestion:
    feature: F
    value: ObservationValue
    temporary: bool
    confidence: float


def _polarity(clause: str) -> ObservationValue | None:
    if any(w in clause for w in NEGATIVE) or re.search(r"\bno\b", clause):
        return ObservationValue.NO
    if any(w in clause for w in POSITIVE):
        return ObservationValue.YES
    return None


def parse_text(text: str) -> list[TextSuggestion]:
    found: dict[F, TextSuggestion] = {}
    for clause in CLAUSES.split(text.lower()):
        clause = clause.strip()
        if not clause:
            continue
        temporary = bool(TEMPORARY.search(clause))
        polarity = _polarity(clause)
        if any(p in clause for p in STEP_FREE):
            found.setdefault(F.STEP_FREE_ENTRANCE,
                             TextSuggestion(F.STEP_FREE_ENTRANCE, ObservationValue.YES, temporary, EXPLICIT))
        elif any(w in clause for w in STAIRS) and not any(e in clause for e in ESCALATOR_WORDS):
            found.setdefault(F.STEP_FREE_ENTRANCE,
                             TextSuggestion(F.STEP_FREE_ENTRANCE, ObservationValue.NO, temporary, IMPLIED))
        if polarity is None:
            continue
        for feature, words in TEXT_KEYWORDS.items():
            if any(w in clause for w in words):
                found.setdefault(feature, TextSuggestion(feature, polarity, temporary, EXPLICIT))
    return list(found.values())
