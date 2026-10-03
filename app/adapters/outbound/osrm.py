"""OSRM walking router (F28). Default server: FOSSGIS routed-foot (real pedestrian profile).
Errors raise; `NoRoute` → None; the use case falls back to the straight line."""
import httpx

from app.adapters.outbound.osm_live import _LazyClient
from app.domain.model import GeoPoint
from app.domain.route import RoutePath


class OsrmRouter(_LazyClient):
    def __init__(self, base_url: str, user_agent: str, *, timeout_s: float = 10.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(user_agent, timeout_s, transport)
        self.base_url = base_url.rstrip("/")

    async def walk(self, a: GeoPoint, b: GeoPoint) -> RoutePath | None:
        url = f"{self.base_url}/route/v1/foot/{a.lon},{a.lat};{b.lon},{b.lat}"
        r = await self.client.get(url, params={"overview": "full", "geometries": "geojson"})
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        points = [GeoPoint(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
        return RoutePath(points, int(route["distance"]), int(route["duration"]))
