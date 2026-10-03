import pytest

from app.domain.errors import Forbidden, Unauthorized
from tests.application.test_observations import report, user


def conflict(uc):
    anna = report(uc).observation_ids[0]
    marek = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes")
    (item,) = uc.list_queue(user(uc, "admin"))
    return anna, marek, item


async def test_admin_stats_after_scenario(uc):
    conflict(uc)
    s = uc.admin_stats(user(uc, "admin"))
    assert (s.new_reports_today.value, s.data_conflicts.value, s.places.value) == (1, 1, 4)
    assert s.observations_today.value == 2


@pytest.mark.parametrize("who, error", [("anna", Forbidden), ("ewa", Forbidden), (None, Unauthorized)])
async def test_stats_admin_only(uc, who, error):
    with pytest.raises(error):
        uc.admin_stats(user(uc, who) if who else None)


async def test_history_records_decision_time(uc):
    _, marek, item = conflict(uc)
    uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=marek.id)
    assert uc.repo.get_queue_item(item.id).resolved_at == uc.clock.now()
    events = uc.place_history(user(uc, "admin"), "plc_mnk")
    assert events[0].event in ("conflict_resolved", "observation_added")
    assert {e.event for e in events} >= {"conflict_detected", "conflict_resolved", "observation_added"}


async def test_history_for_owner_of_place_only(uc):
    assert uc.place_history(user(uc, "ewa"), "plc_mnk")  # ewa owns plc_mnk
    with pytest.raises(Forbidden):
        uc.place_history(user(uc, "ewa"), "plc_ice")
    with pytest.raises(Forbidden):
        uc.place_history(user(uc, "anna"), "plc_mnk")
