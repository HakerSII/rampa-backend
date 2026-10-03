"""F12: the map front end's path over HTTP — anonymous device identity, pin → place, report, vote."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from tests.conftest import NOW

PIN = {"name": "Rondo Mogilskie", "lat": 50.0656, "lon": 19.9585}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(auth_mode="demo", demo_now=NOW, media_dir=str(tmp_path))))


def device(client, name=None) -> dict:
    body = {"display_name": name} if name else {}
    r = client.post("/api/v1/auth/anonymous", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["role"] == "user" and r.json()["token"]
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_anonymous_login_is_a_real_user(client):
    headers = device(client, "Gość")
    me = client.get("/api/v1/me", headers=headers).json()
    assert (me["display_name"], me["role"], me["email"]) == ("Gość", "user", None)


def test_anonymous_login_can_be_disabled(tmp_path):
    client = TestClient(create_app(Settings(anonymous_auth=False, media_dir=str(tmp_path))))
    assert client.post("/api/v1/auth/anonymous", json={}).status_code == 404


def test_resolve_needs_login_and_validates(client):
    assert client.post("/api/v1/places/resolve", json=PIN).status_code == 401
    r = client.post("/api/v1/places/resolve", json={"name": "", "lat": 1, "lon": 2}, headers=device(client))
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_resolve_creates_then_matches(client):
    a, b = device(client), device(client)
    r1 = client.post("/api/v1/places/resolve", json=PIN, headers=a)
    assert r1.status_code == 201 and r1.json()["created"] is True
    place = r1.json()["place"]
    assert place["name"] == "Rondo Mogilskie" and place["location"] == {"lat": 50.0656, "lon": 19.9585}
    assert place["category"] == {"key": "other", "label": "Inne"}

    r2 = client.post("/api/v1/places/resolve", json={**PIN, "lat": 50.0657}, headers=b)
    assert r2.status_code == 200 and r2.json()["created"] is False
    assert r2.json()["place"]["id"] == place["id"]
    assert client.get(f"/api/v1/places/{place['id']}").status_code == 200


def test_report_and_vote_between_two_devices(client):
    a, b = device(client), device(client)
    place_id = client.post("/api/v1/places/resolve", json=PIN, headers=a).json()["place"]["id"]
    r = client.post("/api/v1/reports", headers=a, json={
        "place_id": place_id, "element": "elevator", "current_state": "not_working",
        "severity": "critical", "nature": "temporary", "description": "Winda nie działa."})
    assert r.status_code == 201, r.text
    (obs_id,) = r.json()["observation_ids"]

    # the reporting device cannot confirm its own report, another device can
    assert client.post(f"/api/v1/observations/{obs_id}/votes", headers=a, json={"value": 1}).status_code == 400
    v = client.post(f"/api/v1/observations/{obs_id}/votes", headers=b, json={"value": 1})
    assert v.status_code == 200 and v.json()["observation"]["votes"] == {"up": 1, "down": 0, "my_vote": 1}
    assert v.json()["feature_state"]["state"] == "no" and v.json()["feature_state"]["confidence"] == 0.6

    # guests still read everything
    obs = client.get(f"/api/v1/places/{place_id}/observations").json()["items"]
    assert [o["id"] for o in obs] == [obs_id] and obs[0]["author"]["display_name"] == "Anonim"


def test_undecodable_body_is_a_validation_error(client):
    """Starlette's own 400 (body not UTF-8) must map to VALIDATION_ERROR, not to another 400 code."""
    r = client.post("/api/v1/places/resolve", headers={**device(client), "Content-Type": "application/json"},
                    content=b'{"name": "\xff"}')
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
