from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ANNA = {"Authorization": "Bearer demo-anna"}


def test_me_endpoints(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    assert c.put("/api/v1/me/favorites/plc_mnk", headers=ANNA).status_code == 204
    fav = c.get("/api/v1/me/favorites", headers=ANNA).json()["items"]
    assert [p["id"] for p in fav] == ["plc_mnk"] and fav[0]["verification"]["label"]
    assert c.delete("/api/v1/me/favorites/plc_mnk", headers=ANNA).status_code == 204
    assert c.get("/api/v1/me/favorites", headers=ANNA).json()["items"] == []
    assert c.put("/api/v1/me/favorites/nope", headers=ANNA).status_code == 404
    assert c.get("/api/v1/me/favorites").status_code == 401
    assert c.get("/api/v1/me/reports", headers=ANNA).json()["items"] == []
