"""REPO_MODE=sql over HTTP: data survives an app restart (new create_app on the same DB file)."""
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from tests.conftest import NOW

ANNA = {"Authorization": "Bearer demo-anna"}
ADMIN = {"Authorization": "Bearer demo-admin"}


def app(tmp_path):
    return TestClient(create_app(Settings(repo_mode="sql", database_url=f"sqlite:///{tmp_path / 'r.db'}",
                                          demo_now=NOW, media_dir=str(tmp_path / "m"))))


def elevator(c):
    groups = c.get("/api/v1/places/plc_mnk/accessibility").json()["groups"]
    return next(f for g in groups for f in g["features"] if f["key"] == "elevator")


def test_report_survives_restart_and_reset_wipes(tmp_path):
    c = app(tmp_path)
    assert c.get("/health").json()["storage"] == "sql"
    r = c.post("/api/v1/places/plc_mnk/observations", headers=ANNA,
               json={"feature": "elevator", "value": "no", "temporary": True})
    assert r.status_code == 201

    restarted = app(tmp_path)
    assert elevator(restarted)["state"] == "no"
    obs = restarted.get("/api/v1/places/plc_mnk/observations", params={"feature": "elevator"}).json()["items"]
    assert any(o["id"] == r.json()["id"] for o in obs)

    assert restarted.post("/api/v1/admin/demo/reset", headers=ADMIN).status_code == 204
    assert elevator(app(tmp_path))["state"] == "yes"


def test_osm_import_survives_restart(tmp_path):
    c = app(tmp_path)
    c.post("/api/v1/admin/imports", headers=ADMIN, json={"source": "osm_file"})
    assert len(app(tmp_path).get("/api/v1/places", params={"q": "tauron"}).json()["items"]) == 3
