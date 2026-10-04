"""F44: POST /ai/image-tags/stream — Server-Sent Events while the vision chain runs."""
import asyncio
import json

from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.adapters.inbound.http.routers import ai as ai_router
from app.adapters.outbound.vision_mock import MockVisionAnalyzer
from app.config import Settings
from tests.application.test_observations import PNG

ANNA = {"Authorization": "Bearer demo-anna"}


def client(tmp_path):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))


def upload(c, name):
    return c.post("/api/v1/uploads", headers=ANNA, files={"file": (name, PNG, "image/png")}).json()["id"]


def events(body: str):
    """[(event, data | None)] of an SSE body; comments become ("comment", text)."""
    out = []
    for block in body.split("\n\n"):
        lines = [line for line in block.split("\n") if line]
        if not lines:
            continue
        if all(line.startswith(":") for line in lines):
            out.append(("comment", lines[0][1:].strip()))
            continue
        name = next(line[7:] for line in lines if line.startswith("event: "))
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        out.append((name, json.loads(data) if data else None))
    return out


def test_stream_sends_status_then_the_result(tmp_path):
    c = client(tmp_path)
    photo = upload(c, "winda.png")
    r = c.post("/api/v1/ai/image-tags/stream", headers=ANNA, json={"photo_ids": [photo], "place_id": "plc_mnk"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    ev = [e for e in events(r.text) if e[0] != "comment"]
    assert ev[0] == ("status", {"stage": "received"})
    assert ev[-1][0] == "result"
    plain = c.post("/api/v1/ai/image-tags", headers=ANNA, json={"photo_ids": [photo], "place_id": "plc_mnk"}).json()
    assert ev[-1][1] == plain


def test_not_a_real_place_is_an_error_event(tmp_path):
    c = client(tmp_path)
    r = c.post("/api/v1/ai/image-tags/stream", headers=ANNA, json={"photo_ids": [upload(c, "screenshot.png")]})
    assert r.status_code == 200
    name, data = [e for e in events(r.text) if e[0] != "comment"][-1]
    assert name == "error" and data["error"]["code"] == "NOT_A_REAL_PLACE"


def test_validation_error_is_an_error_event(tmp_path):
    c = client(tmp_path)
    r = c.post("/api/v1/ai/image-tags/stream", headers=ANNA, json={"photo_ids": []})
    name, data = [e for e in events(r.text) if e[0] != "comment"][-1]
    assert name == "error" and data["error"]["code"] == "VALIDATION_ERROR"


def test_login_required_before_the_stream(tmp_path):
    c = client(tmp_path)
    r = c.post("/api/v1/ai/image-tags/stream", json={"photo_ids": ["ph_1"]})
    assert r.status_code == 401


def test_keepalive_while_a_slow_model_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_router, "KEEPALIVE_S", 0.02)
    original = MockVisionAnalyzer.analyze

    async def slow(self, image_path, original_name):
        await asyncio.sleep(0.15)
        return await original(self, image_path, original_name)

    monkeypatch.setattr(MockVisionAnalyzer, "analyze", slow)
    c = client(tmp_path)
    r = c.post("/api/v1/ai/image-tags/stream", headers=ANNA, json={"photo_ids": [upload(c, "winda.png")]})
    ev = events(r.text)
    assert ("comment", "keepalive") in ev and ev[-1][0] == "result"
