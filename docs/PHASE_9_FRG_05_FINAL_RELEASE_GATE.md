# Phase 9 final release gate

**CODE_MERGE_READINESS · PASS.** The Phase 9 diff is a descendant of the fetched `origin/main`, and the Python, browser and integrity gates passed. This is a pre-merge decision. `production_approved=false`.

**REAL_DATA_DEFENSE_READINESS · PASS at the verification time only.** The actual Windows service returned **1.38–1.25 xG** for Levante–Elche on 23 November 2026 before the confirmed 20:00 UTC kickoff. It reproduced the same result after restarting real localhost. Only this fixture had both a READY verdict and a confirmed exact kickoff in the reviewed eligible set. Once it kicks off, it is no longer a prospective demonstration. The remaining six provider times were unconfirmed by LaLiga. [Real forecast evidence](PHASE_9_FRG_03_REAL_FORECAST_EVIDENCE.md) · [Schedule and expiry](PHASE_9_FRG_02_SCHEDULE_EVIDENCE.md)

The run used the existing `phase9-real-data-first-ui-finalization` branch. Local HEAD and fetched upstream matched `edc258cf53f322275681b7b7bbac40a5588c0df3` before changes. The tested UI/browsers implementation is `c9692b1993c417c63117936c090fe36346dc3244`. The ancestry check placed `origin/main` at `37f0e1e7d57b3f90197479cf1ce6db3b70b66ab8` as a direct ancestor. The report checkpoint's exact hash is available with `git log -1 --format=%H -- docs/PHASE_9_FRG_05_FINAL_RELEASE_GATE.md`.

## Acceptance criteria

| Criterion | State | Evidence |
|---|---|---|
| FRG-01 independent candidate review and recommendation | PASS | Recomputed exact candidate content, effect and inputs. The dossier recommends holding the Athletic Club–Espanyol change pending same-model corroboration. [Candidate review](PHASE_9_FRG_01_CANDIDATE_REVIEW.md) |
| FRG-02 official scheduling and expiry | PASS | Independently matched the two reviewed near-term kickoffs and verified the V3 expiry. Six later provider times lack league-confirmed hours. [Schedule evidence](PHASE_9_FRG_02_SCHEDULE_EVIDENCE.md) |
| FRG-03 actual prospective real forecast | PASS | Levante–Elche was genuinely upcoming, eligible, repeatable and matched direct frozen-model inference. [Forecast evidence](PHASE_9_FRG_03_REAL_FORECAST_EVIDENCE.md) |
| FRG-04 six V9.12 pages | PASS | Real Edge on three viewports, three real forecast states, canonical analysis round trip, expiry and isolated failure handling. [Browser validation](PHASE_9_FRG_04_BROWSER_VALIDATION.md) |
| FRG-05 frozen model and protected hashes | PASS | 77/77 inference manifest entries, 107/107 provider-PoC entries, all 13 required inputs, all eight prior research SQLite/manifest files, model and metadata, exact 13 ordered features, original and prepared V9.12. |
| FRG-06 publication and ledger safeguards | PASS | The staged candidate remains PREPARED/REVIEW_REQUIRED. The real ledger stayed at zero with no directory created, HTTP 403 on the unauthorized probe and zero browser publish requests. |
| FRG-07 Windows runbook | PASS | Read-only startup, current preflight, browser workflow and fallback were verified. The runbook gives separate operator steps for optional publication and candidate review. [Defense runbook](PHASE_9_DEFENSE_RUNBOOK.md) |
| FRG-08 independent code and data decisions | PASS | Both verdicts were recorded independently, with the data verdict limited to the confirmed upcoming fixture at the observed time. |

| Remaining external action | State | Evidence needed |
|---|---|---|
| Formal review of the pending xG correction | BLOCKED | Dated evidence for the same Sportmonks metric and fixture, then explicit operator decision. |
| Renew unchanged upcoming schedules | BLOCKED | Dated, fixture-specific official evidence and a controlled reviewed successor. Downloading the current CSV again gives the same candidate bytes. |
| Real V1 publication | BLOCKED | Separate authorization for a still-upcoming eligible fixture. The successful read-only preview supplies the values and hashes for the operator's verification. |

## New test evidence

| Suite | Result |
|---|---|
| Targeted Python | 142/142 passed in 102.802 s, exit 0. Included controlled review, forecast eligibility, inference parity, trust pins, immutable ledger and concurrent writers. |
| Full Python discovery | 367/367 passed in 138.961 s, zero failures, errors or skips, exit 0. |
| Real HTTP | 17 successful HTTP calls including readiness, bootstrap, teams, fixtures, status, model, eligibility, previews, statistics and ledger. Unauthorized publication separately returned 403. |
| Real Edge 158.0.4370.33 | 18 page pairs, 49 screenshots including separately simulated expiry, exit 0. All six pages passed at 1440 × 900, 820 × 1180 and 390 × 844, with zero browser errors and zero publish requests. |
| Isolated internal Edge | 18 page pairs, 43 screenshots, exit 0. |

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_phase96_research tests.test_phase857_api tests.test_multisource_refresh tests.test_multisource_refresh_security tests.test_forecast_eligibility tests.test_forecast_integration tests.test_forecast_ledger -v
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase9 --run-id frg-real-final-20261123
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase857 --run-id frg-internal-final-20261123
```

Use a fresh run ID for another browser capture. FRG API evidence, candidate verification output, logs and public source captures are stored under ignored `data/external/multisource/phase9/frg-20261123/`. Browser images and structured evidence are covered in [FRG-04](PHASE_9_FRG_04_BROWSER_VALIDATION.md). The full Python runner preceded the final browser-only catalogue timing adjustment. The two browser suites reran against the final client bytes. The Windows environment used Python 3.14.0, FastAPI 0.121.3, Uvicorn 0.38.0, scikit-learn 1.9.1, NumPy 2.5.4, pandas 3.1.0, Playwright 1.58.0 and Edge 158.0.4370.33.

| Frozen artifact | SHA-256 |
|---|---|
| Linear Regression pipeline including fitted imputer | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| Metadata | `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c` |
| V3 SQLite | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| V3 manifest | `22f32a8bd31a7b27f2183ec4b594b79a36f9421bc0727a01d297123155735e12` |
| Original supplied and prepared V9.12 reference | `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4` |

Implementation changes are limited to `web/xpecta/app.js` and `tests/browser_phase9.py`. The documentation checkpoint contains the six FRG and defense documents. The historical Phase 9 reports keep their original test evidence.
