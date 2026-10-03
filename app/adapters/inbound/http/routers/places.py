from typing import Annotated

from fastapi import APIRouter, Query

from app.adapters.inbound.http.deps import UC
from app.adapters.inbound.http.schemas import (
    AccessibilityOut,
    CheckResultOut,
    FeatureDictGroup,
    PlaceOut,
    PlacePage,
    accessibility_out,
    check_out,
    feature_dictionary,
    place_out,
    place_summary,
)
from app.domain.enums import FeatureKey, NeedsProfile
from app.domain.errors import ValidationFailed

router = APIRouter()


def parse_features(raw: str | None) -> list[FeatureKey] | None:
    """CSV (`a,b`) per OpenAPI style=form, explode=false."""
    if not raw:
        return None
    try:
        return [FeatureKey(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError as e:
        raise ValidationFailed(f"unknown feature: {e}") from e


@router.get("/places", response_model=PlacePage, tags=["places"])
async def search_places(uc: UC, features: Annotated[str | None, Query()] = None,
                        category: str | None = None, q: str | None = None):
    places = uc.search_places(parse_features(features), category, q)
    items = [place_summary(p, uc.yes_features(p.id)) for p in places]
    return PlacePage(items=items, page_size=max(len(items), 1), total=len(items))


@router.get("/places/{place_id}", response_model=PlaceOut, tags=["places"])
async def get_place(place_id: str, uc: UC):
    return place_out(uc.get_place(place_id), uc.yes_features(place_id))


@router.get("/places/{place_id}/accessibility", response_model=AccessibilityOut, tags=["places"])
async def get_accessibility(place_id: str, uc: UC):
    return accessibility_out(place_id, uc.get_accessibility(place_id))


@router.get("/places/{place_id}/check", response_model=CheckResultOut, tags=["places"])
async def check_place(place_id: str, profile: NeedsProfile, uc: UC):
    return check_out(uc.check_place(place_id, profile))


@router.get("/accessibility/features", response_model=list[FeatureDictGroup], tags=["dictionaries"])
async def list_features():
    return feature_dictionary()
