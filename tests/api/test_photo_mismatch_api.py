"""F45 over HTTP: upload 201 with metadata, then the (streamed) check fails with PHOTO_MISMATCH and the photo is gone."""
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from tests.api.test_vision_stream_api import events
from tests.application.test_observations import PNG

ANNA = {"Authorization": "Bearer demo-anna"}


def client(tmp_path):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))


def upload(c, name, **meta):
    return c.post("/api/v1/uploads", headers=ANNA, data=meta, files={"file": (name, PNG, "image/png")})


def test_upload_with_metadata_is_201(tmp_path):
    r = upload(client(tmp_path), "winda.png", place_id="plc_mnk", element="elevator", current_state="not_working")
    assert r.status_code == 201
    assert {k: r.json()[k] for k in ("place_id", "element", "current_state")} == {
        "place_id": "plc_mnk", "element": "elevator", "current_state": "not_working"}


def test_upload_with_bad_metadata_is_400(tmp_path):
    r = upload(client(tmp_path), "winda.png", element="teleport")
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_stream_mismatch_is_an_error_event_and_the_photo_is_deleted(tmp_path):
    c = client(tmp_path)
    ph = upload(c, "winda.png", element="ramp").json()
    assert c.get(ph["url"]).status_code == 200
    r = c.post("/api/v1/ai/image-tags/stream", headers=ANNA, json={"photo_ids": [ph["id"]]})
    name, data = [e for e in events(r.text) if e[0] != "comment"][-1]
    assert name == "error" and data["error"]["code"] == "PHOTO_MISMATCH"
    assert data["error"]["details"]["deleted_photo_ids"] == [ph["id"]]
    assert c.get(ph["url"]).status_code == 404


def test_plain_mismatch_is_400_with_details(tmp_path):
    c = client(tmp_path)
    ph = upload(c, "winda.png").json()
    r = c.post("/api/v1/ai/image-tags", headers=ANNA,
               json={"photo_ids": [ph["id"]], "expected": {"element": "ramp", "current_state": None}})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "PHOTO_MISMATCH" and err["details"]["suggested"]["element"] == "elevator"


def test_match_streams_the_result(tmp_path):
    c = client(tmp_path)
    ph = upload(c, "winda.png", element="elevator", current_state="not_working").json()
    r = c.post("/api/v1/ai/image-tags/stream", headers=ANNA, json={"photo_ids": [ph["id"]]})
    assert [e for e in events(r.text) if e[0] != "comment"][-1][0] == "result"
