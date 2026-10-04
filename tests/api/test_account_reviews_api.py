"""F54 account settings (name, delete account) and F55 reviews (rating 1–5 + text, one per account and place),
as on the Accessly main branch."""
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings

ANNA = {"Authorization": "Bearer demo-anna"}
OLA = {"Authorization": "Bearer demo-ola"}


def client(tmp_path):
    return TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path), _env_file=None)))


def anonymous(c):
    return {"Authorization": f"Bearer {c.post('/api/v1/auth/anonymous', json={}).json()['token']}"}


# ---------------------------------------------------------------- F54
def test_change_display_name(tmp_path):
    c = client(tmp_path)
    r = c.patch("/api/v1/me", headers=ANNA, json={"display_name": "  Ania <b>K</b> "})
    assert r.status_code == 200 and r.json()["display_name"] == "Ania K"
    assert c.get("/api/v1/me", headers=ANNA).json()["display_name"] == "Ania K"


def test_display_name_validation(tmp_path):
    c = client(tmp_path)
    assert c.patch("/api/v1/me", headers=ANNA, json={"display_name": "  "}).status_code == 400
    assert c.patch("/api/v1/me", headers=ANNA, json={"display_name": "x" * 61}).status_code == 400
    assert c.patch("/api/v1/me", json={"display_name": "A"}).status_code == 401


def test_delete_account_signs_out_and_forgets_the_person(tmp_path):
    c = client(tmp_path)
    c.put("/api/v1/me/favorites/plc_mnk", headers=ANNA)
    c.put("/api/v1/places/plc_mnk/reviews/me", headers=ANNA, json={"rating": 4, "text": "OK"})
    obs = c.post("/api/v1/places/plc_mnk/observations", headers=ANNA, json={"feature": "elevator", "value": "no"}).json()
    assert c.delete("/api/v1/me", headers=ANNA).status_code == 204
    assert c.get("/api/v1/me", headers=ANNA).status_code == 401  # every session ended
    assert c.get("/api/v1/places/plc_mnk/reviews").json()["items"] == []  # reviews deleted
    kept = c.get("/api/v1/places/plc_mnk/observations").json()["items"]
    mine = next(o for o in kept if o["id"] == obs["id"])  # contributions stay, without the person
    assert mine["author"]["display_name"] == "Usunięty użytkownik"


# ---------------------------------------------------------------- F55
def test_review_add_change_and_list(tmp_path):
    c = client(tmp_path)
    r = c.put("/api/v1/places/plc_mnk/reviews/me", headers=ANNA, json={"rating": 5, "text": "Winda działa."})
    assert r.status_code == 200 and r.json()["rating"] == 5
    c.put("/api/v1/places/plc_mnk/reviews/me", headers=OLA, json={"rating": 2, "text": ""})
    c.put("/api/v1/places/plc_mnk/reviews/me", headers=ANNA, json={"rating": 4, "text": "Winda działa, ale wolna."})
    page = c.get("/api/v1/places/plc_mnk/reviews", headers=ANNA).json()
    assert (page["count"], page["average"]) == (2, 3.0)
    assert page["mine"]["rating"] == 4 and page["mine"]["text"] == "Winda działa, ale wolna."
    assert {i["author"]["display_name"] for i in page["items"]} == {"Anna K.", "Ola W."}  # public names
    assert c.get("/api/v1/places/plc_mnk/reviews").json()["mine"] is None  # guest


def test_review_validation_and_account(tmp_path):
    c = client(tmp_path)
    assert c.put("/api/v1/places/plc_mnk/reviews/me", headers=ANNA, json={"rating": 6}).status_code == 400
    assert c.put("/api/v1/places/plc_mnk/reviews/me", headers=ANNA, json={"rating": 3, "text": "x" * 501}).status_code == 400
    assert c.put("/api/v1/places/plc_nope/reviews/me", headers=ANNA, json={"rating": 3}).status_code == 404
    assert c.put("/api/v1/places/plc_mnk/reviews/me", json={"rating": 3}).status_code == 401
    # this device's anonymous identity: an account is needed (as on main: "Zaloguj się, aby dodać opinię.")
    assert c.put("/api/v1/places/plc_mnk/reviews/me", headers=anonymous(c), json={"rating": 3}).status_code == 403


def test_delete_own_review(tmp_path):
    c = client(tmp_path)
    c.put("/api/v1/places/plc_mnk/reviews/me", headers=ANNA, json={"rating": 5})
    assert c.delete("/api/v1/places/plc_mnk/reviews/me", headers=ANNA).status_code == 204
    assert c.get("/api/v1/places/plc_mnk/reviews").json()["count"] == 0


def test_rating_on_the_place_and_in_the_list(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/v1/places/plc_mnk").json()["rating"] is None
    c.put("/api/v1/places/plc_mnk/reviews/me", headers=ANNA, json={"rating": 5})
    c.put("/api/v1/places/plc_mnk/reviews/me", headers=OLA, json={"rating": 4})
    assert c.get("/api/v1/places/plc_mnk").json()["rating"] == {"avg": 4.5, "count": 2}
    items = c.get("/api/v1/places", params={"q": "Muzeum Narodowe"}).json()["items"]
    assert items[0]["rating"] == {"avg": 4.5, "count": 2}
