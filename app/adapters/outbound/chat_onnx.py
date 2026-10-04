"""F46: chat with the local Phi-3.5 (onnxruntime-genai, text only). Loaded in a background thread at app start
(CHAT_PRELOAD); tokens are streamed to the caller as they are generated; a timeout stops the generation."""
import asyncio
import logging
import threading
from collections.abc import Callable, Iterator

from app.adapters.outbound import phi_onnx

log = logging.getLogger(__name__)

MODEL_NAME = "phi-3.5-vision-onnx"
STOP = ("<|end|>", "<|endoftext|>")


def build_prompt(messages: list[dict]) -> str:
    """Phi-3.5 chat format (tokenizer_config chat_template)."""
    return "".join(f"<|{m['role']}|>\n{m['content']}<|end|>\n" for m in messages) + "<|assistant|>\n"


def _generate(loaded: phi_onnx.Loaded, prompt: str, max_new_tokens: int, cancel: threading.Event) -> Iterator[str]:
    """Greedy generation, one decoded piece at a time (blocking; runs in a worker thread)."""
    og = phi_onnx._og()
    with phi_onnx.RUN_LOCK:
        inputs = loaded.processor(prompt, images=None)
        params = og.GeneratorParams(loaded.model)
        params.set_search_options(max_length=4096, do_sample=False)
        generator = og.Generator(loaded.model, params)
        generator.set_inputs(inputs)
        stream = loaded.processor.create_stream()
        try:
            for _ in range(max_new_tokens):
                if cancel.is_set() or generator.is_done():
                    return
                generator.generate_next_token()
                tokens = generator.get_next_tokens()
                if not len(tokens):
                    continue
                piece = stream.decode(tokens[0])
                if piece in STOP:
                    return
                yield piece
        finally:
            del generator


class OnnxPhiChatModel:
    name = MODEL_NAME

    def __init__(self, model_path: str, timeout_s: float = 120.0):
        self.model_path = model_path
        self.timeout_s = timeout_s
        self._state = "off"
        self._loaded: phi_onnx.Loaded | None = None
        self._thread: threading.Thread | None = None

    def state(self) -> str:
        return self._state

    def start_loading(self) -> None:
        """Load in a daemon thread; the app keeps answering (rules) meanwhile."""
        if self._state in ("loading", "ready"):
            return
        self._state = "loading"
        self._thread = threading.Thread(target=self.load_now, name="chat-model-load", daemon=True)
        self._thread.start()

    def load_now(self) -> None:
        self._state = "loading"
        try:
            self._loaded = phi_onnx.load(self.model_path)
            self._state = "ready"
            log.info("chat model ready: %s", self.model_path)
        except Exception as e:  # noqa: BLE001 — missing extra / model / memory → rules answers
            self._state = "error"
            log.warning("chat model could not load (%s: %s) → rules", type(e).__name__, e)

    async def complete(self, messages: list[dict], max_new_tokens: int,
                       on_token: Callable[[str], None] | None = None) -> str:
        if self._state != "ready":
            raise RuntimeError(f"chat model not ready ({self._state})")
        loop = asyncio.get_running_loop()
        cancel = threading.Event()
        prompt = build_prompt(messages)
        pieces: list[str] = []

        def work():
            for piece in _generate(self._loaded, prompt, max_new_tokens, cancel):
                pieces.append(piece)
                if on_token:
                    loop.call_soon_threadsafe(on_token, piece)

        try:
            await asyncio.wait_for(asyncio.to_thread(work), self.timeout_s)
        except asyncio.TimeoutError:
            cancel.set()
            raise
        await asyncio.sleep(0)  # deliver the last on_token callbacks before returning
        return "".join(pieces)
