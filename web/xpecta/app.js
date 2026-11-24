import {api} from "./api.js";
import {fixturePage} from "./fixtures.js";
import {$, comparison, csvText, fixtureCard, historyDetails, historyTable, leaderboard, matchAnalysis,
  message, cardForecast, prediction, renderModel, seasonName, simulationDetails, simulationResult, teamStats, UTC_LABEL} from "./view.js";
import {teamPicker} from "./team-picker.js";
import {simulationHistory, saveSimulation, validSimulation} from "./simulations.js";

const pages = {
  home: "Overview", predict: "Prediction", analysis: "Match Analysis",
  stats: "Team Statistics", history: "Prediction History", model: "AI Model",
};
const state = {
  page: "home", tab: "fixture", fixture: null, config: null, teams: [], fixtures: [],
  history: [], historyStatus: "loading", analysisOrigin: null, discoveryPage: 1, catalogueReady: false, data: null,
};
const pending = new Map();
let scheduleTimer;
let statusReceivedAt;
const cardBatches = new Map();
const pickers = {};
let historyPending;
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
    addOptions(id, state.teams.map(team => [team.id, team.name]), preferred);
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
    if (!state.data || row.history_snapshot_version !== state.config.snapshot_version
        || row.history_database_sha256 !== state.data.database_sha256 || row.model_version !== state.config.model_version
        || row.dataset_kind !== (state.config.mode === "SYNTHETIC_DEMO" ? "synthetic" : "real")) continue;
    const key = row.canonical_fixture_key;
    if (!latest.has(key) || latest.get(key).forecast_revision < row.forecast_revision) latest.set(key, row);
  }
  return latest;
}

function catalogueTime() {
  if (!state.data) return new Date().toISOString();
  if (state.config.mode !== "REAL_RESEARCH") return state.data.evaluated_at_utc;
  return new Date(Date.parse(state.data.evaluated_at_utc) + performance.now() - statusReceivedAt).toISOString();
}

function stopCards(region) {
  const batch = cardBatches.get(region);
  if (!batch) return;
  batch.controller.abort();
  batch.timers.forEach(timer => clearTimeout(timer));
  cardBatches.delete(region);
}

function matchesForecastContext(fixture, preview) {
  return preview.canonical_fixture_key === fixture.canonical_fixture_key &&
    preview.history_snapshot_version === state.config.snapshot_version &&
    preview.model_version === state.config.model_version &&
    preview.dataset_kind === (state.config.mode === "SYNTHETIC_DEMO" ? "synthetic" : "real");
}

