"""Pydantic schemas = contract from features/*/openapi.yaml, plus domain → schema mappers."""
from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import (
    FEATURE_GROUP,
    LABELS_PL,
    CheckAnswer,
    FeatureGroupKey,
    FeatureKey,
    NeedsProfile,
    ObservationSource,
    ObservationValue,
    Role,
    StateValue,
    ValidationStatus,
)
from app.domain.model import CheckResult, FeatureStateRecord, Observation, Photo, Place, QueueItem, Report, User


class UserOut(BaseModel):
    id: str
    display_name: str
    email: str | None = None
    role: Role


class LoginResult(BaseModel):
    token: str
    user: UserOut


class DemoLoginIn(BaseModel):
    username: str


# ---------------------------------------------------------------- places (F2)
class Location(BaseModel):
    lat: float
    lon: float


class Category(BaseModel):
    key: str
    label: str


class VerificationOut(BaseModel):
    status: str
    label: str
    last_verified: str | None
    confidence: float
    confidence_level: str
    sources: list[str]


class PlaceSummary(BaseModel):
    id: str
    name: str
    category: Category
    location: Location
    accessibility_summary: list[FeatureKey]
    verification: VerificationOut | None = None
    distance_m: int | None = None


class PlaceOut(PlaceSummary):
    short_description: str
    address: str
    opening_hours: list[dict] = []
    contact: dict = {}


class PlacePage(BaseModel):
    items: list[PlaceSummary]
    page: int = 1
    page_size: int
    total: int


class FeatureStateOut(BaseModel):
    key: FeatureKey
    label: str
    state: StateValue
    temporary: bool
    confidence: float
    last_verified: str | None
    sources_count: int
    validation: ValidationStatus
    active_observation_id: str | None


class FeatureGroupOut(BaseModel):
    key: FeatureGroupKey
    label: str
    features: list[FeatureStateOut]


class AccessibilityOut(BaseModel):
    place_id: str
    groups: list[FeatureGroupOut]


class FeatureDictItem(BaseModel):
    key: FeatureKey
    label: str


class FeatureDictGroup(BaseModel):
    key: FeatureGroupKey
    label: str
    features: list[FeatureDictItem]


class CheckReasonOut(BaseModel):
    feature: FeatureKey
    state: StateValue


class ActiveIssueOut(BaseModel):
    observation_id: str
    feature: FeatureKey
    temporary: bool
    comment: str


class CheckResultOut(BaseModel):
    place_id: str
    profile: NeedsProfile
    answer: CheckAnswer
    confidence: float
    reasons: list[CheckReasonOut]
    active_issues: list[ActiveIssueOut]
    advice: str


CATEGORY_LABELS = {"museum": "Muzeum", "cafe": "Kawiarnia", "culture": "Kultura", "office": "Urząd"}


def verification_out(v) -> VerificationOut:
    return VerificationOut(status=v.status, label=v.label, last_verified=iso(v.last_verified),
                           confidence=v.confidence, confidence_level=v.confidence_level, sources=v.sources)


def place_summary(place: Place, yes_features: list[FeatureKey], verification=None,
                  distance: int | None = None) -> PlaceSummary:
    return PlaceSummary(
        distance_m=distance,
        verification=verification_out(verification) if verification else None,
        id=place.id, name=place.name,
        category=Category(key=place.category, label=CATEGORY_LABELS.get(place.category, place.category)),
        location=Location(lat=place.location.lat, lon=place.location.lon),
        accessibility_summary=yes_features,
    )


def place_out(place: Place, yes_features: list[FeatureKey], verification=None) -> PlaceOut:
    return PlaceOut(**place_summary(place, yes_features, verification).model_dump(),
                    short_description=place.short_description, address=place.address,
                    opening_hours=place.opening_hours, contact=place.contact)


def feature_state_out(s: FeatureStateRecord) -> FeatureStateOut:
    return FeatureStateOut(
        key=s.feature, label=LABELS_PL[s.feature], state=s.state, temporary=s.temporary,
        confidence=s.confidence, last_verified=iso(s.last_verified), sources_count=s.sources_count,
        validation=s.validation, active_observation_id=s.active_observation_id,
    )


def accessibility_out(place_id: str, states: dict[FeatureKey, FeatureStateRecord]) -> AccessibilityOut:
    groups = []
    for group in FeatureGroupKey:
        features = [feature_state_out(states[f]) for f in FeatureKey if FEATURE_GROUP[f] == group]
        groups.append(FeatureGroupOut(key=group, label=LABELS_PL[group], features=features))
    return AccessibilityOut(place_id=place_id, groups=groups)


