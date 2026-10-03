# F23 — Domain gaps from the full model

Overview: [../../README.md](../../README.md)

- **partial**: `ObservationValue/StateValue.PARTIAL`; report `current_state=partially_works`; OSM `wheelchair=limited` → partial; check: required feature partial → answer `partial`; Open API flat `"partial"`; map marker `partial`.
- **Trust ageing**: observations older than 180 days → confidence ×0.5 (`observation_confidence(obs, now)`).
- **Temporary issue end date**: `valid_until` on observations (future only, else 400); expired observations are ignored by trust and conflicts; states refresh lazily on read (`get_accessibility`, `check`, search).
- **Place type**: `Place.place_type` (`venue, shop, public_transport_stop, platform, parking, office, street_segment, other`; default `venue`); filter `GET /places?place_type=a,b`; seed: Urząd = `office`.
- Feature specs enums updated (partial, partially_works).
