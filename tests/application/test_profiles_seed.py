import pytest

from app.domain.enums import CheckAnswer as A, FeatureKey as F, NeedsProfile as P


@pytest.mark.parametrize("place, profile, answer", [
    ("plc_mnk", P.BLIND, A.YES),
    ("plc_mnk", P.LOW_VISION, A.YES),
    ("plc_mnk", P.DEAF, A.YES),
    ("plc_mnk", P.ASSISTANCE_DOG, A.YES),
    ("plc_mnk", P.STROLLER, A.YES),
    ("plc_urzad", P.DEAF, A.YES),            # sign language interpreter
    ("plc_urzad", P.LOW_VISION, A.NO),       # poor lighting
    ("plc_urzad", P.WHEELCHAIR, A.NO),
    ("plc_ice", P.BLIND, A.UNKNOWN),
])
async def test_seeded_answers_for_user_questions(uc, place, profile, answer):
    assert uc.check_place(place, profile).answer == answer


async def test_accessibility_lists_all_features(uc):
    states = uc.get_accessibility("plc_urzad")
    assert len(states) == 52 and states[F.LOWERED_CURB].state == "yes"


async def test_search_by_new_feature(uc):
    assert [p.id for p in uc.search_places(features=[F.ASSISTANCE_DOG_ALLOWED, F.SIGN_LANGUAGE_INTERPRETER])] == [
        "plc_urzad"]
