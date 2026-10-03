"""Accessible route A→B — straight-line heuristic (no routing engine). Pure.
Street-level features of places within BUFFER_M of the line: `no` = barrier, `yes` = helper."""
from dataclasses import dataclass
from math import ceil

from app.domain.enums import FeatureKey as F, NeedsProfile as P, StateValue
from app.domain.geo import distance_to_segment_m, haversine_m
from app.domain.model import FeatureStateRecord, GeoPoint, Place

BUFFER_M = 100
SPEED_M_PER_MIN = 50
NOTE = ("heuristic: straight line between the points; barriers/helpers = street-level features of places "
        f"within {BUFFER_M} m of the line — not a routing engine")

ROUTE_FEATURES: dict[P, tuple[F, ...]] = {
    P.WHEELCHAIR: (F.LOWERED_CURB, F.PLATFORM_ELEVATOR),
    P.STROLLER: (F.LOWERED_CURB, F.PLATFORM_ELEVATOR),
    P.CRUTCHES: (F.LOWERED_CURB, F.PLATFORM_ELEVATOR),
    P.BLIND: (F.TACTILE_PATHS, F.LOWERED_CURB),
    P.LOW_VISION: (F.GOOD_LIGHTING,),
    P.DEAF: (),
    P.ASSISTANCE_DOG: (),
}


@dataclass(slots=True)
class RoutePoint:
    place_id: str
    name: str
    feature: F
    location: GeoPoint


@dataclass(slots=True)
class RouteResult:
    feasible: str  # yes | partial | unknown
    distance_m: int
    duration_min: int
    geometry: list[list[float]]  # [[lon, lat], [lon, lat]]
    barriers: list[RoutePoint]
    helpers: list[RoutePoint]
    note: str = NOTE


def plan_route(a: GeoPoint, b: GeoPoint, profile: P,
               places: list[tuple[Place, dict[F, FeatureStateRecord]]]) -> RouteResult:
    relevant = ROUTE_FEATURES[profile]
    barriers, helpers = [], []
    for place, states in places:
        if distance_to_segment_m(place.location, a, b) > BUFFER_M:
            continue
        for feature in relevant:
            state = states.get(feature)
            if state is None or state.state == StateValue.UNKNOWN:
                continue
            point = RoutePoint(place.id, place.name, feature, place.location)
            (barriers if state.state == StateValue.NO else helpers).append(point)
    feasible = "partial" if barriers else "yes" if helpers else "unknown"
    distance = round(haversine_m(a, b))
    return RouteResult(feasible, distance, ceil(distance / SPEED_M_PER_MIN),
                       [[a.lon, a.lat], [b.lon, b.lat]], barriers, helpers)
