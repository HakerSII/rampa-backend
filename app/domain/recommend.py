"""F30 recommendations. Pure.
interpret_rules: query → Intent (needs + filters only, PL + EN keywords).
rank: places + DB states → items with reasons (facts from DB) and missing data. Nothing is guessed."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.check import PROFILE_RULES, check_place
from app.domain.city import DEFAULT_CITY_FILE, City, load_city
from app.domain.enums import CheckAnswer, FeatureKey as F, NeedsProfile as P, StateValue
from app.domain.geo import haversine_m
from app.domain.model import FeatureStateRecord, GeoPoint, Place
from app.domain.verification import STALE_DAYS

MAX_QUERY = 500

_DEFAULT: City | None = None


def default_city() -> City:
    """Kraków file, loaded once (tests and code paths without an explicit city)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_city(DEFAULT_CITY_FILE)
    return _DEFAULT


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
    (F.BABY_CHANGING_TABLE, ("przewij", "changing table")),
    (F.STROLLER_SPACE, ("miejsce na wózek", "miejscem na wózek", "stroller parking", "stroller space")),
    (F.LUGGAGE_STORAGE, ("bagaż", "bagaz", "walizk", "luggage")),
    (F.REST_AREAS, ("odpocz", "ławk", "lawk", "usiąść", "rest area", "bench")),
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


def interpret_rules(query: str, city: City | None = None) -> Intent:
    city = city or default_city()
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
    categories = [key for key, g in city.category_groups.items() if any(w in q for w in g.words)]
    area = next((key for key, a in city.areas.items() if any(w in q for w in a.words)), None)
    return Intent(profiles, features, categories, area)


def _valid(enum_cls, values) -> list:
    out = []
    for v in values or []:
        try:
            out.append(enum_cls(v))
        except ValueError:
            continue  # model answered outside the schema → drop
    return list(dict.fromkeys(out))


FILTER_TOOL = "set_filters"
FILTER_TOOL_DESCRIPTION = "Accessibility needs and place filters extracted from the user's query."
FILTER_SYSTEM_PROMPT = (
    "You convert a user's request for an accessible place in {city} into search filters by calling "
    "set_filters. Only list needs and features the user actually mentioned. Do not answer the question, "
    "do not describe places. The query may be Polish or English.")


def filters_schema(city: City) -> dict:
    """JSON schema of the filter tool — ONE definition for every LLM provider (Claude, Gemini).
    Kept to the subset both accept: no union types, `area` optional instead of nullable."""
    return {
        "type": "object",
        "properties": {
            "profiles": {"type": "array", "items": {"type": "string", "enum": [p.value for p in P]},
                         "description": "needs of the visitor (wheelchair, stroller = baby stroller, …)"},
            "features": {"type": "array", "items": {"type": "string", "enum": [f.value for f in F]},
                         "description": "extra place features explicitly requested (toilet, pets, parking …)"},
            "categories": {"type": "array", "items": {"type": "string", "enum": list(city.category_groups)}},
            "area": {"type": "string", "enum": list(city.areas), "description": "only if a named area is mentioned"},
        },
        "required": ["profiles", "features", "categories"],
    }


def intent_from_filters(data: dict, city: City) -> Intent:
    """Model tool-call arguments → Intent; anything outside the schema / city is dropped."""
    area = data.get("area")
    return Intent(_valid(P, data.get("profiles")), _valid(F, data.get("features")),
                  [c for c in dict.fromkeys(data.get("categories") or []) if c in city.category_groups],
                  area if area in city.areas else None)


_SCORE = {CheckAnswer.YES: 2, CheckAnswer.PARTIAL: 1, CheckAnswer.UNKNOWN: 0, CheckAnswer.NO: -3}
_FEATURE_SCORE = {StateValue.YES: 2, StateValue.PARTIAL: 1, StateValue.UNKNOWN: 0, StateValue.NO: -3,
                  StateValue.NOT_APPLICABLE: 0}


def evaluate(place_id: str, states: dict[F, FeatureStateRecord], profiles: list[P],
             features: list[F]) -> tuple[str, int, list[CheckAnswer]]:
    """match (yes | partial | unknown | no) + score for a place, from DB states only."""
    full = {f: states.get(f) or FeatureStateRecord(place_id, f, StateValue.UNKNOWN) for f in F}
    answers = [check_place(place_id, full, p).answer for p in profiles]
    feature_states = [full[f].state for f in features if full[f].state != StateValue.NOT_APPLICABLE]
    parts = [str(a) for a in answers] + [str(s) for s in feature_states]
    match = ("no" if "no" in parts else "unknown" if not parts or all(p == "unknown" for p in parts)
             else "yes" if all(p == "yes" for p in parts) else "partial")
    score = sum(_SCORE[a] for a in answers) + sum(_FEATURE_SCORE[s] for s in feature_states)
    return match, score, answers


def in_categories(place: Place, groups: list[str], city: City) -> bool:
    return not groups or any(place.category in (city.category_groups[g].categories if g in city.category_groups
                                                else (g,)) for g in groups)


def rank(places: list[tuple[Place, dict[F, FeatureStateRecord], dict[str, str]]], intent: Intent,
         origin: GeoPoint | None, now: datetime, limit: int, city: City | None = None) -> list[Recommendation]:
    """places: (place, states, source per active observation id)."""
    city = city or default_city()
    area = city.areas.get(intent.area or "")
    centre, radius = (area.center, area.radius_m) if area else (None, None)
    here = origin or centre
    stale = now - timedelta(days=STALE_DAYS)
    items = []
    for place, states, sources in places:
        if not in_categories(place, intent.categories, city):
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
