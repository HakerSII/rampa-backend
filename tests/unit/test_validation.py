from datetime import timedelta

from app.domain import validation
from app.domain.enums import ValidationStatus
from tests.conftest import NOW
from tests.unit.test_trust import OLD, obs


def conflicting_ids(*observations):
    return {o.id for o in validation.conflicting_observations(list(observations), NOW)}


def test_old_seed_and_fresh_report_do_not_conflict():
    assert conflicting_ids(obs("seed", "yes", author="seed", at=OLD), obs("anna", "no", author="anna")) == set()


def test_two_authors_with_opposite_fresh_values_conflict():
    assert conflicting_ids(obs("anna", "no", author="anna"), obs("marek", "yes", author="marek")) == {"anna", "marek"}


def test_same_author_changing_mind_is_not_a_conflict():
    assert conflicting_ids(obs("a1", "no", author="anna"), obs("a2", "yes", author="anna")) == set()


def test_rejected_observations_do_not_conflict():
    rejected = obs("anna", "no", author="anna", validation=ValidationStatus.REJECTED)
    assert conflicting_ids(rejected, obs("marek", "yes", author="marek")) == set()


def test_window_edge_is_30_days():
    edge = obs("edge", "yes", author="x", at=NOW - timedelta(days=30))
    assert conflicting_ids(edge, obs("anna", "no", author="anna")) == {"edge", "anna"}
