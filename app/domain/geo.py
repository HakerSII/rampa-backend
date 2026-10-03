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


def distance_to_segment_m(p: GeoPoint, a: GeoPoint, b: GeoPoint) -> float:
    """Distance from p to segment a–b in meters (local equirectangular projection; fine for city scale)."""
    k = 111_320.0
    c = cos(radians((a.lat + b.lat) / 2))
    ax, ay, bx, by = a.lon * k * c, a.lat * k, b.lon * k * c, b.lat * k
    px, py = p.lon * k * c, p.lat * k
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5
