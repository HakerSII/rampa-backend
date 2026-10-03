"""Google Gemini vision (AI_MODE=gemini) via REST generateContent — httpx, no SDK.
Key goes in the x-goog-api-key header (never in URL/logs). Wrap in FallbackVisionAnalyzer (bootstrap does)."""
import asyncio
import base64
from pathlib import Path

import httpx

from app.adapters.outbound.vision_prompt import INSTRUCTION, parse_analysis
from app.domain.model import ImageAnalysis

DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash"
RETRY_STATUS = {429, 500, 502, 503, 504}  # transient (e.g. "high demand")


def _mime(data: bytes) -> str:
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


class GeminiVisionAnalyzer:
    LABEL = "gemini"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, api_url: str = DEFAULT_API_URL,
                 http: httpx.AsyncClient | None = None, timeout_s: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.api_url = api_url.rstrip("/")
        self._http = http
        self.timeout_s = timeout_s
        self.max_retries = 2
        self.retry_pause_s = 2.0  # doubles each retry; whole call still bounded by FallbackVisionAnalyzer timeout

    async def analyze(self, image_path: str, original_name: str) -> ImageAnalysis:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        data = await asyncio.to_thread(Path(image_path).read_bytes)
        body = {
            "contents": [{"parts": [
                {"text": INSTRUCTION},
                {"inline_data": {"mime_type": _mime(data), "data": base64.b64encode(data).decode()}},
            ]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0},
        }
        url = f"{self.api_url}/models/{self.model}:generateContent"
        client = self._http or httpx.AsyncClient(timeout=self.timeout_s)
        try:
            for attempt in range(self.max_retries + 1):
                r = await client.post(url, json=body, headers={"x-goog-api-key": self.api_key})
                if r.status_code not in RETRY_STATUS or attempt == self.max_retries:
                    break
                await asyncio.sleep(self.retry_pause_s * 2 ** attempt)
        finally:
            if self._http is None:
                await client.aclose()

        if r.status_code >= 400:
            try:
                detail = r.json()["error"]["message"]
            except Exception:  # noqa: BLE001
                detail = r.text[:200]
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {detail}")
        candidates = r.json().get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates (blocked or empty)")
        text = "".join(p.get("text", "") for p in candidates[0].get("content", {}).get("parts", []))
        return parse_analysis(text, model="gemini")
