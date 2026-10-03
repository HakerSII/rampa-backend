from fastapi import APIRouter
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, CurrentUser
from app.domain.enums import LABELS_PL, CurrentState, FeatureKey, ObservationValue, Severity

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
