# Phase 8.5.7 — XPECTA local research bridge

The feature branch starts at `ea555a05168f773399e154f12d1a2be2a593fca7`, the Phase 8.5.6 merge on `main`. XPECTA serves a thesis-defense research interface on `127.0.0.1:8765`. `production_approved=false`.

## Architecture

FastAPI lifespan verifies the protected-file manifests from Git, the frozen artifact and metadata, the fitted imputer, runtime package versions, the ordered 13-feature schema, and the selected immutable Composite History. Readiness returns 503 when those inputs are unavailable or the bound history has changed. A missing local HTML leaves the API usable and makes the frontend route return 503 with a preparation message.

Request fields carry canonical identities only. Server settings select a dataset mode, snapshot ID, forecast namespace, clock, allowed development origins, and operator write policy. The router uses Pydantic input and output models. The adapter invokes `ForecastService`, `ForecastEligibility`, the existing `generate_forecast()` entry point, and the immutable `ForecastLedger`. Preview uses the same generation path before ledger publication. Ledger checksums, compare-and-swap, lineage, atomic hard-link publication and locking remain in Phase 8.5.5.

Historical analytics read the registry and statistics through immutable SQLite. A reviewed completed match may retain its goals and result while xG is missing. Averages count observed values only. The interface shows the number observed, the verified denominator and the sources used. Shot averages preserve provider definitions. Historical windows exclude the simulated or real UTC calendar day in the applicable server mode. Same-season head-to-head and venue breakdowns use the same boundary.

| Mode | Trusted snapshot and clock | Forecast behavior |
|---|---|---|
| `REAL_RESEARCH` | Hash-pinned `phase853_v3_20261122`, current UTC | Existing verified schedule, expiry, coverage and last-five policies. Real ledger namespace. |
| `SYNTHETIC_DEMO` | Local named demo, server profile allowlist, specified simulated UTC clock | Isolated synthetic history and ledger. Visible **SYNTHETIC DEMO** label. |
| `HISTORICAL_REFERENCE` | Hash-pinned V3, current UTC | Read-only history and labelled retrospective metrics. Preview reports `UNAVAILABLE/HISTORICAL_ONLY`. |

## Setup and launch in PowerShell

From the repository root with the existing Python 3.14.0 virtual environment:

```powershell
.venv/Scripts/python.exe -X utf8 -m pip install -r scripts/xpecta_api/requirements-test.txt
.venv/Scripts/python.exe -X utf8 -m scripts.xpecta_api.prepare_frontend 'D:/Downloads/XPECTA_V9_12_Glass_Navigation (2).html'
.venv/Scripts/python.exe -m scripts.xpecta_api.demo --name defense
```

The preparer checks the source SHA-256 and writes the byte-identical reference, editable integrated HTML and checksum manifest in `data/external/multisource/phase857/frontend/`. Keep this ignored directory and the original attachment local. Montserrat ships with its OFL license so the page can load its font offline. [Google Fonts Montserrat source and license](https://github.com/google/fonts/tree/7085eb89a950e85db5b166b7a58d414544b4140c/ofl/montserrat)

```powershell
$env:XPECTA_MODE = 'SYNTHETIC_DEMO'
$env:XPECTA_DEMO_NAME = 'defense'
$env:XPECTA_SNAPSHOT = 'initial'
.venv/Scripts/python.exe -m scripts.xpecta_api.app
```

Open `http://127.0.0.1:8765/`. For real research or historical reference, set `XPECTA_MODE` to the corresponding value and `XPECTA_SNAPSHOT=phase853_v3_20261122`. Real V3 and its manifest must already exist in `data/history/research/phase853_v3_20261122/`. The server validates the snapshot hash and reports waiting when schedule verification is stale or unavailable. To allow a separate loopback development UI, set `XPECTA_DEV_ORIGINS` to a comma-separated list of full HTTP loopback origins.

## Offline A–F walkthrough

Keep each run on the same named synthetic demo and restart the app when changing its server-selected profile. Create a new demo name for a fresh isolated walkthrough. For operator publication, create a local-only token before starting the server. Set it in the terminal sessions that launch the server and send the operator request, without putting the value in browser code or source control.

```powershell
$phase857Target = 'research:laliga:2026:Valencia:Real Madrid'
$phase857Headers = @{ Authorization = "Bearer $env:XPECTA_OPERATOR_TOKEN" }
$phase857Body = @{ fixture_key = $phase857Target } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri http://127.0.0.1:8765/api/v1/forecasts/publish -Method Post -Headers $phase857Headers -ContentType 'application/json' -Body $phase857Body
```

| Scenario | Server profile and action | Expected result |
|---|---|---|
| A | `initial`, preview in the UI and publish with the local operator request | `EARLY_READY`, immutable `INITIAL` revision |
| B | `updated`, rerun operator publication for the same fixture | `EARLY_READY`, immutable `UPDATED` revision. History can compare V1 and V2. |
| C | `same-features`, rerun the same operator request | `NO_CHANGE`, reuses V2 |
| D | `incomplete`, preview the fixture in the Prediction page | `WAITING_DATA / MISSING_ROLLING_STATISTICS`, no xG values |
| E | Preview a completed fixture via Custom Matchup | `UNAVAILABLE / TARGET_NOT_UPCOMING` |
| F | Start `HISTORICAL_REFERENCE` for history. Run `python -m scripts.xpecta_api.demo --name defense --historical-parity` on the existing local Phase 8.5.3 private evidence for exact replay parity. | Observed historical statistics and separately labelled retrospective results. |

Browser tests use Edge with HTTP on loopback and block external requests. The CLI keeps screenshots and browser evidence in the ignored phase directory.

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_phase857_api -v
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase857 --run-id defense-review
```

Phase 9 handoff should keep the data modes, server-owned snapshot and operator policy in place. Browser demo previews and immutable revisions have separate UI states. Historical replay metrics keep separate label sources and the as-of-vintage limitation. Review redistribution rights before any expanded serving or publication of assets or historical rows. No public deployment is authorized by this bridge.
