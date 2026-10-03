from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

H = lambda u: {"Authorization": f"Bearer demo-{u}"}  # noqa: E731


def test_abuse_and_escalate_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    o = c.post("/api/v1/places/plc_camelot/observations", headers=H("marek"),
               json={"feature": "ramp", "value": "no"}).json()
    r = c.post(f"/api/v1/observations/{o['id']}/abuse", headers=H("anna"), json={"reason": "spam"})
    assert r.status_code == 201 and r.json()["type"] == "abuse"
    assert c.post(f"/api/v1/observations/{o['id']}/abuse", headers=H("anna"), json={"reason": "x"}).status_code == 409
    q = c.get("/api/v1/admin/queue", params={"filter": "abuse"}, headers=H("admin")).json()
    assert q["counts"]["abuse"] == 1
    item_id = q["items"][0]["id"]
    e = c.post(f"/api/v1/admin/queue/{item_id}/decision", headers=H("admin"), json={"action": "escalate"})
    assert e.json()["status"] == "escalated"
    d = c.post(f"/api/v1/admin/queue/{item_id}/decision", headers=H("admin"), json={"action": "confirm"})
    assert d.json()["status"] == "approved"
    obs = c.get("/api/v1/places/plc_camelot/observations", params={"active": "false"}).json()["items"]
    assert next(x for x in obs if x["id"] == o["id"])["validation"]["status"] == "FLAGGED"
