"""Demo scenario (README §1), end-to-end over HTTP. Steps share one app instance
and run in file order. xfail markers are removed feature by feature (TDD)."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from tests.conftest import NOW

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(auth_mode="demo", demo_now=NOW, media_dir=str(tmp_path_factory.mktemp("media")))
    return TestClient(create_app(settings))


@pytest.fixture(scope="module")
def ctx():
    return {}


def auth(username: str) -> dict:
    return {"Authorization": f"Bearer demo-{username}"}


def elevator(client) -> dict:
    groups = client.get("/api/v1/places/plc_mnk/accessibility").json()["groups"]
    return next(f for g in groups for f in g["features"] if f["key"] == "elevator")


def test_step0_reset(client):
    assert client.post("/api/v1/admin/demo/reset", headers=auth("admin")).status_code == 204
    assert client.post("/api/v1/admin/demo/reset", headers=auth("anna")).status_code == 403


def test_step1_search_step_free(client):
    r = client.get("/api/v1/places", params={"features": "step_free_entrance"})
    ids = {p["id"] for p in r.json()["items"]}
    assert ids == {"plc_mnk", "plc_ice"}


def test_step2_details(client):
    assert client.get("/api/v1/places/plc_mnk").json()["name"] == "Muzeum Narodowe w Krakowie"
    assert elevator(client)["state"] == "yes"


def test_step3_check_wheelchair_yes(client):
    r = client.get("/api/v1/places/plc_mnk/check", params={"profile": "wheelchair"})
    assert r.json()["answer"] == "yes"



def test_step4_anna_reports_broken_elevator(client, ctx):
    photo = client.post("/api/v1/uploads", headers=auth("anna"),
                        files={"file": ("winda.png", PNG, "image/png")})
    assert photo.status_code == 201
    r = client.post("/api/v1/reports", headers=auth("anna"), json={
        "place_id": "plc_mnk", "element": "elevator", "current_state": "not_working",
        "severity": "critical", "nature": "temporary",
        "description": "Winda przy wejściu głównym nieczynna, kartka o awarii.",
        "photo_ids": [photo.json()["id"]],
    })
    assert r.status_code == 201
    ctx["anna_obs"] = r.json()["observation_ids"][0]
    state = elevator(client)
    assert (state["state"], state["temporary"], state["confidence"]) == ("no", True, 0.6)



def test_step5_three_confirmations(client, ctx):
    for voter in ("jan", "ola", "piotr"):
        r = client.post(f"/api/v1/observations/{ctx['anna_obs']}/votes", headers=auth(voter), json={"value": 1})
        assert r.status_code == 200
    assert elevator(client)["confidence"] == 0.9
    r = client.get("/api/v1/places/plc_mnk/check", params={"profile": "wheelchair"})
    assert r.json()["answer"] == "partial"



def test_step6_marek_contradicts_conflict(client, ctx):
    r = client.post("/api/v1/places/plc_mnk/observations", headers=auth("marek"),
                    json={"feature": "elevator", "value": "yes", "comment": "Winda działa"})
    assert r.status_code == 201
    ctx["marek_obs"] = r.json()["id"]
    state = elevator(client)
    assert (state["state"], state["validation"]) == ("no", "CONFLICT")
    q = client.get("/api/v1/admin/queue", params={"filter": "conflict"}, headers=auth("admin")).json()
    assert len(q["items"]) == 1
    ctx["queue_id"] = q["items"][0]["id"]



def test_step7_admin_confirms(client, ctx):
    r = client.post(f"/api/v1/admin/queue/{ctx['queue_id']}/decision", headers=auth("admin"),
                    json={"action": "confirm", "winning_observation_id": ctx["marek_obs"]})
    assert r.status_code == 200
    state = elevator(client)
    assert (state["state"], state["confidence"], state["validation"]) == ("yes", 1.0, "VALID")
    r = client.get("/api/v1/places/plc_mnk/check", params={"profile": "wheelchair"})
    assert r.json()["answer"] == "yes"
