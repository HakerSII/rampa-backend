from datetime import timedelta

import pytest

from app.adapters.outbound.memory import FixedClock
from app.domain.enums import FeatureKey as F
from app.domain.errors import ValidationFailed
from tests.application.test_observations import report, user
from tests.conftest import NOW, make_use_cases

OLD_TOWN = "19.93,50.055,19.95,50.07"  # Camelot + Urząd, not MNK / ICE


def ids(rows):
    return [o.id for o, _, _ in rows]


async def test_bbox_filters_by_place_location_and_carries_place_and_severity(uc):
    r = report(uc, place_id="plc_camelot", element="ramp", severity="obstacle")
    report(uc)  # MNK, outside bbox
    fresh = (NOW - timedelta(days=1)).isoformat()  # skip 60-day-old seed (Urząd has seed "no"s in the bbox)
    rows = uc.map_observations(bbox=OLD_TOWN, value="no", since=fresh)
    assert ids(rows) == r.observation_ids
    obs, place, severity = rows[0]
    assert (place.id, severity) == ("plc_camelot", "obstacle")


async def test_active_excludes_rejected_flagged_and_expired():
    clock = FixedClock(NOW)
    uc = make_use_cases(clock=clock)
    o = uc.add_observation(user(uc, "anna"), "plc_mnk", feature="elevator", value="no", temporary=True,
                           valid_until=(NOW + timedelta(days=1)).isoformat())
    assert o.id in ids(uc.map_observations(value="no"))
    clock._now = NOW + timedelta(days=2)
    assert o.id not in ids(uc.map_observations(value="no"))
    assert o.id in ids(uc.map_observations(value="no", active=False))


async def test_current_only_returns_observations_deciding_the_state(uc):
    weak = uc.add_observation(user(uc, "anna"), "plc_ice", feature="ramp", value="no")  # 0.5, newest → wins
    ice_only = "19.92,50.04,19.935,50.05"  # other places have seeded ramp observations
    rows = uc.map_observations(current=True, feature="ramp", bbox=ice_only)
    assert ids(rows) == [weak.id]
    assert uc.map_observations(current=True, feature="ramp", value="yes", bbox=ice_only) == []


async def test_seed_observations_visible_newest_first_with_limit(uc):
    report(uc)
    rows = uc.map_observations(limit=3)
    assert len(rows) == 3 and rows[0][0].author_id == "usr_anna"


@pytest.mark.parametrize("kwargs", [dict(bbox="1,2,3"), dict(limit=0), dict(limit=501), dict(feature="x"),
                                    dict(value="maybe"), dict(since="yesterday")])
async def test_validation(uc, kwargs):
    with pytest.raises(ValidationFailed):
        uc.map_observations(**kwargs)


async def test_since_filters_old_seed(uc):
    report(uc)
    rows = uc.map_observations(since=(NOW - timedelta(days=1)).isoformat())
    assert len(rows) == 1 and rows[0][0].feature == F.ELEVATOR
