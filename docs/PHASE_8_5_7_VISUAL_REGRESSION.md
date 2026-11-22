# Phase 8.5.7 — V9.12 visual regression

**PASS** in Microsoft Edge 158.0.4370.33 headless. The browser used localhost HTTP for the integrated page and the original HTML for the reference. Both used the pinned Montserrat asset. External page requests were intercepted. The original and integrated layouts were inspected side by side as well as exercised through controls.

| Viewport | Reference and integrated pages | Result |
|---|---|---|
| Desktop 1440 × 900 | Overview, Prediction, Match Analysis, Team Statistics, Prediction History, AI Model | Six pairs matched the glass navigation styling and width. The hero, card grid and layout held. |
| Tablet 820 × 1180 | Same six pages | Six pairs verified responsive menu, card grids, typography and spacing. |
| Mobile 390 × 844 | Same six pages | Six pairs showed no main document horizontal overflow. Logo, responsive page order and compact navigation held. The mode badge remains visible. |

The evidence contains 36 screenshots for the 18 paired pages and five additional states for loading, a successful preset preview, forecast comparison, open mobile navigation, and mobile waiting-data. The browser run captured zero console errors and zero uncaught rejections. It also exercised custom matchup parity, two historical windows, season and team filters, history search/sort, CSV download and formula escaping, and a malformed API response displayed as an error. Screenshot pairs and the browser evidence manifest are in the ignored local path `data/external/multisource/phase857/visual/browser-final/`.

## Intentional differences

- Overview and Prediction preserve the fixture cards and responsive grid. The verified catalogue changes the teams, dates, number of rows and data available on each card. The calendar stays chronological. Published xG, when present, comes from a verified ledger record. The synthetic badge is visible on all viewports.
- Match Analysis places the season filter beside the window selector on wider screens and stacks it on mobile. The mirrored charts, trend cards and form layout use observed history. A trend gap indicates missing data.
- Team Statistics uses verified season fixtures and observed-coverage counts. Goals − xG uses the games with observed xG.
- Prediction History now starts from the selected immutable ledger. It can show zero entries in a new demo. Clear filters operates on the display. The revision modal and export use published values.
- AI Model keeps the two-column chart cards and the surrounding layout. Phase 7 and Phase 8.5.6 verified aggregate bars replace the illustrative scatter and residuals. The feature grid contains all 13 frozen features.

Initial visual review found that grouping by individual date left a largely empty fixture grid on wide screens and that the season selector pushed the analysis content down. The final version restores the multi-column fixture grid and places season selection in the existing control row. The final 18 pairs and all five states were rerun and inspected after these adjustments.

## Reproduction

Prepare the trusted reference with the command in [Design and setup](PHASE_8_5_7_DESIGN.md). Run `.venv/Scripts/python.exe -X utf8 -m tests.browser_phase857 --run-id another-review`. The test owns its synthetic snapshots and ledger, starts and stops localhost servers, and writes evidence under the new run ID. The reference, integrated HTML, and screenshot artifacts contain locally supplied imagery. Keep them out of Git until redistribution rights are confirmed.
