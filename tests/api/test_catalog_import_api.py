"""F49 over HTTP: POST /admin/imports {"source": "catalog"} loads CATALOG_FILE (default data/krakow_catalog.json)."""
import json

from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ADMIN = {"Authorization": "Bearer demo-admin"}


def client(tmp_path, **kw):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path), _env_file=None, **kw)))


def test_catalog_source_imports_the_file(tmp_path):
    f = tmp_path / "catalog.json"
    f.write_text(json.dumps([{"ref": "osm:node/7", "name": "Bar Testowy", "category": "bar", "lat": 50.07, "lon": 19.95,
                              "features": {"step_free_entrance": "yes"}}]), encoding="utf-8")
    c = client(tmp_path, catalog_file=str(f))
    r = c.post("/api/v1/admin/imports", headers=ADMIN, json={"source": "catalog"})
    assert r.status_code == 200
    assert r.json()["source"] == "catalog" and r.json()["places_created"] == 1
    found = c.get("/api/v1/places", params={"q": "Bar Testowy", "lat": 50.07, "lon": 19.95}).json()
    assert found["items"][0]["name"] == "Bar Testowy"


def test_missing_catalog_file_is_400(tmp_path):
    c = client(tmp_path, catalog_file=str(tmp_path / "nope.json"))
    r = c.post("/api/v1/admin/imports", headers=ADMIN, json={"source": "catalog"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_shipped_catalog_is_the_full_main_branch_catalogue():
    from pathlib import Path
    data = json.loads((Path(__file__).parents[2] / "data" / "krakow_catalog.json").read_text(encoding="utf-8"))
    assert len(data) > 6000
    assert sum(1 for e in data if e["features"]) > 1400
    assert {"ref", "name", "category", "lat", "lon", "features"} <= set(data[0])
