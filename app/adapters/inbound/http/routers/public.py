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


class PublicGeoHit(BaseModel):  # F51
    label: str
    lat: float
    lon: float
    place_id: str | None  # null = an address / place found by the geocoder, not in the database


class PublicGeoPage(BaseModel):
    items: list[PublicGeoHit]


class PublicNearbyPlace(PublicPlace):
    distance_m: int


class PublicNearbyPage(BaseModel):
    items: list[PublicNearbyPlace]
    total: int
    radius_m: int


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


@router.get("/geocode", response_model=PublicGeoPage)
async def geocode(q: str, uc: UC, _: ApiKey):
    """F51: coordinates of a place or address, like the app's search box: places of the database first, then the
    geocoder (GEOCODER=nominatim, bounded to the city)."""
    hits = await uc.geocode_live(q)
    return PublicGeoPage(items=[PublicGeoHit(label=h.label, lat=h.location.lat, lon=h.location.lon,
                                             place_id=h.place_id) for h in hits[:10]])


@router.get("/places/nearby", response_model=PublicNearbyPage)
async def places_nearby(uc: UC, _: ApiKey, lat: float, lon: float, radius_m: int = 500,
                        features: Annotated[str | None, Query()] = None):
    """F51: places within radius_m (50–2000, default 500) of the point, nearest first."""
    rows = uc.places_nearby(lat, lon, radius_m, parse_features(features))
    return PublicNearbyPage(items=[PublicNearbyPlace(**public_place(uc, p).model_dump(), distance_m=d) for p, d in rows],
                            total=len(rows), radius_m=radius_m)


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