async function loadCardForecast(fixture, slot, batch) {
  const key = fixture.canonical_fixture_key;
  const signal = batch.controller.signal;
  const render = result => {
    if (cardBatches.get(batch.region) === batch && batch.data === state.data) slot.innerHTML = cardForecast(result);
  };
  try {
    const {data} = batch;
    if (!data || data.mode !== state.config.mode || data.snapshot_version !== state.config.snapshot_version) {
      throw new Error("The active snapshot could not be verified.");
    }
    const eligibility = await api.eligibility(key, signal);
    if (signal.aborted) return;
    const {eligibility_status: status, target, fixture_reviewed_at_utc: reviewed, history_cutoff: cutoff} = eligibility;
    if (eligibility.canonical_fixture_key !== key || eligibility.snapshot_version !== data.snapshot_version) {
      throw new Error("The fixture context changed.");
    }
    if (status === "WAITING_DATA" || status === "UNAVAILABLE") {
      render({status});
      return;
    }

    // The preview response omits schedule evidence. Keep the checked fixture's own expiry.
    const kickoff = Date.parse(fixture.kickoff_utc);
    const freshnessEnds = Date.parse(reviewed) + data.schedule_max_age_hours * 3600000;
    // The eligibility policy includes the final millisecond of the schedule freshness window.
    const expires = Math.min(kickoff, freshnessEnds + 1, Date.parse(cutoff) + 86400000);
    if (!Number.isFinite(expires) || target?.canonical_fixture_key !== key || Date.parse(target.kickoff_utc) !== kickoff) {
      throw new Error("Forecast timing could not be verified.");
    }
    const expire = () => render({status: Date.parse(catalogueTime()) >= kickoff ? "UNAVAILABLE" : "WAITING_DATA"});
    if (Date.parse(catalogueTime()) >= expires) {
      expire();
      return;
    }

    const result = await api.preview(key, signal);
    if (signal.aborted) return;
    if (!result.preview) {
      if (result.eligibility.canonical_fixture_key !== key || result.eligibility.snapshot_version !== data.snapshot_version) {
        throw new Error("The fixture context changed.");
      }
      render(result);
      return;
    }
    const {preview} = result;
    const generated = Date.parse(preview.generated_at_utc);
    if (!matchesForecastContext(fixture, preview) || preview.history_database_sha256 !== data.database_sha256 ||
        !Number.isFinite(generated)) {
      throw new Error("The forecast context changed.");
    }
    const remaining = expires - Math.max(generated, Date.parse(catalogueTime()));
    if (preview.history_cutoff !== cutoff || remaining <= 0) {
      expire();
      return;
    }
    render(result);
    if (state.config.mode === "REAL_RESEARCH") batch.timers.push(setTimeout(expire, remaining));
  } catch {
    if (!signal.aborted) render({status: "FORECAST_ERROR"});
  }
}

function renderCardBatch(region, fixtures, empty, published = new Map()) {
  const keys = fixtures.map(row => row.canonical_fixture_key).join("|");
  const publishedIds = fixtures.map(row => row.observed_status === "completed" ?
    published.get(row.canonical_fixture_key)?.forecast_id ?? "" : "").join("|");
  const previous = cardBatches.get(region);
  if (previous?.keys === keys && previous.data === state.data && previous.publishedIds === publishedIds) return;
  stopCards(region);
  const batch = {keys, publishedIds, region, data: state.data, controller: new AbortController(), timers: []};
  cardBatches.set(region, batch);
  if (!fixtures.length) {
    renderHere(region, message(empty));
    return;
  }
  const cards = fixtures.map(row => {
    if (row.observed_status === "scheduled") return fixtureCard(row);
    const forecast = row.observed_status === "completed" ? published.get(row.canonical_fixture_key) : null;
    return fixtureCard(row, forecast ? {status: "PUBLISHED", preview: forecast} : {status: "UNAVAILABLE"});
  }).join("");
  renderHere(region, region === "homeFixtures" ? cards : `<div class="match-grid mt20">${cards}</div>`);
  const slots = $(region).querySelectorAll(".fixture-xg");
  const queue = fixtures.map((row, index) => [row, slots[index]]).filter(([row]) => row.observed_status === "scheduled");
  async function worker() {
    while (queue.length && !batch.controller.signal.aborted) await loadCardForecast(...queue.shift(), batch);
  }
  const workers = Math.min(4, queue.length);
  for (let index = 0; index < workers; index++) void worker();
}

function renderOverview(time = catalogueTime()) {
  if (state.page !== "home" || !state.catalogueReady) return;
  const fixtures = fixturePage(state.fixtures, {status: "upcoming"}, 1, time).items.slice(0, 6);
  renderCardBatch("homeFixtures", fixtures, "No upcoming fixtures are listed in this snapshot.");
}

function renderFixtures(time = catalogueTime()) {
  renderOverview(time);
  renderDiscovery(publishedByKey(), time);
}

