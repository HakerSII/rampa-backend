# F25 — Full feature model (+ escalator for the front end)

Overview: [../../README.md](../../README.md)

- **35 features in 8 groups** (new group `parking`): the full-model list + `escalator` (front-end request); `partially_inaccessible_exhibition` left out (inverted meaning: yes = bad).
- Front-end keys: `escalator` → `escalator`; `tactile` → `tactile_paths`; `sign` → `sign_language_interpreter` (or `high_contrast_markings` if it means signage — to confirm with the front end).
- Text parsing: "schody ruchome" / "escalator" → `escalator`, never stairs.
- Feature specs enums updated; check rules unchanged (new features are informational unless a profile needs them).
