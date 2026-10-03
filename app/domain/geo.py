from math import asin, cos, radians, sin, sqrt

from app.domain.model import GeoPoint

EARTH_RADIUS_M = 6_371_000


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance in meters."""
    dlat, dlon = radians(b.lat - a.lat), radians(b.lon - a.lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))
