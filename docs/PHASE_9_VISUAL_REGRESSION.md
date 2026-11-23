# Phase 9 V9.12 visual regression

The comparison used Edge 158.0.4370.33 with the original SHA-256 verified V9.12 reference and the real localhost website. The real suite compared 18 pairs covering all six pages at 1440 × 900, 820 × 1180 and 390 × 844. It used the same viewport, device scale, UTC clock display, en-GB locale, Montserrat font and reduced-motion preference for both sides of each pair. The browser route allowed local resources only.

| Page | Checked behavior and visual result |
|---|---|
| Overview | The reference hero and glass navigation remain the main visual anchors. The grid displays actual fixture cards and UTC kickoffs. The synthetic four-card test verifies a centered, equal-width final card. |
| Prediction | Real eligible results show the two crests and xG panels, comparison, combined xG, difference, and model/snapshot information. WAITING_DATA and UNAVAILABLE keep team identity and two placeholders. Loading and invalid API responses use the same panel structure. |
| Match Analysis | Match Overview, factual Match Insights and the final CTA are present. H2H uses observed data and explicitly handles insufficient coverage. Real team, season and Last 10 controls were exercised in each viewport. |
| Team Statistics | Team controls and two comparison crests are present and venue metrics fit the viewport. Real season and team filters were exercised in each viewport. |
| Prediction History | The real ledger's empty state reflects zero records. The internal test checks initial and updated revisions, filtering, sort, comparisons, safe CSV, and Escape handling. |
| AI Model | The 13 features and dated evidence are visible. The Phase 7 and provider replay charts show saved metrics for Linear Regression in the V9.12 visual hierarchy. |

The real suite checked navigation width and height, glass background and blur, readable fonts and absence of horizontal overflow. It exercised mobile and tablet menu expansion and close, semantic labels and status text, and captured three states at each viewport. It saw zero page/console errors and zero publication requests. It compared page structure and visual hierarchy using actual content, including larger fixture counts, longer team names, smaller historical samples and the empty real ledger.

The separate internal suite also covers forecast loading, an invalid API response, live-fixture exclusion, and return to Prediction with the same and a changed matchup. Its two published revisions exist in a temporary test namespace only. The real browser regression validates visual structure and selected accessibility behavior. A full WCAG conformance audit was outside this run.

Evidence paths are ignored local directories. The real suite stores 36 viewport screenshots, nine forecast-panel screenshots and `evidence.json` under `data/external/multisource/phase9/visual/real-release/`. The internal suite stores its 18 full-page pairs, scenario screenshots and `browser-evidence.json` under `data/external/multisource/phase857/visual/phase9-internal-release/`.
