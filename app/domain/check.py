"""'Can I get in?' — generic rule table per needs profile. Pure.

Answer: a required feature is `yes` → yes (→ partial if a downgrade feature is `no`);
required features known but none `yes` → no; no data → unknown."""
from dataclasses import dataclass, field

from app.domain.enums import CheckAnswer, FeatureKey as F, NeedsProfile as P, StateValue
from app.domain.model import CheckReason, CheckResult, FeatureStateRecord, Observation

UNKNOWN_ADVICE = "Brak danych — zadzwoń przed wizytą albo dodaj zgłoszenie."
ELEVATOR_PARTIAL = "Wejdziesz, ale winda nie działa — piętra mogą być niedostępne."


@dataclass(frozen=True)
class Rule:
    required: tuple[F, ...]                # at least one must be `yes`
    downgrades: tuple[F, ...] = ()         # `no` here turns yes → partial
    advice: dict[CheckAnswer, str] = field(default_factory=dict)


_STEP_FREE = Rule((F.STEP_FREE_ENTRANCE, F.RAMP), (F.ELEVATOR,), {
    CheckAnswer.YES: "Wejście bez barier potwierdzone.",
    CheckAnswer.PARTIAL: ELEVATOR_PARTIAL,
    CheckAnswer.NO: "Brak wejścia bez schodów i podjazdu.",
    CheckAnswer.UNKNOWN: "Brak danych o wejściu — zadzwoń przed wizytą albo dodaj zgłoszenie.",
})

PROFILE_RULES: dict[P, Rule] = {
    P.WHEELCHAIR: _STEP_FREE,
    P.STROLLER: _STEP_FREE,
    P.CRUTCHES: Rule((F.STEP_FREE_ENTRANCE, F.RAMP, F.CRUTCHES_FRIENDLY), (F.ELEVATOR,), {
        CheckAnswer.YES: "Wejście dostępne o kulach.",
        CheckAnswer.PARTIAL: ELEVATOR_PARTIAL,
        CheckAnswer.NO: "Schody bez podjazdu i bez udogodnień dla osób o kulach.",
    }),
    P.BLIND: Rule((F.TACTILE_PATHS, F.BRAILLE), (), {
        CheckAnswer.YES: "Są ścieżki prowadzące lub oznaczenia w alfabecie Braille'a.",
        CheckAnswer.NO: "Brak ścieżek prowadzących i oznaczeń Braille'a.",
    }),
    P.LOW_VISION: Rule((F.GOOD_LIGHTING,), (), {
        CheckAnswer.YES: "Miejsce jest dobrze oświetlone.",
        CheckAnswer.NO: "Słabe oświetlenie — zapytaj obsługę o pomoc.",
    }),
    P.DEAF: Rule((F.INDUCTION_LOOP, F.SIGN_LANGUAGE_INTERPRETER), (), {
        CheckAnswer.YES: "Jest pętla indukcyjna lub tłumacz PJM.",
        CheckAnswer.NO: "Brak pętli indukcyjnej i tłumacza PJM.",
    }),
    P.ASSISTANCE_DOG: Rule((F.ASSISTANCE_DOG_ALLOWED,), (), {
        CheckAnswer.YES: "Pies asystujący może wejść.",
        CheckAnswer.NO: "Pies asystujący nie jest wpuszczany — sprawdź przed wizytą.",
    }),
}


def check_place(place_id: str, states: dict[F, FeatureStateRecord], profile: P,
                active_issues: list[Observation] | None = None) -> CheckResult:
    rule = PROFILE_RULES[profile]
    known = {f: s for f, s in states.items() if s.state not in (StateValue.UNKNOWN, StateValue.NOT_APPLICABLE)}
    required = [known[f] for f in rule.required if f in known]
    downgrades = [known[f] for f in rule.downgrades if f in known]

    required_yes = [s for s in required if s.state == StateValue.YES]
    if required_yes:
        used = required_yes + downgrades
        broken = any(s.state == StateValue.NO for s in downgrades)
        answer = CheckAnswer.PARTIAL if broken else CheckAnswer.YES
    elif any(s.state == StateValue.PARTIAL for s in required):
        used, answer = [s for s in required if s.state == StateValue.PARTIAL], CheckAnswer.PARTIAL
    elif required:
        used, answer = required, CheckAnswer.NO
    else:
        used, answer = [], CheckAnswer.UNKNOWN

    reasons = [CheckReason(s.feature, s.state) for s in required + downgrades]
    confidence = round(min(s.confidence for s in used), 2) if used else 0.0
    advice = rule.advice.get(answer, UNKNOWN_ADVICE)
    relevant = set(rule.required) | set(rule.downgrades)
    issues = [o for o in (active_issues or []) if o.feature in relevant]
    return CheckResult(place_id, profile, answer, confidence, reasons, issues, advice)
