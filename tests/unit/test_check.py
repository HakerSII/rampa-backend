from app.domain.check import check_place
from app.domain.enums import CheckAnswer, FeatureKey as F, NeedsProfile, StateValue as S
from app.domain.model import FeatureStateRecord

WHEELCHAIR = NeedsProfile.WHEELCHAIR


def states(**values) -> dict:
    return {
        F(k): FeatureStateRecord("p", F(k), S(v), confidence=0.8, temporary=(k == "elevator" and v == "no"))
        for k, v in values.items()
    }


def test_step_free_entrance_and_working_elevator_means_yes():
    r = check_place("p", states(step_free_entrance="yes", elevator="yes"), WHEELCHAIR)
    assert r.answer == CheckAnswer.YES
    assert r.confidence == 0.8


def test_ramp_alone_is_enough_to_get_in():
    assert check_place("p", states(ramp="yes"), WHEELCHAIR).answer == CheckAnswer.YES


def test_entrance_ok_but_broken_elevator_means_partial():
    r = check_place("p", states(step_free_entrance="yes", elevator="no"), WHEELCHAIR)
    assert r.answer == CheckAnswer.PARTIAL
    assert "elev" in r.advice.lower() or "wind" in r.advice.lower()


def test_no_step_free_and_no_ramp_means_no():
    assert check_place("p", states(step_free_entrance="no", ramp="no"), WHEELCHAIR).answer == CheckAnswer.NO


def test_no_entrance_data_means_unknown_with_zero_confidence():
    r = check_place("p", states(induction_loop="yes"), WHEELCHAIR)
    assert r.answer == CheckAnswer.UNKNOWN
    assert r.confidence == 0.0


def test_reasons_list_states_used():
    r = check_place("p", states(step_free_entrance="yes", ramp="no", elevator="yes"), WHEELCHAIR)
    assert {x.feature for x in r.reasons} == {F.STEP_FREE_ENTRANCE, F.RAMP, F.ELEVATOR}
