from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings


def test_similar_and_route_endpoints(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    sim = c.get("/api/v1/places/plc_mnk/similar", params={"limit": 2}).json()["items"]
    assert [(p["id"], p["distance_m"]) for p in sim] == [("plc_camelot", 1072), ("plc_ice", 1496)]
    r = c.get("/api/v1/routes/accessible", params={"from": "plc_mnk", "to": "plc_urzad"}).json()
    assert r["feasible"] == "yes" and r["geometry"]["type"] == "LineString" and r["duration_min"] == 33
    assert r["helpers"][0]["name"] == "Urząd Dzielnicy I"
    assert c.get("/api/v1/routes/accessible", params={"from": "x", "to": "plc_urzad"}).status_code == 404
