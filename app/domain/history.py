"""Audit trail of a place ("Historia i audyt"), derived from observations + queue items. Pure."""
from dataclasses import dataclass
from datetime import datetime

from app.domain.model import Observation, QueueItem

OBSERVATION, DETECTED, RESOLVED = 0, 1, 2  # tie-break at equal time: conflict after the obs that caused it


@dataclass(slots=True)
class HistoryEvent:
    event: str  # observation_added | conflict_detected | conflict_resolved
    description: str
    created_at: datetime
    actor_id: str | None
    observation_id: str | None = None
    queue_id: str | None = None


def build_history(observations: list[Observation], queue: list[QueueItem]) -> list[HistoryEvent]:
    """Newest first."""
    keyed: list[tuple[tuple, HistoryEvent]] = []
    for i, o in enumerate(observations):
        desc = (f"{o.source}: {o.feature} = {o.value}"
                f"{' (tymczasowo)' if o.temporary else ''} · {o.validation} · 👍{o.up_votes} 👎{o.down_votes}")
        keyed.append(((o.created_at, OBSERVATION, i),
                      HistoryEvent("observation_added", desc, o.created_at, o.author_id, observation_id=o.id)))
    for i, q in enumerate(queue):
        keyed.append(((q.created_at, DETECTED, i), HistoryEvent(
            "conflict_detected", f"Konflikt danych: {q.feature} ({len(q.observation_ids)} obserwacji)",
            q.created_at, None, queue_id=q.id)))
        if q.resolved_at:
            keyed.append(((q.resolved_at, RESOLVED, i), HistoryEvent(
                "conflict_resolved", f"Rozstrzygnięto: {q.feature} → {q.decision}", q.resolved_at, None,
                queue_id=q.id)))
    return [e for _, e in sorted(keyed, key=lambda t: t[0], reverse=True)]
