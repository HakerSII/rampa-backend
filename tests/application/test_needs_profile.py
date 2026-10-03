"""F31: needs profile stored on the server (needs only, no diagnoses) + GET /places?sort=best_match."""
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.application.use_cases import PlaceQuery
from app.config import Settings
from app.domain.enums import FeatureKey as F, NeedsProfile as P
from app.domain.errors import Unauthorized, ValidationFailed
from tests.application.test_observations import user


async def test_set_get_and_clear_profile(uc):
    anna = user(uc, "anna")
    assert uc.get_needs_profile(anna) == ([], [])
    uc.set_needs_profile(anna, ["wheelchair", "assistance_dog"], ["accessible_toilet"])
    assert uc.get_needs_profile(anna) == ([P.WHEELCHAIR, P.ASSISTANCE_DOG], [F.ACCESSIBLE_TOILET])
    uc.set_needs_profile(anna, [], [])
    assert uc.get_needs_profile(anna) == ([], [])


@pytest.mark.parametrize("needs, features", [(["diabetes"], []), ([], ["nonsense"]), (["wheelchair"] * 11, [])])
async def test_profile_validation(uc, needs, features):
    with pytest.raises(ValidationFailed):
        uc.set_needs_profile(user(uc, "anna"), needs, features)


async def test_profile_needs_login(uc):
    with pytest.raises(Unauthorized):
        uc.set_needs_profile(None, ["wheelchair"], [])


async def test_best_match_orders_by_check_answer(uc):
    r = uc.find_places(PlaceQuery(sort="best_match", profiles=[P.WHEELCHAIR]))
    # yes (Camelot, MNK — tie by name) → partial (ICE, elevator broken) → no (Urząd)
    assert [p.id for p, _ in r.items] == ["plc_camelot", "plc_mnk", "plc_ice", "plc_urzad"]
    assert uc.place_match("plc_ice", [P.WHEELCHAIR]) == "partial"


async def test_best_match_needs_a_profile(uc):
    with pytest.raises(ValidationFailed):
        uc.find_places(PlaceQuery(sort="best_match"))


async def test_recommend_uses_stored_profile(uc):
    anna = user(uc, "anna")
    uc.set_needs_profile(anna, ["deaf"], [])
    r = await uc.recommend(anna, "urząd")
    assert r.intent.profiles == [P.DEAF] and r.items[0].match == "yes"


def test_profile_and_best_match_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    h = {"Authorization": "Bearer demo-anna"}
    assert c.get("/api/v1/me/profile", headers=h).json() == {"needs": [], "features": []}
    r = c.put("/api/v1/me/profile", headers=h, json={"needs": ["wheelchair"], "features": []})
    assert r.status_code == 200 and r.json()["needs"] == ["wheelchair"]
    items = c.get("/api/v1/places", params={"sort": "best_match"}, headers=h).json()["items"]
    assert [i["id"] for i in items][-1] == "plc_urzad" and items[-1]["match"] == "no"
    guest = c.get("/api/v1/places", params={"sort": "best_match", "profile": "blind"}).json()["items"]
    assert guest[0]["id"] == "plc_mnk" and guest[0]["match"] == "yes"       # braille + tactile paths
    assert c.get("/api/v1/places", params={"sort": "best_match"}).status_code == 400
    assert c.put("/api/v1/me/profile", headers=h, json={"needs": ["diagnosis"]}).status_code == 400
    assert c.delete("/api/v1/me/profile", headers=h).status_code == 204
    assert c.get("/api/v1/me/profile", headers=h).json()["needs"] == []
