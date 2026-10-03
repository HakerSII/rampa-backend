"""Shared by all vision models (Phi-3.5 ONNX, Gemini): one instruction, one JSON schema, one parser."""
import json
import re

from app.domain.text import clean_text

from app.domain.model import ImageAnalysis

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
}

Rules:
- barrier_type: short English phrase with spaces, e.g. "stairs without ramp", "elevator out of order", "" if none.
- affected_disabilities: subset of ["wheelchair", "mobility", "visual", "hearing", "cognitive"].
- real_place: false for screenshots, drawings, memes or photos of screens.
- confidence: 0.0-1.0."""


def parse_analysis(raw: str, model: str) -> ImageAnalysis:
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
        barrier_type=clean_text(str(data.get("barrier_type") or "")),
        affected_disabilities=[clean_text(str(x)) for x in data.get("affected_disabilities") or []],
        description=clean_text(str(data.get("description") or "")),  # F42: model output is untrusted text
        confidence=float(data.get("confidence") or 0.0),
        model=model,
    )
