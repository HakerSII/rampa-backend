"""Accessible route A→B. Pure.
Path = real walking geometry from a routing engine (F28) or, as a fallback, the straight line.
Street-level features of places within BUFFER_M of the path: `no` = barrier, `yes` = helper."""
from dataclasses import dataclass
from math import ceil

from app.domain.enums import FeatureKey as F, NeedsProfile as P, StateValue
from app.domain.geo import distance_to_segment_m, haversine_m
from app.domain.model import FeatureStateRecord, GeoPoint, Place

BUFFER_M = 100
SPEED_M_PER_MIN = 50
NOTE = ("heuristic: straight line between the points; barriers/helpers = street-level features of places "
        f"within {BUFFER_M} m of the line — not a routing engine")
NOTE_ENGINE = (f"walking route from OSRM (OpenStreetMap); barriers/helpers = street-level features of places "
               f"within {BUFFER_M} m of the path")

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
class RoutePath:
    """Routing engine answer: polyline (≥ 2 points), metres, seconds."""
    points: list[GeoPoint]
    distance_m: int
    duration_s: int


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
    geometry: list[list[float]]  # [[lon, lat], …]
    barriers: list[RoutePoint]
    helpers: list[RoutePoint]
    note: str = NOTE
    engine: str = "straight_line"  # straight_line | osrm


def distance_to_path_m(p: GeoPoint, points: list[GeoPoint]) -> float:
    return min(distance_to_segment_m(p, a, b) for a, b in zip(points, points[1:]))


def plan_route(a: GeoPoint, b: GeoPoint, profile: P,
               places: list[tuple[Place, dict[F, FeatureStateRecord]]], path: RoutePath | None = None) -> RouteResult:
    points = path.points if path and len(path.points) >= 2 else [a, b]
    relevant = ROUTE_FEATURES[profile]
    barriers, helpers = [], []
    for place, states in places:
        if distance_to_path_m(place.location, points) > BUFFER_M:
            continue
        for feature in relevant:
            state = states.get(feature)
            if state is None or state.state in (StateValue.UNKNOWN, StateValue.NOT_APPLICABLE):
                continue
            point = RoutePoint(place.id, place.name, feature, place.location)
            (barriers if state.state == StateValue.NO else helpers).append(point)
    feasible = "partial" if barriers else "yes" if helpers else "unknown"
    geometry = [[p.lon, p.lat] for p in points]
    if path and len(path.points) >= 2:
        return RouteResult(feasible, path.distance_m, ceil(path.duration_s / 60), geometry, barriers, helpers,
                           NOTE_ENGINE, "osrm")
    distance = round(haversine_m(a, b))
    return RouteResult(feasible, distance, ceil(distance / SPEED_M_PER_MIN), geometry, barriers, helpers)
