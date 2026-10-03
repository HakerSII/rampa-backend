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
    Role,
    StateValue,
    ValidationStatus,
)
from app.domain.model import CheckResult, FeatureStateRecord, Place, User


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


class PlaceSummary(BaseModel):
    id: str
    name: str
    category: Category
    location: Location
    accessibility_summary: list[FeatureKey]


class PlaceOut(PlaceSummary):
    short_description: str
    address: str


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


def place_summary(place: Place, yes_features: list[FeatureKey]) -> PlaceSummary:
    return PlaceSummary(
        id=place.id, name=place.name,
        category=Category(key=place.category, label=CATEGORY_LABELS.get(place.category, place.category)),
        location=Location(lat=place.location.lat, lon=place.location.lon),
        accessibility_summary=yes_features,
    )


def place_out(place: Place, yes_features: list[FeatureKey]) -> PlaceOut:
    return PlaceOut(**place_summary(place, yes_features).model_dump(),
                    short_description=place.short_description, address=place.address)


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


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, display_name=user.display_name, email=user.email, role=user.role)


def public_name(display_name: str) -> str:
    """'Anna Kowalska' → 'Anna K.' (privacy rule from mockups)."""
    parts = display_name.split()
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else display_name


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
