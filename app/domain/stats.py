"""Admin dashboard tiles (mockup "Panel administratora"). Pure: today vs yesterday by clock date."""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.enums import QueueStatus, StateValue, ValidationStatus
from app.domain.model import FeatureStateRecord, Observation, QueueItem, Report

LOW_CONFIDENCE = 0.5


@dataclass(slots=True)
class StatTile:
    value: int
    change_pct: float | None  # today vs yesterday; None if yesterday == 0 or not applicable


@dataclass(slots=True)
class AdminStats:
    new_reports_today: StatTile
    data_conflicts: StatTile
    low_confidence: StatTile
    observations_today: StatTile
    abuse_flags: StatTile
    places: StatTile
    updated_at: datetime


def _change(today: int, yesterday: int) -> float | None:
    return None if yesterday == 0 else round((today - yesterday) / yesterday * 100, 1)


def _per_day(times: Iterable[datetime], now: datetime) -> tuple[int, int]:
    today, yesterday = now.date(), (now - timedelta(days=1)).date()
    days = [t.date() for t in times]
    return days.count(today), days.count(yesterday)


def compute_stats(*, reports: list[Report], observations: list[Observation], queue: list[QueueItem],
                  states: list[FeatureStateRecord], places: int, now: datetime) -> AdminStats:
    rep_t, rep_y = _per_day((r.created_at for r in reports), now)
    obs_t, obs_y = _per_day((o.created_at for o in observations), now)
    q_t, q_y = _per_day((q.created_at for q in queue), now)
    open_conflicts = sum(1 for q in queue if q.status == QueueStatus.OPEN)
    low = sum(1 for s in states if s.state != StateValue.UNKNOWN and s.confidence < LOW_CONFIDENCE)
    return AdminStats(
        new_reports_today=StatTile(rep_t, _change(rep_t, rep_y)),
        data_conflicts=StatTile(open_conflicts, _change(q_t, q_y)),
        low_confidence=StatTile(low, None),
        observations_today=StatTile(obs_t, _change(obs_t, obs_y)),
        abuse_flags=StatTile(sum(1 for o in observations if o.validation == ValidationStatus.FLAGGED), None),
        places=StatTile(places, None),
        updated_at=now,
    )
