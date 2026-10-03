import pytest

from app.domain.enums import FeatureKey as F
from app.domain.text_parse import parse_text


def s(text):
    return [(x.feature, x.value, x.temporary) for x in parse_text(text)]


@pytest.mark.parametrize("text, expected", [
    ("winda od dwóch tygodni nie działa", [(F.ELEVATOR, "no", True)]),
    ("Winda naprawiona, działa.", [(F.ELEVATOR, "yes", False)]),
    ("Podjazd zastawiony rowerami, ale winda działa", [(F.RAMP, "no", True), (F.ELEVATOR, "yes", False)]),
    ("Brak pętli indukcyjnej", [(F.INDUCTION_LOOP, "no", False)]),
    ("Wejście bez schodów", [(F.STEP_FREE_ENTRANCE, "yes", False)]),
    ("Trzy schody przy wejściu", [(F.STEP_FREE_ENTRANCE, "no", False)]),
    ("The elevator is out of order today", [(F.ELEVATOR, "no", True)]),
    ("Psy asystujące są wpuszczane, jest dostępne", [(F.ASSISTANCE_DOG_ALLOWED, "yes", False)]),
    ("Ładna pogoda w Krakowie", []),
])
def test_rules(text, expected):
    assert s(text) == expected


def test_confidence_explicit_vs_implied():
    (explicit,) = parse_text("winda nie działa")
    (implied,) = parse_text("trzy schody przy wejściu")
    assert (explicit.confidence, implied.confidence) == (0.8, 0.6)
