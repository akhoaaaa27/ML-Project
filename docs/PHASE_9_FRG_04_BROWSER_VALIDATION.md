# FRG-04 — V9.12 browser validation

**PASS.** Actual real Edge used localhost with mode `REAL_RESEARCH`, snapshot `phase853_v3_20261122`, and the pinned V9.12 reference. Chromium channel was Edge 158.0.4370.33. Both sides used equal desktop 1440 × 900, tablet 820 × 1180 and mobile 390 × 844 viewports, Montserrat, the same browser context and UTC for the 18 page pairs.

| Page | Live checks |
|---|---|
| Overview | Correct real mode, research snapshot and freshness, actual upcoming catalogue and historical ranking. |
| Prediction | Twelve per page, team-name search, team and UTC-date filters, observed status, sorting and disjoint pages. Canonical keyboard selection, focus and filter restoration, real Levante–Elche xG, and null-valued WAITING_DATA/UNAVAILABLE panels. |
| Match Analysis | Real same-fixture navigation from Prediction, observed H2H and Match Insights, actual season/team changes and Last 10 request. Returning to Prediction made another read-only call for the same canonical key and reproduced the displayed values. |
| Team Statistics | Actual observed-provider statistics, comparison crests and season/team filter. |
| Prediction History | Empty real ledger, matching the HTTP count of zero. Populated history, filters, CSV, revision details and V1/V2 comparison were exercised in the isolated suite. |
| AI Model | Frozen Linear Regression summary, dated evaluation evidence and exact 13-feature display. |

Browser checks also covered responsive navigation, keyboard handling, original glass navigation geometry, absence of horizontal overflow, zero console/page errors and zero real publish requests. The internal suite exercised invalid API responses and loading, expiry-related eligibility regressions in the Python suite, isolated write behavior and safe blocked panels. No isolated fixture is evidence for the real-data decision.

## Expiry boundary regression

The original display labeled schedule evidence as recent until an asynchronous refresh returned. The remediation updates the display at the last server-attested expiry using elapsed browser time. A delayed response whose evaluation time precedes the elapsed boundary cannot restore the old label. Catalogue browsing also excludes a fixture once its recorded kickoff has elapsed, even if the recheck is delayed. The server remains the authority for forecast eligibility.

In a **separate browser context**, the test opened real localhost, used the authentic response timestamps, advanced only the browser clock, then replayed the earlier genuine read-only HTTP response as a delayed response. Both Overview and Prediction switched to stale, the already-started fixture left the default upcoming list, and no numeric preview or publication appeared in that test. The JavaScript timer and UI were under test. The actual live forecast proof used the unchanged Windows clock.

| Suite | Local ignored evidence |
|---|---|
| Real Edge | `data/external/multisource/phase9/visual/frg-real-final-20261123/` contains 18 page pairs, nine real forecast-state captures, three discovery captures, the expiry screenshot and `evidence.json`. |
| Internal Edge | `data/external/multisource/phase857/visual/frg-internal-final-20261123/` contains 18 page pairs, seven scenario captures and `browser-evidence.json`. |

The supplied original and prepared reference both matched SHA-256 `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4`. The integrated page uses the original as a visual baseline. Actual fixture records and statistics come from the trusted provider-backed local snapshot.
