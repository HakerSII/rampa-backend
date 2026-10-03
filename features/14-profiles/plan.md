# F14 — More accessibility features + needs profiles

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: F2, F6

Answers the user questions from the brief: *"czy mogę wejść z psem"*, *"czy peron ma windę"*, *"czy krawężnik jest dostosowany"*, *"czy miejsce jest doświetlone"*, *"czy wejdę o kulach"*.

## Scope

- **+8 features** (names from the full contract enum):

  | Feature | Group |
  |---|---|
  | `braille`, `tactile_paths`, `good_lighting` | `vision` (new) |
  | `lowered_curb`, `platform_elevator`, `crutches_friendly` | `mobility` (new) |
  | `sign_language_interpreter` | `hearing` |
  | `assistance_dog_allowed` | `other` (new) |

- **+6 needs profiles**; `check` = generic rule table (`domain/check.py`):

  | Profile | Required (≥1 `yes`) | Downgrade to `partial` if `no` |
  |---|---|---|
  | `wheelchair`, `stroller` | step_free_entrance · ramp | elevator |
  | `crutches` | step_free_entrance · ramp · crutches_friendly | elevator |
  | `blind` | tactile_paths · braille | — |
  | `low_vision` | good_lighting | — |
  | `deaf` | induction_loop · sign_language_interpreter | — |
  | `assistance_dog` | assistance_dog_allowed | — |

  Answer: required `yes` → `yes` (→ `partial` if a downgrade feature is `no`) · required known, none `yes` → `no` · no data → `unknown`.
- Seed: MNK + braille, tactile paths, good lighting, assistance dog; Urząd + lowered curb, sign language, assistance dog, good lighting = no. Appended after the original seed.
- AI keyword mapping: braille, tactile, curb/kerb/krawężnik, dog/pies, dark/ciemno/oświetlenie.
- Feature specs F2/F3/F4/F7 enums updated.

## Tasks

| Id | What |
|---|---|
| F14.1 | 🔴 unit check per profile, enum/label completeness, use case + HTTP checks |
| F14.2 | enums, rules, seed, suggestions, specs, e2e, docs |
