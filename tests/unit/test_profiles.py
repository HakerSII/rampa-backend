import pytest

from app.domain.check import PROFILE_RULES, check_place
from app.domain.enums import FEATURE_GROUP, LABELS_PL, CheckAnswer as A, FeatureGroupKey, FeatureKey as F, NeedsProfile as P
from tests.unit.test_check import states


def test_every_feature_has_group_and_label_and_every_profile_a_rule():
    assert set(FEATURE_GROUP) == set(F)
    assert all(f in LABELS_PL for f in F) and all(g in LABELS_PL for g in FeatureGroupKey)
    assert set(PROFILE_RULES) == set(P)


@pytest.mark.parametrize("profile, data, answer", [
    (P.STROLLER, dict(ramp="yes"), A.YES),
    (P.STROLLER, dict(ramp="yes", elevator="no"), A.PARTIAL),
    (P.CRUTCHES, dict(step_free_entrance="no", crutches_friendly="yes"), A.YES),
    (P.CRUTCHES, dict(step_free_entrance="no", ramp="no"), A.NO),
    (P.BLIND, dict(tactile_paths="no", braille="yes"), A.YES),
    (P.BLIND, dict(tactile_paths="no"), A.NO),
    (P.BLIND, dict(ramp="yes"), A.UNKNOWN),
    (P.LOW_VISION, dict(good_lighting="no"), A.NO),
    (P.DEAF, dict(sign_language_interpreter="yes"), A.YES),
    (P.DEAF, dict(induction_loop="no", sign_language_interpreter="no"), A.NO),
    (P.ASSISTANCE_DOG, dict(assistance_dog_allowed="yes"), A.YES),
    (P.ASSISTANCE_DOG, dict(), A.UNKNOWN),
])
def test_profile_rules(profile, data, answer):
    assert check_place("p", states(**data), profile).answer == answer


def test_reasons_only_list_features_relevant_to_profile():
    r = check_place("p", states(braille="yes", ramp="yes", elevator="no"), P.BLIND)
    assert {x.feature for x in r.reasons} == {F.BRAILLE}


def test_advice_is_profile_specific():
    assert "pies" in check_place("p", states(assistance_dog_allowed="no"), P.ASSISTANCE_DOG).advice.lower()
