"""F51: find a location (like the UI's search box: places of the database, then Nominatim) and the places within
500 m of it — Open API + MCP tools (clients/rampa_tools.py) against the real app via ASGI."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from app.domain.model import GeocodeHit, GeoPoint
from clients.rampa_tools import TOOL_DEFS, RampaTools
from tests.conftest import NOW

KEY = {"X-Api-Key": "k"}
MNK = (50.0603, 19.9238)


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(demo_now=NOW, media_dir=str(tmp_path), public_api_keys="k", _env_file=None))


def tools(app) -> RampaTools:
    return RampaTools(httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test"), api_key="k")


def test_public_geocode_finds_a_place_of_the_database(app):
    r = TestClient(app).get("/public/v1/geocode", params={"q": "muzeum narodowego"}, headers=KEY)
    assert r.status_code == 200
    hit = r.json()["items"][0]
    assert hit["place_id"] == "plc_mnk" and abs(hit["lat"] - MNK[0]) < 1e-3 and "Muzeum Narodowe" in hit["label"]


def test_public_geocode_needs_the_api_key(app):
    assert TestClient(app).get("/public/v1/geocode", params={"q": "muzeum"}).status_code == 401


def test_public_nearby_sorted_by_distance_within_radius(app):
    c = TestClient(app)
    r = c.get("/public/v1/places/nearby", params={"lat": MNK[0], "lon": MNK[1], "radius_m": 500}, headers=KEY).json()
    assert r["items"][0]["id"] == "plc_mnk" and r["items"][0]["distance_m"] == 0
    assert all(i["distance_m"] <= 500 for i in r["items"])
    assert [i["distance_m"] for i in r["items"]] == sorted(i["distance_m"] for i in r["items"])
    far = c.get("/public/v1/places/nearby", params={"lat": 50.0, "lon": 19.0, "radius_m": 500}, headers=KEY).json()
    assert far["items"] == []


def test_public_nearby_validates_radius(app):
    r = TestClient(app).get("/public/v1/places/nearby", params={"lat": 50, "lon": 19, "radius_m": 99999}, headers=KEY)
    assert r.status_code == 400


async def test_tool_find_location(app):
    r = await tools(app).find_location("Muzeum Narodowe")
    assert r["locations"][0]["place_id"] == "plc_mnk" and {"lat", "lon", "label"} <= set(r["locations"][0])


async def test_tool_find_location_uses_the_geocoder(app, monkeypatch):
    class Geo:
        async def search(self, q):
            return [GeocodeHit("Plac Świętego Ducha 1, Kraków", None, GeoPoint(50.0638, 19.9437))]

    app.state.use_cases.geocoder = Geo()
    r = await tools(app).find_location("plac świętego ducha 1")
    assert r["locations"][0]["label"].startswith("Plac Świętego Ducha") and r["locations"][0]["place_id"] is None


async def test_tool_places_nearby(app):
    r = await tools(app).places_nearby(*MNK, radius_m=500)
    assert r["radius_m"] == 500 and r["places"][0]["name"].startswith("Muzeum Narodowe")
    assert {"distance_m", "address", "accessibility_summary"} <= set(r["places"][0])


async def test_tools_dispatch_and_definitions(app):
    assert {t["name"] for t in TOOL_DEFS} >= {"find_location", "places_nearby"}
    r = await tools(app).call("places_nearby", {"lat": MNK[0], "lon": MNK[1]})
    assert r["radius_m"] == 500  # default radius
    assert "error" in await tools(app).call("places_nearby", {"lat": "x"})
