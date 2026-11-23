# Phase 9.9 — Pre-merge revalidation

**PASS for the read-only thesis demonstration on the observed V3 snapshot.** A real successor and real ledger publication remain operator decisions. The gate applies to research use with `production_approved=false`.

This run was performed on 23 November 2026, Asia/Saigon. The existing `phase9-real-data-first-ui-finalization` branch and its fetched upstream matched `68de9c57ac763f65bebc23af0e98d89209eadb73` before changes. The tested remediation implementation is `814e4269844380c1caa1998f12071ca1093a9c8b`. The documentation checkpoint's exact revision is available with `git log -1 --format=%H -- docs/PHASE_9_9_FINAL_REVALIDATION.md`.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| AC-9.6-01 source timestamps and expiry | PASS | Real preflight and live HTTP exposed the UTC acquisition and 48-hour expiry, grouped evidence and actual eligibility. Offline tests exercised valid, expired and missing evidence. |
| AC-9.6-02 reproducible controlled preparation | PASS | Downloaded newer public bytes and created a separate candidate with nine proposed changes. Status rechecked the candidate and returned REVIEW_REQUIRED for one statistics correction. |
| AC-9.6-03 safe binding of approved immutable successors | PASS | Tested explicit ID and both pins, candidate-bound approval, attested parent hashes and V3 lineage with isolated binding fixtures. The live V3 was also verified with both built-in pins. |
| AC-9.7-01 search, filters, sorting, pagination | PASS | Real filters and pages on three viewports. Internal edge cases cover 0, 1, 4, 12 and 20 fixtures, tied and missing kickoffs, and accent matching. |
| AC-9.7-02 responsive V9.12 presentation | PASS | 18 equivalent real/reference page pairs at three sizes. The new filter panel fits across the layouts, with existing card geometry and glass navigation. No horizontal overflow. |
| AC-9.7-03 fixture and xG integrity | PASS | Fixture selection used the canonical key from actual HTTP data, a positive preview matched direct inference and blocked states had null predictions. Listing xG is restricted to matching published context. |
| AC-9.8-01 authorized publication tests | PASS | Isolated token-enabled publication, hash-mismatch rejection before append and real HTTP 403 with operator publication disabled. Real ledger count stayed at zero. |
| AC-9.8-02 empty and populated history | PASS | Real empty History and isolated V1/V2, comparison, metadata, filtered CSV and keyboard interaction. |
| AC-9.8-03 lineage, NO_CHANGE, security | PASS | Tested separate and concurrent writes, invalid lineage, stale or incomplete eligibility, same-input retry and candidate hash mismatch. |
| AC-9.9-01 all six pages on real Edge | PASS | Overview, Prediction, Match Analysis, Team Statistics, History and AI Model at 1440 × 900, 820 × 1180 and 390 × 844. No page/console errors or browser publish requests. |
| AC-9.9-02 full Python regression | PASS | 367 passed, zero failures, errors or skips, exit 0. |
| AC-9.9-03 protected inputs | PASS | Baseline and final checks verified 77 inference entries, 107 provider-PoC entries, 13 required inputs, 8 research snapshot files, the original and prepared V9.12 and all 13 ordered features. |
| AC-9.9-04 limitations | PASS | Real schedule lifetime, coverage gaps, candidate review and real ledger limits are documented. |

| External checkpoint | Result | Reason |
|---|---|---|
| Publish and bind the newly prepared real candidate | BLOCKED | Manual review of the Athletic Club–Espanyol statistics correction and explicit operator approval remain outstanding. |
| Extend the window for previously scheduled upcoming fixtures via this candidate | BLOCKED | Nine changes relate to results and statistics. Unchanged upcoming rows retain their original schedule evidence. |
| Observe a real published V1 or V2 | BLOCKED | The real ledger is empty and publication was disabled. The real V2 outcome is `REAL_V2_NOT_OBSERVED`. |

## Execution evidence

