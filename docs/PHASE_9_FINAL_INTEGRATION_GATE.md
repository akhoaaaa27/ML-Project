# Phase 9 final integration gate

This is the historical gate for the original Phase 9 implementation. The separate Phase 9.6–9.9 run records the newer data acquisition, candidate review state, fixture discovery, publication safeguards and actual rerun results. [Phase 9.9 revalidation](PHASE_9_9_FINAL_REVALIDATION.md)

Verification date: 23 November 2026, Asia/Saigon. Baseline: `37f0e1e7d57b3f90197479cf1ce6db3b70b66ab8`. Tested implementation: `b2adbd49f80a4c454d9a4ee541ef4e88d5c28d9f` on `phase9-real-data-first-ui-finalization`. The decision applies to the localhost research demonstration, with `production_approved=false`.

| Acceptance criterion | Result | Evidence |
|---|---|---|
| Correct Git baseline and existing branch | PASS | Fetched main and Phase 9 both matched the verified commit. Local tracking branch opened from a clean workspace. |
| WS0 real runtime | PASS | Read-only NTFS recovery, pinned snapshot verified and all 8 required live JSON endpoints HTTP 200. [WS0](PHASE_9_WS0_REAL_RUNTIME_REPORT.md) |
| WS1 real catalogue and genuinely eligible preview | PASS | 252 upcoming fixtures and 7 eligible at the initial scan. Looked up Levante–Elche in official LaLiga, checked strict cutoff and repeat/direct frozen-inference parity, and rendered the fixture on the real website. [WS1](PHASE_9_WS1_REAL_DATA_VALIDATION.md) |
| WS1 blocked and unavailable | PASS | Preview values remained null for waiting and unavailable cases. The real UI displayed a reason and matchup placeholders at all three sizes. |
| WS2 fixture layout, result structure and navigation | PASS | UTC metadata, actual counts and desktop grid alignment. Success/loading/blocked/error panels and the same/different-fixture return paths passed browser checks. |
| WS3 analytics, ledger and model | PASS | Live historical filters, observed H2H and comparative team crests; real empty ledger and internal populated ledger with revision comparison; frozen-model feature list and dated evidence. |
| WS4 browser and accessibility checks | PASS | Edge real 18 page pairs and 45 screenshots, plus separate internal browser suite with 18 pairs and 43 screenshots. At all three real viewports, no console errors, horizontal overflow or publication requests. [Visual regression](PHASE_9_VISUAL_REGRESSION.md) |
| Targeted then full Python regression | PASS | 21/21 targeted in 6.549 s. Full discovery ran 361 tests in 176.152 s with 361 passed, zero failures, errors or skips. Both returned exit code 0. The later navigation changes only touched JavaScript and Playwright checks, which were rerun separately. |
| Reference, frozen artifacts, source data and prior snapshots | PASS | 77/77 inference and 107/107 provider-PoC manifest entries matched the Git baseline. All 13 inputs required by the compatibility runner matched. Eight real SQLite and manifest files matched the prior Phase 8.5.4 verification. The original and prepared reference still match their recorded SHA-256. |
| Forecast ledger immutability and isolation | PASS | Zero published records before and after real verification, zero publish requests from real browser, and no real ledger directory was created. Internal revisions were written under the isolated temporary workspace. |
| Reproducible Windows launch | PASS | Started real Uvicorn on loopback under the ordinary Windows account with the pinned V3. Procedure and separate commands are in the [implementation report](PHASE_9_IMPLEMENTATION_REPORT.md). |

| Protected file | Observed SHA-256 |
|---|---|
| Frozen Linear Regression pipeline | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| Frozen model metadata | `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c` |
| Production History Store | `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982` |
| Composite V3 SQLite | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| Composite V3 manifest | `22f32a8bd31a7b27f2183ec4b594b79a36f9421bc0727a01d297123155735e12` |
| Supplied and prepared V9.12 reference | `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4` |

**Local research gate PASS.** An upcoming forecast observed during testing can become unavailable. The source evidence stays subject to the 48-hour schedule window, and coverage remains incomplete for some fixtures. Published history with existing revisions was exercised in the internal namespace because real history had zero records. The research data and metrics retain the documented mixed-provider limitations.

The report commit is identifiable with `git log -1 --format=%H -- docs/PHASE_9_FINAL_INTEGRATION_GATE.md`. The real service, tests and evidence described here are local to this Windows workspace.
