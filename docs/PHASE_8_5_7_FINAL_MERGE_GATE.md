# XPECTA Phase 8.5.7 — Remediation and Final Merge Gate

**Merge-readiness `PASS` for local research and thesis demo.** `production_approved=false`. Gate completed 23 November 2026, Vietnam time.

| Git reference | Verified commit |
|---|---|
| Base `main` | `ea555a05168f773399e154f12d1a2be2a593fca7` |
| Reviewed starting HEAD | `b3f99460fbab43fed8fad6c04f6f5c4ffe0d39ed` |
| Tested remediation | `9e9be901a57b591f1908c7f11932de17321167d7` |

The starting working tree was clean. Local and GitHub branch tips matched the expected references. The remediation commit contains the four tested source and test files. The succeeding documentation commit updates the API and frontend mapping and adds both gate reports. The original integration report and its recorded results stay as published. [Original integration report](PHASE_8_5_7_INTEGRATION_REPORT.md)

## Root cause and remediation

The registry accepted `live` and the catalogue preserved it. Pydantic's shared `ObservedStatus` enum omitted it. The new regression cases reproduced HTTP 500 for fixture list and eligibility response serialization and HTTP 422 for the `status=live` query before the fix.

| File | Change |
|---|---|
| `scripts/xpecta_api/schemas.py` | Added `live` to the shared enum used by `Fixture`, `FixtureQuery`, the nested eligibility target and generated OpenAPI. |
| `web/xpecta/view.js` | Shows `LIVE` in the existing Prediction subtitle when Custom Matchup resolves a live fixture. Upcoming cards still use the scheduled filter. |
| `tests/test_phase857_api.py` | Five regressions covering schema validation, response serialization and canonical identity, query/OpenAPI propagation, forecast boundaries, and backward compatibility. |
| `tests/browser_phase857.py` | Extended the local walkthrough to check live fixture exclusion from both upcoming lists, the Custom Matchup status, and absence of xG panels. Added captures for live and API failure states. |

The eligibility engine already rejects a live target. The HTTP forecast-boundary test exercised that engine with an isolated synthetic snapshot whose live fixture had a future recorded kickoff. Eligibility, preview, and authorized publication returned HTTP 200 with `UNAVAILABLE / TARGET_NOT_UPCOMING`. Forecast fields were null and the ledger stayed empty. The serialization and filtering tests used in-memory catalogue rows. [Updated API contract](PHASE_8_5_7_API_CONTRACT.md) · [Frontend mapping](PHASE_8_5_7_FRONTEND_MAPPING.md)

## Validation on the corrected revision

| Check | Result |
|---|---|
| Before remediation | Five new tests reproduced three HTTP failures and one schema error. The backward-compatibility case passed. Exit 1. |
| Targeted Python | 21/21 pass in 9.374 s, exit 0 |
| Full Python | 361/361 pass in 187.276 s, exit 0. Cross-checked all 356 original test IDs and five additions against the recorded log. |
| Forecast and security | Re-executed frozen preview parity, stale schedule and missing data, immutable `INITIAL`/`UPDATED`, `NO_CHANGE`, revision comparison, operator authorization, origin and Host checks, request limits, storage failure and concurrent publication. |
| Mode and provenance | A forecast published in an isolated synthetic test ledger was absent from the real namespace. Real V3 retained 3,040 fixture identities and four pending statistics cases. Historical reference retained incomplete statistics and returned `UNAVAILABLE / HISTORICAL_ONLY` on preview. |

Both successful Python runs had zero failures, errors and skips. The previous 16/16 targeted and 356/356 full results are historical comparisons. The staged and committed executable file blobs matched the files used for this gate.

### Browser and visual evidence

Edge 158.0.4370.33 reran Overview, Prediction, Match Analysis, Team Statistics, Prediction History and AI Model at **1440×900**, **820×1180**, and **390×844**. Reviewed **18 reference/integrated pairs** and **7 state captures** covering loading, eligible preview, published revision comparison, mobile navigation, missing data, API failure, and live/unavailable. The run recorded no console errors or uncaught rejections. The 43 captures and machine-readable browser evidence remain in Git-ignored local storage under `data/external/multisource/phase857/visual/remediation-gate-20261123/`.

The original and integrated HTML hashes match the earlier validation. Dark green glass styling, Montserrat, the logo, navigation, chart panels and layout were verified against the reference. Seventeen of the 18 integrated page screenshots also matched the prior integrated run at pixel level. The remaining mobile History pair had matching geometry and no visible layout change in side-by-side review. The intentional visual addition is the `LIVE` label in the existing subtitle on the unavailable prediction result.

## Artifact integrity

Both protected manifests matched **77/77** and **107/107** entries, covering **107 unique files**. **13/13** attested inputs and **8/8** research snapshot files matched before and after validation. This includes Phase 7 evidence, the frozen LR and fitted imputer, the 13-feature metadata and existing databases. The Phase 8.5.6 reports and development dependencies were outside the remediation diff. All browser and provider artifacts remain local.

| Artifact | Verified SHA-256 |
|---|---|
| Frozen LR V1 | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| Model metadata | `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c` |
| Production History Store | `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982` |
| Composite History V3 | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| Original V9.12 HTML | `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4` |
| Integrated local HTML | `ffbff2be5620c920e10efb99a47a1f16e29640cef3a44fd7cfde319ac74f82fb` |

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-01 | PASS | Shared enum verified through Pydantic, HTTP response/query and generated OpenAPI. Fifteen routes retained. |
| AC-02 | PASS | Canonical fixture key, team orientation and public fields retained in the live response. |
| AC-03 | PASS | Frozen LR preview parity reran successfully. A live target emitted neither xG preview nor ledger record. |
| AC-04 | PASS | All six observed statuses exercised. Freshness, upcoming filtering and live forecast exclusions passed. |
| AC-05 | PASS | Immutable initial and updated revisions, NO_CHANGE and comparison reran successfully. |
| AC-06 | PASS | Verified real, synthetic and historical reference namespaces through local HTTP. |
| AC-07 | PASS | Verified historical completeness states, nullable observed values, provenance and frozen model metadata. |
| AC-08 | PASS | Operator, Origin, Host, request limits, concurrent writers and storage failure tests reran successfully. |
| AC-09 | PASS | Six V9.12 pages checked against the original at three viewport sizes. |
| AC-10 | PASS | Browser and HTTP workflows verified together, including live/unavailable and API error handling. |
| AC-11 | PASS | All 361 Python tests passed and protected SHA-256 values matched. |
| AC-12 | PASS | API and frontend documentation updated, evidence recorded and local commands verified. |

## Reproduction and handoff

Use the pinned dependencies and prepare the local HTML with the repository setup instructions. Choose a fresh run ID for the browser evidence. [Setup and demo](PHASE_8_5_7_DESIGN.md)

```powershell
.venv/Scripts/python.exe -X utf8 -m unittest tests.test_phase857_api -v
.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
.venv/Scripts/python.exe -X utf8 -m tests.browser_phase857 --run-id phase857-gate-review
```

Phase 8.5.6 retains `SUPPORTED_WITH_LIMITATIONS`. Real forecast availability depends on schedule evidence and snapshot freshness. Historical date-cutoff replay lacks as-of-vintage guarantees. Prospective accuracy and cross-provider statistical equivalence remain unproven. The HTML with embedded imagery, screenshots and provider snapshots stay in ignored local storage.

No merge blockers remain for research-only use. Open a PR manually from `phase8.5.7-fastapi-frontend-bridge` into `main` and review the two remediation commits together. [Machine-readable gate report](PHASE_8_5_7_FINAL_MERGE_GATE.json)
