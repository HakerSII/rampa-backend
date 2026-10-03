from pydantic import BaseModel

from fastapi import APIRouter

from app.adapters.inbound.http.deps import UC, CurrentUser
from app.domain.enums import CurrentState, FeatureKey, Severity

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
