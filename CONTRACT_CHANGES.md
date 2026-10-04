# CONTRACT_CHANGES

Changes to the API contract (PLAN.md section 14) that the frontend must follow. Newest first.

## v0.0 - initial contract
- All endpoints in PLAN.md section 14.4 exist and are served from fixtures
  (`data_version` = `fixture0`). Fixture law text is tagged `[fixture]`; coordinates are `0.0`
  until geocoding lands (Phase 3).
- `UpcomingChange.from` is serialized with the JSON key `from` (a Python keyword internally).
- Unknown routes and malformed bodies return the error envelope with `BAD_REQUEST` (400).
- `GET /geo/jurisdictions/{id}?state=XX` returns a FeatureCollection of the state and its cities.
