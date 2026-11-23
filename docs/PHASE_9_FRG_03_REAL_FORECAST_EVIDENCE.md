# FRG-03 — Prospective real forecast evidence

**PASS at `2026-11-23T06:12:25.239140Z`.** The normal Windows `REAL_RESEARCH` service previewed Levante UD–Elche CF before kickoff using frozen Linear Regression 1.0.0. The API returned Home xG **1.3786658838158377** and Away xG **1.254957398844483**. Edge presented **1.38–1.25 xG**. This result describes expected team goals for a prospective fixture and carries the saved mixed-provider research limitations.

| Required check | Evidence |
|---|---|
| 1. Authentic canonical fixture | `research:laliga:2026:Levante:Elche`, provider ID 19732618, LaLiga 2026/27, home Levante, away Elche. [Official match](https://www.laliga.com/partido/temporada-2026-2027-laliga-ea-sports-levante-ud-elche-cf-13) |
| 2. Kickoff in the future | Official and provider both `2026-11-23T20:00:00Z`. Preview generated more than 13 hours before kickoff. |
| 3. Schedule evidence valid | Attested V3 acquisition `2026-11-21T20:20:23.160077Z`. The 48-hour limit expires `2026-11-23T20:20:23.160077Z`. |
| 4. Established eligibility | Live `/eligibility` and `/forecasts/preview` both returned `READY`. |
| 5. Prematch feature inputs | Strict date cutoff `2026-11-23`. All 10 rolling input rows were earlier than cutoff, five for each side. Levante observed dates spanned October 16–November 8; Elche October 11–November 8. Target statistics were excluded. |
| 6. Frozen feature order | Exact 13 ordered names matched the estimator, feature builder and HTTP model summary. Feature SHA-256 `3c2e3f15c0b3d9c7a2455f111667bd608ae11a97afa3ce35ea175d8990e0e4d9`. |
| 7. Values valid | Both values finite and non-negative. |
| 8. Repeated HTTP previews | Same values, feature hash and database hash on both requests. |
| 9. Direct parity | Same values and hashes from trusted direct generation. Applying the frozen pipeline to the same two feature rows also agreed within `1e-12`. |
| 10. Ledger unchanged | Zero real records before and after, no real ledger directory created, no browser publish requests. An unauthorized HTTP probe was refused with `403 PUBLICATION_DISABLED`. |

The binding was V3 with DB SHA-256 `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` and manifest SHA-256 `22f32a8bd31a7b27f2183ec4b594b79a36f9421bc0727a01d297123155735e12`. SQLite read-only integrity check returned `ok`, with zero foreign key violations. The frozen model hash was `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` and metadata hash was `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c`. `production_approved=false`.

Levante–Racing Santander returned `WAITING_DATA/REGISTRY_COVERAGE_UNVERIFIED`, and Alavés–Getafe returned `UNAVAILABLE/TARGET_NOT_UPCOMING`. Both returned null forecasts. The whole-catalogue reasons, unavailable counts and expiry check are in the [schedule dossier](PHASE_9_FRG_02_SCHEDULE_EVIDENCE.md). The feature vectors and HTTP proof are local under `data/external/multisource/phase9/frg-20261123/`.

The service was restarted with the same read-only V3 launch settings. A second actual preview at `2026-11-23T06:16:06.716853Z` reproduced both values and the feature hash. If kickoff precedes another defense session or fresh trusted schedule evidence is absent, apply the [defense runbook](PHASE_9_DEFENSE_RUNBOOK.md) to that session's actual time. Optional V1 publication requires a fresh preview and separate operator authorization.
