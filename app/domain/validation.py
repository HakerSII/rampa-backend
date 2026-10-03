"""Conflict detection: within the window, ≥2 distinct values AND ≥2 distinct authors."""
from datetime import datetime, timedelta

from app.domain.enums import ValidationStatus
from app.domain.model import Observation

CONFLICT_WINDOW = timedelta(days=30)
INACTIVE = frozenset({ValidationStatus.REJECTED, ValidationStatus.FLAGGED})  # excluded from trust + conflicts


def is_active(o: Observation) -> bool:
    return o.validation not in INACTIVE


def conflicting_observations(observations: list[Observation], now: datetime) -> list[Observation]:
    window = [o for o in observations
              if is_active(o) and o.created_at >= now - CONFLICT_WINDOW]
    if len({o.value for o in window}) >= 2 and len({o.author_id for o in window}) >= 2:
        return window
    return []
