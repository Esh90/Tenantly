# CONTRACT_CHANGES

Changes to the API contract (PLAN.md section 14) that the frontend must follow. Newest first.

## v0.2 - nullable coordinates
- `lat` and `lon` are now `number | null` on `AddressSummary`, `AddressIndexItem` and
  `AffectedAddress`. One sample address (A0295, a parcel lot with no house number) cannot be
  geocoded; its state rules still apply and its local results are `unknown`
  (`missing_facts: ["location"]`). The frontend must hide the map pin when they are null.

## v0.0 - initial contract
- All endpoints in PLAN.md section 14.4 exist and are served from fixtures
  (`data_version` = `fixture0`). Fixture law text is tagged `[fixture]`; coordinates are `0.0`
  until geocoding lands (Phase 3).
- `UpcomingChange.from` is serialized with the JSON key `from` (a Python keyword internally).
- Unknown routes and malformed bodies return the error envelope with `BAD_REQUEST` (400).
- `GET /geo/jurisdictions/{id}?state=XX` returns a FeatureCollection of the state and its cities.
