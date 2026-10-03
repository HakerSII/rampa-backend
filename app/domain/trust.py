"""Trust engine (MVP formula, README F3). Feature state is always computed here."""
from datetime import datetime, timedelta

from app.domain.enums import FeatureKey, ObservationSource, StateValue, ValidationStatus
from app.domain.model import FeatureStateRecord, Observation

SOURCE_WEIGHT = {
    ObservationSource.ADMIN: 1.0,
    ObservationSource.VERIFIED_OWNER: 0.85,
    ObservationSource.OPEN_DATA: 0.6,
    ObservationSource.COMMUNITY: 0.5,
}
EVIDENCE_BONUS = 0.1
UP_VOTE_BONUS = 0.1
UP_VOTE_CAP = 0.3
DOWN_VOTE_PENALTY = 0.1
AGE_LIMIT = timedelta(days=180)  # older observations count half
AGE_FACTOR = 0.5


def is_expired(obs: Observation, now: datetime | None) -> bool:
    return bool(now and obs.valid_until and obs.valid_until <= now)


def observation_confidence(obs: Observation, now: datetime | None = None) -> float:
    c = SOURCE_WEIGHT[obs.source]
    if obs.evidence_ids:
        c += EVIDENCE_BONUS
    c += min(UP_VOTE_BONUS * obs.up_votes, UP_VOTE_CAP)
    c -= DOWN_VOTE_PENALTY * obs.down_votes
    c = min(max(c, 0.0), 1.0)
    if now and now - obs.created_at > AGE_LIMIT:
        c *= AGE_FACTOR
    return round(c, 2)


def compute_feature_state(place_id: str, feature: FeatureKey, observations: list[Observation],
                          conflict_open: bool = False, now: datetime | None = None) -> FeatureStateRecord:
    """Winner = highest confidence; tie → newer; same time → later in list. REJECTED/FLAGGED ignored."""
    validation = ValidationStatus.CONFLICT if conflict_open else ValidationStatus.VALID
    active = [(i, o) for i, o in enumerate(observations)
              if o.validation not in (ValidationStatus.REJECTED, ValidationStatus.FLAGGED) and not is_expired(o, now)]
    if not active:
        return FeatureStateRecord(place_id, feature, StateValue.UNKNOWN, validation=validation)

    _, winner = max(active, key=lambda t: (observation_confidence(t[1], now), t[1].created_at, t[0]))
    return FeatureStateRecord(
        place_id=place_id,
        feature=feature,
        state=StateValue(winner.value),
        confidence=observation_confidence(winner, now),
        temporary=winner.temporary,
        last_verified=winner.created_at,
        sources_count=len({o.author_id for _, o in active}),
        validation=validation,
        active_observation_id=winner.id,
    )
