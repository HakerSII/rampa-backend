from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ANNA = {"Authorization": "Bearer demo-anna"}


def test_map_observations_endpoint(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    c.post("/api/v1/reports", headers=ANNA, json={
        "place_id": "plc_camelot", "element": "ramp", "current_state": "not_working", "severity": "obstacle",
        "nature": "temporary", "description": "Podjazd zastawiony"})
    fresh = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()  # skip seeded "no"s of Urząd
    r = c.get("/api/v1/observations", params={"bbox": "19.93,50.055,19.95,50.07", "value": "no", "since": fresh})
    assert r.status_code == 200
    (item,) = r.json()["items"]
    assert item["place"] == {"id": "plc_camelot", "name": "Cafe Camelot",
                             "location": {"lat": 50.0628, "lon": 19.9383}}
    assert (item["severity"], item["feature"], item["value"], item["temporary"]) == ("obstacle", "ramp", "no", True)
    assert r.json()["total"] == 1
    assert c.get("/api/v1/observations", params={"bbox": "bad"}).status_code == 400


def test_since_with_unencoded_plus_in_query(tmp_path):
    # "+00:00" in a URL arrives as " 00:00" — must still parse (front-end clients rarely encode "+")
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    assert c.get("/api/v1/observations?since=2026-01-01T00:00:00+00:00").status_code == 200
    assert c.get("/api/v1/observations?since=2026-01-01T00:00:00Z").status_code == 200


def test_exclude_source_hides_imported_open_data(tmp_path):
    """The app's barrier list asks without open data: OSM / catalogue facts are place features, not reports."""
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path), _env_file=None)))
    c.post("/api/v1/admin/imports", headers={"Authorization": "Bearer demo-admin"}, json={"source": "osm_file"})
    everything = c.get("/api/v1/observations", params={"limit": 500}).json()["items"]
    assert any(o["source"] == "open_data" for o in everything)
    reports = c.get("/api/v1/observations", params={"limit": 500, "exclude_source": "open_data"}).json()["items"]
    assert reports and all(o["source"] != "open_data" for o in reports)
    assert c.get("/api/v1/observations", params={"exclude_source": "nonsense"}).status_code == 400
