"""F36: places added by users go to a `new_place` queue; admin activity grid, daily trends, data coverage."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from app.domain.enums import FeatureKey as F
from app.domain.errors import ConflictError, Forbidden
from tests.application.test_observations import user


def new_place(uc, who="anna", name="Kawiarnia Nowa"):
    place, created = uc.resolve_place(user(uc, who), name=name, lat=50.0610, lon=19.9370)
    assert created
    return place


async def test_user_created_place_enters_new_place_queue(uc):
    p = new_place(uc)
    (item,) = uc.list_queue(user(uc, "admin"), filter="new_place")
    assert (item.type, item.place_id, item.feature) == ("new_place", p.id, None)
    assert uc.list_queue(user(uc, "admin"), filter="conflict") == []
    uc.resolve_place(user(uc, "jan"), name="Kawiarnia Nowa", lat=50.0610, lon=19.9370)   # same place, no 2nd item
    assert len(uc.list_queue(user(uc, "admin"), filter="new_place")) == 1
    state = uc.decide(user(uc, "admin"), item.id, "confirm")
    assert state is None and item.decision == "approved" and uc.repo.get_place(p.id)


async def test_admin_created_place_skips_queue(uc):
    uc.resolve_place(user(uc, "admin"), name="Biuro", lat=50.06, lon=19.93)
    assert uc.list_queue(user(uc, "admin"), filter="new_place") == []


async def test_reject_new_place_deletes_it_only_without_data(uc):
    empty = new_place(uc, name="Spam Miejsce")
    item = uc.list_queue(user(uc, "admin"), filter="new_place")[0]
    uc.decide(user(uc, "admin"), item.id, "reject")
    assert uc.repo.get_place(empty.id) is None and item.decision == "rejected"
    used = new_place(uc, name="Z Danymi")
    uc.add_observation(user(uc, "anna"), used.id, feature="ramp", value="yes")
    item2 = uc.list_queue(user(uc, "admin"), filter="new_place")[0]
    with pytest.raises(ConflictError):                       # observations are never deleted → merge instead
        uc.decide(user(uc, "admin"), item2.id, "reject")


async def test_merge_resolves_new_place_item(uc):
    dup = new_place(uc, name="Muzeum Narodowe")
    uc.merge_places(user(uc, "admin"), dup.id, "plc_mnk")
    assert uc.list_queue(user(uc, "admin"), filter="new_place") == []
    (item,) = uc.list_queue(user(uc, "admin"), filter="new_place", status="resolved")
    assert item.decision == "merged"


async def test_activity_grid_trends_and_coverage(uc):
    for _ in range(3):
        uc.add_observation(user(uc, "anna"), "plc_camelot", feature="ramp", value="yes")
    admin = user(uc, "admin")
    cells = uc.admin_activity(admin, days=30, cell_deg=0.01)
    top = cells[0]
    assert top.observations >= 3 and abs(top.lat - 50.065) < 0.01 and abs(top.lon - 19.935) < 0.01
    days = uc.admin_trends(admin, days=7)
    assert len(days) == 7 and days[-1].observations == 3 and days[-1].day == "2026-10-03"
    cov = uc.admin_coverage(admin)
    museum = next(c for c in cov.categories if c.category == "museum")
    assert museum.places == 1 and museum.with_data == 1
    missing = dict(cov.most_missing)
    assert missing[F.ACCESSIBLE_TOILET] == 3                 # only MNK has toilet data among 4 places
    with pytest.raises(Forbidden):
        uc.admin_trends(user(uc, "anna"))


def test_insights_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    admin, anna = {"Authorization": "Bearer demo-admin"}, {"Authorization": "Bearer demo-anna"}
    c.post("/api/v1/places/resolve", headers=anna, json={"name": "Nowy Bar", "lat": 50.06, "lon": 19.94})
    q = c.get("/api/v1/admin/queue", params={"filter": "new_place"}, headers=admin).json()
    assert q["counts"]["new_place"] == 1 and q["items"][0]["feature"] is None
    detail = c.get(f"/api/v1/admin/queue/{q['items'][0]['id']}", headers=admin).json()
    assert detail["summary"].startswith("Nowe miejsce") and detail["feature_state"] is None
    d = c.post(f"/api/v1/admin/queue/{q['items'][0]['id']}/decision", headers=admin, json={"action": "confirm"})
    assert d.status_code == 200 and d.json()["status"] == "approved" and d.json()["feature_state"] is None
    assert c.get("/api/v1/admin/activity", headers=admin).status_code == 200
    assert len(c.get("/api/v1/admin/trends", params={"days": 14}, headers=admin).json()["days"]) == 14
    assert c.get("/api/v1/admin/coverage", headers=admin).json()["most_missing"]
    assert c.get("/api/v1/admin/trends", params={"days": 0}, headers=admin).status_code == 400
