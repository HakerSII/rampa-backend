"""Live OpenStreetMap adapters (F27): Nominatim geocoder + Overpass POI source, with offline fallback.
OSM usage policy: identifying User-Agent, low volume (search box + admin-triggered import only)."""
import asyncio
import logging
import time

import httpx

from app.application.ports import OsmSource
from app.domain.model import GeocodeHit, GeoPoint
from app.domain.osm import OsmPoint

log = logging.getLogger(__name__)

CATEGORY_TAGS = ("amenity", "tourism", "shop", "leisure", "office", "public_transport")


class _LazyClient:
    """httpx client built on first use (an SSL context per app start would slow every boot / test)."""

    def __init__(self, user_agent: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None):
        self._args = {"headers": {"User-Agent": user_agent}, "timeout": timeout_s, "transport": transport}
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(**self._args)
        return self._client


class NominatimGeocoder(_LazyClient):
    def __init__(self, url: str, user_agent: str, *, timeout_s: float = 10.0, viewbox: str = "",
                 transport: httpx.AsyncBaseTransport | None = None, min_interval_s: float = 1.1):
        super().__init__(user_agent, timeout_s, transport)
        self.url, self.viewbox = url, viewbox  # lon1,lat1,lon2,lat2 from the city config (F37); "" = unbounded
        self.min_interval_s = min_interval_s  # usage policy: at most 1 request per second
        self._last = 0.0
        self._turn = asyncio.Lock()

    async def search(self, q: str) -> list[GeocodeHit]:
        params = {"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "pl", "accept-language": "pl"}
        if self.viewbox:
            params |= {"viewbox": self.viewbox, "bounded": 1}
        async with self._turn:
            wait = self._last + self.min_interval_s - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                r = await self.client.get(self.url, params=params)
            finally:
                self._last = time.monotonic()
        r.raise_for_status()
        return [GeocodeHit(row.get("display_name") or q, None, GeoPoint(float(row["lat"]), float(row["lon"])))
                for row in r.json() if row.get("lat") is not None and row.get("lon") is not None]


class OverpassOsmSource(_LazyClient):
    """Named POIs with wheelchair / toilets:wheelchair tags around a centre point."""

    def __init__(self, url: str, lat: float, lon: float, radius_m: int, user_agent: str, *,
                 timeout_s: float = 30.0, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(user_agent, timeout_s, transport)
        self.url = url
        self.query = (f"[out:json][timeout:{int(timeout_s)}];"
                      f'(nwr["wheelchair"](around:{radius_m},{lat},{lon});'
                      f'nwr["toilets:wheelchair"](around:{radius_m},{lat},{lon}););out center tags;')

    async def fetch(self) -> list[OsmPoint]:
        r = await self.client.post(self.url, data={"data": self.query})
        r.raise_for_status()
        points = []
        for el in r.json().get("elements", []):
            geo = el if "lat" in el else el.get("center") or {}
            if geo.get("lat") is None or geo.get("lon") is None:
                continue
            tags = el.get("tags", {})
            category = next((tags[t] for t in CATEGORY_TAGS if tags.get(t)), "inne")
            points.append(OsmPoint(tags.get("name", ""), tags.get("wheelchair", ""),
                                   tags.get("toilets:wheelchair", ""), category, float(geo["lat"]), float(geo["lon"]),
                                   tags.get("changing_table", ""), tags.get("dog", "")))
        return points


class FallbackOsmSource:
    """Live source first; error or empty answer → offline snapshot. `last_source` says which one answered."""

    def __init__(self, live: OsmSource, offline: OsmSource):
        self.live, self.offline = live, offline
        self.last_source = "overpass"

    async def fetch(self) -> list[OsmPoint]:
        try:
            points = await self.live.fetch()
        except Exception as e:  # noqa: BLE001 — any network / parse failure → offline data
            log.warning("overpass failed (%s) → offline snapshot", e)
            points = []
        if points:
            self.last_source = "overpass"
            return points
        self.last_source = "osm_file (fallback)"
        return await self.offline.fetch()
