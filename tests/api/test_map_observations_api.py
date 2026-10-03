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
