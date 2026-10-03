"""Place-level trust summary ("Potwierdzone dzisiaj") and activity-feed classification. Pure."""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ObservationSource, ObservationValue, StateValue, ValidationStatus
from app.domain.model import FeatureStateRecord, Observation

RECENT_DAYS = 30
STALE_DAYS = 90


@dataclass(slots=True)
class Verification:
    status: str  # conflict | confirmed | verified_recently | verified | needs_update | unverified
    label: str
    last_verified: datetime | None
    confidence: float
    confidence_level: str  # high | medium | low
    sources: list[str]


def _days_label(days: int) -> str:
    return f"Zweryfikowane {days} {'dzień' if days == 1 else 'dni'} temu"


def summarize(states: Iterable[FeatureStateRecord], sources: set, now: datetime) -> Verification:
    states = list(states)
    known = [s for s in states if s.state != StateValue.UNKNOWN and s.last_verified]
    srcs = sorted(str(s) for s in sources)
    if not known:
        return Verification("unverified", "Brak danych", None, 0.0, "low", srcs)

    last = max(s.last_verified for s in known)
    confidence = round(sum(s.confidence for s in known) / len(known), 2)
    level = "high" if confidence >= 0.8 else "medium" if confidence >= 0.5 else "low"
    days = (now - last).days
    if any(s.validation == ValidationStatus.CONFLICT for s in states):
        status, label = "conflict", "Sprzeczne zgłoszenia"
    elif days <= 0:
        status, label = "confirmed", "Potwierdzone dzisiaj"
    elif days > STALE_DAYS:
        status, label = "needs_update", "Wymaga aktualizacji"
    else:
        status, label = ("verified_recently" if days <= RECENT_DAYS else "verified"), _days_label(days)
    return Verification(status, label, last, confidence, level, srcs)


ACTIVITY_LABELS = {
    "initial_data": "Dane startowe",
    "issue_reported": "Zgłoszono utrudnienie",
    "confirmation": "Potwierdzono dostępność",
    "owner_update": "Aktualizacja właściciela",
    "admin_decision": "Decyzja moderatora",
    "open_data_import": "Import OpenStreetMap",
}


def activity_type(obs: Observation, seed_author_id: str) -> str:
    if obs.author_id == seed_author_id:
        return "initial_data"
    if obs.source == ObservationSource.ADMIN:
        return "admin_decision"
    if obs.source == ObservationSource.VERIFIED_OWNER:
        return "owner_update"
    if obs.source == ObservationSource.OPEN_DATA:
        return "open_data_import"
    return "issue_reported" if obs.value == ObservationValue.NO else "confirmation"
