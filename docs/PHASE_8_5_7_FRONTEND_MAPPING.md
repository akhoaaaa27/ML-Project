# Phase 8.5.7 — V9.12 frontend mapping

The reference is the supplied XPECTA V9.12 file with SHA-256 `f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4`. It contains embedded stadium and brand imagery, 28 club crests, Montserrat, responsive glass navigation, six hash-routed sections and a browser-local mock prediction history. The local preparer preserves the original bytes separately. It strips both old scripts, including the embedded historical dataset, preserves CSS and DOM layout, and substitutes the new modules and academic copy. The original mock history is outside the bridge.

| Page | Preserved anchor and controls | Integrated data |
|---|---|---|
| Overview | `page-home`, hero, `homeFixtures`, `homeSeason`, crest cards, rankings, footer | Recent fixture catalogue, optional published xG, verified history totals and sourced season rankings |
| Prediction | `page-predict`, preset and custom tabs, `customHome`, `customAway`, `predictionOutput` | Canonical fixture lookup, preview readiness, two model xG cards only on success, snapshot, cutoff and source notice |
| Match Analysis | `page-analysis`, Last 5/10, `analysisOutput`, form, venue and trend cards | Season filter, observed xG/xGA and shot definitions by source, actual verified history counts, explicit missing values |
| Team Statistics | `page-stats`, `statsTeam`, `statsSeason`, `statsCompare`, `statsOutput` | Season-bounded outcomes, chart and venue splits, optional comparison |
| Prediction History | `page-history`, filters, `historyTable`, modal, CSV export | Immutable backend revisions, comparison, search/sort, CSV escaping and formula defense. Clear filters resets the display. |
| AI Model | `page-model`, `featuresList`, `modelScatter`, `modelResidual`, metric cards | Frozen LR metadata, all 13 features, verified Phase 7 FBref and Phase 8.5.6 provider cohorts in distinct chart cards |

The original `simulate()` and its callers were removed. The replacements use `api.js` for requests and response checks, `app.js` for state and navigation, and `view.js` for escaped templates, chart paths and CSV. The original `FIXTURES` and stored `HISTORY` are replaced by API results. Assets verified only for local use remain out of Git, including the original and generated HTML and screenshots.

The tab layout, dark green glass colors, charts' card arrangement, crest frames, logo, hero, typography and responsive navigation follow the supplied markup. Visible differences communicate snapshot trust, loading, unavailable/blocked states and schema-correct scientific content. The synthetic mode badge is visible on mobile as well as desktop. Chart gaps represent missing statistics. The historical display uses date labels because the trusted catalogue does not guarantee a reviewable matchweek mapping.
