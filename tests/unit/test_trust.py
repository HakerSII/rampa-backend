from datetime import timedelta

from app.domain import trust
from app.domain.enums import FeatureKey as F, ObservationSource as Src, ObservationValue as V, StateValue, ValidationStatus
from tests.conftest import NOW

OLD = NOW - timedelta(days=60)


def obs(id, value, *, author="u1", source=Src.COMMUNITY, at=NOW, photo=False, votes=None,
        temporary=False, validation=ValidationStatus.VALID):
    from app.domain.model import Observation
    return Observation(id, "p", F.ELEVATOR, V(value), source, author, at, temporary=temporary,
                       evidence_ids=["ph_1"] if photo else [], votes=votes or {}, validation=validation)


def state(*observations, conflict_open=False):
    return trust.compute_feature_state("p", F.ELEVATOR, list(observations), conflict_open=conflict_open)


def test_no_observations_means_unknown():
    s = state()
    assert (s.state, s.confidence) == (StateValue.UNKNOWN, 0.0)


def test_fresh_report_with_photo_beats_old_community_data():
    s = state(obs("seed", "yes", author="seed", at=OLD), obs("anna", "no", author="anna", photo=True, temporary=True))
    assert (s.state, s.confidence, s.temporary, s.active_observation_id) == ("no", 0.6, True, "anna")
    assert s.sources_count == 2


def test_three_confirmations_raise_confidence_to_cap():
    votes = {"jan": 1, "ola": 1, "piotr": 1, "x": 1}  # 4th up-vote ignored by +0.3 cap
    assert state(obs("anna", "no", photo=True, votes=votes)).confidence == 0.9


def test_down_vote_lowers_confidence():
    assert state(obs("a", "yes", votes={"jan": -1})).confidence == 0.4


def test_admin_source_has_full_weight():
    assert state(obs("a", "yes", source=Src.ADMIN)).confidence == 1.0


def test_rejected_observations_are_ignored():
    s = state(obs("seed", "yes", at=OLD), obs("anna", "no", photo=True, validation=ValidationStatus.REJECTED))
    assert (s.state, s.active_observation_id) == ("yes", "seed")


def test_tie_goes_to_newer_then_later_inserted():
    assert state(obs("old", "yes", at=OLD), obs("new", "no")).state == "no"
    assert state(obs("first", "yes"), obs("second", "no")).active_observation_id == "second"


def test_open_conflict_marks_state_validation():
    assert state(obs("a", "yes"), conflict_open=True).validation == ValidationStatus.CONFLICT
