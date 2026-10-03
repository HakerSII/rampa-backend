"""Phi-3.5 Vision (ONNX, onnxruntime-genai) — logic from get_model.py.
Needs `uv sync --extra ai` and the model in AI_MODEL_PATH. Inference is sync + heavy →
runs in a thread, one at a time. Wrap in FallbackVisionAnalyzer (bootstrap does)."""
import asyncio
import json
import re

from app.domain.model import ImageAnalysis

MODEL_NAME = "phi-3.5-vision-onnx"
INSTRUCTION = """You are an accessibility inspector.
Analyze this photo and return ONLY a valid JSON object without markdown formatting or introductory text.

Schema:
{
  "real_place": true,
  "barrier_detected": true,
  "barrier_type": "",
  "affected_disabilities": [],
  "description": "",
  "confidence": 0.0
}"""
PROMPT = f"<|user|>\n<|image_1|>\n{INSTRUCTION}<|end|>\n<|assistant|>\n"


def parse_analysis(raw: str) -> ImageAnalysis:
    """Extract the JSON object from model output. Raises ValueError if there is none."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return ImageAnalysis(
        real_place=bool(data.get("real_place", True)),
        barrier_detected=bool(data.get("barrier_detected", False)),
        barrier_type=str(data.get("barrier_type") or ""),
        affected_disabilities=[str(x) for x in data.get("affected_disabilities") or []],
        description=str(data.get("description") or ""),
        confidence=float(data.get("confidence") or 0.0),
        model=MODEL_NAME,
    )


class OnnxPhiVisionAnalyzer:
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
        import onnxruntime_genai as og  # optional extra "ai"

        self._model = og.Model(self.model_path)
        self._processor = self._model.create_multimodal_processor()

    def _infer(self, image_path: str) -> str:
        import onnxruntime_genai as og

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
