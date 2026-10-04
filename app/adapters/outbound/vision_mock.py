"""Deterministic offline vision (AI_MODE=mock) + fallback chain for the real models (F44)."""
import asyncio
import logging
import zlib
from collections.abc import Callable

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
    LABEL = "mock"

    async def analyze(self, image_path: str, original_name: str) -> ImageAnalysis:
        name = original_name.lower()
        base = next((case for words, case in BY_NAME if any(w in name for w in words)), None)
        base = base or BY_HASH[zlib.crc32(name.encode()) % len(BY_HASH)]
        return ImageAnalysis(base.real_place, base.barrier_detected, base.barrier_type,
                             list(base.affected_disabilities), base.description, base.confidence, "mock")


def label(analyzer) -> str:
    """Model name shown in status events; a chain is named after its first step."""
    if isinstance(analyzer, FallbackVisionAnalyzer):
        return label(analyzer.primary)
    return getattr(analyzer, "LABEL", type(analyzer).__name__)


class FallbackVisionAnalyzer:
    """Real model first; any error or timeout → next step (chain: Gemini → local ONNX → mock; demo never breaks).
    on_step(event) reports progress: {"stage":"analyzing","model"} and {"stage":"fallback","from","model"}."""
    REPORTS_STEPS = True

    def __init__(self, primary: VisionAnalyzer, fallback: VisionAnalyzer, timeout_s: float = 60.0):
        self.primary = primary
        self.fallback = fallback
        self.timeout_s = timeout_s

    async def analyze(self, image_path: str, original_name: str,
                      on_step: Callable[[dict], None] | None = None, announced: bool = False) -> ImageAnalysis:
        step = on_step or (lambda event: None)
        if not announced:
            step({"stage": "analyzing", "model": label(self.primary)})
        try:
            return await asyncio.wait_for(self.primary.analyze(image_path, original_name), self.timeout_s)
        except Exception as e:  # noqa: BLE001 — any model failure must degrade to the next step
            log.warning("vision model %s failed (%s: %s) → %s", label(self.primary), type(e).__name__, e,
                        label(self.fallback))
            step({"stage": "fallback", "from": label(self.primary), "model": label(self.fallback)})
            if isinstance(self.fallback, FallbackVisionAnalyzer):
                return await self.fallback.analyze(image_path, original_name, on_step, announced=True)
            return await self.fallback.analyze(image_path, original_name)
