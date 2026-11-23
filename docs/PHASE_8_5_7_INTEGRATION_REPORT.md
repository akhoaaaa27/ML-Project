# Phase 8.5.7 — XPECTA integration gate

**Verdict `PASS` for local research and thesis demo.** `production_approved=false`. The integration uses the frozen model and the existing pre-match eligibility, publication and comparison contracts. The machine-readable evidence accompanies this report. [Integration JSON](PHASE_8_5_7_INTEGRATION_REPORT.json)

## Git scope and functionality

Branch `phase8.5.7-fastapi-frontend-bridge` was created from the verified `main` merge of Phase 8.5.6 at `ea555a05168f773399e154f12d1a2be2a593fca7`. The changes are additive. They include the API/settings/schemas/service adapter, local preparation and demo tools, JavaScript modules and OFL font, tests and documentation. Existing model, pipeline, Phase 7 metrics, research snapshot schema, eligibility policy and forecast ledger stay as supplied.

The 15 endpoints cover health, bootstrap, teams, fixtures, eligibility, freshness, preview, operator publication, ledger listing/detail/comparison, team statistics, match analysis and model summary. All six V9.12 pages use those APIs with visible loading or availability. [API contract](PHASE_8_5_7_API_CONTRACT.md) · [Frontend mapping](PHASE_8_5_7_FRONTEND_MAPPING.md)

| Evidence | Verified result |
|---|---|
| Real research | V3 loaded 3,040 fixture identities and retained all 4 pending statistics cases. Four read-only smoke previews returned `READY` and matched the eligibility endpoint at the time of checking. Both xG values were finite. The real ledger's validated record set stayed unchanged. Freshness is checked again when a forecast is requested. |
| Synthetic A–E | HTTP preview matched the direct frozen generator. Operator scenarios created immutable `INITIAL` and `UPDATED` revisions, replayed `NO_CHANGE`, and produced `WAITING_DATA` and `UNAVAILABLE` without fabricated xG. Comparison followed same-fixture lineage. |
| Historical reference / F | Historical mode exposed verified observed statistics with incomplete coverage visible and returned `UNAVAILABLE/HISTORICAL_ONLY` for a preview. The separate Phase 8.5.3 replay ran on 123 fixtures and 246 team predictions. All 111 parity cases matched, with maximum feature and raw-prediction deltas of 0. |
| Security and concurrency | Rejected unexpected fields, local path inputs, foreign Host, invalid authorization, disallowed Origin, and oversized bodies. A filesystem failure mapped to 503 and released the writer lock. Two concurrent HTTP publishers created one immutable revision. |
| Browser and visual | Edge passed all six pages on 1440×900, 820×1180 and 390×844. Reviewed 18 screenshot pairs and 5 interactive states. Zero console errors and uncaught rejections in the final verified workflows. |
| Python | 16/16 targeted tests in 7.297 s, exit 0. Full regression 356/356 in 203.224 s, exit 0, including all 340 baseline tests. Zero failures, errors and skips. `pip check` found no broken requirements. |

## Protected evidence

Manifest checks passed 77/77 and 107/107 entries, covering 107 unique protected files. The gate verified 13/13 attested local inputs and 8/8 research snapshot files against the existing baseline. The trusted loader verified the fitted imputer and ordered schema. No frozen artifact was refit or written.

| Artifact | SHA-256 |
|---|---|
| Frozen LR V1 | `0258a05256e4b96fa71e229fdd98dead58cf914cb79811eaa829aa6afc4ebf69` |
| Model metadata | `6044687950628d0310a8a7f3bde2692ed03c746e71b9679bde5a11e2c563a04c` |
| Production History Store | `d76706a0c8ba26b8a29b6964b22553b6fe1195f28d2885fa6dc0032576457982` |
| Composite History V3 | `110f336daf40a6957cad6f5dc6c56298619ee96a52224b0fc4aa47a6b311b40e` |
| Original V9.12 HTML | `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4` |
| Integrated local HTML | `ffbff2be5620c920e10efb99a47a1f16e29640cef3a44fd7cfde319ac74f82fb` |

## Acceptance criteria

| AC | Status | Evidence |
|---|---|---|
| AC-01 | PASS | 15 routes, typed contracts, readiness, strict validation and generated OpenAPI. |
| AC-02 | PASS | Canonical identifiers and verified snapshot lookup preserve home/away order and schedule evidence. |
| AC-03 | PASS | Candidate generation matched frozen service parity with no ledger or snapshot mutation. |
| AC-04 | PASS | Freshness, stale rejection, incomplete last-five, schedule states and missing xG were exercised. |
| AC-05 | PASS | A–E verified through HTTP, including preserved initial bytes, immutable revisions and NO_CHANGE. |
| AC-06 | PASS | Startup mode and snapshot allowlists, synthetic isolation and historical-only controls were verified. |
| AC-07 | PASS | Historical coverage, nullable statistics, source attribution and separately labelled model results are presented. |
| AC-08 | PASS | Operator authorization and Origin, body and query limits, storage failure and writer races were exercised. |
| AC-09 | PASS | All six pages verified at three sizes. Visual differences are listed in the visual report. |
| AC-10 | PASS | Local end-to-end API and Edge workflows, including API errors and missing-data behavior. |
| AC-11 | PASS | 356 Python tests and protected hashes passed. No prior phase files changed. |
| AC-12 | PASS | Setup, standalone reproduction, contract, visual evidence and Phase 9 handoff are documented. |

## Known limits and review

Real research uses a fixed local snapshot, current UTC and the existing schedule review horizon. A passing smoke preview at one clock time does not carry forward after the evidence expires. Phase 8.5.6 remains `SUPPORTED_WITH_LIMITATIONS`. Provider definitions may differ and historical date-cutoff replay lacks as-of-vintage evidence. The thesis demo offers an isolated synthetic clock and dataset. Only permitted public assets are tracked. The supplied HTML, local generated HTML, visual evidence and all provider and ledger records stay in ignored directories.

For review, compare this branch with `main`, run the local defense walkthrough, and review the API and visual evidence. A maintainer can open and merge the PR manually after review. Retain the mode, publication and scientific boundaries in the Phase 9 handoff. [Design and walkthrough](PHASE_8_5_7_DESIGN.md) · [Visual regression](PHASE_8_5_7_VISUAL_REGRESSION.md)
