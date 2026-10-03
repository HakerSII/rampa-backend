import pytest

from app.domain.enums import FeatureKey as F, Role, ValidationStatus
from app.domain.errors import ConflictError, Forbidden, NotFound, ValidationFailed
from tests.application.test_observations import report, user


def admin(uc):
    return user(uc, "admin")


async def test_confidence_widget(uc):
    c = uc.place_confidence(admin(uc), "plc_ice")
    assert c.by_group == {"entrance": 0.5, "inside": 0.5} and c.overall == 0.5
    with pytest.raises(Forbidden):
        uc.place_confidence(user(uc, "anna"), "plc_ice")


async def test_queue_comments(uc):
    report(uc)
    uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes")
    (item,) = uc.list_queue(admin(uc))
    uc.add_queue_comment(admin(uc), item.id, "Dzwonię do muzeum")
    assert [c["text"] for c in uc.get_queue_item(admin(uc), item.id).comments] == ["Dzwonię do muzeum"]
    with pytest.raises(ValidationFailed):
        uc.add_queue_comment(admin(uc), item.id, "  ")
    with pytest.raises(Forbidden):
        uc.add_queue_comment(user(uc, "anna"), item.id, "x")


async def test_flag_excludes_observation_and_recomputes(uc):
    spam = report(uc).observation_ids[0]
    assert uc.repo.states_for("plc_mnk")[F.ELEVATOR].state == "no"
    uc.flag_observation(admin(uc), spam, "spam / fake report")
    o = uc.repo.get_observation(spam)
    assert (o.validation, o.flag_reason) == (ValidationStatus.FLAGGED, "spam / fake report")
    assert uc.repo.states_for("plc_mnk")[F.ELEVATOR].state == "yes"  # seed wins again
    assert spam not in {x.id for x in uc.list_observations("plc_mnk")}
    assert uc.admin_stats(admin(uc)).abuse_flags.value == 1
    with pytest.raises(Forbidden):
        uc.flag_observation(user(uc, "jan"), spam, "x")


async def test_merge_duplicate_into_target(uc):
    anna = user(uc, "anna")
    uc.add_favorite(anna, "plc_camelot")
    r = report(uc, place_id="plc_camelot", element="ramp")
    uc.merge_places(admin(uc), "plc_camelot", "plc_mnk")
    with pytest.raises(NotFound):
        uc.get_place("plc_camelot")
    assert uc.repo.get_report(r.id).place_id == "plc_mnk"
    assert anna.favorite_place_ids == ["plc_mnk"]
    assert uc.repo.states_for("plc_mnk")[F.RAMP].state == "no"  # moved fresh report wins
    with pytest.raises(ValidationFailed):
        uc.merge_places(admin(uc), "plc_mnk", "plc_mnk")


async def test_revalidate_counts(uc):
    r = uc.revalidate(admin(uc))
    assert r == {"places": 4, "features": 19}


async def test_ownership_request_flow(uc):
    req = uc.request_ownership(user(uc, "anna"), "plc_ice", "Jestem kierownikiem ICE")
    assert [x.id for x in uc.list_ownership_requests(admin(uc), "pending")] == [req.id]
    uc.verify_ownership(admin(uc), req.id, approved=True)
    assert uc.get_place("plc_ice").owner_id == "usr_anna" and user(uc, "anna").role == Role.OWNER
    with pytest.raises(ConflictError):
        uc.verify_ownership(admin(uc), req.id, approved=False)
    rejected = uc.request_ownership(user(uc, "jan"), "plc_urzad", "")
    uc.verify_ownership(admin(uc), rejected.id, approved=False)
    assert uc.get_place("plc_urzad").owner_id is None and user(uc, "jan").role == Role.USER
