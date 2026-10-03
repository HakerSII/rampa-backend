from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.adapters.inbound.http.deps import UC, CurrentUser
from app.adapters.inbound.http.schemas import (
    AccessibilityOut,
    CheckResultOut,
    FeatureDictGroup,
    PlaceOut,
    PlacePage,
    ResolvedPlaceOut,
    ResolvePlaceIn,
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


@router.post("/places/resolve", response_model=ResolvedPlaceOut, tags=["places"],
             responses={201: {"model": ResolvedPlaceOut, "description": "Created"}})
async def resolve_place(body: ResolvePlaceIn, uc: UC, user: CurrentUser, response: Response):
    """Map pin → place: the same name within 50 m is matched (200), otherwise created (201)."""
    place, created = uc.resolve_place(user, **body.model_dump())
    response.status_code = 201 if created else 200
    return ResolvedPlaceOut(place=place_out(place, uc.yes_features(place.id)), created=created)


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
