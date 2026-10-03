from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ADMIN = {"Authorization": "Bearer demo-admin"}
ANNA = {"Authorization": "Bearer demo-anna"}


def test_admin_extras_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    assert c.get("/api/v1/admin/places/plc_ice/confidence", headers=ADMIN).json()["overall"] == 0.5
    o = c.post("/api/v1/places/plc_mnk/observations", headers=ANNA, json={"feature": "ramp", "value": "no"}).json()
    f = c.post(f"/api/v1/admin/observations/{o['id']}/flag", headers=ADMIN, json={"reason": "spam"})
    assert f.status_code == 200 and f.json()["validation"]["status"] == "FLAGGED"
    req = c.post("/api/v1/owner/ownership-requests", headers=ANNA, json={"place_id": "plc_ice", "justification": "x"})
    assert req.status_code == 201
    pending = c.get("/api/v1/admin/ownership-requests", headers=ADMIN).json()["items"]
    assert [r["id"] for r in pending] == [req.json()["id"]]
    v = c.post(f"/api/v1/admin/ownership-requests/{req.json()['id']}/verify", headers=ADMIN, json={"approved": True})
    assert v.json()["status"] == "approved"
    assert c.post("/api/v1/admin/revalidate", headers=ADMIN).json()["places"] == 4
    m = c.post("/api/v1/admin/places/plc_camelot/merge", headers=ADMIN, json={"into_place_id": "plc_mnk"})
    assert m.status_code == 200 and c.get("/api/v1/places/plc_camelot").status_code == 404
    assert c.post("/api/v1/admin/revalidate", headers=ANNA).status_code == 403
