"""Model analysis → report-form suggestions. Pure keyword mapping (PL + EN).
AI output is a suggestion only — it never changes feature state."""
from dataclasses import dataclass

from app.domain.enums import LABELS_PL, CurrentState, FeatureKey, Severity
from app.domain.model import ImageAnalysis

FEATURE_KEYWORDS: dict[FeatureKey, tuple[str, ...]] = {
    FeatureKey.ESCALATOR: ("escalator", "schody ruchome", "ruchome schody"),
    FeatureKey.ELEVATOR: ("elevator", "lift", "winda", "windy"),
    FeatureKey.STEP_FREE_ENTRANCE: ("stairs", "steps", "step", "schody", "stopnie", "stopień"),
    FeatureKey.RAMP: ("ramp", "podjazd"),
    FeatureKey.ACCESSIBLE_TOILET: ("toilet", "wc", "toaleta"),
    FeatureKey.INDUCTION_LOOP: ("induction", "pętla"),
    FeatureKey.BRAILLE: ("braille", "brajl"),
    FeatureKey.TACTILE_PATHS: ("tactile", "ścieżk"),
    FeatureKey.LOWERED_CURB: ("curb", "kerb", "krawęż"),
    FeatureKey.GOOD_LIGHTING: ("poorly lit", "dark", "lighting", "ciemn", "oświetl"),
    FeatureKey.ASSISTANCE_DOG_ALLOWED: ("guide dog", "assistance dog", "pies", "psa"),
}
EXTRA_TAGS: dict[str, tuple[str, ...]] = {
    "awaria": ("out of order", "broken", "not working", "nieczynn", "awari", "zepsut", "damaged"),
    "tablica informacyjna": ("notice", "sign", "kartk", "tablic"),
}


MOBILITY_WORDS = ("wheelchair", "mobility", "physical", "wózek", "ruch")  # blocks movement → critical


@dataclass(slots=True)
class Tag:
    label: str
    feature: FeatureKey | None
    confidence: float


@dataclass(slots=True)
class Suggested:
    element: FeatureKey
    current_state: CurrentState
    severity: Severity


@dataclass(slots=True)
class Suggestion:
    tags: list[Tag]
    suggested: Suggested | None


def _features_in(text: str) -> list[FeatureKey]:
    """Features in order of first appearance in text."""
    text = text.lower()
    found = []
    for feature, words in FEATURE_KEYWORDS.items():
        positions = [text.find(w) for w in words if w in text]
        if positions:
            found.append((min(positions), feature))
    return [f for _, f in sorted(found)]


def suggest(a: ImageAnalysis) -> Suggestion:
    features: list[FeatureKey] = []
    for f in _features_in(a.barrier_type) + _features_in(a.description):
        if f not in features:
            features.append(f)
    text = f"{a.barrier_type} {a.description}".lower()
    tags = [Tag(LABELS_PL[f].lower(), f, a.confidence) for f in features]
    tags += [Tag(label, None, a.confidence) for label, words in EXTRA_TAGS.items() if any(w in text for w in words)]

    suggested = None
    if a.barrier_detected and features:
        affected = " ".join(a.affected_disabilities).lower()
        critical = any(word in affected for word in MOBILITY_WORDS)
        severity = Severity.CRITICAL if critical else Severity.OBSTACLE
        suggested = Suggested(features[0], CurrentState.NOT_WORKING, severity)
    return Suggestion(tags, suggested)
