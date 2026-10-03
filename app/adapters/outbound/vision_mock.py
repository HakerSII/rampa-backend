"""Deterministic offline vision (AI_MODE=mock) + fallback wrapper for the real model."""
import asyncio
import logging
import zlib

from app.application.ports import VisionAnalyzer
from app.domain.model import ImageAnalysis

log = logging.getLogger(__name__)

ELEVATOR_BROKEN = ImageAnalysis(
    True, True, "elevator out of order", ["wheelchair", "mobility"],
    "Elevator door with an 'out of order' notice; stairs next to the entrance.", 0.82)
STAIRS_NO_RAMP = ImageAnalysis(
    True, True, "stairs without ramp", ["wheelchair", "mobility"],
    "Entrance with 4 steps and no ramp or handrail.", 0.77)
NO_BARRIER = ImageAnalysis(
    True, False, "", [], "Level entrance with automatic doors.", 0.7)
NOT_A_PLACE = ImageAnalysis(
    False, False, "", [], "Screenshot or graphic, not a photo of a real place.", 0.9)

BY_NAME = [
    (("screenshot", "screen", "meme"), NOT_A_PLACE),
    (("winda", "elevator", "lift"), ELEVATOR_BROKEN),
    (("schody", "stairs", "steps"), STAIRS_NO_RAMP),
]
BY_HASH = [ELEVATOR_BROKEN, STAIRS_NO_RAMP, NO_BARRIER]


class MockVisionAnalyzer:
    async def analyze(self, image_path: str, original_name: str) -> ImageAnalysis:
        name = original_name.lower()
        base = next((case for words, case in BY_NAME if any(w in name for w in words)), None)
        base = base or BY_HASH[zlib.crc32(name.encode()) % len(BY_HASH)]
        return ImageAnalysis(base.real_place, base.barrier_detected, base.barrier_type,
                             list(base.affected_disabilities), base.description, base.confidence, "mock")


class FallbackVisionAnalyzer:
    """Real model first; any error or timeout → fallback answer (demo never breaks)."""

    def __init__(self, primary: VisionAnalyzer, fallback: VisionAnalyzer, timeout_s: float = 60.0):
        self.primary = primary
        self.fallback = fallback
        self.timeout_s = timeout_s

    async def analyze(self, image_path: str, original_name: str) -> ImageAnalysis:
        try:
            return await asyncio.wait_for(self.primary.analyze(image_path, original_name), self.timeout_s)
        except Exception as e:  # noqa: BLE001 — any model failure must degrade to mock
            log.warning("vision model failed (%s: %s) → mock", type(e).__name__, e)
            return await self.fallback.analyze(image_path, original_name)
