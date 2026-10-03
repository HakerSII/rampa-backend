"""F30 recommendations. Pure.
interpret_rules: query → Intent (needs + filters only, PL + EN keywords).
rank: places + DB states → items with reasons (facts from DB) and missing data. Nothing is guessed."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.check import PROFILE_RULES, check_place
from app.domain.enums import CheckAnswer, FeatureKey as F, NeedsProfile as P, StateValue
from app.domain.geo import haversine_m
from app.domain.model import FeatureStateRecord, GeoPoint, Place
from app.domain.verification import STALE_DAYS

MAX_QUERY = 500

# category group → place categories (seed + OSM) — F37 moves this to city config
CATEGORY_GROUPS: dict[str, tuple[str, ...]] = {
    "gastronomy": ("cafe", "restaurant", "fast_food", "bar", "pub", "food_court", "ice_cream"),
    "culture": ("museum", "culture", "theatre", "cinema", "arts_centre", "gallery", "attraction", "library"),
    "services": ("office", "townhall", "post_office", "bank", "pharmacy", "hairdresser", "clinic", "hospital"),
    "shopping": ("shop", "supermarket", "mall", "marketplace", "convenience"),
}
CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "gastronomy": ("restaurac", "kawiar", "knajp", "jedzen", "obiad", "gastronom", "restaurant", "cafe", "coffee",
                   "kawa", "kawę", "bar "),
    "culture": ("muze", "teatr", "kino", "kina", "kultur", "galeri", "museum", "theatre", "cinema", "zabyt"),
    "services": ("urząd", "urzęd", "urzad", "poczt", "bank", "aptek", "fryzjer", "office", "pharmacy"),
    "shopping": ("sklep", "zakup", "market", "galeria handlowa", "shop", "store"),
}
# named areas — F37 moves this to city config
AREAS: dict[str, tuple[GeoPoint, int, tuple[str, ...]]] = {
    "centrum": (GeoPoint(50.0617, 19.9373), 1500, ("centrum", "rynek", "stare miasto", "starym mieście", "center",
                                                    "centre", "old town")),
    "kazimierz": (GeoPoint(50.0513, 19.9454), 800, ("kazimierz",)),
}
STROLLER_WORDS = ("stroller", "pram", "pushchair", "z dzieckiem")
STROLLER_PHRASE = re.compile(r"w[óo]z\w*\s+(?:dla\s+)?dzie\w*")
CRUTCHES = re.compile(r"kul(?:e|ach|ami|i)|crutch")
ASSIST = re.compile(r"(?:pies|psem|psa)\s+(?:asystuj\w*|przewodnik\w*)|(?:guide|assistance) dog")
PET_APART = re.compile(r"(?:pies|psem|psa)|pets?|dog|zwierz")
PROFILE_WORDS: list[tuple[P, tuple[str, ...]]] = [
    (P.WHEELCHAIR, ("wózk", "wozk", "wheelchair")),
    (P.STROLLER, STROLLER_WORDS),
    (P.CRUTCHES, ()),  # regex CRUTCHES
    (P.BLIND, ("niewidom", "blind")),
    (P.LOW_VISION, ("słabo widz", "slabo widz", "słabowidz", "niedowid", "low vision")),
    (P.DEAF, ("głuch", "gluch", "niesłysz", "nieslysz", "deaf", "hard of hearing")),
    (P.ASSISTANCE_DOG, ("asystując", "asystujac", "przewodnik", "guide dog", "assistance dog")),
]
FEATURE_WORDS: list[tuple[F, tuple[str, ...]]] = [
    (F.ACCESSIBLE_TOILET, ("toalet", "wc", "łazienk", "toilet")),
    (F.ELEVATOR, ("winda", "windą", "windy", "elevator", "lift")),
    (F.INDUCTION_LOOP, ("pętl", "induction")),
    (F.DISABLED_PARKING, ("parking", "zaparkow")),
    (F.SIGN_LANGUAGE_INTERPRETER, ("pjm", "język migowy", "sign language")),
    (F.PETS_ALLOWED, (" pies", " psem", " psa", "zwierz", " dog", " pet")),
]


@dataclass(slots=True)
class Intent:
    profiles: list[P] = field(default_factory=list)
    features: list[F] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    area: str | None = None

    @property
    def empty(self) -> bool:
        return not (self.profiles or self.features or self.categories or self.area)


@dataclass(slots=True)
class Reason:
    feature: F
    state: StateValue
    source: str | None
    last_verified: datetime | None


@dataclass(slots=True)
class Recommendation:
    place: Place
    match: str  # yes | partial | unknown | no
    score: int
    distance_m: int | None
    reasons: list[Reason]
    missing: list[F]


def interpret_rules(query: str) -> Intent:
    q = f" {query.lower()} "
    rest = STROLLER_PHRASE.sub(" ", q)  # "wózek dziecięcy" = stroller; wheelchair only if mentioned apart from it
    profiles = []
    for profile, words in PROFILE_WORDS:
        text = rest if profile == P.WHEELCHAIR else q
        if profile == P.CRUTCHES:
            hit = bool(CRUTCHES.search(q))  # "kultura" ≠ crutches
        else:
            hit = any(w in text for w in words) or (profile == P.STROLLER and STROLLER_PHRASE.search(q) is not None)
        if hit:
            profiles.append(profile)
    features = [f for f, words in FEATURE_WORDS if any(w in q for w in words)]
    if P.ASSISTANCE_DOG in profiles and F.PETS_ALLOWED in features and not PET_APART.search(ASSIST.sub(" ", q)):
        features.remove(F.PETS_ALLOWED)  # "pies asystujący" is the profile, not a pet
    categories = [c for c, words in CATEGORY_WORDS.items() if any(w in q for w in words)]
    area = next((name for name, (_, _, words) in AREAS.items() if any(w in q for w in words)), None)
    return Intent(profiles, features, categories, area)


_SCORE = {CheckAnswer.YES: 2, CheckAnswer.PARTIAL: 1, CheckAnswer.UNKNOWN: 0, CheckAnswer.NO: -3}
_FEATURE_SCORE = {StateValue.YES: 2, StateValue.PARTIAL: 1, StateValue.UNKNOWN: 0, StateValue.NO: -3}


def evaluate(place_id: str, states: dict[F, FeatureStateRecord], profiles: list[P],
             features: list[F]) -> tuple[str, int, list[CheckAnswer]]:
    """match (yes | partial | unknown | no) + score for a place, from DB states only."""
    full = {f: states.get(f) or FeatureStateRecord(place_id, f, StateValue.UNKNOWN) for f in F}
    answers = [check_place(place_id, full, p).answer for p in profiles]
    feature_states = [full[f].state for f in features]
    parts = [str(a) for a in answers] + [str(s) for s in feature_states]
    match = ("no" if "no" in parts else "unknown" if not parts or all(p == "unknown" for p in parts)
             else "yes" if all(p == "yes" for p in parts) else "partial")
    score = sum(_SCORE[a] for a in answers) + sum(_FEATURE_SCORE[s] for s in feature_states)
    return match, score, answers


def in_categories(place: Place, groups: list[str]) -> bool:
    return not groups or any(place.category in CATEGORY_GROUPS.get(g, (g,)) for g in groups)


def rank(places: list[tuple[Place, dict[F, FeatureStateRecord], dict[str, str]]], intent: Intent,
         origin: GeoPoint | None, now: datetime, limit: int) -> list[Recommendation]:
    """places: (place, states, source per active observation id)."""
    centre, radius = (AREAS[intent.area][0], AREAS[intent.area][1]) if intent.area in AREAS else (None, None)
    here = origin or centre
    stale = now - timedelta(days=STALE_DAYS)
    items = []
    for place, states, sources in places:
        if not in_categories(place, intent.categories):
            continue
        if centre and haversine_m(place.location, centre) > radius:
            continue
        get = lambda f: states.get(f) or FeatureStateRecord(place.id, f, StateValue.UNKNOWN)  # noqa: E731
        match, score, answers = evaluate(place.id, states, intent.profiles, intent.features)
        relevant = []
        for profile in intent.profiles:
            rule = PROFILE_RULES[profile]
            relevant += list(rule.required) + list(rule.downgrades)
        relevant += intent.features
        relevant = list(dict.fromkeys(relevant))
        reasons = [Reason(f, s.state, sources.get(s.active_observation_id or ""), s.last_verified)
                   for f in relevant if (s := get(f)).state != StateValue.UNKNOWN]
        missing = [f for f in intent.features if get(f).state == StateValue.UNKNOWN]
        for profile, answer in zip(intent.profiles, answers):
            if answer == CheckAnswer.UNKNOWN:
                missing += [f for f in PROFILE_RULES[profile].required if f not in missing]
        missing += [r.feature for r in reasons if r.last_verified and r.last_verified < stale
                    and r.feature not in missing]
        distance = round(haversine_m(place.location, here)) if here else None
        items.append(Recommendation(place, match, score, distance, reasons, missing))
    items.sort(key=lambda r: (r.match == "no", -r.score, r.distance_m if r.distance_m is not None else 0,
                              r.place.name))
    return items[:limit]
