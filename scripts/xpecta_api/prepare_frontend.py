"""Build an independently editable local HTML from the supplied, checksum-pinned reference."""

import argparse
from base64 import b64encode
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from .settings import PREPARED

REFERENCE_SHA256 = "f5aada295d659b8856cc5b4c465f1a20ba912056aa431d1565e67426f57728e4"
LOCAL_CRESTS = {
    "Deportivo La Coruna": ("deportivo-la-coruna.png", "image/png"),
    "Racing Santander": ("racing-santander.webp", "image/webp"),
    "Malaga": ("malaga.webp", "image/webp"),
}
COPY_EDITS = (
    ("select,input[type=text],input[type=search]{", "select,input[type=text],input[type=search],input[type=date]{"),
    ("select,input[type=text],input[type=search],textarea{\n",
     "select,input[type=text],input[type=search],input[type=date],textarea{\n"),
    ("select,input[type=text],input[type=search],textarea{background:",
     "select,input[type=text],input[type=search],input[type=date],textarea{background:"),
    ("Preconfigured sample fixtures. Select a match to explore simulated xG.", "Select a catalogue fixture to check availability and preview xG."),
    ("All preconfigured La Liga sample fixtures · 2026/27", "Fixtures from the selected research catalogue"),
    ("DEMO FIXTURES", "FIXTURE CATALOGUE"),
    ('<div class="indicator mt20">ⓘ Illustrative schedule only · Not verified against the official schedule · No automatic updates</div>', ""),
    ("Choose two teams to generate a simulated pre-match xG result.",
     "Choose the home and away teams for a hypothetical simulation."),
    (">DEMO ONLY</span>", ">HYPOTHETICAL</span>"),
    ("ⓘ Hypothetical matchup using the fixed historical data cutoff, not an official fixture.",
     "ⓘ Simulations use verified history from the selected snapshot."),
    ("Explore xG, xGA, shots and team form using the available dataset. Only matches before the analysis cutoff are included.",
     "Explore observed xG, xGA and team form."),
    ('<span class="chip">HISTORICAL DATA</span>', ""),
    ('<div class="mt20 analysis-controls">', '<div class="mt20 analysis-controls"><div class="field analysis-season"><label for="analysisSeason">Season</label><select id="analysisSeason"></select></div>'),
    ("Simulated xG predictions created in this browser. No post-match actual xG or ongoing accuracy tracking.",
     "Browse official match forecasts and custom simulations."),
    ("SIMULATED PREDICTION HISTORY", "PREDICTION RECORDS"),
    ("Data is stored locally in your browser", "Custom simulations are saved in this browser."),
    ('<div class="grid3 mt20"><div class="field"><label for="historySearch">',
     '<div class="grid4 mt20 history-filters"><div class="field"><label for="historySearch">'),
    ('<div class="field"><label for="historyType">Prediction type</label>',
     '<div class="field"><label for="historyRecordType">Record type</label><select id="historyRecordType">'
     '<option value="all">All records</option><option value="OFFICIAL_MATCH_FORECAST">Official Match Forecast</option>'
     '<option value="CUSTOM_SIMULATION">Custom Simulation</option></select></div>'
     '<div class="field"><label for="historyType">Prediction type</label>'),
    ("Prediction type", "Forecast stage"),
    ("✕ Clear history", "✕ Clear filters"),
    ('<option value="fixture">Preset fixture</option><option value="custom">Custom simulation</option>',
     '<option value="INITIAL">Initial</option><option value="UPDATED">Updated</option>'),
    ('<div id="historyTable"', '<p id="historyNotice" class="subtext" role="status"></p><div id="historyTable"'),
    ("This HTML version has no trained model integrated.", "The backend uses the frozen Linear Regression V1 pipeline."),
    ("INTERACTIVE DEMO · NO TRAINED MODEL", "FROZEN LINEAR REGRESSION V1"),
    ("Planned model: XGBoost Regression. In this HTML version, a simulation formula replaces model inference to demonstrate the interface and user experience; it is not a trained AI model.",
     "The fitted Linear Regression model estimates total team xG from the frozen 13-feature schema and fitted median imputer."),
    ("Available La Liga history from 2019/20 to 2025/26. The final season is incomplete; no new data synchronization.",
     "Season coverage and source attribution come from the currently selected history snapshot."),
    ("PROPOSED PIPELINE", "FROZEN PIPELINE"),
    ("This section illustrates the metrics to report after training. All values below are fictional and were not calculated from the HTML simulation.",
     "Verified metrics are shown separately by label source and evaluation period."),
    ("ACTUAL VS. PREDICTED", "OBSERVED VS. PREDICTED"),
    ("Sample chart illustrating how evaluation results could be presented", '<span id="modelScatterScope"></span>'),
    ("Illustrative residuals, not calculated from saved website predictions", '<span id="modelResidualScope"></span>'),
    ("Real evaluation requires chronological train/validation/test splits and comparison on an independent test set. Replace these values only after training and evaluating the actual model.",
     '<span id="modelEvaluationNotice">Loading evaluation context…</span><div id="modelEvidence"></div>'),
    ("No external football API. Sample fixtures are not official schedules. Form data ends at the dataset cutoff.",
     "The local application uses a fixed snapshot. Schedule evidence can expire."),
    ("Simulated xG values are for testing the interface workflow. Integrating a real model requires replacing the formula and validating its outputs.",
     "Synthetic demo fixtures are isolated. Retrospective results do not establish prospective accuracy."),
    ("Selected season · Actual xG per match", "Selected season · Observed xG per match"),
    ("Actual average xG from the available historical data, not new predictions.",
     "Compare average xG across teams in the selected season."),
    ("historical matches included in this demo", "verified historical matches"),
)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Reference layout marker differs: {old[:80]}")
    return text.replace(old, new, 1)


