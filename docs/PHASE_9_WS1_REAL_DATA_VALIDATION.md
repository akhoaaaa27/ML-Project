# Phase 9 WS1 — real fixture and forecast validation

**PASS for the observed snapshot and time.** The real HTTP scan at `2026-11-23T05:06:57Z` used V3 `phase853_v3_20261122` and frozen Linear Regression `1.0.0`.

| Catalogue measure | Count |
|---|---:|
| Registry entries across season IDs 2019–2026 | 3,040 |
| Teams across those seasons | 31 |
| Verified completed | 2,783 |
| Complete / pending statistics among verified completed | 2,779 / 4 |
| Unverified / conflicts | 257 / 0 |
| Season 2026 fixtures / completed / provider-scheduled | 380 / 123 / 257 |
| Upcoming at the check / missing assigned kickoff in that group | 252 / 0 |
| Upcoming `READY` / `EARLY_READY` / `WAITING_DATA` | 1 / 6 / 245 |
| `UNAVAILABLE` across the full season | 128 |

The schedule evidence was the xGTables Sportmonks fixture archive for 2026 acquired `2026-11-21T20:20:23Z`. The latest registry verification was `2026-11-21T21:33:38Z` and V3 was built at `2026-11-21T21:34:08Z`. The latest verified completed date was November 21. All 252 upcoming rows were within the source-review window at the check. The 48-hour freshness boundary for this schedule evidence was about `2026-11-23T20:20Z`. Future entries in the provider catalogue can still move. The independent public cross-check covered the eligible Levante UD–Elche CF fixture at `2026-11-23T20:00:00Z`. [Official LaLiga match](https://www.laliga.com/partido/temporada-2026-2027-laliga-ea-sports-levante-ud-elche-cf-13) · [Official Levante fixture list](https://www.laliga.com/en-GB/clubs/levante-ud/next-matches)

Of the 245 waiting fixtures, 154 lacked verified registry coverage and 91 lacked the rolling statistical history required by the existing rules. A populated kickoff alone cannot establish forecast eligibility. The API resolves stale or past fixtures at request time.

| Read-only preview probe | Evidence |
|---|---|
| `READY` | Levante–Elche had two finite xG outputs. Repeat HTTP previews and direct frozen-pipeline inference matched. The ordered 13-feature input and historical cutoff were verified. |
| `EARLY_READY` | One genuinely upcoming provider-backed sample gave two finite xG outputs and direct/repeat parity under the same cutoff checks. This was a representative eligibility test of pinned evidence. |
| `WAITING_DATA` | Representative `REGISTRY_COVERAGE_UNVERIFIED` returned null predictions. |
| `UNAVAILABLE` | Representative `TARGET_NOT_UPCOMING` returned null predictions. |

The two eligible requests used history strictly before the applicable cutoff and the configured frozen artifact. The real forecast ledger contained zero records before and after the scan. No retrospective forecast was substituted for an eligible upcoming one.

## Controlled refresh decision

V3 was sufficient for the observed run. A fresh, reviewed successor would be needed to restore schedule eligibility after the evidence expires. Phase 8.5.4 already supplies Prepare → Review → Validate → Publish, evidence and input hashes, manual adjudication of ambiguous identity or statistical changes, frozen-model compatibility and immutable versioning. Pairing a permitted newer schedule export with provenance and any required independent confirmation is a prerequisite to that workflow. The one public cross-check is evidence for one fixture only. This phase retained V3 and did not publish a successor or edit fixture timestamps. [Phase 8.5.4 closure and controlled refresh checks](PHASE_8_5_4_FINAL_MERGE_GATE.md)
