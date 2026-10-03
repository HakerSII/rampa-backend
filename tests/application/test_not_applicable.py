"""F32: value `not_applicable` ("nie dotyczy") + attributes baby_changing_table, stroller_space, luggage_storage,
rest_areas. n/a is a fact (not missing data) but never a barrier and never a helper."""
from fastapi.testclient import TestClient

from app.adapters.inbound.http.main import create_app
from app.config import Settings
from app.domain import osm
from app.domain.enums import FEATURE_GROUP, LABELS_PL, FeatureGroupKey as G, FeatureKey as F, NeedsProfile as P
from app.domain.recommend import interpret_rules
from tests.application.test_observations import user


async def test_new_features_have_labels_and_groups():
    for f, g in [(F.BABY_CHANGING_TABLE, G.TOILET), (F.STROLLER_SPACE, G.INSIDE), (F.LUGGAGE_STORAGE, G.OTHER),
                 (F.REST_AREAS, G.INSIDE)]:
        assert FEATURE_GROUP[f] == g and LABELS_PL[f]


async def test_not_applicable_becomes_state_and_is_not_missing(uc):
    o = uc.add_observation(user(uc, "ewa"), "plc_camelot", feature="elevator", value="not_applicable",
                           comment="Lokal parterowy")
    assert o.value == "not_applicable"
    assert uc.get_accessibility("plc_camelot")[F.ELEVATOR].state == "not_applicable"
    # single-storey: the elevator rule must not downgrade the wheelchair answer
    assert uc.check_place("plc_camelot", P.WHEELCHAIR).answer == "yes"


async def test_not_applicable_required_feature_is_ignored_by_check(uc):
    # ICE: step-free entrance yes; ramp n/a must not change anything
    uc.add_observation(user(uc, "jan"), "plc_ice", feature="ramp", value="not_applicable")
    assert uc.check_place("plc_ice", P.WHEELCHAIR).answer == "partial"   # elevator still broken


async def test_not_applicable_is_neither_barrier_nor_helper_on_routes(uc):
    uc.add_observation(user(uc, "anna"), "plc_camelot", feature="lowered_curb", value="not_applicable")
    r = uc.accessible_route("plc_mnk", "plc_urzad", P.WHEELCHAIR)
    assert "plc_camelot" not in {p.place_id for p in r.barriers + r.helpers}


async def test_recommend_treats_not_applicable_as_known():
    from tests.conftest import make_use_cases
    uc = make_use_cases()
    uc.add_observation(user(uc, "ewa"), "plc_mnk", feature="pets_allowed", value="not_applicable")
    r = await uc.recommend(None, "muzeum z psem")
    mnk = next(x for x in r.items if x.place.id == "plc_mnk")
    assert F.PETS_ALLOWED not in mnk.missing


async def test_rules_recognise_new_attributes():
    i = interpret_rules("kawiarnia z przewijakiem i miejscem na wózek, gdzie zostawię bagaż i odpocznę")
    assert {F.BABY_CHANGING_TABLE, F.STROLLER_SPACE, F.LUGGAGE_STORAGE, F.REST_AREAS} <= set(i.features)


async def test_osm_changing_table_and_dog_tags():
    p = osm.OsmPoint("Kawiarnia", "yes", "", "cafe", 50.0, 19.9, changing_table="yes", dog="no")
    assert set(osm.map_features(p)) == {(F.STEP_FREE_ENTRANCE, "yes"), (F.BABY_CHANGING_TABLE, "yes"),
                                        (F.PETS_ALLOWED, "no")}
    leashed = osm.OsmPoint("Bar", "", "", "bar", 50.0, 19.9, dog="leashed")
    assert osm.map_features(leashed) == [(F.PETS_ALLOWED, "yes")]


def test_not_applicable_over_http(tmp_path):
    c = TestClient(create_app(Settings(repo_mode="memory", media_dir=str(tmp_path))))
    r = c.post("/api/v1/places/plc_camelot/observations", headers={"Authorization": "Bearer demo-ewa"},
               json={"feature": "baby_changing_table", "value": "not_applicable"})
    assert r.status_code == 201
    acc = c.get("/api/v1/places/plc_camelot/accessibility").json()
    flat = {f["key"]: f["state"] for g in acc["groups"] for f in g["features"]}
    assert flat["baby_changing_table"] == "not_applicable"
    pub = c.get("/public/v1/places/plc_camelot/accessibility", headers={"X-Api-Key": "demo-key"}).json()
    assert pub["accessibility"]["baby_changing_table"]["value"] == "not_applicable"
    assert c.post("/api/v1/places/plc_camelot/observations", headers={"Authorization": "Bearer demo-ewa"},
                  json={"feature": "ramp", "value": "maybe"}).status_code == 400