function renderDiscovery(latest = publishedByKey(), time = catalogueTime()) {
  if (!state.catalogueReady || state.page !== "predict" || state.tab !== "fixture" || state.fixture) return;
  const filters = Object.fromEntries(new FormData($("fixtureFilters")));
  filters.team1 = pickers.fixtureTeam1.value();
  filters.team2 = pickers.fixtureTeam2.value();
  const found = fixturePage(state.fixtures, filters, state.discoveryPage, time);
  state.discoveryPage = found.page;
  $("fixtureResults").textContent = found.total
    ? `${found.first}–${found.last} of ${found.total} matches · ${state.fixtures.length} in season`
    : `0 matches · ${state.fixtures.length} in season`;
  $("fixturePage").textContent = `Page ${found.page} of ${found.pages}`;
  $("fixturePrevious").disabled = found.page === 1;
  $("fixtureNext").disabled = found.page === found.pages;
  if (found.invalidRange || found.invalidTeams) {
    stopCards("presetFixtures");
    notice("presetFixtures", found.invalidTeams ? "Select two different teams to filter fixtures." :
      `The end date (${UTC_LABEL}) must be on or after the start date.`, true);
  } else {
    renderCardBatch("presetFixtures", found.items, "No fixtures match these filters.", latest);
  }
}

function installDiscovery() {
  $("fixturePick").querySelector("h2").textContent = "FIND FIXTURES";
  $("presetFixtures").insertAdjacentHTML("beforebegin", `
    <form id="fixtureFilters" class="card fixture-filters mt20" aria-label="Filter fixture catalogue">
      <div class="field"><label for="fixtureTeam1">Team 1</label><input id="fixtureTeam1"></div>
      <div class="field"><label for="fixtureTeam2">Team 2</label><input id="fixtureTeam2"></div>
      <div class="field"><label for="fixtureStart">From (${UTC_LABEL})</label><input id="fixtureStart" name="start" type="date"></div>
      <div class="field"><label for="fixtureEnd">To (${UTC_LABEL})</label><input id="fixtureEnd" name="end" type="date"></div>
      <div class="field"><label for="fixtureStatus">Catalogue status</label><select id="fixtureStatus" name="status">
        <option value="upcoming">Upcoming</option><option value="">All listed</option><option value="scheduled">Scheduled</option>
        <option value="completed">Completed</option><option value="live">Live in snapshot</option>
        <option value="postponed">Postponed</option><option value="cancelled">Cancelled</option><option value="unverified">Unverified</option>
      </select></div>
      <button class="btn btn-outline" type="reset">Clear filters</button>
    </form>
    <p id="fixtureResults" class="subtext mt20" role="status" tabindex="-1"></p>`);
  $("presetFixtures").insertAdjacentHTML("afterend", `
    <nav class="fixture-pagination mt20" aria-label="Fixture pages">
      <button class="btn btn-outline btn-sm" id="fixturePrevious" disabled>Previous</button>
      <span id="fixturePage" class="chip"></span>
      <button class="btn btn-outline btn-sm" id="fixtureNext" disabled>Next</button>
    </nav>`);
  $("homeFixtures").insertAdjacentHTML("beforebegin", '<p id="homeSchedule" class="indicator"></p>');
  $("fixtureFilters").addEventListener("submit", event => event.preventDefault());
  const apply = () => {
    state.discoveryPage = 1;
    renderDiscovery();
  };
  pickers.fixtureTeam1 = teamPicker($("fixtureTeam1"), "Team 1", apply);
  pickers.fixtureTeam2 = teamPicker($("fixtureTeam2"), "Team 2", apply);
  $("fixtureFilters").addEventListener("input", apply);
  $("fixtureFilters").addEventListener("reset", () => {
    pickers.fixtureTeam1.clear();
    pickers.fixtureTeam2.clear();
    setTimeout(apply, 0);
  });
  for (const [id, direction] of [["fixturePrevious", -1], ["fixtureNext", 1]]) {
    $(id).addEventListener("click", () => {
      state.discoveryPage += direction;
      renderDiscovery();
      $("fixtureResults").focus();
    });
  }
}

