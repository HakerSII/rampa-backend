from fastapi import APIRouter
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, CurrentUser, OptionalUser
from app.domain.enums import LABELS_PL, CurrentState, FeatureKey, NeedsProfile, ObservationValue, Severity

router = APIRouter(tags=["ai"])


class ImageTagsIn(BaseModel):
    photo_ids: list[str]
    place_id: str | None = None


class ImageAnalysisOut(BaseModel):
    real_place: bool
    barrier_detected: bool
    barrier_type: str
    affected_disabilities: list[str]
    description: str
    confidence: float


class TagOut(BaseModel):
    label: str
    feature: FeatureKey | None
    confidence: float


class SuggestedOut(BaseModel):
    element: FeatureKey
    current_state: CurrentState
    severity: Severity


class ImageTagsOut(BaseModel):
    analysis: ImageAnalysisOut
    tags: list[TagOut]
    detected: str
    suggested: SuggestedOut | None
    model: str


class ParseTextIn(BaseModel):
    text: str


class TextSuggestionOut(BaseModel):
    feature: FeatureKey
    label: str
    value: ObservationValue
    temporary: bool
    confidence: float


class ParseTextOut(BaseModel):
    suggestions: list[TextSuggestionOut]
    model: str


@router.post("/ai/parse-text", response_model=ParseTextOut)
async def parse_text(body: ParseTextIn, uc: UC, user: CurrentUser):
    """Description → suggested observations (rules, PL + EN, offline). Suggestion only."""
    return ParseTextOut(model="rules", suggestions=[
        TextSuggestionOut(feature=s.feature, label=LABELS_PL[s.feature], value=s.value, temporary=s.temporary,
                          confidence=s.confidence) for s in uc.parse_text(user, body.text)])


@router.post("/ai/image-tags", response_model=ImageTagsOut)
async def image_tags(body: ImageTagsIn, uc: UC, user: CurrentUser):
    r = await uc.analyze_image(user, body.photo_ids, body.place_id)
    a = r.analysis
    return ImageTagsOut(
        analysis=ImageAnalysisOut(real_place=a.real_place, barrier_detected=a.barrier_detected,
                                  barrier_type=a.barrier_type, affected_disabilities=a.affected_disabilities,
                                  description=a.description, confidence=a.confidence),
        tags=[TagOut(label=t.label, feature=t.feature, confidence=t.confidence) for t in r.tags],
        detected=r.detected,
        suggested=SuggestedOut(element=r.suggested.element, current_state=r.suggested.current_state,
                               severity=r.suggested.severity) if r.suggested else None,
        model=r.model,
    )


# ---------------------------------------------------------------- F30 recommendations
class RecommendIn(BaseModel):
    query: str
    profile: NeedsProfile | None = None
    lat: float | None = None
    lon: float | None = None
    limit: int = 5


class IntentOut(BaseModel):
    profiles: list[NeedsProfile]
    features: list[FeatureKey]
    categories: list[str]
    area: str | None


class RecReasonOut(BaseModel):
    feature: FeatureKey
    label: str
    state: str
    source: str | None
    last_verified: str | None


class RecPlaceOut(BaseModel):
    id: str
    name: str
    category: str
    address: str | None
    location: dict


class RecItemOut(BaseModel):
    place: RecPlaceOut
    match: str
    distance_m: int | None
    reasons: list[RecReasonOut]
    missing: list[FeatureKey]


class RecommendOut(BaseModel):
    intent: IntentOut
    items: list[RecItemOut]
    model: str
    note: str


@router.post("/ai/recommend", response_model=RecommendOut)
async def recommend(body: RecommendIn, uc: UC, user: OptionalUser):
    """Natural-language query → places from the database only, with reasons and missing data (guest allowed)."""
    r = await uc.recommend(user, body.query, body.profile, body.lat, body.lon, body.limit)
    i = r.intent
    return RecommendOut(
        intent=IntentOut(profiles=i.profiles, features=i.features, categories=i.categories, area=i.area),
        items=[RecItemOut(
            place=RecPlaceOut(id=x.place.id, name=x.place.name, category=x.place.category, address=x.place.address,
                              location={"lat": x.place.location.lat, "lon": x.place.location.lon}),
            match=x.match, distance_m=x.distance_m,
            reasons=[RecReasonOut(feature=c.feature, label=LABELS_PL[c.feature], state=str(c.state), source=c.source,
                                  last_verified=c.last_verified.isoformat() if c.last_verified else None)
                     for c in x.reasons],
            missing=x.missing) for x in r.items],
        model=r.model, note=r.note)
