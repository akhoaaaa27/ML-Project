# XPECTA Phase 9 design

Phase 9 runs on the existing `phase9-real-data-first-ui-finalization` branch from verified baseline `37f0e1e7d57b3f90197479cf1ce6db3b70b66ab8`. The primary thesis demonstration is the localhost `REAL_RESEARCH` website backed by the pinned Composite History V3 snapshot and frozen Linear Regression pipeline. The internal browser suite launches its own isolated synthetic workspace.

| Boundary | Behavior |
|---|---|
| Runtime | FastAPI serves the existing prepared V9.12 reference overlay and verifies the configured research binding. The default research setup identifies its snapshot and exposes readiness separately from data freshness. |
| Fixture catalogue | Counts and chronological order come from the API. Cards show UTC kickoff only when supplied, and show xG only for an existing published forecast. Desktop cards retain their width when one or two close the grid. |
| Preview | One panel presents success, loading, blocked eligibility and transport failures. The UI requires a matching fixture key, runtime mode, snapshot and model before rendering a numeric prediction. Blocked panels preserve matchup and size with placeholders. |
| Return from analysis | The browser remembers the canonical fixture and prediction tab for navigation. A return from the same matchup requests a fresh read-only preview. A different matchup opens the input form. There is no automatic publication path. |
| Historical views | Match insights and H2H summarize observed results and xG where coverage exists. Team comparisons retain provider/metric coverage, observed values and Goals − xG semantics. History uses the immutable published ledger, with search, revisions, filters and filtered CSV export. |
| Model view | The API supplies the frozen model, 13 ordered features, actual evaluation metrics and periods from the saved Phase 7 and Phase 8.5.6 evidence. No training is required to serve them. |
| Assets | The original HTML SHA-256 is `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4`. The existing repo-native bridge extends the prepared runtime with a same-origin stylesheet. The original reference, handoff HTML and local screenshots stay ignored. |

The baseline discrepancies and earlier API behavior are recorded in the [V9.12 fidelity audit](PHASE_9_V912_VISUAL_FIDELITY_AUDIT.md) and [Phase 8.5.7 API contract](PHASE_8_5_7_API_CONTRACT.md).
