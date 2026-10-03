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
