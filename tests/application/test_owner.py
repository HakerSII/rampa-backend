import pytest

from app.domain.enums import FeatureKey as F, ObservationSource, QueueStatus, Role, ValidationStatus
from app.domain.errors import Forbidden, NotFound, Unauthorized, ValidationFailed
from tests.application.test_ai import upload
from tests.application.test_observations import report, user


def owner_obs(uc, place="plc_mnk", who="ewa", items=None):
    items = items or [{"feature": "elevator", "value": "yes", "comment": "Winda naprawiona 3.10"}]
    return uc.add_owner_observations(user(uc, who), place, items)


async def test_owner_sees_only_own_places(uc):
    assert [p.id for p in uc.list_owner_places(user(uc, "ewa"))] == ["plc_mnk", "plc_camelot"]


@pytest.mark.parametrize("who, error", [("anna", Forbidden), ("admin", Forbidden), (None, Unauthorized)])
async def test_owner_endpoints_need_owner_role(uc, who, error):
    with pytest.raises(error):
        uc.list_owner_places(user(uc, who) if who else None)


async def test_owner_observation_is_verified_owner_with_085(uc):
    (o,) = owner_obs(uc, items=[{"feature": "ramp", "value": "yes"}])
    assert (o.source, o.confidence) == (ObservationSource.VERIFIED_OWNER, 0.85)
    s = uc.repo.states_for("plc_mnk")[F.RAMP]
    assert (s.state, s.confidence, s.active_observation_id) == ("yes", 0.85, o.id)


async def test_owner_batch_creates_one_observation_per_item(uc):
    obs = owner_obs(uc, place="plc_camelot", items=[
        {"feature": "accessible_toilet", "value": "yes"}, {"feature": "step_free_entrance", "value": "no"}])
    assert [o.feature for o in obs] == [F.ACCESSIBLE_TOILET, F.STEP_FREE_ENTRANCE]
    assert uc.repo.states_for("plc_camelot")[F.ACCESSIBLE_TOILET].state == "yes"


async def test_owner_cannot_update_someone_elses_place(uc):
    with pytest.raises(Forbidden):
        owner_obs(uc, place="plc_ice")


@pytest.mark.parametrize("items", [[], [{"feature": "ramp", "value": "yes"}] * 11, [{"feature": "x", "value": "yes"}]])
async def test_owner_batch_validation(uc, items):
    with pytest.raises(ValidationFailed):
        uc.add_owner_observations(user(uc, "ewa"), "plc_mnk", items)


async def test_owner_vs_users_conflict_goes_to_queue_and_admin_can_confirm_owner(uc):
    anna_obs = report(uc, photo_ids=[await upload(uc, "winda.png")]).observation_ids[0]  # 0.6
    for name in ("jan", "ola", "piotr"):
        uc.vote(user(uc, name), anna_obs, 1)
    (ewa_obs,) = owner_obs(uc)
    s = uc.repo.states_for("plc_mnk")[F.ELEVATOR]
    assert (s.state, s.validation) == ("no", ValidationStatus.CONFLICT)  # users 0.9 (photo + 3 votes) > owner 0.85
    (item,) = uc.list_queue(user(uc, "admin"), filter="conflict")
    state = uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=ewa_obs.id)
    assert (state.state, state.confidence) == ("yes", 1.0)
    assert uc.repo.get_queue_item(item.id).status == QueueStatus.RESOLVED


async def test_generic_observation_endpoint_by_owner_is_verified_owner(uc):
    o = uc.add_observation(user(uc, "ewa"), "plc_mnk", feature="ramp", value="no")
    assert o.source == ObservationSource.VERIFIED_OWNER
    o = uc.add_observation(user(uc, "ewa"), "plc_ice", feature="ramp", value="no")
    assert o.source == ObservationSource.COMMUNITY  # not her place


async def test_owner_reports_lists_reports_on_own_places_newest_first(uc):
    r1 = report(uc)
    r2 = report(uc, author="jan", element="ramp", description="Podjazd zastawiony")
    report(uc, place_id="plc_ice")
    assert [r.id for r in uc.list_owner_reports(user(uc, "ewa"))] == [r2.id, r1.id]


async def test_admin_assigns_owner_and_promotes_user(uc):
    place = uc.assign_owner(user(uc, "admin"), "plc_ice", "usr_anna")
    assert place.owner_id == "usr_anna" and user(uc, "anna").role == Role.OWNER
    (o,) = owner_obs(uc, place="plc_ice", who="anna", items=[{"feature": "elevator", "value": "yes"}])
    assert o.source == ObservationSource.VERIFIED_OWNER


@pytest.mark.parametrize("place, user_id, error", [("nope", "usr_anna", NotFound), ("plc_ice", "usr_nope", NotFound)])
async def test_assign_owner_validation(uc, place, user_id, error):
    with pytest.raises(error):
        uc.assign_owner(user(uc, "admin"), place, user_id)


async def test_only_admin_assigns_owner(uc):
    with pytest.raises(Forbidden):
        uc.assign_owner(user(uc, "ewa"), "plc_ice", "usr_ewa")


async def test_demo_reset_restores_ownership_and_does_not_leak_between_instances(uc):
    uc.assign_owner(user(uc, "admin"), "plc_ice", "usr_anna")
    uc.reset_demo(user(uc, "admin"))
    assert uc.get_place("plc_ice").owner_id is None
    assert user(uc, "anna").role == Role.USER
    from tests.conftest import make_use_cases
    uc.assign_owner(user(uc, "admin"), "plc_ice", "usr_anna")
    assert make_use_cases().get_place("plc_ice").owner_id is None
