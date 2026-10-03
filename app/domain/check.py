"""'Can I get in?' — pure rules per needs profile (MVP: wheelchair)."""
from app.domain.enums import CheckAnswer, FeatureKey, NeedsProfile, StateValue
from app.domain.model import CheckReason, CheckResult, FeatureStateRecord, Observation

ENTRANCE = (FeatureKey.STEP_FREE_ENTRANCE, FeatureKey.RAMP)

ADVICE = {
    CheckAnswer.YES: "Wejście bez barier potwierdzone.",
    CheckAnswer.PARTIAL: "Wejdziesz, ale winda nie działa — piętra mogą być niedostępne.",
    CheckAnswer.NO: "Brak wejścia bez schodów i podjazdu.",
    CheckAnswer.UNKNOWN: "Brak danych o wejściu — zadzwoń przed wizytą albo dodaj zgłoszenie.",
}


def check_place(place_id: str, states: dict[FeatureKey, FeatureStateRecord], profile: NeedsProfile,
                active_issues: list[Observation] | None = None) -> CheckResult:
    known = {f: s for f, s in states.items() if s.state != StateValue.UNKNOWN}
    entrance = [known[f] for f in ENTRANCE if f in known]
    elevator = known.get(FeatureKey.ELEVATOR)

    entrance_yes = [s for s in entrance if s.state == StateValue.YES]
    if entrance_yes:
        used = entrance_yes + ([elevator] if elevator else [])
        broken = elevator is not None and elevator.state == StateValue.NO
        answer = CheckAnswer.PARTIAL if broken else CheckAnswer.YES
    elif entrance:
        used, answer = entrance, CheckAnswer.NO
    else:
        used, answer = [], CheckAnswer.UNKNOWN

    reasons = [CheckReason(s.feature, s.state) for s in entrance + ([elevator] if elevator else [])]
    confidence = round(min(s.confidence for s in used), 2) if used else 0.0
    return CheckResult(place_id, profile, answer, confidence, reasons, active_issues or [], ADVICE[answer])
