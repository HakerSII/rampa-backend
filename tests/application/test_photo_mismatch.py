"""F45: photo metadata on upload; the AI check compares it and deletes the photo on a mismatch."""
from pathlib import Path

import pytest

from app.domain.errors import PhotoMismatch, ValidationFailed
from tests.application.test_observations import PNG, chunks, user
from tests.conftest import make_use_cases


@pytest.fixture
def uc(tmp_path):
    from app.adapters.outbound.files import LocalFileStorage
    u = make_use_cases()
    u.storage = LocalFileStorage(str(tmp_path))
    return u


async def upload(uc, name, **meta):
    return await uc.upload_photo(user(uc, "anna"), chunks(PNG), name, **meta)


async def test_upload_keeps_metadata(uc):
    ph = await upload(uc, "winda.png", place_id="plc_mnk", element="elevator", current_state="not_working")
    stored = uc.repo.get_photo(ph.id)
    assert (stored.place_id, stored.element, stored.current_state) == ("plc_mnk", "elevator", "not_working")


async def test_upload_without_metadata_unchanged(uc):
    ph = await upload(uc, "winda.png")
    assert (ph.place_id, ph.element, ph.current_state) == (None, None, None)


@pytest.mark.parametrize("meta", [{"element": "teleport"}, {"current_state": "broken"}, {"place_id": "plc_nope"}])
async def test_upload_rejects_bad_metadata(uc, meta):
    with pytest.raises(ValidationFailed):
        await upload(uc, "winda.png", **meta)


async def test_matching_metadata_gives_the_result(uc):
    ph = await upload(uc, "winda.png", element="elevator", current_state="not_working")
    r = await uc.analyze_image(user(uc, "anna"), [ph.id])
    assert r.suggested.element == "elevator" and uc.repo.get_photo(ph.id) is not None


async def test_other_element_is_a_mismatch_and_deletes_the_photo(uc):
    ph = await upload(uc, "winda.png", element="ramp")
    with pytest.raises(PhotoMismatch) as e:
        await uc.analyze_image(user(uc, "anna"), [ph.id])
    assert e.value.code == "PHOTO_MISMATCH"
    assert e.value.details["expected"] == {"element": "ramp", "current_state": None}
    assert e.value.details["suggested"]["element"] == "elevator"
    assert e.value.details["deleted_photo_ids"] == [ph.id]
    assert uc.repo.get_photo(ph.id) is None and not Path(ph.path).exists()


async def test_same_element_other_state_is_a_mismatch(uc):
    ph = await upload(uc, "winda.png", element="elevator", current_state="works")
    with pytest.raises(PhotoMismatch):
        await uc.analyze_image(user(uc, "anna"), [ph.id])


async def test_expected_in_the_request_overrides_metadata(uc):
    ph = await upload(uc, "winda.png", element="ramp")
    r = await uc.analyze_image(user(uc, "anna"), [ph.id], expected={"element": "elevator"})
    assert r.suggested.element == "elevator"


async def test_no_expectation_is_only_a_suggestion(uc):
    ph = await upload(uc, "winda.png")
    r = await uc.analyze_image(user(uc, "anna"), [ph.id])
    assert r.suggested.element == "elevator"


async def test_photo_used_as_evidence_is_kept(uc):
    ph = await upload(uc, "winda.png")
    uc.add_observation(user(uc, "anna"), "plc_mnk", feature="elevator", value="no", photo_ids=[ph.id])
    with pytest.raises(PhotoMismatch) as e:
        await uc.analyze_image(user(uc, "anna"), [ph.id], expected={"element": "ramp"})
    assert e.value.details["deleted_photo_ids"] == [] and uc.repo.get_photo(ph.id) is not None


async def test_invalid_expected_element(uc):
    ph = await upload(uc, "winda.png")
    with pytest.raises(ValidationFailed):
        await uc.analyze_image(user(uc, "anna"), [ph.id], expected={"element": "teleport"})
