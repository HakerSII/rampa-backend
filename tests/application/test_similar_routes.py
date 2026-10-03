import pytest

from app.domain.enums import NeedsProfile as P
from app.domain.errors import NotFound, ValidationFailed
from tests.application.test_observations import user


async def test_similar_nearest_other_places(uc):
    assert [p.id for p, _ in uc.similar_places("plc_mnk")] == ["plc_camelot", "plc_ice", "plc_urzad"]
    assert [(p.id, d) for p, d in uc.similar_places("plc_mnk", limit=1)] == [("plc_camelot", 1072)]


async def test_similar_validation(uc):
    with pytest.raises(NotFound):
        uc.similar_places("nope")
    with pytest.raises(ValidationFailed):
        uc.similar_places("plc_mnk", limit=0)


async def test_route_with_helper_only_is_yes(uc):
    r = uc.accessible_route("plc_mnk", "plc_urzad", P.WHEELCHAIR)
    assert (r.feasible, r.distance_m, r.duration_min) == ("yes", 1601, 33)
    assert [(h.place_id, h.feature) for h in r.helpers] == [("plc_urzad", "lowered_curb")]
    assert r.barriers == [] and "heuristic" in r.note


async def test_barrier_near_line_makes_route_partial(uc):
    # Café Camelot is ~75 m from the MNK → Urząd line
    uc.add_observation(user(uc, "anna"), "plc_camelot", feature="lowered_curb", value="no")
    r = uc.accessible_route("plc_mnk", "plc_urzad", P.WHEELCHAIR)
    assert r.feasible == "partial" and [(b.place_id, b.feature) for b in r.barriers] == [("plc_camelot", "lowered_curb")]


async def test_profile_specific_features_and_coordinates(uc):
    blind = uc.accessible_route("plc_mnk", "plc_urzad", P.BLIND)
    assert {h.feature for h in blind.helpers} == {"tactile_paths", "lowered_curb"}
    far = uc.accessible_route("50.10,19.80", "50.11,19.81", P.WHEELCHAIR)
    assert far.feasible == "unknown" and far.geometry == [[19.8, 50.1], [19.81, 50.11]]


@pytest.mark.parametrize("a, b", [("nope", "plc_mnk"), ("50.1", "plc_mnk"), ("abc,def", "plc_mnk")])
async def test_route_endpoint_validation(uc, a, b):
    with pytest.raises((NotFound, ValidationFailed)):
        uc.accessible_route(a, b, P.WHEELCHAIR)
