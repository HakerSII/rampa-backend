"""F42 XSS hardening (defence in depth — the front end must still render user text as text, never as HTML):
user text is stripped of HTML / angle brackets / control chars at the HTTP boundary, links must be http(s),
responses carry security headers (nosniff, strict CSP; sandboxed /media)."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.adapters.outbound.vision_prompt import parse_analysis
from app.config import Settings
from app.domain.text import clean_text
from tests.application.test_observations import user

ANNA = {"Authorization": "Bearer demo-anna"}
EWA = {"Authorization": "Bearer demo-ewa"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def c(tmp_path):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))


@pytest.mark.parametrize("raw, clean", [
    ("<script>alert(1)</script>Winda nie działa", "alert(1)Winda nie działa"),
    ('<img src=x onerror="alert(1)">', ""),
    ("<img src=x onerror=alert(1)", "img src=x onerror=alert(1)"),   # unclosed tag: brackets removed
    ("Podjazd <b>stromy</b>", "Podjazd stromy"),
    ("a\u0000b\u0007c", "abc"),                                       # control chars
    ("linia 1\nlinia 2\ttab", "linia 1\nlinia 2\ttab"),              # newlines / tabs kept
    ("Zażółć gęślą jaźń — 50% & więcej", "Zażółć gęślą jaźń — 50% & więcej"),
])
def test_clean_text(raw, clean):
    assert clean_text(raw) == clean


def test_observation_comment_is_cleaned(c):
    r = c.post("/api/v1/places/plc_mnk/observations", headers=ANNA,
               json={"feature": "ramp", "value": "no", "comment": "<script>alert(1)</script>Stromy"})
    assert r.status_code == 201 and r.json()["comment"] == "alert(1)Stromy"


def test_nested_and_list_strings_are_cleaned(c):
    # owner batch: list of dicts; question; new place name
    r = c.post("/api/v1/owner/observations/batch", headers=EWA,
               json=[{"place_id": "plc_mnk", "feature": "ramp", "value": "yes", "comment": "<i>ok</i>"}])
    assert r.status_code == 201 and r.json()["items"][0]["comment"] == "ok"
    q = c.post("/api/v1/places/plc_mnk/questions", headers=ANNA, json={"text": "<b>Pies?</b>"}).json()
    assert q["text"] == "Pies?"
    p = c.post("/api/v1/places/resolve", headers=ANNA,
               json={"name": "<svg onload=alert(1)>Bar", "lat": 50.06, "lon": 19.94}).json()
    assert p["place"]["name"] == "Bar"


def test_text_that_becomes_empty_is_rejected_like_empty(c):
    r = c.post("/api/v1/places/plc_mnk/questions", headers=ANNA, json={"text": "<script></script>"})
    assert r.status_code == 400


def test_website_must_be_http(c):
    bad = c.patch("/api/v1/owner/places/plc_mnk", headers=EWA, json={"contact": {"website": "javascript:alert(1)"}})
    assert bad.status_code == 400
    ok = c.patch("/api/v1/owner/places/plc_mnk", headers=EWA, json={"contact": {"website": "https://mnk.pl"}})
    assert ok.status_code == 200


def test_upload_filename_is_cleaned(c):
    r = c.post("/api/v1/uploads", headers=ANNA, files={"file": ('<img src=x onerror=1>.png', PNG, "image/png")})
    assert r.status_code == 201
    photo_id = r.json()["id"]
    assert "<" not in c.app.state.use_cases.repo.get_photo(photo_id).original_name


def test_model_output_is_cleaned():
    a = parse_analysis('{"description": "<script>x()</script>Schody", "barrier_type": "<b>stairs</b>"}', "gemini")
    assert (a.description, a.barrier_type) == ("x()Schody", "stairs")


def test_security_headers(c):
    r = c.get("/api/v1/places")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["referrer-policy"] == "no-referrer"
    docs = c.get("/docs")
    assert docs.status_code == 200 and "default-src 'none'" not in docs.headers.get("content-security-policy", "")


def test_media_is_sandboxed(c):
    photo = c.post("/api/v1/uploads", headers=ANNA, files={"file": ("w.png", PNG, "image/png")}).json()
    m = c.get(photo["url"])
    assert m.status_code == 200 and "sandbox" in m.headers["content-security-policy"]
    assert m.headers["x-content-type-options"] == "nosniff"


def test_use_case_level_text_is_also_safe(uc):
    """Defence also below HTTP (MCP / scripts call use cases directly)."""
    o = uc.add_observation(user(uc, "anna"), "plc_mnk", feature="ramp", value="no", comment="<b>x</b>")
    assert o.comment == "x"
