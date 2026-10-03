"""Open API (read-only) for external apps — same use cases as the internal places API."""
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, ApiKey
from app.adapters.inbound.http.routers.places import parse_features
from app.adapters.inbound.http.schemas import Location
from app.domain.enums import FeatureKey, NeedsProfile, StateValue
from app.domain.model import FeatureStateRecord, Place

router = APIRouter(tags=["public"])


class PublicPlace(BaseModel):
    id: str
    name: str
    category: str
    address: str
    location: Location
    accessibility_summary: list[FeatureKey]


class PublicPlacePage(BaseModel):
    items: list[PublicPlace]
    total: int


class PublicFeature(BaseModel):
    value: bool | str  # true | false | "partial"
    temporary: bool
    confidence: float
    last_verified: str | None


class PublicPlaceRef(BaseModel):
    id: str
    name: str


class PublicAccessibility(BaseModel):
    place: PublicPlaceRef
    accessibility: dict[FeatureKey, PublicFeature]


class PublicCheck(BaseModel):
    place_id: str
    profile: NeedsProfile
    answer: str
    confidence: float
    advice: str


def public_place(uc, place: Place) -> PublicPlace:
    return PublicPlace(id=place.id, name=place.name, category=place.category, address=place.address,
                       location=Location(lat=place.location.lat, lon=place.location.lon),
                       accessibility_summary=uc.yes_features(place.id))


def public_feature(s: FeatureStateRecord) -> PublicFeature:
    value = (str(s.state) if s.state in (StateValue.PARTIAL, StateValue.NOT_APPLICABLE)
             else s.state == StateValue.YES)
    return PublicFeature(value=value, temporary=s.temporary, confidence=s.confidence,
                         last_verified=s.last_verified.date().isoformat() if s.last_verified else None)


@router.get("/places", response_model=PublicPlacePage)
async def search_places(uc: UC, _: ApiKey, features: Annotated[str | None, Query()] = None,
                        category: str | None = None, q: str | None = None):
    places = uc.search_places(parse_features(features), category, q)
    return PublicPlacePage(items=[public_place(uc, p) for p in places], total=len(places))


@router.get("/places/{place_id}", response_model=PublicPlace)
async def get_place(place_id: str, uc: UC, _: ApiKey):
    return public_place(uc, uc.get_place(place_id))


@router.get("/places/{place_id}/accessibility", response_model=PublicAccessibility)
async def get_accessibility(place_id: str, uc: UC, _: ApiKey):
    """yes → true, no → false, unknown → omitted."""
    place = uc.get_place(place_id)
    states = uc.get_accessibility(place_id)
    return PublicAccessibility(
        place=PublicPlaceRef(id=place.id, name=place.name),
        accessibility={f: public_feature(s) for f, s in states.items() if s.state != StateValue.UNKNOWN},
    )


@router.get("/places/{place_id}/check", response_model=PublicCheck)
async def check_place(place_id: str, profile: NeedsProfile, uc: UC, _: ApiKey):
    r = uc.check_place(place_id, profile)
    return PublicCheck(place_id=r.place_id, profile=r.profile, answer=r.answer,
                       confidence=r.confidence, advice=r.advice)
