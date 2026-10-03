from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.adapters.inbound.http.deps import UC, CurrentUser
from app.adapters.inbound.http.schemas import (
    CATEGORY_LABELS,
    AccessibilityOut,
    ActivityList,
    CheckResultOut,
    FeatureDictGroup,
    GalleryOut,
    GalleryPhotoOut,
    Location,
    PlaceOut,
    PlacePage,
    PlaceSummary,
    accessibility_out,
    activity_item_out,
    author_out,
    check_out,
    feature_dictionary,
    iso,
    place_out,
    place_summary,
)
from app.application.use_cases import PlaceQuery
from app.domain.enums import LABELS_PL, FeatureKey, NeedsProfile
from app.domain.model import GeoPoint
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


class MapMarker(BaseModel):
    id: str
    name: str
    location: Location
    category: str
    marker: str  # accessible | partial | inaccessible | unknown (wheelchair check)


class MapMarkers(BaseModel):
    total: int
    items: list[MapMarker]


class CategoryOut(BaseModel):
    key: str
    label: str
    count: int


class GeocodeOut(BaseModel):
    label: str
    place_id: str
    location: Location


@router.get("/places", response_model=PlacePage | MapMarkers, tags=["places"])
async def search_places(uc: UC, features: Annotated[str | None, Query()] = None,
                        category: str | None = None, q: str | None = None,
                        lat: float | None = None, lon: float | None = None, radius_m: int | None = None,
                        bbox: str | None = None, sort: str | None = None,
                        page: int = 1, page_size: int = 20, view: Literal["list", "map"] = "list",
                        place_type: str | None = None):
    if (lat is None) != (lon is None):
        raise ValidationFailed("lat and lon must be given together")
    query = PlaceQuery(parse_features(features), category, q, GeoPoint(lat, lon) if lat is not None else None,
                       radius_m, bbox, sort, page, page_size,
                       [t.strip() for t in place_type.split(",") if t.strip()] if place_type else None)
    if view == "map":
        markers = [MapMarker(id=p.id, name=p.name, location=Location(lat=p.location.lat, lon=p.location.lon),
                             category=p.category, marker=m) for p, m in uc.map_markers(query)]
        return MapMarkers(total=len(markers), items=markers)
    r = uc.find_places(query)
    items = [place_summary(p, uc.yes_features(p.id), uc.verification_for(p.id), d) for p, d in r.items]
    return PlacePage(items=items, page=r.page, page_size=r.page_size, total=r.total)


@router.get("/categories", response_model=list[CategoryOut], tags=["dictionaries"])
async def list_categories(uc: UC):
    return [CategoryOut(key=c.key, label=CATEGORY_LABELS.get(c.key, c.key), count=c.count)
            for c in uc.list_categories()]


@router.get("/geocode", response_model=list[GeocodeOut], tags=["dictionaries"])
async def geocode(q: str, uc: UC):
    """Search-box suggestions from the local place index (offline)."""
    return [GeocodeOut(label=h.label, place_id=h.place_id, location=Location(lat=h.location.lat, lon=h.location.lon))
            for h in uc.geocode(q)]


@router.get("/places/{place_id}", response_model=PlaceOut, tags=["places"])
async def get_place(place_id: str, uc: UC):
    return place_out(uc.get_place(place_id), uc.yes_features(place_id), uc.verification_for(place_id))


@router.get("/places/{place_id}/accessibility", response_model=AccessibilityOut, tags=["places"])
async def get_accessibility(place_id: str, uc: UC):
    return accessibility_out(place_id, uc.get_accessibility(place_id))


@router.get("/places/{place_id}/check", response_model=CheckResultOut, tags=["places"])
async def check_place(place_id: str, profile: NeedsProfile, uc: UC):
    return check_out(uc.check_place(place_id, profile))


