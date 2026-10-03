"""JSON handling of the ONNX adapter — no model needed."""
import pytest

from app.adapters.outbound.vision_onnx import parse_analysis


def test_parses_json_surrounded_by_model_chatter():
    raw = 'Sure! Here is the result:\n```json\n{"real_place": true, "barrier_detected": true, ' \
          '"barrier_type": "stairs", "affected_disabilities": ["wheelchair"], ' \
          '"description": "Three steps", "confidence": 0.9}\n```<|end|>'
    a = parse_analysis(raw)
    assert (a.real_place, a.barrier_type, a.confidence, a.model) == (True, "stairs", 0.9, "phi-3.5-vision-onnx")


def test_missing_fields_get_safe_defaults():
    a = parse_analysis('{"barrier_detected": false}')
    assert (a.real_place, a.affected_disabilities, a.description, a.confidence) == (True, [], "", 0.0)


@pytest.mark.parametrize("raw", ["no json here", "{broken json", '["not", "an object"]'])
def test_invalid_output_raises_value_error(raw):
    with pytest.raises(ValueError):
        parse_analysis(raw)
