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
    favorite_place_ids: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)          # F31 NeedsProfile values (needs, never diagnoses)
    pref_features: list[str] = field(default_factory=list)  # F31 FeatureKey values the user cares about


@dataclass(slots=True)
class Session:
    token: str
    user_id: str
    expires_at: datetime


@dataclass(slots=True)
class Question:
    """F34 user → owner question about a place ("Czy można wejść z psem?")."""
    id: str
    place_id: str
    author_id: str
    text: str
    created_at: datetime
    feature: FeatureKey | None = None
    status: str = "open"  # open | answered
    answer_text: str | None = None
    answered_by: str | None = None
    answered_at: datetime | None = None
    outcome: str | None = None  # ObservationValue (attribute set) | planned | None (text only)


@dataclass(slots=True)
class Notification:
    """F35 in-app notification for one user."""
    id: str
    user_id: str
    kind: str
    text: str
    created_at: datetime
    place_id: str | None = None
    ref_id: str | None = None  # question / report / queue item / ownership request id
    read: bool = False


@dataclass(slots=True)
class LoginToken:
    """F33 one-time e-mail login code; only the SHA-256 of the code is stored."""
    token_hash: str
    email: str
    created_at: datetime
    expires_at: datetime
    used: bool = False


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
    external_id: str | None = None  # e.g. osm:<lat>,<lon>
    opening_hours: list[dict] = field(default_factory=list)  # [{days, open, close} | {days, closed: True}]
    contact: dict = field(default_factory=dict)  # {phone, website, email}
    photo_ids: list[str] = field(default_factory=list)  # owner/presentation photos
    place_type: str = "venue"  # PlaceType value


@dataclass(slots=True)
class GeocodeHit:
    label: str
    place_id: str | None  # None = external geocoder hit (no accessibility data yet)
    location: GeoPoint


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
    flag_reason: str | None = None  # set when validation == FLAGGED
    valid_until: datetime | None = None  # temporary issue end; after it the observation no longer counts

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
    element: FeatureKey | None  # None allowed only while status == "draft"
    current_state: CurrentState | None
    severity: Severity | None
    nature: Nature | None
    description: str | None
    created_at: datetime
    photo_ids: list[str] = field(default_factory=list)
    status: str = "submitted"
    observation_ids: list[str] = field(default_factory=list)
    replies: list[dict] = field(default_factory=list)  # owner replies {author_id, text, created_at}
    owner_status: str | None = None  # approved (owner confirmed the report)


@dataclass(slots=True)
class QueueItem:
    id: str
    place_id: str
    feature: FeatureKey | None  # None for type new_place (F36)
    created_at: datetime
    observation_ids: list[str] = field(default_factory=list)
    type: str = "conflict"
    status: QueueStatus = QueueStatus.OPEN
    decision: str | None = None  # approved | rejected
    resolved_at: datetime | None = None
    comments: list[dict] = field(default_factory=list)  # {author_id, text, created_at (ISO)}

    @property
    def pending(self) -> bool:
        """open or escalated — still waiting for a decision"""
        return self.status != QueueStatus.RESOLVED

    @property
    def open_conflict(self) -> bool:
        return self.type == "conflict" and self.pending


@dataclass(slots=True)
class OwnershipRequest:
    id: str
    place_id: str
    user_id: str
    justification: str
    created_at: datetime
    status: str = "pending"  # pending | approved | rejected
    decided_at: datetime | None = None


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
