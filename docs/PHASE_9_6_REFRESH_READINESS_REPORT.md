# Phase 9.6 — Real-data freshness and refresh readiness

The real runtime still selects `phase853_v3_20261122`. The preflight checked its pinned SQLite and manifest, evaluated actual upcoming fixtures with the existing policy and prepared a separate candidate from a newer public export. `production_approved=false`.

| Evidence | Observed result |
|---|---|
| V3 schedule acquisition and expiry | `2026-11-21T20:20:23.160077Z` through `2026-11-23T20:20:23.160077Z` inclusive |
| V3 at `2026-11-23T05:42:56Z` | 252 upcoming, 252 with recent schedule evidence, 1 READY, 6 EARLY_READY and 245 WAITING_DATA |
| V3 blocking reasons | 154 lacked verified registry coverage and 91 lacked rolling statistics; eligibility is independent of the aggregate schedule badge |
| V3 history coverage | 2,783 verified completions, 2,779 with complete statistics, four pending; 257 unverified fixtures and zero conflicts in the full registry |
| New source acquisition | `2026-11-23T05:39:18.010085Z`; response Last-Modified `2026-11-22T23:19:37Z`; CSV SHA-256 `9ba0715cf23c49d493550655fd82fe0039c9f26a512f40d3cdfb54abffe131e0` |
| Candidate `phase96-20261123-candidate` | `PREPARED`, `REVIEW_REQUIRED`, nine proposed changes, eight deterministic accepts and one manual review. No conflicts. |