| Test | Observed result |
|---|---|
| Targeted Python | 37/37 in 11.329 s, exit 0 |
| Full Python discovery | 367/367 in 185.555 s, exit 0 |
| Real Edge 158.0.4370.33 | 18 pairs and 48 automated screenshots, exit 0. Real READY, WAITING_DATA and UNAVAILABLE in all three sizes. |
| Isolated internal Edge | 18 pairs, 43 screenshots, exit 0. Loading and bad API responses, V1/V2 history, isolation, filter edge cases and live exclusion. |
| Actual Windows real HTTP | Health, bootstrap, teams, fixtures, data status, eligibility, preview, historical team stats, match analysis, model summary and ledger reader returned HTTP 200. The read-only server refused a write with 403. |

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_phase96_research tests.test_phase857_api tests.test_forecast_integration tests.test_forecast_ledger -v
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase9 --run-id phase96-real-final
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase857 --run-id phase96-internal
```

For another browser run, use fresh IDs. Real images and evidence are in ignored `data/external/multisource/phase9/visual/phase96-real-final/`, synthetic evidence is in `data/external/multisource/phase857/visual/phase96-internal/`, and API, preflight and candidate evidence is in `data/external/multisource/phase96/`. Browser comparisons used equivalent browser, viewport, font and UTC settings. Manual screenshot review checked the discovery controls and card proportions across all three sizes.

The real test read 31 teams overall and 380 current-season fixtures. Levante–Elche returned 1.3786658838 and 1.2549573988 xG, with snapshot SHA-256, feature SHA-256 and both values identical to direct frozen inference. Levante–Racing Santander returned WAITING_DATA because registry coverage was unverified. Alavés–Getafe returned UNAVAILABLE because it was not upcoming. Valencia's 2026 statistics came from Sportmonks, and the Valencia–Real Madrid 2025 Last 10 samples came from Understat. The original research files and Windows permissions were retained. No real ledger directory was created.

| Protected artifact | Verified SHA-256 |
|---|---|
| Frozen LR | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| Model metadata | `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c` |
| V3 SQLite | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| V3 manifest | `22f32a8bd31a7b27f2183ec4b594b79a36f9421bc0727a01d297123155735e12` |
| Original V9.12 HTML | `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4` |

## Windows thesis-defense runbook

1. From the repository root, confirm that the tested implementation commit is an ancestor of your local revision. The tested environment was Windows with Python 3.14.0, FastAPI 0.121.3, Uvicorn 0.38.0, scikit-learn 1.9.1, NumPy 2.5.4 and pandas 3.1.0. For browser verification, use Playwright 1.58.0 with Edge. Keep the existing prepared HTML, frozen artifacts and read access to the pinned snapshot. Instructions for preparing the pinned frontend remain in the [original implementation report](PHASE_9_IMPLEMENTATION_REPORT.md#reproduce-the-real-website-on-windows).
2. Use a foreground PowerShell terminal from the repository root. Check port 8765 before starting. When finished, use Ctrl+C in the terminal that owns this foreground instance. If an existing listener is already the verified read-only service, use it while it is ready.

```powershell
git log -2 --oneline
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
$env:XPECTA_MODE = 'REAL_RESEARCH'
$env:XPECTA_SNAPSHOT = 'phase853_v3_20261122'
$env:XPECTA_SNAPSHOT_SHA256 = ''
$env:XPECTA_SNAPSHOT_MANIFEST_SHA256 = ''
$env:XPECTA_OPERATOR_TOKEN = ''
$env:XPECTA_DEV_ORIGINS = ''
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.research_preflight
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.app
```

3. In a second terminal, check readiness, mode, snapshot and freshness. Open `http://127.0.0.1:8765/`. Select a current real READY or EARLY_READY fixture printed by preflight, find it using team or UTC date, and verify Preview still shows both xG values. Explain that this is a pre-match estimate and the exact cutoff and model are visible in the result.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/health/ready'
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/data-status'
```

4. Demonstrate Match Analysis and Team Statistics with a dated season/window, then explain the model summary and history screen. A waiting fixture displays the reason and two empty xG panels. An empty History means there are no published forecasts. If no prospective fixture is currently eligible, retain the real research site and demonstrate observations and blocked-state behavior. Keep synthetic cases for internal verification.
5. For optional real publication, obtain explicit approval for the selected fixture. Start the authorized service from a private terminal using the operator workflow, then stop that session and resume the read-only launch. For a newer snapshot, publish only after controlled review and use both recorded pins. [Publication workflow](PHASE_9_8_REAL_HISTORY_REPORT.md) · [Refresh runbook](PHASE_9_6_REFRESH_READINESS_REPORT.md)

```powershell
# Authorized operator server only. Run after stopping your own read-only instance.
$env:XPECTA_OPERATOR_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Temporary operator token' -AsSecureString)).Password
try {
  .venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.app
} finally {
  Remove-Item Env:XPECTA_OPERATOR_TOKEN
}
```

The implementation checkpoint contains the publication binding, preflight, web fixture discovery and their regression tests. The separate documentation checkpoint contains this gate, the three workstream reports and the two Phase 9 baseline-document updates. Use `git show --name-status 814e426` for the exact implementation files.
