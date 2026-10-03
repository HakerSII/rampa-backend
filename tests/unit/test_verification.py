from datetime import timedelta

from app.domain.enums import FeatureKey as F, ObservationSource as Src, StateValue as S, ValidationStatus as V
from app.domain.model import FeatureStateRecord
from app.domain.verification import summarize
from tests.conftest import NOW


def st(feature, state="yes", conf=0.9, days=0, validation=V.VALID):
    return FeatureStateRecord("p", F(feature), S(state), conf, last_verified=NOW - timedelta(days=days),
                              validation=validation)


def test_no_data_is_unverified():
    v = summarize([FeatureStateRecord("p", F.RAMP, S.UNKNOWN)], set(), NOW)
    assert (v.status, v.label, v.confidence, v.confidence_level, v.last_verified) == (
        "unverified", "Brak danych", 0.0, "low", None)


def test_fresh_data_is_confirmed_today_with_mean_confidence():
    v = summarize([st("ramp", conf=1.0), st("elevator", conf=0.6, days=10)], {Src.COMMUNITY, Src.ADMIN}, NOW)
    assert (v.status, v.label, v.confidence, v.confidence_level) == ("confirmed", "Potwierdzone dzisiaj", 0.8, "high")
    assert v.last_verified == NOW and v.sources == ["admin", "community"]


def test_days_ago_label_and_levels():
    assert summarize([st("ramp", conf=0.5, days=3)], set(), NOW).label == "Zweryfikowane 3 dni temu"
    assert summarize([st("ramp", conf=0.5, days=3)], set(), NOW).confidence_level == "medium"
    assert summarize([st("ramp", conf=0.5, days=1)], set(), NOW).label == "Zweryfikowane 1 dzień temu"
    assert summarize([st("ramp", conf=0.4, days=60)], set(), NOW).status == "verified"


def test_old_data_needs_update():
    v = summarize([st("ramp", days=120)], set(), NOW)
    assert (v.status, v.label) == ("needs_update", "Wymaga aktualizacji")


def test_conflict_wins():
    v = summarize([st("ramp"), st("elevator", validation=V.CONFLICT)], set(), NOW)
    assert (v.status, v.label) == ("conflict", "Sprzeczne zgłoszenia")
