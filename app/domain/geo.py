from math import asin, cos, radians, sin, sqrt

from app.domain.model import GeoPoint

EARTH_RADIUS_M = 6_371_000


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance in meters."""
    dlat, dlon = radians(b.lat - a.lat), radians(b.lon - a.lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))


BBox = tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat


def parse_bbox(raw: str) -> BBox:
    """'minLon,minLat,maxLon,maxLat' → tuple. Raises ValueError."""
    parts = [float(x) for x in raw.split(",")]
    if len(parts) != 4 or parts[0] > parts[2] or parts[1] > parts[3]:
        raise ValueError("bbox must be minLon,minLat,maxLon,maxLat")
    return parts[0], parts[1], parts[2], parts[3]


def in_bbox(p: GeoPoint, b: BBox) -> bool:
    return b[0] <= p.lon <= b[2] and b[1] <= p.lat <= b[3]
