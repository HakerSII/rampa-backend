from app.domain.enums import FeatureKey as F
from app.domain.model import ImageAnalysis
from app.domain.suggestions import suggest

ELEVATOR = ImageAnalysis(True, True, "elevator out of order",
                         ["wheelchair", "mobility"],
                         "Elevator door with an 'out of order' notice; stairs next to the entrance.", 0.82)
STAIRS = ImageAnalysis(True, True, "stairs without ramp", ["elderly"],
                       "Entrance with 4 steps and no ramp or handrail.", 0.77)
CLEAR = ImageAnalysis(True, False, "", [], "Level entrance with automatic doors.", 0.7)


def labels(result):
    return [t.label for t in result.tags]


def test_broken_elevator_gives_tags_and_critical_suggestion():
    r = suggest(ELEVATOR)
    assert labels(r) == ["winda", "wejście bez schodów", "awaria", "tablica informacyjna"]
    assert r.tags[0].feature == F.ELEVATOR and r.tags[0].confidence == 0.82
    assert (r.suggested.element, r.suggested.current_state, r.suggested.severity) == (
        F.ELEVATOR, "not_working", "critical")


def test_stairs_without_wheelchair_impact_is_an_obstacle():
    r = suggest(STAIRS)
    assert labels(r)[:2] == ["wejście bez schodów", "podjazd"]
    assert (r.suggested.element, r.suggested.severity) == (F.STEP_FREE_ENTRANCE, "obstacle")


def test_no_barrier_means_no_suggestion():
    r = suggest(CLEAR)
    assert r.suggested is None and r.tags == []


def test_physical_or_mobility_impairment_is_critical_like_wheelchair():
    for affected in (["physical"], ["mobility"], ["Wheelchair users"]):
        a = ImageAnalysis(True, True, "stairs_without_ramp", affected, "Stairs, no ramp.", 0.99)
        assert suggest(a).suggested.severity == "critical"
