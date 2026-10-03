"""Domain enums. Values are a subset of the full contract (sourcedoc/openapi.yaml)."""
from enum import StrEnum


class FeatureKey(StrEnum):
    STEP_FREE_ENTRANCE = "step_free_entrance"
    RAMP = "ramp"
    ELEVATOR = "elevator"
    ACCESSIBLE_TOILET = "accessible_toilet"
    INDUCTION_LOOP = "induction_loop"
    BRAILLE = "braille"
    TACTILE_PATHS = "tactile_paths"
    GOOD_LIGHTING = "good_lighting"
    LOWERED_CURB = "lowered_curb"
    PLATFORM_ELEVATOR = "platform_elevator"
    CRUTCHES_FRIENDLY = "crutches_friendly"
    SIGN_LANGUAGE_INTERPRETER = "sign_language_interpreter"
    ASSISTANCE_DOG_ALLOWED = "assistance_dog_allowed"


class FeatureGroupKey(StrEnum):
    ENTRANCE = "entrance"
    INSIDE = "inside"
    TOILET = "toilet"
    HEARING = "hearing"
    VISION = "vision"
    MOBILITY = "mobility"
    OTHER = "other"


class StateValue(StrEnum):
    YES = "yes"
    PARTIAL = "partial"
    NO = "no"
    UNKNOWN = "unknown"


class ObservationValue(StrEnum):
    YES = "yes"
    PARTIAL = "partial"
    NO = "no"


class ObservationSource(StrEnum):
    COMMUNITY = "community"
    OPEN_DATA = "open_data"
    VERIFIED_OWNER = "verified_owner"
    ADMIN = "admin"


class ValidationStatus(StrEnum):
    VALID = "VALID"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    FLAGGED = "FLAGGED"  # abuse / spam, set by a moderator


class NeedsProfile(StrEnum):
    WHEELCHAIR = "wheelchair"
    CRUTCHES = "crutches"
    STROLLER = "stroller"
    BLIND = "blind"
    LOW_VISION = "low_vision"
    DEAF = "deaf"
    ASSISTANCE_DOG = "assistance_dog"


class CheckAnswer(StrEnum):
    YES = "yes"
    PARTIAL = "partial"
    NO = "no"
    UNKNOWN = "unknown"


class Role(StrEnum):
    GUEST = "guest"
    USER = "user"
    OWNER = "owner"
    ADMIN = "admin"


class CurrentState(StrEnum):
    WORKS = "works"
    PARTIALLY_WORKS = "partially_works"
    NOT_WORKING = "not_working"


class PlaceType(StrEnum):
    VENUE = "venue"
    SHOP = "shop"
    PUBLIC_TRANSPORT_STOP = "public_transport_stop"
    PLATFORM = "platform"
    PARKING = "parking"
    OFFICE = "office"
    STREET_SEGMENT = "street_segment"
    OTHER = "other"


class Severity(StrEnum):
    CRITICAL = "critical"
    OBSTACLE = "obstacle"
    MINOR = "minor"


class Nature(StrEnum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class QueueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class DecisionAction(StrEnum):
    CONFIRM = "confirm"
    REJECT = "reject"


FEATURE_GROUP: dict[FeatureKey, FeatureGroupKey] = {
    FeatureKey.STEP_FREE_ENTRANCE: FeatureGroupKey.ENTRANCE,
    FeatureKey.RAMP: FeatureGroupKey.ENTRANCE,
    FeatureKey.ELEVATOR: FeatureGroupKey.INSIDE,
    FeatureKey.ACCESSIBLE_TOILET: FeatureGroupKey.TOILET,
    FeatureKey.INDUCTION_LOOP: FeatureGroupKey.HEARING,
    FeatureKey.SIGN_LANGUAGE_INTERPRETER: FeatureGroupKey.HEARING,
    FeatureKey.BRAILLE: FeatureGroupKey.VISION,
    FeatureKey.TACTILE_PATHS: FeatureGroupKey.VISION,
    FeatureKey.GOOD_LIGHTING: FeatureGroupKey.VISION,
    FeatureKey.LOWERED_CURB: FeatureGroupKey.MOBILITY,
    FeatureKey.PLATFORM_ELEVATOR: FeatureGroupKey.MOBILITY,
    FeatureKey.CRUTCHES_FRIENDLY: FeatureGroupKey.MOBILITY,
    FeatureKey.ASSISTANCE_DOG_ALLOWED: FeatureGroupKey.OTHER,
}

LABELS_PL: dict[str, str] = {
    FeatureGroupKey.ENTRANCE: "Wejście",
    FeatureGroupKey.INSIDE: "Wewnątrz",
    FeatureGroupKey.TOILET: "Toaleta",
    FeatureGroupKey.HEARING: "Słuch",
    FeatureGroupKey.VISION: "Wzrok",
    FeatureGroupKey.MOBILITY: "Poruszanie się",
    FeatureGroupKey.OTHER: "Inne",
    FeatureKey.STEP_FREE_ENTRANCE: "Wejście bez schodów",
    FeatureKey.RAMP: "Podjazd",
    FeatureKey.ELEVATOR: "Winda",
    FeatureKey.ACCESSIBLE_TOILET: "Toaleta dostępna",
    FeatureKey.INDUCTION_LOOP: "Pętla indukcyjna",
    FeatureKey.BRAILLE: "Oznaczenia w alfabecie Braille'a",
    FeatureKey.TACTILE_PATHS: "Ścieżki prowadzące",
    FeatureKey.GOOD_LIGHTING: "Dobre oświetlenie",
    FeatureKey.LOWERED_CURB: "Obniżony krawężnik",
    FeatureKey.PLATFORM_ELEVATOR: "Winda na peron",
    FeatureKey.CRUTCHES_FRIENDLY: "Udogodnienia dla osób o kulach",
    FeatureKey.SIGN_LANGUAGE_INTERPRETER: "Tłumacz PJM",
    FeatureKey.ASSISTANCE_DOG_ALLOWED: "Wejście z psem asystującym",
}
