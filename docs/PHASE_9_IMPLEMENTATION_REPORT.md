# Phase 9 implementation report

This report records the original Phase 9 implementation. For the current Windows procedure and pre-merge state, use the [Phase 9.9 thesis-defense runbook](PHASE_9_9_FINAL_REVALIDATION.md#windows-thesis-defense-runbook). The remediation reports cover [data freshness](PHASE_9_6_REFRESH_READINESS_REPORT.md), [fixture discovery](PHASE_9_7_FIXTURE_DISCOVERY_REPORT.md), and [forecast publication and history](PHASE_9_8_REAL_HISTORY_REPORT.md).

The website serves six research pages at `http://127.0.0.1:8765/`. It uses the real Composite History V3 and frozen Linear Regression `1.0.0`. The originally protected histories, model, fitted imputer, Phase 7 evidence and eligibility service stay on their existing paths and versions.

| Workstream | Scope and implementation |
|---|---|
| WS0 | Restored the real local service through exact-account NTFS read grants. [Real runtime report](PHASE_9_WS0_REAL_RUNTIME_REPORT.md) |
| WS1 | Scanned the pinned catalogue, verified one eligible fixture against public LaLiga evidence and checked real HTTP preview parity with direct inference. [Real data validation](PHASE_9_WS1_REAL_DATA_VALIDATION.md) |
| WS2 | `web/xpecta/app.js`, `view.js` and `phase9.css` align fixture grids, use compact UTC kickoff, show published-only xG on fixture cards and provide shared forecast panels. Matching context on return from Match Analysis triggers a fresh read-only preview. |
| WS3 | The same view files restore observed Match Insights, H2H xG and the analysis CTA, clear comparison crests and venue breakdowns, and a real ledger empty state. The API exposes the existing Phase 7 partitions and Phase 8.5.6 retrospective periods. History retains revision comparison and filtered CSV. |
| WS4 | `tests/test_phase857_api.py`, `tests/browser_phase857.py` and `tests/browser_phase9.py` cover the API and the real and internal browser workflows. [Visual regression](PHASE_9_VISUAL_REGRESSION.md) · [Final gate](PHASE_9_FINAL_INTEGRATION_GATE.md) |

Model summary entries now include the additive `period` field. Phase 7 entries express the exact saved date ranges. Phase 8.5.6 entries carry their season. The 2025/26 retrospective label also gives its training boundary because the replay excluded fixtures on or before that date. The scores, providers, sample counts and feature order come from the existing validation artifacts.

## Reproduce the real website on Windows

Use PowerShell from the repo root with the existing `.venv`, accessible pinned snapshot and locally prepared reference. If the prepared frontend is absent, prepare it from your copy of the approved hash-pinned original.

```powershell
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.prepare_frontend 'D:/Downloads/XPECTA_V9_12_Glass_Navigation (2).html'
```

Check an existing listener before starting a service on 8765. Run the real app in the foreground so `Ctrl+C` stops the process launched in this terminal.

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
$env:XPECTA_MODE = 'REAL_RESEARCH'
$env:XPECTA_SNAPSHOT = 'phase853_v3_20261122'
$env:XPECTA_OPERATOR_TOKEN = ''
$env:XPECTA_DEV_ORIGINS = ''
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.app
```

From a second PowerShell terminal, confirm the mode, snapshot and readiness before opening the site. Check data status for the schedule evidence freshness at demonstration time.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/health/ready'
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/data-status'
Start-Process 'http://127.0.0.1:8765/'
```

## Run verification

The real Edge check reads the running site and uses a new local run ID for evidence. The separate internal Edge check provisions its test data and ephemeral service itself, with published revisions built inside its temporary namespace. It can run while the real site is serving.

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_phase857_api -v
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
$phase9Run = Get-Date -Format 'yyyyMMdd-HHmmss'
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase9 --run-id "real-$phase9Run"
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase857 --run-id "internal-$phase9Run"
```

The service can be ready even after the fixture schedule review ages out. At that point use the observed historical pages and the actual eligibility status in Prediction until a controlled refresh provides reviewed evidence.