def feature_dictionary() -> list[FeatureDictGroup]:
    return [
        FeatureDictGroup(key=g, label=LABELS_PL[g], features=[
            FeatureDictItem(key=f, label=LABELS_PL[f]) for f in FeatureKey if FEATURE_GROUP[f] == g
        ])
        for g in FeatureGroupKey
    ]


def check_out(r: CheckResult) -> CheckResultOut:
    return CheckResultOut(
        place_id=r.place_id, profile=r.profile, answer=r.answer, confidence=r.confidence,
        reasons=[CheckReasonOut(feature=x.feature, state=x.state) for x in r.reasons],
        active_issues=[ActiveIssueOut(observation_id=o.id, feature=o.feature, temporary=o.temporary,
                                      comment=o.comment) for o in r.active_issues],
        advice=r.advice,
    )


# ---------------------------------------------------------------- observations (F3)
class PhotoOut(BaseModel):
    id: str
    url: str


class AuthorOut(BaseModel):
    id: str
    display_name: str


class ReportFields(BaseModel):
    element: str | None = None
    current_state: str | None = None
    severity: str | None = None
    nature: str | None = None
    description: str | None = None
    photo_ids: list[str] = []


class ReportIn(ReportFields):
    place_id: str
    draft: bool = False  # true → "Zapisz szkic": no observation until submit


class ReportPatchIn(ReportFields):
    photo_ids: list[str] | None = None


class ReplyOut(BaseModel):
    author: "AuthorOut"
    text: str
    created_at: str


class ReportOut(ReportFields):
    place_id: str
    replies: list[ReplyOut] = []
    owner_status: str | None = None
    id: str
    status: str
    author: AuthorOut
    created_at: str
    observation_ids: list[str]


class ObservationIn(BaseModel):
    feature: str
    value: str
    temporary: bool = False
    comment: str = ""
    photo_ids: list[str] = []


class VotesOut(BaseModel):
    up: int
    down: int
    my_vote: int | None


class ValidationOut(BaseModel):
    status: ValidationStatus
    reason: str = ""


class ObservationOut(BaseModel):
    id: str
    place_id: str
    feature: FeatureKey
    value: ObservationValue
    temporary: bool
    source: ObservationSource
    author: AuthorOut
    report_id: str | None
    comment: str
    evidence: list[PhotoOut]
    votes: VotesOut
    validation: ValidationOut
    confidence: float
    created_at: str


class ObservationList(BaseModel):
    items: list[ObservationOut]


class VoteIn(BaseModel):
    value: int


class VoteResultOut(BaseModel):
    observation: ObservationOut
    feature_state: FeatureStateOut


def author_out(uc, user_id: str) -> AuthorOut:
    user = uc.repo.get_user(user_id)
    return AuthorOut(id=user_id, display_name=public_name(user.display_name) if user else user_id)


def photo_out(photo: Photo) -> PhotoOut:
    return PhotoOut(id=photo.id, url=photo.url)


def observation_out(uc, o: Observation, me: User | None = None) -> ObservationOut:
    photos = [p for p in (uc.repo.get_photo(i) for i in o.evidence_ids) if p]
    reason = ("contradicting observations within 30 days" if o.validation == ValidationStatus.CONFLICT
              else (o.flag_reason or "") if o.validation == ValidationStatus.FLAGGED else "")
    return ObservationOut(
        id=o.id, place_id=o.place_id, feature=o.feature, value=o.value, temporary=o.temporary,
        source=o.source, author=author_out(uc, o.author_id), report_id=o.report_id, comment=o.comment,
        evidence=[photo_out(p) for p in photos],
        votes=VotesOut(up=o.up_votes, down=o.down_votes, my_vote=o.votes.get(me.id) if me else None),
        validation=ValidationOut(status=o.validation, reason=reason),
        confidence=o.confidence, created_at=iso(o.created_at),
    )


def report_out(uc, r: Report) -> ReportOut:
    return ReportOut(
        id=r.id, place_id=r.place_id, element=r.element, current_state=r.current_state,
        severity=r.severity, nature=r.nature, description=r.description, photo_ids=r.photo_ids,
        status=r.status, author=author_out(uc, r.author_id), created_at=iso(r.created_at),
        observation_ids=r.observation_ids, owner_status=r.owner_status,
        replies=[ReplyOut(author=author_out(uc, x["author_id"]), text=x["text"], created_at=x["created_at"])
                 for x in r.replies],
    )