function renderFreshness(data) {
  const wording = {
    VERIFIED: "Recent schedule evidence",
    PARTIAL: "Some fixtures lack recent schedule evidence",
    UNVERIFIED: data?.expired_review_upcoming_fixtures ? "Schedule evidence is stale" : "Schedule evidence is unverified",
    NO_UPCOMING: "No upcoming fixtures in the snapshot",
    HISTORICAL_ONLY: "Historical reference",
  };
  const label = wording[data?.schedule_freshness] ?? "Schedule status unavailable";
  const snapshotLabel = state.config?.mode === "SYNTHETIC_DEMO" ? "Synthetic test snapshot" : "Research snapshot available";
  $("homeSchedule").textContent = data ? `${snapshotLabel} · ${label}` : label;
}

function showFreshness(data) {
  clearTimeout(scheduleTimer);
  state.data = data;
  statusReceivedAt = performance.now();
  renderFreshness(data);
  if (!data || state.config.mode !== "REAL_RESEARCH") return;
  const serverTime = Date.parse(data.evaluated_at_utc);
  const start = statusReceivedAt;
  const expiries = data.schedule_evidence.filter(group => group.status === "VALID")
    .map(group => Date.parse(group.expires_at_utc)).sort((a, b) => a - b);

  function watch(now) {
    const next = expiries.find(expiry => expiry >= now);
    if (next === undefined) return;
    scheduleTimer = setTimeout(async () => {
      const effectiveTime = Math.max(next + 1, serverTime + performance.now() - start);
      let newlyExpired = 0;
      const evidence = data.schedule_evidence.map(group => {
        if (group.status !== "VALID" || Date.parse(group.expires_at_utc) >= effectiveTime) return group;
        newlyExpired += group.fixtures;
        return {...group, status: "EXPIRED"};
      });
      const recent = data.recent_review_upcoming_fixtures - newlyExpired;
      renderFreshness({...data, schedule_evidence: evidence, recent_review_upcoming_fixtures: recent,
        expired_review_upcoming_fixtures: data.expired_review_upcoming_fixtures + newlyExpired,
        schedule_freshness: recent ? "PARTIAL" : "UNVERIFIED"});
      if (state.catalogueReady) renderFixtures(new Date(effectiveTime).toISOString());
      watch(effectiveTime);
      try {
        const latest = await api.dataStatus();
        if (state.data === data && latest.snapshot_version === data.snapshot_version &&
            Date.parse(latest.evaluated_at_utc) > next &&
            Date.parse(latest.evaluated_at_utc) >= serverTime + performance.now() - start) {
          showFreshness(latest);
          if (state.catalogueReady) renderFixtures();
        }
      } catch {
        // The recorded expiry still applies if localhost does not respond.
      }
    }, next - now + 1);
  }
  watch(serverTime);
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
  if (tab === "fixture") renderDiscovery();
  else stopCards("presetFixtures");
}

