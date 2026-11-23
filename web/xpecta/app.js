import {api} from "./api.js";
import {$, comparison, csvText, fixtureCard, historyDetails, historyTable, leaderboard, matchAnalysis,
  message, prediction, presetFixtures, renderModel, seasonName, statusName, teamStats} from "./view.js";

const pages = {
  home: "Overview", predict: "Prediction", analysis: "Match Analysis",
  stats: "Team Statistics", history: "Prediction History", model: "AI Model",
};
const state = {
  page: "home", tab: "fixture", fixture: null, config: null, teams: [], fixtures: [],
  history: [], hasHistory: false, analysisOrigin: null,
};
const pending = new Map();
const seasons = ["homeSeason", "analysisSeason", "statsSeason"];
const selectors = {
  customHome: "Valencia", customAway: "Real Madrid",
  analysisHome: "Real Madrid", analysisAway: "Barcelona",
  statsTeam: "Real Madrid", statsCompare: "Barcelona",
};

function renderHere(id, content) {
  $(id).innerHTML = content;
}

function notice(id, text, error = false) {
  renderHere(id, message(text, error));
}

function loading(id) {
  $(id).setAttribute("aria-busy", "true");
  notice(id, "Loading…");
}

async function display(id, work, apply, forecastContext) {
  const request = Symbol();
  pending.set(id, request);
  if (forecastContext) {
    $(id).setAttribute("aria-busy", "true");
    renderHere(id, prediction(forecastContext(), {status: "LOADING"}));
  } else {
    loading(id);
  }
  try {
    const result = await work();
    if (pending.get(id) === request) apply(result);
  } catch (error) {
    if (pending.get(id) === request) {
      const text = error.message || "The request failed.";
      if (forecastContext) {
        renderHere(id, prediction(forecastContext(), {status: "FORECAST_ERROR", error: {message: text}}));
      } else {
        notice(id, text, true);
      }
    }
  } finally {
    if (pending.get(id) === request) {
      $(id)?.removeAttribute("aria-busy");
      pending.delete(id);
    }
  }
}

function cancel(id) {
  pending.delete(id);
  $(id)?.removeAttribute("aria-busy");
}

function addOptions(id, rows, defaultValue = $(id).value) {
  const select = $(id);
  select.replaceChildren(...rows.map(([value, label]) => new Option(label, value)));
  if (rows.some(([value]) => String(value) === String(defaultValue))) select.value = defaultValue;
}

function setSelectors() {
  const available = [...state.config.seasons].reverse();
  for (const id of seasons) addOptions(id, available.map(year => [year, seasonName(year)]),
    id === "analysisSeason" && state.config.mode === "SYNTHETIC_DEMO" ? state.config.current_season : available.find(y => y < state.config.current_season) ?? available[0]);
  for (const [id, preferred] of Object.entries(selectors)) {
    const teams = id.startsWith("custom") ? state.teams.filter(team => team.seasons.includes(state.config.current_season)) : state.teams;
    addOptions(id, teams.map(team => [team.id, team.name]), preferred);
  }
  for (const prefix of ["stats", "analysis"]) filterTeams(prefix);
}

function filterTeams(prefix) {
  const year = Number($(prefix + "Season").value);
  const ids = prefix === "stats" ? ["statsTeam", "statsCompare"] : ["analysisHome", "analysisAway"];
  const teams = state.teams.filter(team => team.seasons.includes(year));
  ids.forEach(id => addOptions(id, teams.map(team => [team.id, team.name])));
  if ($(ids[0]).value === $(ids[1]).value && teams.length > 1) $(ids[1]).selectedIndex = 1;
}

function toast(text) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = text;
  $("toastWrap").append(node);
  setTimeout(() => node.remove(), 3600);
}

function modal(title) {
  $("modalTitle").textContent = title;
  $("modalCover").classList.add("open");
  $("closeModal").focus();
}

function closeModal() {
  cancel("modalBody");
  cancel("compareOutput");
  $("modalCover").classList.remove("open");
}

function openGuide() {
  cancel("modalBody");
  modal("WHAT IS xG?");
  renderHere("modalBody", '<p class="subtext">Observed expected goals (xG) measures the quality of shots in a match. XPECTA predicts total team xG before kickoff when the fixture is eligible.</p><div class="card mint mt20"><div class="mini-label">ILLUSTRATIVE EXAMPLE</div><div class="forecast-big">0.25 xG</div><p>Four shots each worth 0.25 xG sum to 1.00 xG.</p></div>');
}

function publishedByKey() {
  const latest = new Map();
  for (const row of state.history) {
    const key = row.canonical_fixture_key;
    if (!latest.has(key) || latest.get(key).forecast_revision < row.forecast_revision) latest.set(key, row);
  }
  return latest;
}

