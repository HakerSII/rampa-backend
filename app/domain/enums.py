"""Domain enums. Values are a subset of the full contract (sourcedoc/openapi.yaml)."""
from enum import StrEnum


class FeatureKey(StrEnum):
    STEP_FREE_ENTRANCE = "step_free_entrance"
    RAMP = "ramp"
    ELEVATOR = "elevator"
    ACCESSIBLE_TOILET = "accessible_toilet"
    INDUCTION_LOOP = "induction_loop"


class FeatureGroupKey(StrEnum):
    ENTRANCE = "entrance"
    INSIDE = "inside"
    TOILET = "toilet"
    HEARING = "hearing"


class StateValue(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class ObservationValue(StrEnum):
    YES = "yes"
    NO = "no"


class ObservationSource(StrEnum):
    COMMUNITY = "community"
    VERIFIED_OWNER = "verified_owner"
    ADMIN = "admin"


class ValidationStatus(StrEnum):
    VALID = "VALID"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"


class NeedsProfile(StrEnum):
    WHEELCHAIR = "wheelchair"


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
    NOT_WORKING = "not_working"


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
}

LABELS_PL: dict[str, str] = {
    FeatureGroupKey.ENTRANCE: "Wejście",
    FeatureGroupKey.INSIDE: "Wewnątrz",
    FeatureGroupKey.TOILET: "Toaleta",
    FeatureGroupKey.HEARING: "Słuch",
    FeatureKey.STEP_FREE_ENTRANCE: "Wejście bez schodów",
    FeatureKey.RAMP: "Podjazd",
    FeatureKey.ELEVATOR: "Winda",
    FeatureKey.ACCESSIBLE_TOILET: "Toaleta dostępna",
    FeatureKey.INDUCTION_LOOP: "Pętla indukcyjna",
}
