from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ANNA = {"Authorization": "Bearer demo-anna"}


def test_draft_flow_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    d = c.post("/api/v1/reports", headers=ANNA, json={"place_id": "plc_mnk", "draft": True})
    assert d.status_code == 201 and d.json()["status"] == "draft"
    rid = d.json()["id"]
    p = c.patch(f"/api/v1/reports/{rid}", headers=ANNA, json={
        "element": "ramp", "current_state": "not_working", "severity": "obstacle", "nature": "temporary",
        "description": "Podjazd zastawiony rowerami"})
    assert p.status_code == 200 and p.json()["element"] == "ramp"
    s = c.post(f"/api/v1/reports/{rid}/submit", headers=ANNA)
    assert s.status_code == 200 and s.json()["status"] == "submitted" and s.json()["observation_ids"]
    assert c.post(f"/api/v1/reports/{rid}/submit", headers=ANNA).status_code == 409
    incomplete = c.post("/api/v1/reports", headers=ANNA, json={"place_id": "plc_mnk"})
    assert incomplete.status_code == 400  # not a draft → full validation
