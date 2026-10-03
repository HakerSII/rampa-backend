import asyncio

import pytest

from app.adapters.outbound.vision_mock import FallbackVisionAnalyzer, MockVisionAnalyzer
from app.domain.enums import FeatureKey as F
from app.domain.errors import NotARealPlace, Unauthorized, ValidationFailed
from tests.application.test_observations import PNG, chunks, user
from tests.conftest import make_use_cases


async def upload(uc, name, who="anna"):
    return (await uc.upload_photo(user(uc, who), chunks(PNG), name)).id


async def test_mock_elevator_photo_suggests_broken_elevator(uc):
    r = await uc.analyze_image(user(uc, "anna"), [await upload(uc, "winda.png")])
    assert r.model == "mock"
    assert r.analysis.barrier_type == "elevator out of order"
    assert "winda" in [t.label for t in r.tags]
    assert (r.suggested.element, r.suggested.current_state, r.suggested.severity) == (
        F.ELEVATOR, "not_working", "critical")


async def test_mock_is_deterministic_for_unknown_names(uc):
    a = await uc.analyze_image(user(uc, "anna"), [await upload(uc, "IMG_1234.jpg")])
    b = await uc.analyze_image(user(uc, "anna"), [await upload(uc, "IMG_1234.jpg")])
    assert a.analysis == b.analysis


async def test_screenshot_only_is_not_a_real_place(uc):
    with pytest.raises(NotARealPlace):
        await uc.analyze_image(user(uc, "anna"), [await upload(uc, "screenshot.png")])


async def test_many_photos_merge_and_skip_non_real(uc):
    ids = [await upload(uc, n) for n in ("screenshot.png", "schody.jpg", "winda.png")]
    r = await uc.analyze_image(user(uc, "anna"), ids)
    assert r.analysis.confidence == 0.82  # best real photo (elevator)
    labels = [t.label for t in r.tags]
    assert labels.count("wejście bez schodów") == 1 and "podjazd" in labels and "winda" in labels
    assert "Entrance with 4 steps" in r.detected and "Elevator door" in r.detected


@pytest.mark.parametrize("photo_ids", [[], ["ph_missing"], ["a", "b", "c", "d", "e", "f"]])
async def test_photo_ids_validated(uc, photo_ids):
    with pytest.raises(ValidationFailed):
        await uc.analyze_image(user(uc, "anna"), photo_ids)


async def test_login_required(uc):
    with pytest.raises(Unauthorized):
        await uc.analyze_image(None, ["ph_1"])


class Failing:
    async def analyze(self, path, original_name):
        raise RuntimeError("GPU on fire")


class Slow:
    async def analyze(self, path, original_name):
        await asyncio.sleep(5)


@pytest.mark.parametrize("primary", [Failing(), Slow()])
async def test_onnx_failure_or_timeout_falls_back_to_mock(primary):
    uc = make_use_cases(vision=FallbackVisionAnalyzer(primary, MockVisionAnalyzer(), timeout_s=0.05))
    r = await uc.analyze_image(user(uc, "anna"), [await upload(uc, "winda.png")])
    assert r.model == "mock" and r.suggested.element == F.ELEVATOR
