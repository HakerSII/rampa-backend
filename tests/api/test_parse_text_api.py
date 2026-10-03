from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ANNA = {"Authorization": "Bearer demo-anna"}


def test_parse_text_endpoint(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    r = c.post("/api/v1/ai/parse-text", headers=ANNA, json={"text": "winda od dwóch tygodni nie działa"}).json()
    assert r["model"] == "rules"
    assert r["suggestions"] == [{"feature": "elevator", "label": "Winda", "value": "no", "temporary": True,
                                 "confidence": 0.8}]
    assert c.post("/api/v1/ai/parse-text", headers=ANNA, json={"text": ""}).status_code == 400
    assert c.post("/api/v1/ai/parse-text", headers=ANNA, json={"text": "x" * 1001}).status_code == 400
    assert c.post("/api/v1/ai/parse-text", json={"text": "winda"}).status_code == 401
