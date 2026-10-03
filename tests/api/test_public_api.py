"""F5 Open API: X-Api-Key, flat accessibility, rate limit, same data as internal API."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from tests.conftest import NOW

KEY = {"X-Api-Key": "test-key"}


@pytest.fixture
def client(tmp_path):
    settings = Settings(auth_mode="demo", demo_now=NOW, media_dir=str(tmp_path),
                        public_api_keys="test-key,other-key", public_rate_limit_per_min=100)
    return TestClient(create_app(settings))


@pytest.mark.parametrize("headers", [{}, {"X-Api-Key": "wrong"}])
def test_missing_or_wrong_key_is_unauthorized(client, headers):
    r = client.get("/public/v1/places", headers=headers)
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_internal_bearer_token_is_not_an_api_key(client):
    assert client.get("/public/v1/places", headers={"Authorization": "Bearer demo-admin"}).status_code == 401


def test_search_with_features(client):
    r = client.get("/public/v1/places", params={"features": "step_free_entrance"}, headers=KEY)
    assert {p["id"] for p in r.json()["items"]} == {"plc_mnk", "plc_ice"}
    assert r.json()["total"] == 2


def test_place_and_404(client):
    assert client.get("/public/v1/places/plc_mnk", headers=KEY).json()["name"] == "Muzeum Narodowe w Krakowie"
    assert client.get("/public/v1/places/nope", headers=KEY).status_code == 404


def test_flat_accessibility_maps_yes_no_and_omits_unknown(client):
    mnk = client.get("/public/v1/places/plc_mnk/accessibility", headers=KEY).json()
    assert mnk["place"] == {"id": "plc_mnk", "name": "Muzeum Narodowe w Krakowie"}
    assert mnk["accessibility"]["elevator"] == {
        "value": True, "temporary": False, "confidence": 0.5, "last_verified": "2026-08-04"}

    ice = client.get("/public/v1/places/plc_ice/accessibility", headers=KEY).json()["accessibility"]
    assert ice["elevator"]["value"] is False

    camelot = client.get("/public/v1/places/plc_camelot/accessibility", headers=KEY).json()["accessibility"]
    assert set(camelot) == {"ramp"}  # toilet etc. unknown → omitted


def test_check(client):
    r = client.get("/public/v1/places/plc_ice/check", params={"profile": "wheelchair"}, headers=KEY).json()
    assert (r["answer"], r["place_id"]) == ("partial", "plc_ice")


def test_community_report_is_visible_in_public_api(client):
    client.post("/api/v1/places/plc_mnk/observations", headers={"Authorization": "Bearer demo-anna"},
                json={"feature": "elevator", "value": "no", "temporary": True})
    elevator = client.get("/public/v1/places/plc_mnk/accessibility", headers=KEY).json()["accessibility"]["elevator"]
    assert (elevator["value"], elevator["temporary"]) == (False, True)


def test_rate_limit_per_key(tmp_path):
    settings = Settings(media_dir=str(tmp_path), public_api_keys="a,b", public_rate_limit_per_min=3)
    c = TestClient(create_app(settings))
    for _ in range(3):
        assert c.get("/public/v1/places", headers={"X-Api-Key": "a"}).status_code == 200
    r = c.get("/public/v1/places", headers={"X-Api-Key": "a"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) > 0
    assert c.get("/public/v1/places", headers={"X-Api-Key": "b"}).status_code == 200  # separate bucket
