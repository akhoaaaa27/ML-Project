# Phase 8.5.7 — Local FastAPI contract

Base path `/api/v1`. `/openapi.json` exposes the full Pydantic schema for requests and filtered responses. Dates are ISO calendar dates. Timestamps are UTC. Canonical fixture keys preserve home and away orientation, e.g. `research:laliga:2026:Valencia:Real Madrid`. Percent-encode query values. Team IDs match the canonical catalogue. Forecast IDs are lowercase 32-character opaque identifiers.

| Method and route | Input | Success payload |
|---|---|---|
| GET `/health/live` | None | `ALIVE`, API version |
| GET `/health/ready` | None | Readiness status, snapshot/model versions, frontend availability |
| GET `/bootstrap` | None | API and model versions, mode, display label, snapshot, available seasons and write policy |
| GET `/teams` | Optional `season`, `offset`, `limit` | Catalogue page with IDs, names and season memberships |
| GET `/fixtures` | Optional `season`, `home`, `away`, `status`, `upcoming`, `offset`, `limit` | Fixture page with canonical teams, scheduled kickoff when known, observed/verified/statistics states and snapshot provenance |
| GET `/eligibility` | `fixture_key` | Eligibility status, reason, target if found, cutoff, review time and intermediate fixture keys where present |
| GET `/data-status` | None | Registry counts, snapshot hash/build time, latest verified completion, schedule freshness and date-cutoff policy |
| POST `/forecasts/preview` | JSON `{"fixture_key":"..."}` | `ForecastAction` with a read-only candidate or an eligibility reason |
| POST `/forecasts/publish` | Same JSON and operator bearer authorization | `ForecastAction` with immutable revision, re-used revision or a blocked business status |
| GET `/forecasts` | Optional `fixture_key`, `offset`, `limit` | Validated ledger page newest first in the current namespace |
| GET `/forecasts/compare` | `fixture_key`, `v1`, `v2`, in lineage order | Both revisions, Home/Away xG deltas, changed/unchanged feature names and inputs, and optional schedule notice |
| GET `/forecasts/{forecast_id}` | Opaque ID | Single validated published revision |
| GET `/historical/team-stats` | `team`, `season` | Verified result totals, observed and missing xG counts and means, shot counts with source attribution, venue splits and a date trend |
| GET `/historical/match-analysis` | `home`, `away`, `season`, `window=5\|10` | Selected form windows, coverage, source counts, head-to-head and exclusive cutoff |
| GET `/model/summary` | None | Frozen LR training metadata, all 13 ordered features, Phase 7 and Phase 8.5.6 cohort aggregates, evaluation limits |

Pagination returns `items`, `total`, `offset` and `limit`. Defaults are 0 and 25. Limit is 1–100 and offset 0–10,000. Query and JSON schemas reject extra parameters. Clients use the configured mode and version. Read responses expose a projection of the ledger. Private history windows, raw model output, provider fixture IDs, raw source files and database paths remain local.

## Forecast and history states

The fixture catalogue, status filter, and eligibility target share the observed status enum `scheduled`, `completed`, `live`, `postponed`, `cancelled`, and `unverified`. Use `GET /api/v1/fixtures?status=live` to list live fixtures. An `upcoming=true` request only lists qualifying scheduled fixtures. In a forecasting mode, eligibility and forecast actions for a live target return HTTP 200 with `UNAVAILABLE / TARGET_NOT_UPCOMING`, even if the recorded kickoff falls after the current forecast clock. Forecast fields in these action responses are null.

Successful preview returns `READY` or `EARLY_READY`, with Home/Away xG, model and snapshot identity, cutoff, dataset kind and source notice. `WAITING_DATA`, `UNAVAILABLE` and `FORECAST_ERROR` have nullable forecast fields and eligibility or an error code. Publication uses `PUBLISHED` with `INITIAL` or `UPDATED`, or `NO_CHANGE` with the prior record. The comparison preserves the ledger's same-fixture and ordered-lineage rules.

History returns `COMPLETE`, `INSUFFICIENT_HISTORY`, `INCOMPLETE_STATISTICS` or `ZERO_HISTORY`. Forms select the actual last N verified completed matches in the selected season. A missing xG remains null inside the requested window. Current schedule freshness summarizes review evidence within the existing 48-hour bound. Fixture-specific eligibility also checks kickoff, intermediate matches and history evidence.

## Local transport and trust

Read-only is the default. Publication requires `Authorization: Bearer …` configured on the local server. The UI never requests a token. Browser writes require the same origin or an explicit loopback development origin and bearer authorization. Cross-site requests without a valid Origin are rejected when marked cross-site. CORS credentials are off. The Host header is restricted to localhost or 127.0.0.1. The bundled runner binds to 127.0.0.1 and ignores proxy headers.

The server explicitly serves the prepared document, three JavaScript modules and the OFL font. CSP limits scripts and fetches to the same origin, allows local embedded images, and denies framing. JSON bodies and query strings are bounded at 2 KiB. Validation and mapped domain errors use `{"error":{"code":"…","message":"…"}}`, with sanitized messages. Readiness 503 uses the readiness schema. The framework handles optional CORS preflight.

| HTTP code | Meaning |
|---|---|
| 200 | Valid request with business status, including a waiting or unavailable forecast |
| 400 / 413 / 415 | Untrusted Host, oversized request, or unsupported body content type |
| 401 / 403 | Missing or invalid bearer authorization, disabled publication, or disallowed write origin |
| 404 / 422 | Unknown route or resource, invalid schema or incompatible forecast revisions |
| 409 | Writer lock, stale ledger revision or incompatible snapshot lineage |
| 503 | Trusted inputs or local storage unavailable |
| 500 | Sanitized unexpected application error |
