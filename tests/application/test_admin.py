import pytest

from app.domain.enums import FeatureKey as F, QueueStatus, ValidationStatus
from app.domain.errors import ConflictError, Forbidden, NotFound, ValidationFailed
from tests.application.test_observations import report, user


def conflict(uc):
    """anna: elevator broken (+3 votes) vs marek: works → one open queue item."""
    anna_obs = report(uc).observation_ids[0]
    for name in ("jan", "ola", "piotr"):
        uc.vote(user(uc, name), anna_obs, 1)
    marek_obs = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes").id
    (item,) = uc.list_queue(user(uc, "admin"), filter="conflict")
    return item, anna_obs, marek_obs


async def test_queue_lists_open_conflict_with_detail(uc):
    item, anna_obs, marek_obs = conflict(uc)
    detail = uc.get_queue_item(user(uc, "admin"), item.id)
    assert (detail.place_id, detail.feature, detail.status) == ("plc_mnk", F.ELEVATOR, QueueStatus.OPEN)
    assert set(detail.observation_ids) == {anna_obs, marek_obs}


async def test_confirm_keeps_winner_rejects_opposite_and_resolves(uc):
    item, anna_obs, marek_obs = conflict(uc)
    state = uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=marek_obs, comment="sprawdzone")
    assert (state.state, state.confidence, state.validation) == ("yes", 1.0, ValidationStatus.VALID)
    assert uc.repo.get_observation(anna_obs).validation == ValidationStatus.REJECTED
    assert uc.repo.get_observation(marek_obs).validation == ValidationStatus.VALID
    assert uc.repo.get_queue_item(item.id).status == QueueStatus.RESOLVED
    assert uc.list_queue(user(uc, "admin"), filter="conflict") == []


async def test_reject_rejects_all_and_falls_back_to_seed(uc):
    item, _, _ = conflict(uc)
    state = uc.decide(user(uc, "admin"), item.id, "reject")
    assert (state.state, state.confidence) == ("yes", 0.5)  # seed observation (60 days old)
    assert uc.repo.get_queue_item(item.id).decision == "rejected"


async def test_second_decision_is_a_conflict(uc):
    item, _, marek_obs = conflict(uc)
    uc.decide(user(uc, "admin"), item.id, "reject")
    with pytest.raises(ConflictError):
        uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=marek_obs)


@pytest.mark.parametrize("winner", [None, "obs_1"])
async def test_confirm_needs_winner_from_the_item(uc, winner):
    item, _, _ = conflict(uc)
    with pytest.raises(ValidationFailed):
        uc.decide(user(uc, "admin"), item.id, "confirm", winning_observation_id=winner)


async def test_only_admin_moderates(uc):
    item, _, _ = conflict(uc)
    with pytest.raises(Forbidden):
        uc.list_queue(user(uc, "anna"))
    with pytest.raises(Forbidden):
        uc.decide(user(uc, "anna"), item.id, "reject")


async def test_unknown_item(uc):
    with pytest.raises(NotFound):
        uc.get_queue_item(user(uc, "admin"), "q_404")
