# CONTRACT_CHANGES

Changes to the API contract (PLAN.md section 14) that the frontend must follow. Newest first.

## v0.6 - judges need no ingest token
- Extract, review, publish, reject, edit and rejudge are public whenever `PUBLIC_INGEST_ENABLED=true`.
- The documented demo header is `X-Admin-Token: tenantly-demo` if a host later locks the API.
- Failed primary-model and Groq-backup calls surface as `PROVIDER_UNAVAILABLE`; failed jobs never
  publish.

## v0.5 - public ingestion demo
- In hackathon demo mode, ingest mutations no longer require visitors to know `ADMIN_TOKEN`.
  The independent `INGEST_BUDGET_USD` model-spend cap is the only ingestion usage limit.
- `X-Admin-Token` remains a server-side override when public ingestion is disabled.

## v0.4 - persistent watched-address notifications
- `POST /v1/alerts/subscriptions` now returns the canonical `address_id`, creation state and whether
  server-side email delivery is configured, in addition to the private unsubscribe token and feeds.
- `GET /v1/alerts/subscriptions/{token}` returns watch and last-delivery status without exposing the
  recipient email. The token is the only client-side credential for this record.
- Publication dispatches notifications only from the real `ChangeEvent.affected` set. Delivery
  failures are audited and never roll back publication.

## v0.3 - unsubscribe response
- `DELETE /v1/alerts/subscriptions/{token}` returns `200 {"ok": true}` instead of `204`, because the
  frontend client requires a JSON body on every success.
- List endpoints keep their `{ "items": [...] }` wrapper (and the snapshot files do too); the frontend
  `api.ts` unwraps them. `GET /v1/audit` rows are mapped to the app's audit entry shape there.

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
