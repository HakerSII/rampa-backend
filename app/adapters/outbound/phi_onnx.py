"""One loaded Phi-3.5 Vision model (onnxruntime-genai) per folder, shared by photo analysis (AI_MODE=onnx), the chat
(CHAT_MODE=onnx, F46) and recommendations (AI_RECOMMENDER=onnx, F47): ~2.6 GB in memory once.
RUN_LOCK: one inference at a time (CPU/GPU memory).

F48: missing → downloaded first (AI_MODEL_DOWNLOAD, model_fetch); not enough free memory (AI_MODEL_MIN_RAM_MB) →
not loaded at all (an out-of-memory kill would take the whole server down); preload() does it in the background at
start. STATE per folder (off | downloading | loading | ready | error + detail) is shown in /health."""
import logging
import threading
from dataclasses import dataclass

from app.adapters.outbound import model_fetch

log = logging.getLogger(__name__)

_LOADED: dict[str, "Loaded"] = {}
_LOAD_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()
STATE: dict[str, dict] = {}
_CONFIG = {"download": False, "repo": "", "subfolder": "", "min_ram_mb": 0}


@dataclass
class Loaded:
    model: object
    processor: object


def _og():
    import onnxruntime_genai as og  # optional extra "ai"

    return og


def configure(*, download: bool, repo: str, subfolder: str, min_ram_mb: int) -> None:
    _CONFIG.update(download=download, repo=repo, subfolder=subfolder, min_ram_mb=min_ram_mb)


def download_enabled() -> bool:
    return bool(_CONFIG["download"])


def state(model_path: str) -> dict:
    return dict(STATE.get(model_path) or {"state": "off", "detail": ""})


def _set(model_path: str, value: str, detail: str = "") -> None:
    STATE[model_path] = {"state": value, "detail": detail}


def load(model_path: str) -> Loaded:
    """Download if needed, check memory, load once (blocking; call from a thread)."""
    with _LOAD_LOCK:
        if model_path in _LOADED:
            return _LOADED[model_path]
        try:
            if _CONFIG["download"] and not model_fetch.is_complete(model_path):
                _set(model_path, "downloading", f"{_CONFIG['repo']}/{_CONFIG['subfolder']}")
                model_fetch.ensure_model(model_path, _CONFIG["repo"], _CONFIG["subfolder"])
            need, free = _CONFIG["min_ram_mb"], model_fetch.available_memory_mb()
            if need and free is not None and free < need:
                raise MemoryError(f"not enough memory: {free} MB available, needs {need} MB (AI_MODEL_MIN_RAM_MB)")
            _set(model_path, "loading")
            model = _og().Model(model_path)
            _LOADED[model_path] = Loaded(model, model.create_multimodal_processor())
            _set(model_path, "ready")
            return _LOADED[model_path]
        except Exception as e:
            _set(model_path, "error", f"{type(e).__name__}: {e}")
            raise


def preload(model_path: str) -> threading.Thread:
    """Start load() in a daemon thread (server start); failures only change STATE and log."""
    def run():
        try:
            load(model_path)
            log.info("local model ready: %s", model_path)
        except Exception as e:  # noqa: BLE001 — the app keeps answering with the fallbacks
            log.warning("local model not loaded (%s: %s) → fallbacks", type(e).__name__, e)

    thread = threading.Thread(target=run, name="local-model-preload", daemon=True)
    thread.start()
    return thread