The public current-season CSV had genuinely different bytes and newer match results. The candidate reconciles five additional completions with independent LaLiga results, resolves three prior pending statistical entries, and flags the Athletic Club–Espanyol statistics correction for review. Public calendar variants sometimes still showed Getafe–Atlético in progress, so the dedicated full-time match page was used for that result. [xGTables season export](https://www.xgtables.io/data/la-liga/2026/) · [xGTables provider provenance](https://www.xgtables.io/sources/) · [LaLiga matchday 13](https://www.laliga.com/laliga-easports/resultados/2026-27/jornada-13) · [LaLiga Getafe–Atlético match](https://www.laliga.com/es-DE/partido/temporada-2026-2027-laliga-ea-sports-getafe-cf-atletico-de-madrid-13)

Phase 8.5.4 kept the original evidence for rows whose schedule did not change. This candidate has zero schedule changes. Its newly retrieved CSV and the candidate build date therefore leave the unchanged upcoming fixtures on their original evidence window. The candidate is awaiting manual review and operator approval to publish. Actual statistics and schedule coverage remain those of V3.

## Pre-defense check on Windows

From the repository root, use the same `XPECTA_*` environment as the server. The preflight is local and read-only by default. It reports source and expiry groups, UTC evaluation time, actual eligible fixture keys, counts by blocking code, registry identity and outstanding history coverage.

```powershell
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.research_preflight
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/data-status'
```

An expired group is distinct from absent evidence and a not-yet-current source. If no fixture qualifies, use the historical pages and the actual blocked state. To inspect one eligible fixture, pass its canonical ID to `--fixture`. The report contains detailed local forecast evidence, including the feature vectors, so keep the output in ignored storage.

## Prepare and review a successor

1. Acquire the explicitly published CSVs into a new ignored directory. The existing downloader records checksums, response status, UTC acquisition and HTTP publication hints. Review the provider's update and the actual changed rows. Supply independent full-time evidence for new or corrected completions in the existing `independent_completed.json` format. Preserve old acquisitions and use the already verified identity mapping.
2. Supply the staged directory to `research_preflight`. The command checks the manifest and bytes and blocks preparation if the same schedule bytes are redownloaded or if the newer acquisition is outside the policy window. `--prepare` writes only a candidate and its report to a new private directory.
3. Use the existing Phase 8.5.4 review flow. Inspect the candidate privately. For each manual item, record an explicit decision, evidence reference and rationale against that exact change and candidate. `status` rechecks the candidate and reports outstanding receipts. If evidence conflicts or is insufficient, leave the candidate unapproved.
4. Once the operator authorizes publication, `refresh_composite publish` rechecks exact content and receipts, validates rolling feature order and frozen-inference parity in its provisional transaction, and publishes a separate immutable version only on success. Keep `phase853_v3_20261122` and its source inputs at their existing paths. [Phase 8.5.4 controlled refresh](PHASE_8_5_4_FINAL_MERGE_GATE.md)

For kickoffs independently reconfirmed against LaLiga, the staging directory can include `independent_schedule.json`. Set `reviewed_at` to the actual UTC review timestamp. Each entry in `matches` needs the season, UTC date, directed `home` and `away` team names, `status` of `scheduled`, `kickoff_utc`, and an official LaLiga round or match URL in `source_url`. Record only fixtures whose status and kickoff match the provider export. A reconfirmed unchanged kickoff has a `SCHEDULE_REVERIFIED` change tied to the evidence digest. A changed kickoff still requires manual review. The 48-hour window uses the actual review timestamp.

```powershell
$run = Get-Date -Format 'yyyyMMdd-HHmmss'
$source = "data/external/multisource/phase96/provider-$run"
$version = "phase96-$run"
$candidate = "data/external/multisource/phase96/candidates/$version"
.venv/Scripts/python.exe -X utf8 -m scripts.multisource.acquire --download --directory $source
# Add and verify independent_completed.json when required by the changed export.
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.research_preflight --source-dir $source --prepare $version
.venv/Scripts/python.exe -X utf8 -m scripts.multisource.refresh_composite status --candidate $candidate
# Once authorized, use the review CLI for each item, then publish the reviewed candidate.
.venv/Scripts/python.exe -X utf8 -m scripts.multisource.refresh_composite review --candidate $candidate --change-id $reviewedChangeId --decision $explicitDecision --reason $recordedRationale --evidence-reference $evidenceReference
.venv/Scripts/python.exe -X utf8 -m scripts.multisource.refresh_composite status --candidate $candidate
.venv/Scripts/python.exe -X utf8 -m scripts.multisource.refresh_composite publish --candidate $candidate
```

## Select an approved version

With the server stopped, use the published version ID and both independently recorded checksums. The real loader resolves a direct version under its research root and verifies both local files, the embedded manifest, candidate-bound approvals, completed inference validation and hash-linked parentage through pinned V3. Invalid scope, IDs, hashes and incomplete review fail startup verification. HTTP requests do not select snapshots or filesystem paths.

```powershell
$env:XPECTA_MODE = 'REAL_RESEARCH'
$env:XPECTA_SNAPSHOT = $approvedVersion
$env:XPECTA_SNAPSHOT_SHA256 = $approvedDatabaseSha256
$env:XPECTA_SNAPSHOT_MANIFEST_SHA256 = $approvedManifestSha256
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.research_preflight
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.app
```

Compute the manifest SHA-256 at the authorized publication checkpoint and record it alongside the published database SHA-256. On V3, use the built-in pins by clearing the two environment overrides. The tests exercised valid and invalid binding evidence with isolated fixtures.

## 24 November 2026 refresh

The local `phase96-20261124-verified` successor reconciled six new completed fixtures, filled statistics for three previously pending fixtures and applied one reviewed xG correction. Match history reached 23 November. LaLiga and the current export agreed on 30 kickoffs in rounds 14–16. The real runtime reported 10 `READY`, 20 `EARLY_READY` and 221 `WAITING_DATA` fixtures. Browser verification matched the six Overview forecasts to their read-only API previews. The 48-hour schedule evidence window expires at 10:20 UTC on 26 November. [LaLiga round 13 results](https://www.laliga.com/laliga-easports/resultados/2026-27/jornada-13) · [xGTables current-season export](https://www.xgtables.io/data/la-liga/2026/)

The published local snapshot and acquisition evidence reside in the ignored research and staging directories. For another machine, obtain its reviewed snapshot separately and configure its local version and both pins, or run the controlled refresh with newly verified inputs.
