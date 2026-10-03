from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings


def client(tmp_path):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))


def test_places_near_with_distance_and_pagination(tmp_path):
    r = client(tmp_path).get("/api/v1/places", params={"lat": 50.0617, "lon": 19.9373, "page_size": 2}).json()
    assert [p["id"] for p in r["items"]] == ["plc_camelot", "plc_urzad"]
    assert r["items"][0]["distance_m"] == 142 and (r["page"], r["page_size"], r["total"]) == (1, 2, 4)


def test_map_view_markers(tmp_path):
    r = client(tmp_path).get("/api/v1/places", params={"view": "map"}).json()
    assert {m["id"]: m["marker"] for m in r["items"]} == {
        "plc_mnk": "accessible", "plc_camelot": "accessible", "plc_ice": "partial", "plc_urzad": "inaccessible"}


def test_old_calls_unchanged_and_errors(tmp_path):
    c = client(tmp_path)
    r = c.get("/api/v1/places", params={"features": "step_free_entrance"}).json()
    assert {p["id"] for p in r["items"]} == {"plc_mnk", "plc_ice"} and r["items"][0]["distance_m"] is None
    assert c.get("/api/v1/places", params={"sort": "nearest"}).status_code == 400
    assert c.get("/api/v1/places", params={"lat": 50.06}).status_code == 400  # lon missing


def test_categories_and_geocode(tmp_path):
    c = client(tmp_path)
    cats = c.get("/api/v1/categories").json()
    assert {"key": "museum", "label": "Muzeum", "count": 1} in cats
    g = c.get("/api/v1/geocode", params={"q": "muzeum"}).json()
    assert g[0]["place_id"] == "plc_mnk" and g[0]["location"]["lat"] == 50.0603
    assert c.get("/api/v1/geocode", params={"q": "m"}).status_code == 400