function showForecast(fixture, result) {
  const preview = result.preview;
  if (preview && !matchesForecastContext(fixture, preview)) {
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
  const preview = display("predictionOutput", () => api.preview(fixture.canonical_fixture_key),
    result => showForecast(fixture, result), () => fixture);
  $("predictionOutput").focus({preventScroll: true});
  await preview;
}

function selectFixture(key) {
  const fixture = state.fixtures.find(row => row.canonical_fixture_key === key);
  if (!fixture) return;
  stopCards("homeFixtures");
  stopCards("presetFixtures");
  state.tab = "fixture";
  state.fixture = fixture;
  state.analysisOrigin = null;
  updatePredictTab();
  go("predict");
  void forecastFor(fixture);
}

async function customPrediction() {
  if (!state.config) return;
  const button = $("runPrediction");
  const home = $("customHome").value;
  const away = $("customAway").value;
  state.fixture = null;
  $("predictionOutput").hidden = false;
  if (home === away) {
    cancel("predictionOutput");
    notice("predictionOutput", "Select two different teams to simulate.", true);
    return;
  }
  button.disabled = true;
  try {
    await display("predictionOutput", () => api.simulate(home, away), result => {
      const kind = simulationKind();
      if (!validSimulation(result, kind) || result.home_team !== home || result.away_team !== away ||
          result.history_snapshot_version !== state.config.snapshot_version || result.model_version !== state.config.model_version) {
        throw new Error("The simulation context changed. Reload XPECTA and try again.");
      }
      state.fixture = result;
      renderHere("predictionOutput", simulationResult(result));
      try {
        saveSimulation(result, kind);
      } catch {
        toast("The simulation ran, but local history could not save it.");
      }
    });
  } finally {
    button.disabled = false;
  }
}

function showAnalysis() {
  if (!state.config) return;
  const home = $("analysisHome").value;
  const away = $("analysisAway").value;
  if (home === away) {
    cancel("analysisOutput");
    notice("analysisOutput", "Select two different teams to analyze.", true);
    return;
  }
  return display("analysisOutput", () => api.analysis({
    home, away,
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

const simulationKind = () => state.config?.mode === "SYNTHETIC_DEMO" ? "synthetic" : "real";

function visibleHistory() {
  const team = pickers.historySearch.value();
  const recordType = $("historyRecordType").value;
  const stage = $("historyType").value;
  const direction = $("historySort").value === "old" ? 1 : -1;
  const {rows: simulations, warning} = simulationHistory(simulationKind());
  const all = [...state.history.map(row => ({...row, record_type: "OFFICIAL_MATCH_FORECAST"})), ...simulations];
  const rows = all.filter(row => (recordType === "all" || recordType === row.record_type) &&
    (stage === "all" || stage === row.forecast_stage) && (!team || [row.home_team, row.away_team].includes(team)))
    .sort((a, b) => direction * (Date.parse(a.generated_at_utc) - Date.parse(b.generated_at_utc) ||
      (a.forecast_revision ?? 0) - (b.forecast_revision ?? 0)));
  return {rows, total: all.length, warning};
}

function renderHistory() {
  const {rows, total, warning} = visibleHistory();
  const showOfficial = $("historyRecordType").value !== "CUSTOM_SIMULATION";
  const showSimulations = $("historyRecordType").value !== "OFFICIAL_MATCH_FORECAST" && $("historyType").value === "all";
  const messages = [showSimulations && warning, showOfficial && state.historyStatus === "loading" && "Loading official forecasts…",
    showOfficial && state.historyStatus === "error" && "Official forecasts are unavailable."].filter(Boolean);
  $("historyCount").textContent = `${rows.length} / ${total} records`;
  $("historyNotice").textContent = messages.join(" ");
  renderHere("historyTable", historyTable(rows, total, showOfficial && state.historyStatus !== "ready"));
}

async function showHistory() {
  if (historyPending) return;
  state.historyStatus = "loading";
  renderHistory();
  historyPending = api.history();
  try {
    state.history = await historyPending;
    state.historyStatus = "ready";
  } catch {
    state.historyStatus = "error";
  } finally {
    historyPending = null;
    renderHistory();
    renderFixtures();
  }
}

function exportHistory() {
  const {rows} = visibleHistory();
  if (!rows.length) return toast("No matching records to export.");
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

function showSimulation(id) {
  const row = simulationHistory(simulationKind()).rows.find(record => record.simulation_id === id);
  if (!row) return toast("This simulation is unavailable.");
  modal("CUSTOM SIMULATION");
  renderHere("modalBody", simulationDetails(row));
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
  if (page === "home") renderOverview();
  else stopCards("homeFixtures");
  if (page !== "predict") stopCards("presetFixtures");
  if (previousPage === "home" && page === "predict" && state.fixture) {
    $("predictionOutput").focus({preventScroll: true});
  }
  if (previousPage === "predict" && page !== "predict") {
    state.fixture = null;
    updatePredictTab();
  }
  if (previousPage === "analysis" && page !== "analysis") {
    if (page === "predict" && state.analysisOrigin) restorePredictionFromAnalysis();
    else state.analysisOrigin = null;
  }
  if (page === "predict") renderDiscovery();
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
  const sameFixture = origin?.fixture.canonical_fixture_key && origin.fixture.home_team === home && origin.fixture.away_team === away &&
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
    const button = event.target.closest("[data-page],[data-jump],[data-fixture],[data-pred-mode],[data-history],[data-simulation],[data-compare],[data-guide],[data-analyze],[data-to-custom],[data-retry-forecast],[data-back-to-fixtures]");
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
    else if (button.dataset.simulation) showSimulation(button.dataset.simulation);
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
    const key = state.fixture?.canonical_fixture_key;
    resetPrediction("fixture");
    const prior = [...$("presetFixtures").querySelectorAll("[data-fixture]")].find(button => button.dataset.fixture === key);
    (prior || $("fixtureResults")).focus();
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
  for (const id of ["analysisHome", "analysisAway", "analysisWindow"]) $(id).addEventListener("change", showAnalysis);
  $("statsRefresh").addEventListener("click", showStats);
  $("historyRecordType").addEventListener("change", () => {
    const simulations = $("historyRecordType").value === "CUSTOM_SIMULATION";
    $("historyType").disabled = simulations;
    if (simulations) $("historyType").value = "all";
    renderHistory();
  });
  $("historyType").addEventListener("change", renderHistory);
  $("historySort").addEventListener("change", renderHistory);
  $("exportHistory").addEventListener("click", exportHistory);
  $("clearHistory").addEventListener("click", () => {
    pickers.historySearch.clear();
    $("historyRecordType").value = "all";
    $("historyType").value = "all";
    $("historyType").disabled = false;
    $("historySort").value = "new";
    renderHistory();
  });
  window.addEventListener("storage", event => {
    if (state.page === "history" && (event.key === null || event.key.startsWith("xpecta.simulation."))) renderHistory();
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
  $("predictionOutput").tabIndex = -1;
  $("exportHistory").textContent = "↓ Export filtered CSV";
  installDiscovery();
  pickers.historySearch = teamPicker($("historySearch"), "Search teams", renderHistory);
  bind();
  resetPrediction("fixture");
  navigate();
  loading("homeFixtures");
  loading("presetFixtures");
  try {
    [state.config, state.teams] = await Promise.all([api.bootstrap(), api.teams()]);
    $("bridgeModeText").textContent = state.config.label;
    setSelectors();
    const current = state.teams.filter(team => team.seasons.includes(state.config.current_season));
    pickers.fixtureTeam1.setTeams(current);
    pickers.fixtureTeam2.setTeams(current);
    pickers.historySearch.setTeams(state.teams);
    navigate();
    void showHistory();
    const [fixtures, freshness] = await Promise.allSettled([
      api.fixtures({season: state.config.current_season}), api.dataStatus(),
    ]);
    if (freshness.status === "fulfilled") {
      const data = freshness.value;
      $("totalMatches").textContent = data.verified_completed.toLocaleString("en-GB");
      showFreshness(data);
    } else {
      showFreshness(null);
    }
    if (fixtures.status === "fulfilled") {
      state.fixtures = fixtures.value;
      state.catalogueReady = true;
      renderFixtures();
    } else {
      notice("homeFixtures", fixtures.reason.message, true);
      notice("presetFixtures", fixtures.reason.message, true);
    }
    void homeBars();
  } catch (error) {
    $("bridgeModeText").textContent = "SERVICE UNAVAILABLE";
    showFreshness(null);
    for (const id of ["homeFixtures", "presetFixtures", "homeTeamBars", "analysisOutput", "statsOutput",
      "historyTable", "featuresList"]) notice(id, error.message, true);
  } finally {
    for (const id of ["homeFixtures", "presetFixtures"]) $(id).removeAttribute("aria-busy");
  }
}

void initialize();
