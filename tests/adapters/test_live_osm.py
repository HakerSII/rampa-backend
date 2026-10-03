"""F27: live Nominatim geocoder + Overpass OSM source (httpx.MockTransport — no network)."""
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.adapters.outbound.osm_live import FallbackOsmSource, NominatimGeocoder, OverpassOsmSource
from app.domain.osm import OsmPoint

NOMINATIM = [
    {"display_name": "Tauron Arena Kraków, Stanisława Lema 7, Kraków", "lat": "50.0675", "lon": "19.9915"},
    {"display_name": "bad row", "lat": None, "lon": "19.9"},
]
OVERPASS = {"elements": [
    {"type": "node", "lat": 50.06, "lon": 19.94,
     "tags": {"name": "Kawiarnia A", "amenity": "cafe", "wheelchair": "yes", "toilets:wheelchair": "no"}},
    {"type": "way", "center": {"lat": 50.07, "lon": 19.95}, "tags": {"name": "Muzeum B", "tourism": "museum",
                                                                    "wheelchair": "limited"}},
    {"type": "node", "lat": 50.0, "lon": 19.0, "tags": {"wheelchair": "yes"}},  # unnamed → kept, import skips it
    {"type": "way", "tags": {"name": "No geometry"}},
]}


def transport(payload, status=200, seen=None):
    def handler(request: httpx.Request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(handler)


async def test_nominatim_maps_results_and_sends_user_agent():
    seen = []
    g = NominatimGeocoder("https://nominatim.example/search", "RampaTest/1.0", transport=transport(NOMINATIM, seen=seen))
    hits = await g.search("tauron")
    assert [(h.label, h.location.lat, h.location.lon) for h in hits] == [
        ("Tauron Arena Kraków, Stanisława Lema 7, Kraków", 50.0675, 19.9915)]
    assert hits[0].place_id is None
    req = seen[0]
    assert req.headers["user-agent"] == "RampaTest/1.0"
    assert req.url.params["q"] == "tauron" and req.url.params["format"] == "jsonv2"
    assert req.url.params["viewbox"] and req.url.params["bounded"] == "1"  # limited to Kraków


async def test_nominatim_http_error_raises():
    g = NominatimGeocoder("https://nominatim.example/search", "x", transport=transport({}, status=503))
    with pytest.raises(httpx.HTTPError):
        await g.search("tauron")


async def test_overpass_maps_nodes_and_way_centers():
    seen = []
    src = OverpassOsmSource("https://overpass.example/api/interpreter", 50.0647, 19.945, 1500, "RampaTest/1.0",
                            transport=transport(OVERPASS, seen=seen))
    points = await src.fetch()
    assert points == [
        OsmPoint("Kawiarnia A", "yes", "no", "cafe", 50.06, 19.94),
        OsmPoint("Muzeum B", "limited", "", "museum", 50.07, 19.95),
        OsmPoint("", "yes", "", "inne", 50.0, 19.0),
    ]
    body = parse_qs(seen[0].content.decode())["data"][0]  # form-encoded
    assert "around:1500,50.0647,19.945" in body and "wheelchair" in body


class Boom:
    async def fetch(self):
        raise httpx.ConnectError("offline")


class Fixed:
    def __init__(self, points):
        self.points = points

    async def fetch(self):
        return self.points


async def test_fallback_uses_file_when_live_fails_or_is_empty():
    p = [OsmPoint("A", "yes", "", "cafe", 50.0, 19.9)]
    src = FallbackOsmSource(Boom(), Fixed(p))
    assert await src.fetch() == p and src.last_source == "osm_file (fallback)"
    src = FallbackOsmSource(Fixed([]), Fixed(p))
    assert await src.fetch() == p and src.last_source == "osm_file (fallback)"
    src = FallbackOsmSource(Fixed(p), Fixed([]))
    assert await src.fetch() == p and src.last_source == "overpass"


def test_overpass_payload_fixture_is_json():
    json.dumps(OVERPASS)  # keeps the fixture honest
