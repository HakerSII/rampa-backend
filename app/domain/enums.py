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
    ELEVATOR_ENTRANCE = "elevator_entrance"
    WIDE_DOORS = "wide_doors"
    AUTOMATIC_DOORS = "automatic_doors"
    CALL_BELL = "call_bell"
    SPACIOUS_INTERIOR = "spacious_interior"
    HIGH_CONTRAST_INFO = "high_contrast_info"
    TACTILE_INFO = "tactile_info"
    ESCALATOR = "escalator"
    ADULT_CHANGING_TABLE = "adult_changing_table"
    TURNING_SPACE = "turning_space"
    EXTRA_ACCESSIBLE_TOILETS = "extra_accessible_toilets"
    HIGH_CONTRAST_MARKINGS = "high_contrast_markings"
    ACCESSIBLE_DIGITAL_MATERIALS = "accessible_digital_materials"
    AUDIO_DESCRIPTION = "audio_description"
    VIDEO_CAPTIONS = "video_captions"
    FM_SYSTEM = "fm_system"
    DISABLED_PARKING = "disabled_parking"
    MARKED_PARKING = "marked_parking"
    LEVEL_SURFACE = "level_surface"
    MORE_THAN_N_SPOTS = "more_than_n_spots"
    DROP_OFF_ZONE = "drop_off_zone"
    PETS_ALLOWED = "pets_allowed"


class FeatureGroupKey(StrEnum):
    ENTRANCE = "entrance"
    INSIDE = "inside"
    TOILET = "toilet"
    HEARING = "hearing"
    VISION = "vision"
    MOBILITY = "mobility"
    PARKING = "parking"
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
    FeatureKey.ELEVATOR_ENTRANCE: FeatureGroupKey.ENTRANCE,
    FeatureKey.WIDE_DOORS: FeatureGroupKey.ENTRANCE,
    FeatureKey.AUTOMATIC_DOORS: FeatureGroupKey.ENTRANCE,
    FeatureKey.CALL_BELL: FeatureGroupKey.ENTRANCE,
    FeatureKey.SPACIOUS_INTERIOR: FeatureGroupKey.INSIDE,
    FeatureKey.HIGH_CONTRAST_INFO: FeatureGroupKey.INSIDE,
    FeatureKey.TACTILE_INFO: FeatureGroupKey.INSIDE,
    FeatureKey.ESCALATOR: FeatureGroupKey.INSIDE,
    FeatureKey.ADULT_CHANGING_TABLE: FeatureGroupKey.TOILET,
    FeatureKey.TURNING_SPACE: FeatureGroupKey.TOILET,
    FeatureKey.EXTRA_ACCESSIBLE_TOILETS: FeatureGroupKey.TOILET,
    FeatureKey.HIGH_CONTRAST_MARKINGS: FeatureGroupKey.VISION,
    FeatureKey.ACCESSIBLE_DIGITAL_MATERIALS: FeatureGroupKey.VISION,
    FeatureKey.AUDIO_DESCRIPTION: FeatureGroupKey.VISION,
    FeatureKey.VIDEO_CAPTIONS: FeatureGroupKey.HEARING,
    FeatureKey.FM_SYSTEM: FeatureGroupKey.HEARING,
    FeatureKey.DISABLED_PARKING: FeatureGroupKey.PARKING,
    FeatureKey.MARKED_PARKING: FeatureGroupKey.PARKING,
    FeatureKey.LEVEL_SURFACE: FeatureGroupKey.PARKING,
    FeatureKey.MORE_THAN_N_SPOTS: FeatureGroupKey.PARKING,
    FeatureKey.DROP_OFF_ZONE: FeatureGroupKey.PARKING,
    FeatureKey.PETS_ALLOWED: FeatureGroupKey.OTHER,
}

LABELS_PL: dict[str, str] = {
    FeatureGroupKey.ENTRANCE: "Wejście",
    FeatureGroupKey.INSIDE: "Wewnątrz",
    FeatureGroupKey.TOILET: "Toaleta",
    FeatureGroupKey.HEARING: "Słuch",
    FeatureGroupKey.VISION: "Wzrok",
    FeatureGroupKey.MOBILITY: "Poruszanie się",
    FeatureGroupKey.PARKING: "Parking",
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
    FeatureKey.ELEVATOR_ENTRANCE: "Winda przy wejściu",
    FeatureKey.WIDE_DOORS: "Szerokie drzwi (min. 90 cm)",
    FeatureKey.AUTOMATIC_DOORS: "Automatyczne drzwi",
    FeatureKey.CALL_BELL: "Dzwonek przy wejściu",
    FeatureKey.SPACIOUS_INTERIOR: "Przestronne wnętrze",
    FeatureKey.HIGH_CONTRAST_INFO: "Informacja w kontrastowych kolorach",
    FeatureKey.TACTILE_INFO: "Plany tyflograficzne",
    FeatureKey.ESCALATOR: "Schody ruchome",
    FeatureKey.ADULT_CHANGING_TABLE: "Przewijak dla dorosłych",
    FeatureKey.TURNING_SPACE: "Przestrzeń manewrowa",
    FeatureKey.EXTRA_ACCESSIBLE_TOILETS: "Dodatkowe toalety dostępne",
    FeatureKey.HIGH_CONTRAST_MARKINGS: "Kontrastowe oznaczenia",
    FeatureKey.ACCESSIBLE_DIGITAL_MATERIALS: "Dostępne materiały cyfrowe",
    FeatureKey.AUDIO_DESCRIPTION: "Audiodeskrypcja",
    FeatureKey.VIDEO_CAPTIONS: "Napisy do treści wideo",
    FeatureKey.FM_SYSTEM: "System FM",
    FeatureKey.DISABLED_PARKING: "Miejsca dla osób z niepełnosprawnościami",
    FeatureKey.MARKED_PARKING: "Oznakowane miejsca parkingowe",
    FeatureKey.LEVEL_SURFACE: "Równa, utwardzona nawierzchnia",
    FeatureKey.MORE_THAN_N_SPOTS: "Więcej niż 2 miejsca",
    FeatureKey.DROP_OFF_ZONE: "Strefa wysiadania",
    FeatureKey.PETS_ALLOWED: "Wejście ze zwierzętami",
}
