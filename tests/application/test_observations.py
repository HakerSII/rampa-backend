import pytest

from app.application import use_cases as uc_module
from app.domain.enums import FeatureKey as F, QueueStatus, ValidationStatus
from app.domain.errors import FileTooLarge, NotFound, Unauthorized, ValidationFailed

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32


async def chunks(*parts):
    for p in parts:
        yield p


def user(uc, name):
    return uc.repo.find_user_by_username(name)


def report(uc, author="anna", **overrides):
    data = dict(place_id="plc_mnk", element="elevator", current_state="not_working", severity="critical",
                nature="temporary", description="Winda nieczynna", photo_ids=[])
    data.update(overrides)
    return uc.create_report(user(uc, author), **data)


# ---------------------------------------------------------------- uploads
async def test_upload_png_is_stored(uc):
    photo = await uc.upload_photo(user(uc, "anna"), chunks(PNG[:5], PNG[5:]), "winda.png")
    assert photo.url.startswith("/media/") and uc.repo.get_photo(photo.id)


async def test_upload_rejects_non_image(uc):
    with pytest.raises(ValidationFailed):
        await uc.upload_photo(user(uc, "anna"), chunks(GIF), "x.gif")


async def test_upload_rejects_too_large(uc, monkeypatch):
    monkeypatch.setattr(uc_module, "MAX_PHOTO_BYTES", 40)
    with pytest.raises(FileTooLarge):
        await uc.upload_photo(user(uc, "anna"), chunks(PNG, PNG), "big.png")


async def test_upload_requires_login(uc):
    with pytest.raises(Unauthorized):
        await uc.upload_photo(None, chunks(PNG), "x.png")


# ---------------------------------------------------------------- reports
async def test_report_creates_observation_and_updates_state(uc):
    photo = await uc.upload_photo(user(uc, "anna"), chunks(PNG), "winda.png")
    r = report(uc, photo_ids=[photo.id])
    assert r.status == "submitted" and len(r.observation_ids) == 1
    o = uc.repo.get_observation(r.observation_ids[0])
    assert (o.feature, o.value, o.temporary, o.evidence_ids) == (F.ELEVATOR, "no", True, [photo.id])
    s = uc.repo.states_for("plc_mnk")[F.ELEVATOR]
    assert (s.state, s.confidence, s.temporary) == ("no", 0.6, True)


@pytest.mark.parametrize("override, error", [
    ({"description": ""}, ValidationFailed),
    ({"description": "x" * 1001}, ValidationFailed),
    ({"photo_ids": ["ph_missing"]}, ValidationFailed),
    ({"photo_ids": ["a", "b", "c", "d", "e", "f"]}, ValidationFailed),
    ({"element": "teleporter"}, ValidationFailed),
    ({"place_id": "nope"}, NotFound),
])
async def test_report_validation(uc, override, error):
    with pytest.raises(error):
        report(uc, **override)


async def test_report_requires_login(uc):
    with pytest.raises(Unauthorized):
        uc.create_report(None, place_id="plc_mnk", element="elevator", current_state="works",
                         severity="minor", nature="permanent", description="ok")


# ---------------------------------------------------------------- votes
async def test_author_cannot_vote_own_observation(uc):
    obs_id = report(uc).observation_ids[0]
    with pytest.raises(ValidationFailed):
        uc.vote(user(uc, "anna"), obs_id, 1)


async def test_re_vote_replaces_previous_and_remove_works(uc):
    obs_id = report(uc).observation_ids[0]
    uc.vote(user(uc, "jan"), obs_id, 1)
    o, _ = uc.vote(user(uc, "jan"), obs_id, -1)
    assert (o.up_votes, o.down_votes) == (0, 1)
    uc.remove_vote(user(uc, "jan"), obs_id)
    assert uc.repo.get_observation(obs_id).votes == {}


async def test_votes_raise_state_confidence(uc):
    obs_id = report(uc).observation_ids[0]
    for name in ("jan", "ola", "piotr"):
        _, state = uc.vote(user(uc, name), obs_id, 1)
    assert state.confidence == 0.8  # 0.5 base (no photo) + 0.3


# ---------------------------------------------------------------- conflicts
async def test_contradicting_observation_opens_single_queue_item(uc):
    report(uc)
    uc.add_observation(user(uc, "marek"), "plc_mnk", feature="elevator", value="yes")
    uc.add_observation(user(uc, "jan"), "plc_mnk", feature="elevator", value="yes")
    items = [q for q in uc.repo.list_queue_items() if q.status == QueueStatus.OPEN]
    assert len(items) == 1 and len(items[0].observation_ids) == 3
    s = uc.repo.states_for("plc_mnk")[F.ELEVATOR]
    # all three score 0.5 (no photo, no votes) → tie → newest ("yes") wins, flagged as conflict
    assert (s.state, s.validation) == ("yes", ValidationStatus.CONFLICT)


async def test_list_observations_hides_rejected_when_active(uc):
    o = uc.add_observation(user(uc, "marek"), "plc_mnk", feature="ramp", value="no")
    o.validation = ValidationStatus.REJECTED
    assert o.id not in {x.id for x in uc.list_observations("plc_mnk", F.RAMP)}
    assert o.id in {x.id for x in uc.list_observations("plc_mnk", F.RAMP, active=False)}
