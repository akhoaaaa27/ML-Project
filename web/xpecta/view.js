// Presentation only. Escape API text at every HTML interpolation boundary.
export const $ = id => document.getElementById(id);
export const esc = value => String(value ?? "").replace(/[&<>"']/g, character =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[character]);
export const number = value => Number.isFinite(value) ? value.toFixed(2) : "—";
export const seasonName = year => `${year}/${String(Number(year) + 1).slice(-2)}`;
export const statusName = value => String(value ?? "").replaceAll("_", " ");
const day = value => value ? esc(value.slice(0, 10)) : "—";
const time = value => value ? `${day(value)} ${esc(value.slice(11, 16))} UTC` : "—";
const signed = value => (value > 0 ? "+" : "") + number(value);
const width = (value, max) => Number.isFinite(value) ? Math.max(0, Math.min(100, value / max * 100)) : 0;
const logos = new Map([...$("clubAssets").content.querySelectorAll("img")].map(image => [image.dataset.team, image.src]));
const labels = {FBref_frozen_snapshot: "FBref", Understat_shot_events: "Understat shot events"};

function crest(team, size = "") {
  const source = logos.get(team);
  const initials = team.split(/\s+/).map(word => word[0]).slice(0, 3).join("").toUpperCase();
  return source
    ? `<span class="crest official ${size}" title="${esc(team)}"><img src="${esc(source)}" alt="" decoding="async"></span>`
    : `<span class="crest ${size}" title="${esc(team)}">${esc(initials)}</span>`;
}

export const message = (text, error = false) =>
  `<div class="${error ? "error-box" : "empty"}" role="${error ? "alert" : "status"}">${esc(text)}</div>`;

function metric(title, value, note = "") {
  return `<div class="metric"><div class="mini-label">${esc(title)}</div><div class="value">${esc(value)}</div><div class="caption">${esc(note)}</div></div>`;
}

function bars(rows, max = Math.max(1, ...rows.map(([, value]) => value ?? 0)) * 1.15) {
  return rows.map(([label, value], i) => `<div class="simple-bar ${i % 2 ? "orange" : ""}">
    <div class="title"><span>${esc(label)}</span><span>${number(value)}</span></div>
    <div class="track"><div class="fill" style="width:${width(value, max)}%"></div></div></div>`).join("");
}

function xgSources(counts) {
  const entries = Object.entries(counts);
  return entries.length ? entries.map(([source, count]) => `${labels[source] || source} (${count})`).join(" · ") : "No observed source";
}

export function fixtureCard(fixture, forecast) {
  const key = esc(fixture.canonical_fixture_key);
  return `<article class="fixture-card">
    <div class="fixture-top"><span class="chip">${esc(seasonName(fixture.season))}</span><span>${fixture.kickoff_utc ? time(fixture.kickoff_utc) : day(fixture.match_date)}</span></div>
    <div class="fixture-teams"><div class="fixture-team">${crest(fixture.home_team)}<strong>${esc(fixture.home_team)}</strong></div>
      <span class="fixture-vs">VS</span><div class="fixture-team">${crest(fixture.away_team)}<strong>${esc(fixture.away_team)}</strong></div></div>
    <div class="fixture-bottom"><div class="fixture-xg">${forecast ? `${number(forecast.home_xg)} <span class="fixture-xg-vs">VS</span> ${number(forecast.away_xg)}` : "—"}
      <small>${forecast ? "Published xG" : "Availability on selection"}</small></div>
      <button class="btn btn-green btn-sm" data-fixture="${key}">VIEW PREDICTION ↗</button></div>
    </article>`;
}

export function presetFixtures(fixtures, published) {
  return `<section class="preset-round mt20">
    <div class="top-small"><h3 class="card-title">Upcoming catalogue</h3><span class="chip">${fixtures.length} fixtures</span></div>
    <div class="match-grid">${fixtures.map(fixture => fixtureCard(fixture, published.get(fixture.canonical_fixture_key))).join("")}</div>
    </section>`;
}

export function leaderboard(stats) {
  const rank = stats.filter(row => row.overall.observed_xg_fixtures >= 4)
    .sort((a, b) => b.overall.mean_xg - a.overall.mean_xg).slice(0, 7);
  const max = Math.max(2.8, ...rank.map(row => row.overall.mean_xg));
  if (!rank.length) return message("No team has four observed xG matches in this season.");
  return rank.map(({team, overall}) => `<div class="bar-row" title="${esc(xgSources(overall.xg_sources))}">
    <div class="bar-label">${crest(team, "tiny")}<span>${esc(team)}</span></div>
    <div class="bar-track"><div class="bar-fill" style="width:${width(overall.mean_xg, max)}%"></div></div>
    <div class="bar-number">${number(overall.mean_xg)}</div></div>`).join("") +
    `<p class="tiny muted">Sources by team · ${rank.map(row => `${esc(row.team)}: ${esc(xgSources(row.overall.xg_sources))}`).join(" · ")}</p>`;
}

function panels(home, away, forecast) {
  return `<div class="forecast-output">${[["home", home], ["away", away]].map(([side, team]) =>
    `<div class="forecast-panel ${side === "away" ? "away" : ""}">
      <div class="forecast-team-name">${crest(team, "sm")}<div>${esc(team)}<div class="mini-label">${side.toUpperCase()} TEAM</div></div></div>
      <div class="forecast-big" data-xg="${side}">${number(forecast[side + "_xg"])}</div><div class="mini-label">PREDICTED xG</div></div>`).join("")}</div>`;
}

export function prediction(fixture, result) {
  const live = fixture.observed_status === "live";
  const title = `<div class="title-row"><div><div class="eyebrow">PREDICTION RESULTS · RESEARCH</div>
    <h2 class="section-title">${esc(fixture.home_team.toUpperCase())} <span class="detail-vs">VS</span> ${esc(fixture.away_team.toUpperCase())}</h2>
    <p class="subtext">${seasonName(fixture.season)} · ${fixture.kickoff_utc ? time(fixture.kickoff_utc) : day(fixture.match_date)}
    ${live ? ' · <strong data-observed-status="live">LIVE</strong>' : ""}</p></div>
    <span class="chip orange" data-readiness>${esc(statusName(result.status))}</span></div>`;
  const forecast = result.preview;
  if (!forecast) {
    const reason = result.eligibility?.reason || result.error?.code || "No eligible prediction";
    return title + message(statusName(reason), true);
  }
  const [home, away] = [fixture.home_team, fixture.away_team];
  return title + panels(home, away, forecast) +
    `<div class="card mt20"><div class="top-small"><h3 class="card-title">PREDICTED xG COMPARISON</h3><span class="chip orange">PREVIEW</span></div>
      ${bars([[home, forecast.home_xg], [away, forecast.away_xg]])}</div>
    <div class="grid2 mt20"><div class="card"><div class="mini-label">COMBINED PREDICTED xG</div><div class="prediction-metric">${number(forecast.home_xg + forecast.away_xg)}</div></div>
      <div class="card"><div class="mini-label">PREDICTED xG DIFFERENCE</div><div class="prediction-metric">${signed(forecast.home_xg - forecast.away_xg)}</div><p class="card-desc">Home xG minus away xG</p></div></div>
    <div class="card mt20"><h3 class="card-title">PREDICTION SUMMARY</h3><p class="subtext">${esc(forecast.source_notice)}</p></div>
    <div class="card mt20"><div class="top-small"><h3 class="card-title">PREDICTION INFORMATION</h3><button class="help-icon" data-guide>?</button></div>
      <div class="grid3 mt20"><div><div class="mini-label">History cutoff</div><p>${day(forecast.history_cutoff)}</p></div>
        <div><div class="mini-label">Model and snapshot</div><p>LR ${esc(forecast.model_version)} · ${esc(forecast.history_snapshot_version)}</p></div>
        <div><div class="mini-label">Generated</div><p>${time(forecast.generated_at_utc)}</p></div></div></div>
    <div class="mt20 matchup-actions"><button class="btn btn-green" data-analyze>VIEW MATCH ANALYSIS ↗</button>
      <button class="btn btn-outline" data-jump="history">VIEW PREDICTION HISTORY ↗</button></div>`;
}

function trend(series, labels) {
  const [w, h, left, top, right, bottom] = [580, 238, 39, 18, 18, 32];
  const scale = Math.max(1, ...series.flatMap(row => row.values).filter(Number.isFinite)) * 1.18;
  const slots = Math.max(2, labels.length);
  const x = i => left + i * (w - left - right) / (slots - 1);
  const y = value => h - bottom - (value / scale) * (h - top - bottom);
  const grid = Array.from({length: 5}, (_, i) => {
    const value = i * scale / 4;
    return `<line class="grid-line" x1="${left}" y1="${y(value)}" x2="${w - right}" y2="${y(value)}"/>
      <text x="${left - 7}" y="${y(value) + 3}" text-anchor="end">${number(value)}</text>`;
  }).join("");
  const ticks = labels.map((label, i) => {
    if (i !== 0 && i !== labels.length - 1 && i % Math.ceil(slots / 6)) return "";
    return `<text x="${x(i)}" y="${h - 10}" text-anchor="middle">${esc(label)}</text>`;
  }).join("");
  const plots = series.map(({name, values}, side) => {
    const color = side ? "#ff5f25" : "#2f8601";
    let path = "";
    let points = "";
    values.forEach((value, i) => {
      if (!Number.isFinite(value)) return;
      path += `${i > 0 && Number.isFinite(values[i - 1]) ? "L" : "M"}${x(i)},${y(value)} `;
      points += `<circle class="point" cx="${x(i)}" cy="${y(value)}" r="4" fill="${color}" stroke="#fff" stroke-width="2" data-tip="${esc(name)} · ${esc(labels[i])}: ${number(value)}"/>`;
    });
    return `<path d="${path}" fill="none" stroke="${color}" stroke-width="3"/>${points}`;
  }).join("");
  return `<svg viewBox="0 0 ${w} ${h}" class="chart-svg" role="img" aria-label="Historical xG trend">${grid}${ticks}${plots}</svg>
    <div class="chart-legend">${series.map(({name}, i) => `<span><i class="legend-dot ${i ? "orange" : ""}"></i>${esc(name)}</span>`).join("")}</div>`;
}

function historyNote(data) {
  return `${statusName(data.status)} · ${data.overall.observed_xg_fixtures}/${data.overall.verified_fixtures} with xG · ${xgSources(data.overall.xg_sources)}`;
}

function venue(team, title, row, role) {
  return `<div class="location-box venue-identity ${role}">
    <div class="venue-crest">${crest(team)}</div><div class="venue-content">
      <div class="compare-team venue-heading"><strong>${esc(team)}<br><span class="mini-label">${esc(title)}</span></strong></div>
      <div class="stat-value-xl venue-xg">${number(row.mean_xg)}</div>
      <div class="tiny muted">Average xG · ${row.observed_xg_fixtures}/${row.verified_fixtures} matches</div>
      <div class="venue-detail"><span>Average xGA</span><strong>${number(row.mean_xga)}</strong>
        <span>Win rate</span><strong>${row.verified_fixtures ? number(row.wins / row.verified_fixtures * 100) + "%" : "—"}</strong></div></div></div>`;
}

export function teamStats(main, comparison) {
  const {team, season, overall} = main;
  const rows = main.trend;
  const observed = rows.filter(row => Number.isFinite(row.xg) && Number.isFinite(row.xga));
  const goalsMinusXg = observed.length ? observed.reduce((sum, row) => sum + row.goals_for - row.xg, 0) : null;
  return `<div class="card mint"><div class="compare-head"><div class="compare-team">${crest(team)}
      <div><h2 class="section-title" style="font-size:31px">${esc(team.toUpperCase())}</h2><span class="mini-label">LA LIGA · ${seasonName(season)}</span></div></div></div>
      <p class="card-desc">${esc(historyNote(main))}</p></div>
    <div class="metric-grid mt20">${metric("MATCHES", overall.verified_fixtures, "Verified completed")}
      ${metric("WIN / DRAW / LOSS", `${overall.wins}/${overall.draws}/${overall.losses}`)}
      ${metric("POINTS", overall.wins * 3 + overall.draws)}${metric("GOALS − xG", signed(goalsMinusXg), "Matches with observed xG")}</div>
    <div class="grid2 mt20"><div class="card"><h3 class="card-title">AVERAGE METRICS</h3>
      ${bars([["xG created", overall.mean_xg], ["xGA conceded", overall.mean_xga],
      ["Goals scored", overall.verified_fixtures ? overall.goals_for / overall.verified_fixtures : null],
      ["Goals conceded", overall.verified_fixtures ? overall.goals_against / overall.verified_fixtures : null]])}</div>
      <div class="card"><h3 class="card-title">xG TREND</h3>${rows.length ? trend([
        {name: "xG", values: rows.map(item => item.xg)}, {name: "xGA", values: rows.map(item => item.xga)}
      ], rows.map(item => item.date.slice(5))) : message("No matches in the selected season.")}</div></div>
    <div class="grid2 mt20"><div class="card"><h3 class="card-title">HOME AND AWAY</h3><div class="location-grid mt20">
      ${venue(team, "HOME", main.home, "venue-home")}${venue(team, "AWAY", main.away, "venue-away")}</div></div>
      <div class="card"><h3 class="card-title">TEAM COMPARISON · ${seasonName(season)}</h3>
        ${comparison ? `<p class="card-desc">${esc(historyNote(comparison))}</p>${bars([
          [team + " · xG", overall.mean_xg], [comparison.team + " · xG", comparison.overall.mean_xg],
          [team + " · xGA", overall.mean_xga], [comparison.team + " · xGA", comparison.overall.mean_xga]
        ])}` : message("The comparison statistics are unavailable.")}</div></div>`;
}

export function matchAnalysis(data) {
  const {home, away, head_to_head: h2h} = data;
  const side = (row, role) => `<div class="compare-team matchup-${role}">${crest(row.team)}
    <div class="matchup-team-info"><strong>${esc(row.team)}</strong><span class="mini-label matchup-role">${role.toUpperCase()} TEAM</span>
      <div class="matchup-record"><p>${day(row.trend.at(-1)?.date)}</p><div class="tiny muted">${esc(historyNote(row))}</div></div></div></div>`;
  const mirrors = definitions => definitions.map(([title, value]) => {
    const [left, right] = [value(home.overall), value(away.overall)];
    const max = Math.max(left ?? 0, right ?? 0, 1) * 1.12;
    return `<div class="mirror-row"><div class="mirror-values"><span>${number(left)}</span>
      <span class="mini-label">${title}</span><span>${number(right)}</span></div>
      <div class="mirror-tracks"><div class="mirror-track left"><i style="width:${width(left, max)}%"></i></div>
        <div class="mirror-track right"><i style="width:${width(right, max)}%"></i></div></div></div>`;
  }).join("");
  const mirrorTeams = `<div class="mirror-key"><span>${esc(home.team)}</span><span>${esc(away.team)}</span></div>`;
  const form = row => `<div class="card analysis-form-card"><h3 class="card-title analysis-team-title">${crest(row.team, "sm")}${esc(row.team)}</h3>
    <div class="form-detail-list">${[...row.trend].reverse().map(item => {
      const result = item.goals_for > item.goals_against ? "W" : item.goals_for === item.goals_against ? "D" : "L";
      return `<div class="wdl-item form-detail"><span class="wdl-box ${result}">${result}</span>${crest(item.opponent, "tiny")}
        <span class="opp">${esc(item.opponent)}</span><strong>${item.goals_for}–${item.goals_against}</strong>
        <span class="score">${day(item.date)}</span><span class="tiny muted">${esc(item.venue)}</span></div>`;
    }).join("") || message("No verified matches in this window.")}</div></div>`;
  const chart = (key, heading) => {
    const max = Math.max(home.trend.length, away.trend.length);
    const series = [home, away].map(row => ({name: row.team, values: [
      ...Array(max - row.trend.length).fill(null), ...row.trend.map(item => item[key])
    ]}));
    return `<div class="card analysis-trend-card"><h3 class="card-title">${heading}</h3>${max
      ? trend(series, Array.from({length: max}, (_, i) => `T-${max - i}`)) : message("No matches to chart.")}</div>`;
  };
  return `<div class="title-row"><div><div class="eyebrow">TEAM COMPARISON · HISTORICAL DATA</div><h2 class="section-title">MATCHUP OVERVIEW.</h2></div>
    <span class="chip">LAST ${data.window} · ${seasonName(data.season)}</span></div>
    <div class="card analysis-overview-card"><div class="compare-head matchup-identity">${side(home, "home")}<span class="detail-vs">VS</span>${side(away, "away")}</div>
      <div class="indicator mt20">Verified completed matches before ${day(data.as_of_exclusive)}.</div>
      <div class="mt20"><button class="btn btn-green" data-to-custom>VIEW PREDICTION ↗</button></div></div>
    <div class="grid2 mt20 analysis-performance-grid"><div class="card analysis-performance-card"><h3 class="card-title">ATTACKING PERFORMANCE</h3>
      ${mirrorTeams}${mirrors([["AVERAGE xG", row => row.mean_xg], ["GOALS / MATCH", row => row.verified_fixtures ? row.goals_for / row.verified_fixtures : null],
      ["SHOTS", row => row.mean_shots], ["SHOTS ON TARGET", row => row.mean_sot]])}
      <p class="card-desc">Shot sources · ${esc(xgSources(home.overall.shots_sources))} / ${esc(xgSources(away.overall.shots_sources))}. Definitions may differ.</p></div>
    <div class="card analysis-performance-card"><h3 class="card-title">DEFENSIVE PERFORMANCE</h3>${mirrorTeams}
      ${mirrors([["AVERAGE xGA", row => row.mean_xga], ["GOALS CONCEDED / MATCH", row => row.verified_fixtures ? row.goals_against / row.verified_fixtures : null],
      ["CLEAN SHEETS", row => row.verified_fixtures ? row.clean_sheets : null]])}</div></div>
    <div class="mt30 analysis-content-section"><h2 class="section-title analysis-section-title">RECENT FORM</h2><div class="grid2 mt20">${form(home)}${form(away)}</div></div>
    <div class="mt30 analysis-content-section"><h2 class="section-title analysis-section-title">PERFORMANCE TRENDS</h2>
      <p class="card-desc">T-1 is each team's last verified match. Empty points represent missing values.</p>
      <div class="grid2 mt20">${chart("xg", "xG TREND COMPARISON")}${chart("xga", "xGA TREND COMPARISON")}</div></div>
    <div class="card mt20 analysis-venue-card"><h3 class="card-title">HOME / AWAY PERFORMANCE</h3><div class="location-grid mt20">
      ${venue(home.team, "HOME PERFORMANCE", home.home, "venue-home")}${venue(away.team, "AWAY PERFORMANCE", away.away, "venue-away")}</div></div>
    <div class="card mt20 analysis-h2h-card"><h3 class="card-title">HEAD-TO-HEAD HISTORY</h3><p class="card-desc">Selected season · ${h2h.verified_fixtures} verified meetings</p>
      ${h2h.verified_fixtures ? `<div class="grid3 mt20">${metric(home.team + " wins", h2h.wins)}${metric("Draws", h2h.draws)}${metric(away.team + " wins", h2h.losses)}</div>
      <div class="table-wrap mt20"><table class="data-table"><thead><tr><th>Date</th><th>Venue</th><th>Score · ${esc(home.team)} first</th><th>Observed xG</th></tr></thead><tbody>
      ${data.head_to_head_matches.map(item => `<tr><td>${day(item.date)}</td><td>${esc(item.venue)}</td><td>${item.goals_for} – ${item.goals_against}</td><td>${number(item.xg)} / ${number(item.xga)}</td></tr>`).join("")}</tbody></table></div>`
      : message("No verified meetings in this season.")}</div>`;
}

export function historyTable(rows) {
  if (!rows.length) return message("No matching published forecasts in this ledger.");
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Matchup</th><th>Revision</th><th>Home xG</th><th>Away xG</th><th>Created</th><th>Model</th><th>Details</th></tr></thead>
    <tbody>${rows.map(row => `<tr><td><strong>${esc(row.home_team)} vs ${esc(row.away_team)}</strong></td>
      <td><span class="chip">${esc(row.forecast_stage)} · V${row.forecast_revision}</span></td><td>${number(row.home_xg)}</td><td>${number(row.away_xg)}</td>
      <td>${time(row.generated_at_utc)}</td><td>LR ${esc(row.model_version)}</td>
      <td><button class="btn btn-outline btn-sm" data-history="${esc(row.forecast_id)}">VIEW ↗</button></td></tr>`).join("")}</tbody></table></div>`;
}

export function historyDetails(row, revisions) {
  return panels(row.home_team, row.away_team, row) + `<div class="space20"></div>
    <p class="subtext">V${row.forecast_revision} · ${esc(row.forecast_stage)} · ${esc(statusName(row.eligibility_status))}<br>
      Created ${time(row.generated_at_utc)} · Cutoff ${day(row.history_cutoff)}<br>
      Snapshot ${esc(row.history_snapshot_version)} · LR ${esc(row.model_version)}</p>
    <div class="list-note">${esc(row.source_notice)}</div>
    ${revisions.length > 1 ? `<div class="bridge-compare mt20"><label>Earlier <select id="compareV1">${revisions.slice(0, -1).map(revisionOption).join("")}</select></label>
      <label>Later <select id="compareV2">${revisions.slice(1).map(revisionOption).join("")}</select></label>
      <button class="btn btn-outline" data-compare="${esc(row.canonical_fixture_key)}">COMPARE REVISIONS ↗</button></div><div id="compareOutput" class="mt20"></div>` : ""}`;
}

function revisionOption(row) {
  return `<option value="${esc(row.forecast_id)}">V${row.forecast_revision}</option>`;
}

export function comparison(data) {
  return `<div class="card"><h3 class="card-title">V${data.v1.forecast_revision} → V${data.v2.forecast_revision}</h3>
    <p class="card-desc">${esc(data.v1.history_snapshot_version)} → ${esc(data.v2.history_snapshot_version)}</p>
    ${data.schedule_notice ? `<p>${esc(statusName(data.schedule_notice))}</p>` : ""}
    <div class="grid2">${metric("HOME xG CHANGE", signed(data.home_xg_delta))}${metric("AWAY xG CHANGE", signed(data.away_xg_delta))}</div>
    <p class="subtext">Changed features · ${data.changed_features.map(item => esc(item.feature)).join(", ") || "None"}</p></div>`;
}

export function renderModel(model) {
  const descriptions = ["Home indicator", "Prior matches", "Short history", "Average xG", "Average xGA",
    "Average goals scored", "Average goals conceded", "Average shots", "Average shots on target",
    "Opponent average xG", "Opponent average xGA", "Opponent prior matches", "Opponent short history"];
  $("featuresList").innerHTML = model.features.map((name, i) => `<div style="display:flex;align-items:flex-start;gap:11px;background:#f5faf2;padding:12px;border-radius:10px">
    <span style="color:#2f8601;font-weight:900;font-size:10px">${String(i + 1).padStart(2, "0")}</span>
    <div><code style="font-size:11px;font-weight:850;color:#183f15;overflow-wrap:anywhere">${esc(name)}</code><div class="tiny muted">${descriptions[i] || ""}</div></div></div>`).join("");
  $("modelMetricCards").innerHTML = [...model.phase7, ...model.retrospective].map(row => metric(
    `MAE · ${row.source}`, number(row.mae), `${statusName(row.label)} · ${row.fixtures} matches`
  )).join("");
  $("modelScatter").innerHTML = bars(model.phase7.flatMap(row => [
    [`${statusName(row.label)} · MAE`, row.mae], [`${statusName(row.label)} · RMSE`, row.rmse]
  ]), 1);
  $("modelResidual").innerHTML = bars(model.retrospective.flatMap(row => [
    [`${row.source} · LR MAE`, row.mae], [`${row.source} · Baseline MAE`, row.baseline_mae]
  ]), 1);
  $("modelEvaluationNotice").textContent = `${model.model} V${model.model_version} · ${model.training_observations} training rows · ${model.evaluation_notice}`;
}

export function csvText(rows) {
  const quote = value => {
    let text = String(value ?? "");
    if (typeof value === "string" && (/^[\s\u0000-\u0020]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text))) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const fields = ["forecast_id", "forecast_stage", "forecast_revision", "home_team", "away_team", "home_xg",
    "away_xg", "history_cutoff", "generated_at_utc", "model_version", "history_snapshot_version", "dataset_kind"];
  return "\uFEFF" + [fields, ...rows.map(row => fields.map(name => row[name]))].map(row => row.map(quote).join(",")).join("\r\n");
}
