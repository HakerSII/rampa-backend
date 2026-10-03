# F19 — AI parse-text (description → suggested observations)

Overview: [../../README.md](../../README.md) · contract: [openapi.yaml](openapi.yaml) · needs: F6/F14 keyword dictionary

- `POST /ai/parse-text {text}` (user) → `{ suggestions: [ {feature, label, value, temporary, confidence} ], model: "rules" }`.
- Pure rules, offline (`domain/text_parse.py`), PL + EN; suggestion only (fills the report form), never changes data.
- Clauses split on `. , ; ! ?` and "ale"/"but"/"lecz"; per clause: features (shared `FEATURE_KEYWORDS`) + polarity:
  - negative ("nie działa", "nieczynn", "zepsut", "brak", "zablokow", "zastawion", "awari", "remont", "not working", "broken", "out of order", "blocked", "no ") → `no`
  - positive ("działa", "naprawion", "jest", "dostępn", "odśnieżon", "works", "repaired", "available") → `yes`
  - step-free entrance: "bez schodów"/"step-free"/"level entrance" → yes; stairs mentioned → no
  - temporary: "od ", "tymczasow", "chwilow", "remont", "dziś", "dzisiaj", "zastawion", "temporar", "today"
  - clause without polarity → no suggestion; confidence 0.8 (explicit), 0.6 (stairs implied)
- Text 1..1000 chars (else 400); login required.