function renderFixtures() {
  const latest = publishedByKey();
  const fixtures = state.fixtures;
  if (!fixtures.length) {
    const text = "No upcoming fixtures are listed in this snapshot.";
    notice("homeFixtures", text);
    notice("presetFixtures", text);
    return;
  }
  renderHere("homeFixtures", fixtures.slice(0, 6).map(row => fixtureCard(row, latest.get(row.canonical_fixture_key))).join(""));
  renderHere("presetFixtures", presetFixtures(fixtures, latest));
}

function homeBars() {
  const season = Number($("homeSeason").value);
  const teams = state.teams.filter(team => team.seasons.includes(season));
  return display("homeTeamBars", () => Promise.allSettled(teams.map(team => api.teamStats(team.id, season))),
    results => {
      const available = results.filter(result => result.status === "fulfilled").map(result => result.value);
      renderHere("homeTeamBars", available.length ? leaderboard(available) : message("Historical statistics are unavailable.", true));
    });
}

function updatePredictTab() {
  cancel("predictionOutput");
  $("predError").style.display = "none";
  $("predictionOutput").hidden = true;
  $("predictionOutput").replaceChildren();
  $("fixtureBack").hidden = true;
  $("fixturePick").hidden = state.tab !== "fixture";
  $("customPick").hidden = state.tab !== "custom";
  document.querySelectorAll("[data-pred-mode]").forEach(button => {
    const active = button.dataset.predMode === state.tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function resetPrediction(tab) {
  state.tab = tab;
  state.fixture = null;
  state.analysisOrigin = null;
  updatePredictTab();
}

function showForecast(fixture, result) {
  const preview = result.preview;
  if (preview && (preview.canonical_fixture_key !== fixture.canonical_fixture_key ||
      preview.history_snapshot_version !== state.config.snapshot_version ||
      preview.model_version !== state.config.model_version ||
      preview.dataset_kind !== (state.config.mode === "SYNTHETIC_DEMO" ? "synthetic" : "real"))) {
    throw new Error("The forecast context changed. Reload XPECTA before previewing again.");
  }
  state.fixture = fixture;
  renderHere("predictionOutput", prediction(fixture, result));
}

async function forecastFor(fixture) {
  state.fixture = fixture;
  $("fixturePick").hidden = state.tab === "fixture";
  $("fixtureBack").hidden = state.tab !== "fixture";
  $("predictionOutput").hidden = false;
  await display("predictionOutput", () => api.preview(fixture.canonical_fixture_key),
    result => showForecast(fixture, result), () => fixture);
}

function selectFixture(key) {
  const fixture = state.fixtures.find(row => row.canonical_fixture_key === key);
  if (!fixture) return;
  resetPrediction("fixture");
  go("predict");
  void forecastFor(fixture);
}

async function customPrediction() {
  if (!state.config) return;
  const button = $("runPrediction");
  const home = $("customHome").value;
  const away = $("customAway").value;
  let fixture = {home_team: home, away_team: away, season: state.config.current_season};
  button.disabled = true;
  $("predictionOutput").hidden = false;
  try {
    await display("predictionOutput", async () => {
      const matches = await api.fixtures({home, away, season: state.config.current_season});
      if (matches.length !== 1) throw new Error("No canonical fixture was found for this matchup.");
      fixture = matches[0];
      return api.preview(fixture.canonical_fixture_key);
    }, result => showForecast(fixture, result), () => fixture);
  } finally {
    button.disabled = false;
  }
}

function showAnalysis() {
  return display("analysisOutput", () => api.analysis({
    home: $("analysisHome").value, away: $("analysisAway").value,
    season: $("analysisSeason").value, window: $("analysisWindow").value,
  }), result => renderHere("analysisOutput", matchAnalysis(result)));
}

function showStats() {
  const season = $("statsSeason").value;
  return display("statsOutput", async () => {
    const [main, comparison] = await Promise.allSettled([
      api.teamStats($("statsTeam").value, season), api.teamStats($("statsCompare").value, season),
    ]);
    if (main.status === "rejected") throw main.reason;
    return [main.value, comparison.status === "fulfilled" ? comparison.value : null];
  }, result => renderHere("statsOutput", teamStats(...result)));
}

function visibleHistory() {
  const query = $("historySearch").value.toLowerCase().trim();
  const stage = $("historyType").value;
  const direction = $("historySort").value === "old" ? 1 : -1;
  return state.history.filter(row => (stage === "all" || row.forecast_stage === stage) &&
    [row.home_team, row.away_team].some(team => team.toLowerCase().includes(query)))
    .sort((a, b) => direction * (a.generated_at_utc.localeCompare(b.generated_at_utc) ||
      a.forecast_revision - b.forecast_revision));
}

function renderHistory() {
  if (!state.hasHistory) return;
  const rows = visibleHistory();
  $("historyCount").textContent = `${rows.length} / ${state.history.length} records`;
  renderHere("historyTable", historyTable(rows, state.history.length));
}

function showHistory() {
  return display("historyTable", api.history, rows => {
    state.history = rows;
    state.hasHistory = true;
    renderHistory();
    if (state.fixtures.length) renderFixtures();
  });
}

function exportHistory() {
  const rows = visibleHistory();
  if (!rows.length) return toast("No matching forecasts to export.");
  const file = URL.createObjectURL(new Blob([csvText(rows)], {type: "text/csv;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = file;
  link.download = "xpecta_forecast_history.csv";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(file), 1000);
}

function showDetails(id) {
  modal("PREDICTION DETAILS");
  return display("modalBody", () => api.forecast(id), row => {
    const revisions = state.history.filter(item => item.canonical_fixture_key === row.canonical_fixture_key)
      .sort((a, b) => a.forecast_revision - b.forecast_revision);
    renderHere("modalBody", historyDetails(row, revisions));
  });
}

function showComparison(key) {
  return display("compareOutput", () => api.compare({fixture_key: key, v1: $("compareV1").value,
    v2: $("compareV2").value}), result => renderHere("compareOutput", comparison(result)));
}

function toggleMobile(open) {
  $("mobileMenu").classList.toggle("open", open);
  $("mobileToggle").textContent = open ? "✕" : "☰";
  $("mobileToggle").setAttribute("aria-expanded", String(open));
}

function navigate() {
  const candidate = location.hash.slice(1);
  const page = Object.hasOwn(pages, candidate) ? candidate : "home";
  const previousPage = state.page;
  state.page = page;
  document.querySelectorAll(".page").forEach(section => section.classList.toggle("active", section.id === `page-${page}`));
  document.querySelectorAll("[data-page]").forEach(button => {
    const active = button.dataset.page === page;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  });
  toggleMobile(false);
  document.title = `${pages[page]} · XPECTA`;
  window.scrollTo(0, 0);
  if (!state.config) return;
  if (previousPage === "predict" && page !== "predict") {
    state.fixture = null;
    updatePredictTab();
  }
  if (previousPage === "analysis" && page !== "analysis") {
    if (page === "predict" && state.analysisOrigin) restorePredictionFromAnalysis();
    else state.analysisOrigin = null;
  }
  if (page === "analysis") void showAnalysis();
  if (page === "stats") void showStats();
  if (page === "history") void showHistory();
  if (page === "model") void display("featuresList", api.model, renderModel);
}

function go(page) {
  if (location.hash === `#${page}`) navigate();
  else location.hash = page;
}

function restorePredictionFromAnalysis() {
  const home = $("analysisHome").value;
  const away = $("analysisAway").value;
  const origin = state.analysisOrigin;
  const sameFixture = origin && origin.fixture.home_team === home && origin.fixture.away_team === away &&
    origin.fixture.season === Number($("analysisSeason").value);
  resetPrediction(sameFixture ? origin.tab : "custom");
  if (state.tab === "custom") {
    $("customHome").value = home;
    $("customAway").value = away;
  }
  // Re-evaluate through the current binding. A cached result could have expired at kickoff or on refresh.
  if (sameFixture) void forecastFor(origin.fixture);
}

function bind() {
  document.addEventListener("click", event => {
    const button = event.target.closest("[data-page],[data-jump],[data-fixture],[data-pred-mode],[data-history],[data-compare],[data-guide],[data-analyze],[data-to-custom],[data-retry-forecast],[data-back-to-fixtures]");
    if (!button) return;
    const {page, jump, fixture, predMode, history, compare} = button.dataset;
    if (page || jump) {
      const destination = page || jump;
      if (destination === "predict" && !(state.page === "analysis" && state.analysisOrigin)) {
        resetPrediction("fixture");
      }
      go(destination);
    } else if (fixture) selectFixture(fixture);
    else if (predMode) resetPrediction(predMode);
    else if (history) void showDetails(history);
    else if (compare) void showComparison(compare);
    else if (button.hasAttribute("data-guide")) openGuide();
    else if (button.hasAttribute("data-back-to-fixtures")) resetPrediction("fixture");
    else if (button.hasAttribute("data-retry-forecast")) {
      if (state.tab === "fixture" && state.fixture) void forecastFor(state.fixture);
      else void customPrediction();
    }
    else if (button.hasAttribute("data-analyze") && state.fixture) {
      state.analysisOrigin = {fixture: state.fixture, tab: state.tab};
      $("analysisSeason").value = state.fixture.season;
      filterTeams("analysis");
      $("analysisHome").value = state.fixture.home_team;
      $("analysisAway").value = state.fixture.away_team;
      go("analysis");
    } else if (button.hasAttribute("data-to-custom")) {
      restorePredictionFromAnalysis();
      go("predict");
    }
  });
  $("mobileToggle").addEventListener("click", () => toggleMobile(!$("mobileMenu").classList.contains("open")));
  $("brand").addEventListener("click", () => go("home"));
  $("brand").addEventListener("keydown", event => { if (event.key === "Enter") go("home"); });
  $("backToFixtures").addEventListener("click", () => {
    resetPrediction("fixture");
    window.scrollTo(0, 0);
  });
  $("runPrediction").addEventListener("click", customPrediction);
  for (const id of ["customHome", "customAway"]) $(id).addEventListener("change", () => resetPrediction("custom"));
  for (const prefix of ["stats", "analysis"]) {
    $(prefix + "Season").addEventListener("change", () => {
      filterTeams(prefix);
      if (prefix === "stats") void showStats(); else void showAnalysis();
    });
  }
  $("homeSeason").addEventListener("change", homeBars);
  $("analysisRefresh").addEventListener("click", showAnalysis);
  $("statsRefresh").addEventListener("click", showStats);
  $("historySearch").addEventListener("input", renderHistory);
  $("historyType").addEventListener("change", renderHistory);
  $("historySort").addEventListener("change", renderHistory);
  $("exportHistory").addEventListener("click", exportHistory);
  $("clearHistory").addEventListener("click", () => {
    $("historySearch").value = "";
    $("historyType").value = "all";
    $("historySort").value = "new";
    renderHistory();
  });
  $("openXgGuide").addEventListener("click", openGuide);
  $("footerXgGuide").addEventListener("click", event => { event.preventDefault(); openGuide(); });
  $("closeModal").addEventListener("click", closeModal);
  $("modalCover").addEventListener("click", event => { if (event.target === $("modalCover")) closeModal(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeModal(); });

  const tooltip = $("chartTooltip");
  document.addEventListener("pointerover", event => {
    const item = event.target.closest("[data-tip]");
    if (!item) return;
    tooltip.textContent = item.dataset.tip;
    tooltip.classList.add("show");
  });
  document.addEventListener("pointermove", event => {
    tooltip.style.left = Math.max(0, Math.min(window.innerWidth - 175, event.clientX + 12)) + "px";
    tooltip.style.top = Math.max(6, event.clientY - 48) + "px";
  });
  document.addEventListener("pointerout", event => {
    if (event.target.closest("[data-tip]")) tooltip.classList.remove("show");
  });
  window.addEventListener("hashchange", navigate);
}

async function initialize() {
  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = "/assets/phase9.css";
  document.head.append(stylesheet);
  $("predictionOutput").setAttribute("aria-live", "polite");
  $("exportHistory").textContent = "↓ Export filtered CSV";
  bind();
  resetPrediction("fixture");
  navigate();
  loading("homeFixtures");
  loading("presetFixtures");
  try {
    [state.config, state.teams] = await Promise.all([api.bootstrap(), api.teams()]);
    $("bridgeModeText").textContent = state.config.label;
    setSelectors();
    navigate();
    const [fixtures, freshness, history] = await Promise.allSettled([
      api.fixtures({upcoming: true, season: state.config.current_season}), api.dataStatus(), api.history(),
    ]);
    if (history.status === "fulfilled") {
      state.history = history.value;
      state.hasHistory = true;
    }
    if (fixtures.status === "fulfilled") {
      state.fixtures = fixtures.value;
      renderFixtures();
    } else {
      notice("homeFixtures", fixtures.reason.message, true);
      notice("presetFixtures", fixtures.reason.message, true);
    }
    if (freshness.status === "fulfilled") {
      const data = freshness.value;
      $("cutoffHero").textContent = data.latest_verified_completed_date || "—";
      $("totalMatches").textContent = data.verified_completed.toLocaleString("en-GB");
      $("fixtureDataStatus").textContent = `Schedule review · ${statusName(data.schedule_freshness)} · ${data.snapshot_version}`;
    } else {
      $("fixtureDataStatus").textContent = "Schedule review status unavailable.";
    }
    void homeBars();
  } catch (error) {
    $("bridgeModeText").textContent = "SERVICE UNAVAILABLE";
    for (const id of ["homeFixtures", "presetFixtures", "homeTeamBars", "analysisOutput", "statsOutput",
      "historyTable", "featuresList"]) notice(id, error.message, true);
  } finally {
    for (const id of ["homeFixtures", "presetFixtures"]) $(id).removeAttribute("aria-busy");
  }
}

void initialize();
