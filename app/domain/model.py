from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import (
    CheckAnswer,
    CurrentState,
    FeatureKey,
    Nature,
    NeedsProfile,
    ObservationSource,
    ObservationValue,
    QueueStatus,
    Role,
    Severity,
    StateValue,
    ValidationStatus,
)
from app.domain.errors import ValidationFailed


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lon: float

    def __post_init__(self):
        if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
            raise ValidationFailed(f"invalid coordinates: {self.lat}, {self.lon}")


@dataclass(slots=True)
class User:
    id: str
    display_name: str
    role: Role
    username: str | None = None  # demo accounts
    email: str | None = None
    google_sub: str | None = None


@dataclass(slots=True)
class Session:
    token: str
    user_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str


@dataclass(slots=True)
class Place:
    id: str
    name: str
    category: str
    location: GeoPoint
    short_description: str = ""
    address: str = ""
    owner_id: str | None = None


@dataclass(slots=True)
class Observation:
    id: str
    place_id: str
    feature: FeatureKey
    value: ObservationValue
    source: ObservationSource
    author_id: str
    created_at: datetime
    temporary: bool = False
    comment: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    votes: dict[str, int] = field(default_factory=dict)  # user_id -> 1 | -1
    validation: ValidationStatus = ValidationStatus.VALID
    confidence: float = 0.0
    report_id: str | None = None

    @property
    def up_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v == 1)

    @property
    def down_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v == -1)


@dataclass(slots=True)
class FeatureStateRecord:
    place_id: str
    feature: FeatureKey
    state: StateValue
    confidence: float = 0.0
    temporary: bool = False
    last_verified: datetime | None = None
    sources_count: int = 0
    validation: ValidationStatus = ValidationStatus.VALID
    active_observation_id: str | None = None


@dataclass(slots=True)
class Report:
    id: str
    place_id: str
    author_id: str
    element: FeatureKey
    current_state: CurrentState
    severity: Severity
    nature: Nature
    description: str
    created_at: datetime
    photo_ids: list[str] = field(default_factory=list)
    status: str = "submitted"
    observation_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QueueItem:
    id: str
    place_id: str
    feature: FeatureKey
    created_at: datetime
    observation_ids: list[str] = field(default_factory=list)
    type: str = "conflict"
    status: QueueStatus = QueueStatus.OPEN
    decision: str | None = None  # approved | rejected


@dataclass(slots=True)
class Photo:
    id: str
    path: str
    url: str
    original_name: str = ""


@dataclass(slots=True)
class ImageAnalysis:
    """Same fields as analyze_image() JSON in get_model.py (+ which model produced it)."""
    real_place: bool
    barrier_detected: bool
    barrier_type: str
    affected_disabilities: list[str]
    description: str
    confidence: float
    model: str = "mock"


@dataclass(frozen=True, slots=True)
class CheckReason:
    feature: FeatureKey
    state: StateValue


@dataclass(slots=True)
class CheckResult:
    place_id: str
    profile: NeedsProfile
    answer: CheckAnswer
    confidence: float
    reasons: list[CheckReason]
    active_issues: list[Observation]
    advice: str
