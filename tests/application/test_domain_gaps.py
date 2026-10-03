from datetime import timedelta

import pytest

from app.adapters.outbound.memory import FixedClock
from app.domain import trust
from app.domain.check import check_place
from app.domain.enums import CheckAnswer, FeatureKey as F, NeedsProfile, ObservationValue, StateValue
from app.domain.errors import ValidationFailed
from app.domain.osm import OsmPoint, map_features
from tests.application.test_observations import report, user
from tests.conftest import NOW, make_use_cases
from tests.unit.test_check import states
from tests.unit.test_trust import obs


# ---------------------------------------------------------------- partial
def test_partial_value_and_check_answer():
    assert ObservationValue("partial") == ObservationValue.PARTIAL and StateValue("partial") == StateValue.PARTIAL
    assert check_place("p", states(ramp="partial"), NeedsProfile.WHEELCHAIR).answer == CheckAnswer.PARTIAL
    assert check_place("p", states(ramp="partial", step_free_entrance="yes"),
                       NeedsProfile.WHEELCHAIR).answer == CheckAnswer.YES


def test_osm_limited_is_partial():
    assert map_features(OsmPoint("X", "limited", "brak danych", "cafe", 50, 19)) == [
        (F.STEP_FREE_ENTRANCE, ObservationValue.PARTIAL)]


async def test_report_partially_works_gives_partial_state(uc):
    report(uc, element="ramp", current_state="partially_works", nature="permanent")
    assert uc.repo.states_for("plc_mnk")[F.RAMP].state == StateValue.PARTIAL


# ---------------------------------------------------------------- trust ageing
def test_observations_older_than_180_days_count_half():
    old = obs("o", "yes", at=NOW - timedelta(days=200))
    assert trust.observation_confidence(old, NOW) == 0.25
    assert trust.observation_confidence(obs("n", "yes"), NOW) == 0.5


# ---------------------------------------------------------------- temporary issues with end date
async def test_valid_until_expires_temporary_issue():
    clock = FixedClock(NOW)
    uc = make_use_cases(clock=clock)
    until = NOW + timedelta(days=2)
    uc.add_observation(user(uc, "anna"), "plc_mnk", feature="elevator", value="no", temporary=True,
                       valid_until=until.isoformat())
    assert uc.get_accessibility("plc_mnk")[F.ELEVATOR].state == "no"
    clock._now = NOW + timedelta(days=3)
    assert uc.get_accessibility("plc_mnk")[F.ELEVATOR].state == "yes"  # expired → seed again
    assert uc.check_place("plc_mnk", NeedsProfile.WHEELCHAIR).answer == CheckAnswer.YES


async def test_valid_until_must_be_future(uc):
    with pytest.raises(ValidationFailed):
        uc.add_observation(user(uc, "anna"), "plc_mnk", feature="elevator", value="no",
                           valid_until=(NOW - timedelta(days=1)).isoformat())


# ---------------------------------------------------------------- place type
async def test_place_type_filter(uc):
    from app.application.use_cases import PlaceQuery
    assert uc.get_place("plc_urzad").place_type == "office"
    r = uc.find_places(PlaceQuery(place_types=["office"]))
    assert [p.id for p, _ in r.items] == ["plc_urzad"]
    with pytest.raises(ValidationFailed):
        uc.find_places(PlaceQuery(place_types=["spaceport"]))
