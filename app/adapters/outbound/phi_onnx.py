"""One loaded Phi-3.5 Vision model (onnxruntime-genai) per folder, shared by photo analysis (AI_MODE=onnx) and the
chat (CHAT_MODE=onnx, F46): ~2.6 GB in memory once. RUN_LOCK: one inference at a time (CPU/GPU memory)."""
import threading
from dataclasses import dataclass

_LOADED: dict[str, "Loaded"] = {}
_LOAD_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()


@dataclass
class Loaded:
    model: object
    processor: object


def _og():
    import onnxruntime_genai as og  # optional extra "ai"

    return og


def load(model_path: str) -> Loaded:
    """Load the model once (blocking; call from a thread)."""
    with _LOAD_LOCK:
        if model_path not in _LOADED:
            model = _og().Model(model_path)
            _LOADED[model_path] = Loaded(model, model.create_multimodal_processor())
        return _LOADED[model_path]
