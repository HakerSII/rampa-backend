from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ANNA = {"Authorization": "Bearer demo-anna"}
KEY = {"X-Api-Key": "demo-key"}


def test_partial_place_type_valid_until_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    r = c.post("/api/v1/places/plc_ice/observations", headers=ANNA, json={"feature": "step_free_entrance",
                                                                         "value": "partial"})
    assert r.status_code == 201 and r.json()["value"] == "partial"
    flat = c.get("/public/v1/places/plc_ice/accessibility", headers=KEY).json()["accessibility"]
    assert flat["step_free_entrance"]["value"] == "partial"
    assert [p["id"] for p in c.get("/api/v1/places", params={"place_type": "office"}).json()["items"]] == ["plc_urzad"]
    assert c.get("/api/v1/places/plc_urzad").json()["place_type"] == "office"
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    o = c.post("/api/v1/places/plc_mnk/observations", headers=ANNA,
               json={"feature": "elevator", "value": "no", "temporary": True, "valid_until": future})
    assert o.status_code == 201 and o.json()["valid_until"]
    past = c.post("/api/v1/places/plc_mnk/observations", headers=ANNA,
                  json={"feature": "elevator", "value": "no", "valid_until": "2000-01-01T00:00:00+00:00"})
    assert past.status_code == 400
