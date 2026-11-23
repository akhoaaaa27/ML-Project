# XPECTA Windows thesis defense runbook

Use the existing Phase 9 branch and the implementation revision recorded in the [final release gate](PHASE_9_FRG_05_FINAL_RELEASE_GATE.md). Keep the Windows project `.venv`, trusted frozen model, prepared V9.12 reference, and read permission on the V3 SQLite and manifest. The verified environment was Python 3.14.0, FastAPI 0.121.3, Uvicorn 0.38.0, scikit-learn 1.9.1, NumPy 2.5.4 and pandas 3.1.0. Edge with Playwright 1.58.0 was used for browser regression.

## Launch real research

Run in PowerShell from the repository root. If the prepared frontend is missing, the existing hash-checking builder accepts your local original HTML. If port 8765 is occupied, identify the listener and use the existing service if its readiness and binding match. For a foreground instance you started, stop it with Ctrl+C in its own terminal.

```powershell
git status --short --branch
git rev-parse HEAD
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
# Only if the prepared frontend is missing:
# .venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.prepare_frontend 'D:/Downloads/XPECTA_V9_12_Glass_Navigation (2).html'
$env:XPECTA_MODE = 'REAL_RESEARCH'
$env:XPECTA_SNAPSHOT = 'phase853_v3_20261122'
$env:XPECTA_SNAPSHOT_SHA256 = ''
$env:XPECTA_SNAPSHOT_MANIFEST_SHA256 = ''
$env:XPECTA_OPERATOR_TOKEN = ''
$env:XPECTA_DEV_ORIGINS = ''
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.research_preflight
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.app
```

From a separate terminal confirm the actual run. The readiness API confirms loaded data and model. The data status gives schedule source time and expiry. Check the UTC clock again immediately before selecting a fixture.

```powershell
$api = 'http://127.0.0.1:8765/api/v1'
[DateTime]::UtcNow.ToString('o')
Invoke-RestMethod "$api/health/ready"
Invoke-RestMethod "$api/bootstrap"
Invoke-RestMethod "$api/data-status" | ConvertTo-Json -Depth 6
Start-Process 'http://127.0.0.1:8765/'
```

Use the preflight list to find a genuine `READY` or `EARLY_READY` fixture and independently compare the exact kickoff to the official LaLiga match page. A provider time of midnight with no league-confirmed time is insufficient for the defense. A fixture must be eligible at the actual demo time, with kickoff still ahead and evidence inside the policy window.

## Demonstration sequence

1. **Overview** shows the real research mode, provider-based catalogue and freshness. Explain when the snapshot was last verified.
2. **Prediction** lets you choose a verified fixture via team or UTC date. The FRG observed Levante–Elche at 1.38–1.25 xG for the 23 November 2026 20:00 UTC kickoff. Select that fixture only while it remains genuinely upcoming and passes current eligibility. Show the actual values, cutoff, model and snapshot. The predicted quantity is total team xG.
3. **Match Analysis** and **Team Statistics** show observed form, an actual season/Last 10 and provider provenance. **AI Model** shows the 13 features and original holdout/retrospective evidence. **Prediction History** reads the immutable publication ledger. An empty history is expected when nothing has been published.
4. If a prospective fixture is blocked, show the real reason and null panels, then continue with historical statistics and model evidence. Keep the real mode active. After confirmed kickoff, treat earlier preview evidence as a record of the verification run. After V3 expiry, obtaining a new source and controlled snapshot becomes a separate task.

## Operator decisions

- **Candidate review.** Locate the existing `phase96-20261123-candidate`. Run `refresh_composite status --candidate` with its existing workspace path. For change `775e7c6e43a38401f4764f27e1d4680739553d6971ccbde66d8313a8d500d1ec`, obtain dated, fixture-specific same-model confirmation, record its hash and reference, and decide explicitly. The current dossier recommends holding the candidate. Formal review, validation at publication and explicit dual-pinned binding are covered in the [candidate dossier](PHASE_9_FRG_01_CANDIDATE_REVIEW.md) and [controlled refresh runbook](PHASE_9_6_REFRESH_READINESS_REPORT.md#prepare-and-review-a-successor).
- **Optional authorized V1.** Re-run live eligibility, re-preview the exact canonical fixture, confirm the trial outputs, trusted snapshot hash, feature hash, kickoff and expiry, and record explicit authorization for that fixture. If authorized, start a separate token-enabled localhost session from PowerShell using the non-echoed prompt, submit the two expected hashes with the fixture key, then verify the returned immutable ID, record hash and V1 in History. Return to the read-only process after the authorized session. The [publication runbook](PHASE_9_8_REAL_HISTORY_REPORT.md#authorized-local-publication) contains the exact PowerShell request.

The read-only startup, health/data status, catalogue selection, feature parity, historical analysis, unavailable states and zero-record ledger were verified in FRG. Optional formal candidate review and real V1 publication remain operator actions.
