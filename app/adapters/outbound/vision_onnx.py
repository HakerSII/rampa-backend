"""Phi-3.5 Vision (ONNX, onnxruntime-genai) — logic from get_model.py.
Needs `uv sync --extra ai` and the model in AI_MODEL_PATH. Inference is sync + heavy →
runs in a thread, one at a time. Wrap in FallbackVisionAnalyzer (bootstrap does)."""
import asyncio

from app.adapters.outbound import phi_onnx
from app.adapters.outbound.vision_prompt import INSTRUCTION, parse_analysis as _parse
from app.domain.model import ImageAnalysis

MODEL_NAME = "phi-3.5-vision-onnx"


def onnx_available(model_path: str) -> bool:
    """F44: the local model can run here — onnxruntime-genai installed and the model folder present."""
    import importlib.util
    from pathlib import Path

    return importlib.util.find_spec("onnxruntime_genai") is not None and Path(model_path).is_dir()
PROMPT = f"<|user|>\n<|image_1|>\n{INSTRUCTION}<|end|>\n<|assistant|>\n"


def parse_analysis(raw: str) -> ImageAnalysis:
    return _parse(raw, MODEL_NAME)


class OnnxPhiVisionAnalyzer:
    LABEL = MODEL_NAME

    def __init__(self, model_path: str, max_length: int = 4096):
        self.model_path = model_path
        self.max_length = max_length
        self._model = None
        self._processor = None
        self._load_lock = asyncio.Lock()
        self._run = asyncio.Semaphore(1)  # one inference at a time (GPU/RAM)

    async def analyze(self, image_path: str, original_name: str) -> ImageAnalysis:
        async with self._load_lock:
            if self._model is None:
                await asyncio.to_thread(self._load)
        async with self._run:
            raw = await asyncio.to_thread(self._infer, image_path)
        return parse_analysis(raw)

    def _load(self) -> None:
        loaded = phi_onnx.load(self.model_path)  # shared with the chat (F46)
        self._model, self._processor = loaded.model, loaded.processor

    def _infer(self, image_path: str) -> str:
        with phi_onnx.RUN_LOCK:  # one inference at a time, also across photo analysis and chat
            return self._infer_locked(image_path)

    def _infer_locked(self, image_path: str) -> str:
        og = phi_onnx._og()
        images = og.Images.open(image_path)
        inputs = self._processor(PROMPT, images=images)
        params = og.GeneratorParams(self._model)
        params.set_search_options(max_length=self.max_length, do_sample=False)
        generator = og.Generator(self._model, params)
        generator.set_inputs(inputs)
        stream = self._processor.create_stream()
        out = ""
        try:
            while not generator.is_done():
                generator.generate_next_token()
                tokens = generator.get_next_tokens()
                if len(tokens):
                    out += stream.decode(tokens[0])
        finally:
            del generator
        return out.replace("<|end|>", "").strip()