def refine_overview(text):
    note = '<div class="hero-note">◇ Fixed historical data · Simulated predictions only</div>'
    caption = ('<div class="wrap"><div class="hero-caption"><span>✦ INTERACTIVE DEMO — '
               'predicted xG values are generated by a simulation formula, not a trained model.</span>'
               '<span>Historical data through: <strong id="cutoffHero">—</strong></span></div></div>')
    text = replace_once(replace_once(text, note, ""), caption, "")
    logo = re.search(r'<img class="expecta-logo"[^>]*>', text).group()
    logo = logo.replace('alt="XPECTA"', 'alt="XPECTA · Expect the Unexpected"')
    edits = (
        ('<div class="brand-name" style="font-size:37px;color:#fff">LALIGA<span style="color:#a5e97f">xG.</span></div>',
         f'<div class="foot-brand expecta-logo-frame">{logo}</div>'),
        ('<span class="tag" style="color:#bcebb3;border-color:#4a8150">DEMO · NO LIVE API</span>', ""),
        ('<a href="#stats">Team Statistics</a></div></div><div><h4>INFORMATION</h4>',
         '<a href="#stats">Team Statistics</a><a href="#history">Prediction History</a>'
         '<a href="#model">AI Model</a></div></div><div><h4>INFORMATION</h4>'),
        ('<a href="#history">Prediction History</a><a href="#model">About the Model</a>',
         '<a href="#model">About the Model</a>'),
        ('<p>Fixed historical data · Simulated predictions · No post-match tracking</p>', ""),
        ("© 2026 La Liga xG Predictor · Educational demo, not officially affiliated with La Liga",
         "© 2026 XPECTA · Educational project"),
    )
    for old, new in edits:
        text = replace_once(text, old, new)
    return text


def build(source, directory=PREPARED):
    source = Path(source)
    directory = Path(directory)
    original = source.read_bytes()
    if sha256(original).hexdigest() != REFERENCE_SHA256:
        raise ValueError("The supplied HTML SHA-256 does not match XPECTA V9.12")
    text = original.decode("utf-8-sig")
    match = re.search(r"const CLUB_LOGOS=(\{[^\r\n]+\});", text)
    logos = json.loads(match[1])
    if not all(re.fullmatch(r"data:image/webp;base64,[A-Za-z0-9+/=]+", value) for value in logos.values()):
        raise ValueError("Unexpected crest format in the reference")
    for team, (name, media_type) in LOCAL_CRESTS.items():
        crest = directory / "crests" / name
        if crest.is_file():
            artwork = b64encode(crest.read_bytes()).decode("ascii")
            logos[team] = f"data:{media_type};base64,{artwork}"
    # Keep asset declarations and markup only. Strip both old scripts, including raw match rows.
    text, count = re.subn(r"<script\b[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    if count != 2:
        raise ValueError("Unexpected number of reference script elements")
    text, count = re.subn(r'^<link[^\r\n]+https://fonts\.(?:googleapis|gstatic)\.com[^\r\n]+\r?\n',
                          "", text, flags=re.MULTILINE)
    if count != 3:
        raise ValueError("Unexpected font includes in the reference")
    text = replace_once(text, "</head>",
                        '<link rel="icon" type="image/png" sizes="64x64" href="/assets/favicon.png">\n</head>')
    text = replace_once(text, "</style>", """
@font-face{font-family:Montserrat;src:url('/assets/montserrat.ttf') format('truetype');font-weight:100 900;font-display:swap}
[aria-busy="true"] .indicator{opacity:.8}
.bridge-mode{white-space:nowrap}
.bridge-compare{display:flex;flex-wrap:wrap;gap:8px}
#page-analysis .analysis-season{min-width:120px}
@media(max-width:1200px){.bridge-mode{display:inline-flex;font-size:8px;padding:4px 6px}.bridge-mode .pulse{display:none}}
</style>""")
    for old, new in COPY_EDITS:
        text = replace_once(text, old, new)
    text = refine_overview(text)
    text = replace_once(text, 'class="pill-live"', 'class="pill-live bridge-mode" id="bridgeMode"')
    text = replace_once(text, " DEMO · NOT LIVE</span>", ' <span id="bridgeModeText">CONNECTING</span></span>')
    text = replace_once(text, '<div class="grid4"><div class="metric"><div class="mini-label">MAE · ILLUSTRATIVE',
                        '<p id="modelScope" class="card-desc"></p><div id="modelMetricCards" class="grid4"><div class="metric"><div class="mini-label">MAE · ILLUSTRATIVE')
    text, count = re.subn(r'(<div id="modelMetricCards" class="grid4">).*?(?=<div class="grid2 mt20"><div class="card"><h3 class="card-title">OBSERVED VS. PREDICTED)',
                          r'\1</div>', text, count=1, flags=re.DOTALL)
    if count != 1:
        raise ValueError("Unexpected model metrics section")
    template = '<template id="clubAssets">' + "".join(
        f'<img data-team="{escape(team, quote=True)}" src="{value}" alt="">' for team, value in logos.items()
    ) + '</template>'
    text = replace_once(text, "</body>", template + '\n<script type="module" src="/assets/app.js"></script>\n</body>')
    directory.mkdir(parents=True, exist_ok=True)
    output = text.encode("utf-8")
    (directory / "reference.html").write_bytes(original)
    (directory / "integrated.html").write_bytes(output)
    manifest = dict(reference_sha256=REFERENCE_SHA256, integrated_sha256=sha256(output).hexdigest(),
                    local_crests=len(logos))
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    print(json.dumps(build(parser.parse_args().source), indent=2))
