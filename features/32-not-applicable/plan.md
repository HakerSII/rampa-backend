# F32 — Value "not applicable" + 4 attributes

Overview: [../../PLAN-GAPS.md](../../PLAN-GAPS.md) · specs updated (value + FeatureKey enums)

- `ObservationValue` / `StateValue` += `not_applicable` ("nie dotyczy", e.g. elevator in a single-storey café). It is a fact: not missing data, not a barrier, not a helper; `check` ignores it (no downgrade, no requirement); public API `value: "not_applicable"`.
- Features: `baby_changing_table` (toilet), `stroller_space` (inside), `rest_areas` (inside), `luggage_storage` (other) — 39 total.
- OSM: `changing_table` → `baby_changing_table`; `dog=yes|leashed|no` → `pets_allowed`. Rules interpreter (F30) knows the new words.