@router.get("/places/{place_id}/activity", response_model=ActivityList, tags=["places"])
async def place_activity(place_id: str, uc: UC, limit: int = 20):
    """Feed "Ostatnie zgłoszenia i potwierdzenia" — newest first, includes rejected (history)."""
    return ActivityList(items=[activity_item_out(uc, o) for o in uc.place_activity(place_id, limit)])


@router.get("/places/{place_id}/photos", response_model=GalleryOut, tags=["places"])
async def place_photos(place_id: str, uc: UC):
    owner_id = uc.get_place(place_id).owner_id
    items = [GalleryPhotoOut(id=p.id, url=p.url, author=author_out(uc, owner_id) if owner_id else None, kind="owner")
             for p in uc.place_owner_photos(place_id)]
    items += [GalleryPhotoOut(id=p.id, url=p.url, author=author_out(uc, o.author_id), feature=o.feature,
                              observation_id=o.id, created_at=iso(o.created_at))
              for p, o in uc.place_photos(place_id)]
    return GalleryOut(items=items, total=len(items))


class HistoryActor(BaseModel):
    id: str
    display_name: str


class HistoryEventOut(BaseModel):
    event: str
    description: str
    created_at: str
    actor: HistoryActor | None
    observation_id: str | None
    queue_id: str | None


class HistoryOut(BaseModel):
    items: list[HistoryEventOut]


@router.get("/places/{place_id}/history", response_model=HistoryOut, tags=["admin", "owner"])
async def place_history(place_id: str, uc: UC, user: CurrentUser):
    """Audit trail "Historia i audyt" — admin, or the owner of the place."""
    def actor(user_id):
        if user_id is None:
            return None
        a = author_out(uc, user_id)
        return HistoryActor(id=a.id, display_name=a.display_name)

    return HistoryOut(items=[HistoryEventOut(event=e.event, description=e.description, created_at=iso(e.created_at),
                                             actor=actor(e.actor_id), observation_id=e.observation_id,
                                             queue_id=e.queue_id)
                             for e in uc.place_history(user, place_id)])


class SimilarOut(BaseModel):
    items: list[PlaceSummary]


@router.get("/places/{place_id}/similar", response_model=SimilarOut, tags=["places"])
async def similar_places(place_id: str, uc: UC, limit: int = 5):
    """"Podobne miejsca w okolicy": within 3 km, same category first, then nearest."""
    return SimilarOut(items=[place_summary(p, uc.yes_features(p.id), uc.verification_for(p.id), d)
                             for p, d in uc.similar_places(place_id, limit)])


class RoutePointOut(BaseModel):
    place_id: str
    name: str
    feature: FeatureKey
    label: str
    location: Location


class LineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]


class RouteOut(BaseModel):
    feasible: str
    profile: NeedsProfile
    distance_m: int
    duration_min: int
    geometry: LineString
    barriers: list[RoutePointOut]
    helpers: list[RoutePointOut]
    note: str


def _route_point(p) -> RoutePointOut:
    return RoutePointOut(place_id=p.place_id, name=p.name, feature=p.feature, label=LABELS_PL[p.feature],
                         location=Location(lat=p.location.lat, lon=p.location.lon))


@router.get("/routes/accessible", response_model=RouteOut, tags=["routes"])
async def accessible_route(uc: UC, to: str, origin: Annotated[str, Query(alias="from")],
                           profile: NeedsProfile = NeedsProfile.WHEELCHAIR):
    """A→B for a needs profile. Heuristic (straight line + street-level barriers within 100 m) — see `note`."""
    r = uc.accessible_route(origin, to, profile)
    return RouteOut(feasible=r.feasible, profile=profile, distance_m=r.distance_m, duration_min=r.duration_min,
                    geometry=LineString(coordinates=r.geometry), barriers=[_route_point(p) for p in r.barriers],
                    helpers=[_route_point(p) for p in r.helpers], note=r.note)


@router.get("/accessibility/features", response_model=list[FeatureDictGroup], tags=["dictionaries"])
async def list_features():
    return feature_dictionary()
