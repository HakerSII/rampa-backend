import pytest

from app.domain.enums import CheckAnswer, FeatureKey as F, NeedsProfile
from app.domain.errors import NotFound


async def test_search_by_step_free_entrance_returns_only_places_with_yes(uc):
    places = uc.search_places(features=[F.STEP_FREE_ENTRANCE])
    assert {p.id for p in places} == {"plc_mnk", "plc_ice"}


async def test_search_features_are_combined_with_and(uc):
    places = uc.search_places(features=[F.STEP_FREE_ENTRANCE, F.ELEVATOR])
    assert [p.id for p in places] == ["plc_mnk"]


async def test_search_by_category_and_text(uc):
    assert [p.id for p in uc.search_places(category="cafe")] == ["plc_camelot"]
    assert [p.id for p in uc.search_places(q="muzeum")] == ["plc_mnk"]


async def test_unknown_place_raises_not_found(uc):
    with pytest.raises(NotFound):
        uc.get_place("nope")


async def test_accessibility_lists_all_mvp_features_missing_as_unknown(uc):
    states = uc.get_accessibility("plc_camelot")
    assert set(states) == set(F)
    assert states[F.RAMP].state == "yes"
    assert states[F.ACCESSIBLE_TOILET].state == "unknown"


async def test_check_seeded_places(uc):
    assert uc.check_place("plc_mnk", NeedsProfile.WHEELCHAIR).answer == CheckAnswer.YES
    assert uc.check_place("plc_ice", NeedsProfile.WHEELCHAIR).answer == CheckAnswer.PARTIAL
    assert uc.check_place("plc_urzad", NeedsProfile.WHEELCHAIR).answer == CheckAnswer.NO


# ---------------------------------------------------------------- resolve: map pin → place (F12)
from app.domain.errors import Unauthorized, ValidationFailed  # noqa: E402
from tests.application.test_observations import user  # noqa: E402


async def test_resolve_creates_place_for_a_new_pin(uc):
    place, created = uc.resolve_place(user(uc, "anna"), name="Rondo Mogilskie", lat=50.0656, lon=19.9585)
    assert created and place.id.startswith("plc_")
    assert (place.name, place.category, place.address) == ("Rondo Mogilskie", "other", "")
    assert (place.location.lat, place.location.lon) == (50.0656, 19.9585)
    assert uc.get_place(place.id) is place
    assert uc.get_accessibility(place.id)[F.ELEVATOR].state == "unknown"


async def test_resolve_matches_same_name_within_50_m_case_insensitive(uc):
    place, created = uc.resolve_place(user(uc, "anna"), name="muzeum narodowe W KRAKOWIE", lat=50.0604, lon=19.9239)
    assert (place.id, created) == ("plc_mnk", False)
    assert len(uc.search_places(q="Muzeum Narodowe")) == 1


async def test_resolve_same_name_far_away_is_a_new_place(uc):
    place, created = uc.resolve_place(user(uc, "anna"), name="Muzeum Narodowe w Krakowie", lat=50.07, lon=19.93)
    assert created and place.id != "plc_mnk"


async def test_resolve_twice_returns_the_same_place(uc):
    anna, jan = user(uc, "anna"), user(uc, "jan")
    first, _ = uc.resolve_place(anna, name="Przystanek Teatr Bagatela", lat=50.0640, lon=19.9330)
    second, created = uc.resolve_place(jan, name="Przystanek Teatr Bagatela", lat=50.0642, lon=19.9331)
    assert second.id == first.id and not created


async def test_resolve_keeps_optional_category_and_address(uc):
    place, _ = uc.resolve_place(user(uc, "anna"), name="Sklep", lat=50.07, lon=19.93, category="shop",
                                address="ul. Długa 1")
    assert (place.category, place.address) == ("shop", "ul. Długa 1")


@pytest.mark.parametrize("kwargs", [
    dict(name="", lat=50.07, lon=19.93),
    dict(name=" " * 3, lat=50.07, lon=19.93),
    dict(name="x" * 121, lat=50.07, lon=19.93),
    dict(name="Ok", lat=91, lon=19.93),
])
async def test_resolve_validates_name_and_coordinates(uc, kwargs):
    with pytest.raises(ValidationFailed):
        uc.resolve_place(user(uc, "anna"), **kwargs)


async def test_resolve_requires_a_user(uc):
    with pytest.raises(Unauthorized):
        uc.resolve_place(None, name="Rondo", lat=50.07, lon=19.93)


async def test_resolved_place_accepts_a_report_immediately(uc):
    anna = user(uc, "anna")
    place, _ = uc.resolve_place(anna, name="Winda na Dworcu", lat=50.0675, lon=19.9470)
    report = uc.create_report(anna, place_id=place.id, element="elevator", current_state="not_working",
                              severity="critical", nature="temporary", description="Winda nie działa.")
    assert report.place_id == place.id
    assert uc.get_accessibility(place.id)[F.ELEVATOR].state == "no"