# ---------------------------------------------------------------- moderation (F4)
class QueuePlace(BaseModel):
    id: str
    name: str


class QueueItemOut(BaseModel):
    id: str
    type: str
    status: str
    label: str
    place: QueuePlace
    feature: FeatureKey
    observation_count: int
    created_at: str


class QueuePage(BaseModel):
    items: list[QueueItemOut]
    total: int
    counts: dict[str, int]


class QueueCommentOut(BaseModel):
    author: AuthorOut
    text: str
    created_at: str


class QueueDetailOut(QueueItemOut):
    summary: str
    observations: list[ObservationOut]
    feature_state: FeatureStateOut
    comments: list[QueueCommentOut] = []


class DecisionIn(BaseModel):
    action: str
    winning_observation_id: str | None = None
    comment: str = ""


class DecisionOut(BaseModel):
    id: str
    status: str
    feature_state: FeatureStateOut


def queue_item_out(uc, q: QueueItem) -> QueueItemOut:
    place = uc.repo.get_place(q.place_id)
    return QueueItemOut(
        id=q.id, type=q.type, status=q.status, label="Konflikt danych",
        place=QueuePlace(id=q.place_id, name=place.name if place else q.place_id),
        feature=q.feature, observation_count=len(q.observation_ids), created_at=iso(q.created_at),
    )


def queue_detail_out(uc, q: QueueItem, me: User) -> QueueDetailOut:
    observations = [o for o in (uc.repo.get_observation(i) for i in q.observation_ids) if o]
    state = uc.get_accessibility(q.place_id)[q.feature]
    return QueueDetailOut(
        **queue_item_out(uc, q).model_dump(),
        summary=f"Sprzeczne zgłoszenia: {LABELS_PL[q.feature]}",
        observations=[observation_out(uc, o, me) for o in observations],
        feature_state=feature_state_out(state),
        comments=[QueueCommentOut(author=author_out(uc, c["author_id"]), text=c["text"], created_at=c["created_at"])
                  for c in q.comments],
    )


# ---------------------------------------------------------------- place screen (F12)
class ActivityItemOut(BaseModel):
    type: str
    label: str
    observation_id: str
    feature: FeatureKey
    value: ObservationValue
    source: ObservationSource
    author: AuthorOut
    comment: str
    photo_url: str | None
    votes_up: int
    validation: ValidationStatus
    created_at: str


class ActivityList(BaseModel):
    items: list[ActivityItemOut]


class GalleryPhotoOut(BaseModel):
    id: str
    url: str
    author: AuthorOut | None
    kind: str = "evidence"  # evidence (from observations) | owner (presentation photos)
    feature: FeatureKey | None = None
    observation_id: str | None = None
    created_at: str | None = None


class GalleryOut(BaseModel):
    items: list[GalleryPhotoOut]
    total: int


def activity_item_out(uc, o: Observation) -> ActivityItemOut:
    from app.domain.verification import ACTIVITY_LABELS
    kind = uc.activity_type(o)
    first = next((p for p in (uc.repo.get_photo(i) for i in o.evidence_ids) if p), None)
    return ActivityItemOut(
        type=kind, label=ACTIVITY_LABELS[kind], observation_id=o.id, feature=o.feature, value=o.value,
        source=o.source, author=author_out(uc, o.author_id), comment=o.comment,
        photo_url=first.url if first else None, votes_up=o.up_votes, validation=o.validation,
        created_at=iso(o.created_at),
    )


# ---------------------------------------------------------------- ownership requests (F21)
class OwnershipRequestOut(BaseModel):
    id: str
    place_id: str
    user: AuthorOut
    justification: str
    status: str
    created_at: str
    decided_at: str | None


def ownership_out(uc, r) -> OwnershipRequestOut:
    return OwnershipRequestOut(id=r.id, place_id=r.place_id, user=author_out(uc, r.user_id),
                               justification=r.justification, status=r.status, created_at=iso(r.created_at),
                               decided_at=iso(r.decided_at))


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, display_name=user.display_name, email=user.email, role=user.role)


def public_name(display_name: str) -> str:
    """'Anna Kowalska' → 'Anna K.' (privacy rule from mockups)."""
    parts = display_name.split()
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else display_name


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
