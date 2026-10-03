from datetime import timedelta

from app.domain.enums import CurrentState, FeatureKey as F, Nature, QueueStatus, Severity, StateValue as S
from app.domain.model import FeatureStateRecord, QueueItem, Report
from app.domain.stats import compute_stats
from tests.conftest import NOW
from tests.unit.test_trust import obs

Y = NOW - timedelta(days=1)


def rep(at):
    return Report("r", "p", "u", F.ELEVATOR, CurrentState.NOT_WORKING, Severity.MINOR, Nature.UNKNOWN, "x", at)


def q(at, status=QueueStatus.OPEN):
    return QueueItem("q", "p", F.ELEVATOR, at, [], status=status)


def test_tiles_today_vs_yesterday():
    s = compute_stats(
        reports=[rep(NOW), rep(NOW), rep(NOW), rep(Y), rep(Y)],
        observations=[obs("a", "yes"), obs("b", "no", at=Y)],
        queue=[q(NOW), q(NOW), q(Y, QueueStatus.RESOLVED)],
        states=[FeatureStateRecord("p", F.RAMP, S.YES, 0.4), FeatureStateRecord("p", F.ELEVATOR, S.YES, 0.9),
                FeatureStateRecord("p", F.INDUCTION_LOOP, S.UNKNOWN, 0.0)],
        places=4, now=NOW)
    assert (s.new_reports_today.value, s.new_reports_today.change_pct) == (3, 50.0)
    assert (s.data_conflicts.value, s.data_conflicts.change_pct) == (2, 100.0)
    assert (s.low_confidence.value, s.low_confidence.change_pct) == (1, None)  # unknown not counted
    assert (s.observations_today.value, s.places.value, s.updated_at) == (1, 4, NOW)


def test_change_is_none_when_yesterday_was_zero():
    s = compute_stats(reports=[rep(NOW)], observations=[], queue=[], states=[], places=0, now=NOW)
    assert s.new_reports_today.change_pct is None
