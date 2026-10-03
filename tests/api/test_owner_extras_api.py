from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

EWA = {"Authorization": "Bearer demo-ewa"}
ANNA = {"Authorization": "Bearer demo-anna"}


def test_owner_extras_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    assert c.get("/api/v1/owner/me", headers=EWA).json()["places"] == 2
    assert c.patch("/api/v1/owner/me", headers=EWA, json={"email": "ewa@mnk.pl"}).json()["email"] == "ewa@mnk.pl"
    assert c.get("/api/v1/owner/stats", headers=EWA).json()["managed_places"] == 2
    h = c.put("/api/v1/owner/places/plc_mnk/opening-hours", headers=EWA,
              json=[{"days": "Tue-Sun", "open": "10:00", "close": "18:00"}])
    assert h.status_code == 200 and c.get("/api/v1/places/plc_mnk").json()["opening_hours"][0]["open"] == "10:00"
    assert c.patch("/api/v1/owner/places/plc_mnk", headers=EWA, json={"address": "al. 3 Maja 1"}).status_code == 200
    rep = c.post("/api/v1/reports", headers=ANNA, json={
        "place_id": "plc_mnk", "element": "elevator", "current_state": "not_working", "severity": "critical",
        "nature": "temporary", "description": "Winda"}).json()
    assert c.post(f"/api/v1/owner/reports/{rep['id']}/reply", headers=EWA, json={"text": "OK"}).status_code == 201
    assert c.post(f"/api/v1/owner/reports/{rep['id']}/approve", headers=EWA).json()["source"] == "verified_owner"
    assert c.get("/api/v1/owner/reminders", headers=EWA).status_code == 200
    assert c.get("/api/v1/owner/suggestions", headers=EWA).status_code == 200
    assert c.get("/api/v1/owner/places/plc_mnk/stats", headers=EWA).json()["observations"] >= 10
    b = c.post("/api/v1/owner/observations/batch", headers=EWA,
               json=[{"place_id": "plc_camelot", "feature": "ramp", "value": "yes"}])
    assert b.status_code == 201
    t = c.get("/api/v1/owner/places/import/template", headers=EWA)
    assert t.headers["content-type"].startswith("text/csv")
    imp = c.post("/api/v1/owner/places/import", headers=EWA,
                 files={"file": ("u.csv", b"place_id,feature,value,temporary,comment\nplc_mnk,ramp,yes,false,\n",
                                 "text/csv")})
    assert imp.json() == {"imported": 1, "errors": []}
    assert c.get("/api/v1/owner/stats", headers=ANNA).status_code == 403
