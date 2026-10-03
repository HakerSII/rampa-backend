from datetime import timedelta

from app.domain.enums import FeatureKey as F, QueueStatus, ValidationStatus
from app.domain.history import build_history
from app.domain.model import QueueItem
from tests.conftest import NOW
from tests.unit.test_trust import obs


def test_history_newest_first_with_conflict_lifecycle():
    t0, t1 = NOW - timedelta(hours=2), NOW - timedelta(hours=1)
    a = obs("anna", "no", author="anna", at=t0, validation=ValidationStatus.REJECTED)
    m = obs("marek", "yes", author="marek", at=t1)
    item = QueueItem("q_1", "p", F.ELEVATOR, t1, ["anna", "marek"], status=QueueStatus.RESOLVED,
                     decision="approved", resolved_at=NOW)
    events = build_history([a, m], [item])
    assert [e.event for e in events] == ["conflict_resolved", "conflict_detected", "observation_added",
                                         "observation_added"]
    assert events[0].created_at == NOW and "approved" in events[0].description
    assert events[-1].observation_id == "anna" and "REJECTED" in events[-1].description
    assert events[0].actor_id is None and events[-1].actor_id == "anna"


def test_open_conflict_has_no_resolution_event():
    item = QueueItem("q_1", "p", F.ELEVATOR, NOW, ["x"])
    assert [e.event for e in build_history([], [item])] == ["conflict_detected"]
